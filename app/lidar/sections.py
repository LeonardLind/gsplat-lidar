"""Train the office in sections, each with its own Gaussian budget, and join them into one splat.

    python -m app.lidar.sections plan  <sparse/0 (LiDAR frame)> <out dir> [--k 16] [--overlap 1.5]
    python -m app.lidar.sections queue <out dir> <queue.json> [--cap 1200000] [--epochs 44]
    python -m app.lidar.sections merge <out dir> <run prefix> <merged run name>

Why: one model of the whole office spreads its budget over 30 x 30 m; after cleanup 130-360k Gaussians are left
and every spot is fog. The alcove alone (test A, 2026-10-27: 68 frames, 30k steps, 500k cap) rendered its lamps and
door frames from the same poses, ~3 dB better. So: cluster the camera positions (xy, so the low and high passes of
a spot land in one section), give every frame an owner section, train each section on its own frames plus the
frames within --overlap m of them, starting from the LiDAR points closest to those frames. When joining, every
Gaussian is kept only by the section that owns the camera frame nearest to it: each part of the office comes from
the model whose cameras saw it from closest.

plan writes <out>/s<k>/sparse/0 (+ 0_orient.json: metric, LiDAR frame) and <out>/sections.json; queue appends one
job per section to a scripts/train_queue.py queue (run names <prefix>_s<k>); merge writes
train/068+069/<merged>/result/ply/point_cloud_0.ply + train_params.json, so `python -m app export` takes it as is.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
from scipy.cluster.vq import kmeans2
from scipy.spatial import cKDTree

REPO = Path(__file__).resolve().parents[2]
TRAIN = REPO / "projects" / "office-x4" / "train" / "068+069"


def frame_centres(r) -> tuple[np.ndarray, np.ndarray]:
    """(frame ids, centres): the centre of each registered frame's reference image (lens0_c)."""
    ids, cs = [], []
    for im in r.images.values():
        if im.name.startswith("lens0_c/") and im.has_pose:
            ids.append(im.frame_id)
            cs.append(im.projection_center())
    order = np.argsort(ids)
    return np.array(ids)[order], np.array(cs)[order]


def write_subset(txt: Path, dest: Path, frames: set[int], points: set[int]) -> None:
    """Text model of the full solve -> binary model with only these frames (their images, no 2D points) and points."""
    import pycolmap

    tmp = dest.parent / "txt"
    tmp.mkdir(parents=True, exist_ok=True)
    for f in ("cameras.txt", "rigs.txt"):
        shutil.copy(txt / f, tmp / f)
    with open(txt / "frames.txt") as src, open(tmp / "frames.txt", "w") as out:
        out.writelines(l for l in src if l.startswith("#") or int(l.split(maxsplit=1)[0]) in frames)
    images = set()
    with open(txt / "frames.txt") as src:
        for l in src:
            if not l.startswith("#") and int(l.split(maxsplit=1)[0]) in frames:
                t = l.split()
                images.update(int(t[i + 2]) for i in range(10, 10 + 3 * int(t[9]), 3))
    with open(txt / "images.txt") as src, open(tmp / "images.txt", "w") as out:
        lines = [l for l in src if not l.startswith("#")]
        for head in lines[0::2]:
            if int(head.split(maxsplit=1)[0]) in images:
                out.write(head + "\n")
    with open(txt / "points3D.txt") as src, open(tmp / "points3D.txt", "w") as out:
        out.writelines(l for l in src if not l.startswith("#") and int(l.split(maxsplit=1)[0]) in points)
    r = pycolmap.Reconstruction(str(tmp))
    dest.mkdir(parents=True, exist_ok=True)
    r.write(str(dest))
    shutil.rmtree(tmp)


def plan(a: argparse.Namespace) -> None:
    import pycolmap

    r = pycolmap.Reconstruction(str(a.sparse))
    fid, fc = frame_centres(r)
    _, owner = kmeans2(fc[:, :2], a.k, minit="++", seed=0)
    tree2 = cKDTree(fc[:, :2])
    pid = np.fromiter(r.points3D.keys(), dtype=np.int64)
    pxyz = np.array([r.points3D[int(i)].xyz for i in pid])
    _, near = cKDTree(fc).query(pxyz)
    vis = np.load(a.visible) if a.visible else None
    if vis is not None:
        # LiDAR row k of visibility.py = k-th smallest point id
        vis_names, vis_off, vis_idx = vis["names"], vis["offsets"], vis["indices"]
        sorted_ids = np.sort(pid)
        img_frame = {im.name: im.frame_id for im in r.images.values()}
    txt = a.out / "_full_txt"
    if not (txt / "points3D.txt").exists():
        txt.mkdir(parents=True, exist_ok=True)
        r.write_text(str(txt))
    orient = json.loads((a.sparse.parent / f"{a.sparse.name}_orient.json").read_text(encoding="utf-8-sig"))
    sections = []
    for s in range(a.k):
        own = np.flatnonzero(owner == s)
        if not len(own):
            continue
        near_own = tree2.query_ball_point(fc[own, :2], a.overlap)
        train = np.unique(np.concatenate([own, *map(np.array, near_own)]).astype(int))
        if vis is None:
            pts = pid[np.isin(near, train)]
        else:
            keep = set(int(x) for x in fid[train])
            rows = [k for k, n in enumerate(vis_names) if img_frame.get(str(n)) in keep]
            pts = sorted_ids[np.unique(np.concatenate([vis_idx[vis_off[k]:vis_off[k + 1]] for k in rows]))]
        dest = a.out / f"s{s}" / "sparse" / "0"
        write_subset(txt, dest, set(int(x) for x in fid[train]), set(int(x) for x in pts))
        (dest.parent / "0_orient.json").write_text(json.dumps(
            {"scale": "metric", "frame": "lidar", "lidar_npz": orient.get("lidar_npz"), "section": s,
             "from": str(a.sparse)}, indent=1))
        sections.append({"id": s, "own_frames": int(len(own)), "train_frames": int(len(train)), "points": int(len(pts)),
                         "centre_xy": fc[own, :2].mean(0).round(2).tolist(), "model": str(dest)})
        print(f"section {s}: {len(own)} own frames, {len(train)} training frames, {len(pts):,} LiDAR start points", flush=True)
    (a.out / "sections.json").write_text(json.dumps(
        {"sparse": str(a.sparse), "k": a.k, "overlap_m": a.overlap, "sections": sections,
         "frame_ids": fid.tolist(), "frame_centres": fc.round(4).tolist(), "frame_owner": owner.tolist()}, indent=1))


def queue(a: argparse.Namespace) -> None:
    info = json.loads((a.out / "sections.json").read_text())
    q = json.loads(a.queue.read_text()) if a.queue.exists() else {"jobs": []}
    names = {j["name"] for j in q["jobs"]}
    for s in info["sections"]:
        name = f"{a.prefix}_s{s['id']}"
        if name in names:
            continue
        steps = int(np.clip(round(a.epochs * s["train_frames"] * 10, -3), 30_000, 100_000))
        q["jobs"].append({"name": name, "model": s["model"], "steps": steps, "cap": a.cap, "holdout": -10,
                          "extra": "--strategy.noise-injection-stop-iter 25000",
                          "why": f"section {s['id']} of {len(info['sections'])}: {s['train_frames']} frames, "
                                 f"{a.epochs} passes over its images (test A settings, own budget)"})
    a.queue.write_text(json.dumps(q, indent=1))
    print(f"{len(q['jobs'])} jobs in {a.queue}")


def read_ply(path: Path) -> tuple[bytes, list[str], np.ndarray]:
    raw = path.read_bytes()
    end = raw.index(b"end_header\n") + len(b"end_header\n")
    hdr = raw[:end].decode()
    lines = hdr.splitlines()
    n = int(next(l for l in lines if l.startswith("element vertex")).split()[2])
    props = [l.split()[2] for l in lines if l.startswith("property float")]
    if len(props) != sum(l.startswith("property") for l in lines):
        raise SystemExit(f"{path}: only float properties are supported")
    return raw[:end], props, np.frombuffer(raw, dtype=np.float32, count=n * len(props), offset=end).reshape(n, len(props))


def merge(a: argparse.Namespace) -> None:
    info = json.loads((a.out / "sections.json").read_text())
    fc, owner = np.array(info["frame_centres"]), np.array(info["frame_owner"])
    tree = cKDTree(fc)
    parts, header, props0, report = [], None, None, []
    for s in info["sections"]:
        run = TRAIN / f"{a.prefix}_s{s['id']}"
        if a.fallback and not (run / "result" / "ply").exists():
            run = TRAIN / f"{a.fallback}_s{s['id']}"
        plys = sorted((run / "result" / "ply").glob("*.ply"), key=lambda f: int("".join(c for c in f.stem if c.isdigit()) or 0))
        if not plys:
            raise SystemExit(f"section {s['id']}: no PLY in {run}")
        hdr, props, v = read_ply(plys[-1])
        if props0 is None:
            header, props0 = hdr, props
        elif props != props0:
            raise SystemExit(f"section {s['id']}: PLY layout differs")
        _, near = tree.query(v[:, :3])
        keep = owner[near] == s["id"]
        parts.append(v[keep])
        report.append({"section": s["id"], "ply": str(plys[-1]), "gaussians": int(len(v)), "kept": int(keep.sum())})
        print(f"section {s['id']}: {keep.sum():,} of {len(v):,} Gaussians kept", flush=True)
    allv = np.concatenate(parts)
    run = TRAIN / a.merged
    (run / "result" / "ply").mkdir(parents=True, exist_ok=True)
    head = "\n".join(f"element vertex {len(allv)}" if l.startswith("element vertex") else l
                     for l in header.decode().splitlines()) + "\n"
    with open(run / "result" / "ply" / "point_cloud_0.ply", "wb") as f:
        f.write(head.encode())
        f.write(np.ascontiguousarray(allv, dtype=np.float32).tobytes())
    (run / "train_params.json").write_text(json.dumps(
        {"sparse": info["sparse"], "views": str(REPO / "projects" / "office-x4" / "views" / "068+069"),
         "merged_from": report}, indent=1))
    print(f"{len(allv):,} Gaussians -> {run / 'result' / 'ply' / 'point_cloud_0.ply'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("sparse", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--k", type=int, default=16)
    p.add_argument("--overlap", type=float, default=1.5, help="frames within this many metres (xy) of a section's own frames also train it")
    p.add_argument("--visible", type=Path, help="app/lidar/visibility.py npz: start from every LiDAR point the section's "
                   "images see (default: the points nearest to its frames; 2026-10-28 that left walls seen through doors "
                   "without points, and sections 1, 5, 7, 9 filled them with giant blobs in front of the cameras)")
    p.set_defaults(fn=plan)
    p = sub.add_parser("queue")
    p.add_argument("out", type=Path)
    p.add_argument("queue", type=Path)
    p.add_argument("--prefix", default="sec")
    p.add_argument("--cap", type=int, default=1_200_000)
    p.add_argument("--epochs", type=float, default=44, help="passes over each section's images (test A: 30k steps / 680 images)")
    p.set_defaults(fn=queue)
    p = sub.add_parser("merge")
    p.add_argument("out", type=Path)
    p.add_argument("prefix")
    p.add_argument("merged")
    p.add_argument("--fallback", help="run prefix to use for sections not (yet) trained under <prefix>")
    p.set_defaults(fn=merge)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
