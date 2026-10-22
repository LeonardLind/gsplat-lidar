"""Place the continuous chunks of the walk into the LiDAR frame, one after another.

    python -m app.lidar.chain <sparse dir> <chunks.json> <out dir> [--anchor <chunk id>]

For every chunk: up axis and metric scale from the floor and ceiling planes of the points its images see; then the
placement (yaw, scale factor, position) whose camera path stays over the LiDAR floor and out of walls. Chunks are
placed outwards from an anchor (the chunk with the most distinctive free placement unless --anchor is given): the
neighbour in walking order must start near where the placed chunk ended (~0.45 m per missing frame) and keep its
heading.

Writes <out>/chain.json (4x4 similarity per chunk: model frame -> LiDAR frame, floor at z = 0) and overlay.png.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np
import pycolmap
from scipy.ndimage import gaussian_filter
from scipy.spatial.transform import Rotation

from app.lidar.register import CELL, load_lidar, mat_apply, path_map, sim3_matrix, up_candidates, walkable_map
from app.stages.ply_scene import orient_room


_WALK_FFT: dict = {}


def corr_full(walk: np.ndarray, pic: np.ndarray):
    n = int(2 ** np.ceil(np.log2(max(walk.shape[0] + pic.shape[0], walk.shape[1] + pic.shape[1]))))
    key = (id(walk), n)
    if key not in _WALK_FFT:  # the floor plan never changes: transform it once
        _WALK_FFT[key] = np.fft.rfft2(walk, (n, n))
    cc = np.fft.irfft2(_WALK_FFT[key] * np.conj(np.fft.rfft2(pic, (n, n))), (n, n)) / max(pic.sum(), 1e-9)
    return cc, n


def shift_grid(n: int):
    idx = np.arange(n)
    s = np.where(idx < n // 2, idx, idx - n) * CELL
    return s[:, None], s[None, :]


def heading(c: np.ndarray, end: bool) -> np.ndarray | None:
    seg = c[-6:] if end else c[:6]
    d = seg[-1, :2] - seg[0, :2]
    nrm = np.linalg.norm(d)
    return d / nrm if nrm > 0.3 else None


def load_models(sparse: Path, needed: set[str]):
    out = {}
    for name in needed:
        out[name] = pycolmap.Reconstruction(str(sparse / name))
    return out


def chunk_geometry(r: pycolmap.Reconstruction, frames: list[str]):
    """Camera centres (lens0_c) in walking order and the sparse points seen by the chunk's images."""
    want = set(frames)
    ids, cams = {}, {}
    chunk_ids = set()
    for i in r.reg_image_ids():
        im = r.images[i]
        n = im.name.replace("\\", "/")
        stem = n.split("/")[-1].rsplit(".", 1)[0]
        if stem in want:
            chunk_ids.add(i)
            if n.startswith("lens0_c/"):
                cams[stem] = im.projection_center()
    pts = []
    for p in r.points3D.values():
        if p.error < 2.0 and p.track.length() >= 3 and any(e.image_id in chunk_ids for e in p.track.elements):
            pts.append(p.xyz)
    c = np.array([cams[f] for f in frames if f in cams])
    return c, np.array(pts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sparse", type=Path)
    ap.add_argument("chunks", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--lidar", type=Path, default=Path(r"C:\dev\gsl-data\data\processed\office_lidar_5cm.npz"))
    ap.add_argument("--anchor", type=int, default=None)
    ap.add_argument("--yaw-step", type=float, default=2.0)
    ap.add_argument("--scales", type=float, nargs="+", default=[0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15])
    a = ap.parse_args()
    t0 = time.time()
    a.out.mkdir(parents=True, exist_ok=True)
    chunks = json.loads(a.chunks.read_text())
    lid, room_h, floor_z, origin = load_lidar(a.lidar)
    ext = (lid[:, 0].min() - 10, lid[:, 0].max() + 10, lid[:, 1].min() - 10, lid[:, 1].max() + 10)
    walk, floor_m, wall_m = walkable_map(lid, ext)
    models = load_models(a.sparse, {c["model"] for c in chunks})
    print(f"LiDAR ready, {len(chunks)} chunks ({time.time() - t0:.0f} s)", flush=True)

    # per chunk: cameras, points, base frames (one per usable up candidate)
    G = []
    for c in chunks:
        cams, pts = chunk_geometry(models[c["model"]], c["frames"])
        bases = []
        if len(pts) > 200:
            downs = np.array([[0.0, 1.0, 0.0]])
            for ui, up in enumerate(up_candidates(pts, downs)[:2]):
                try:
                    tr, info = orient_room(pts, up, room_h)
                except Exception:  # noqa: BLE001
                    continue
                M0 = sim3_matrix(tr["scale"], Rotation.from_quat(tr["quaternion_xyzw"]).as_matrix(), np.array(tr["position"]))
                z = mat_apply(M0, cams)[:, 2]
                ok = info["angle_floor_ceiling_deg"] < 6 and np.percentile(z, 5) > 0.2 and np.percentile(z, 95) < room_h + 0.3
                bases.append({"M0": M0, "ok": bool(ok), "scale": tr["scale"], "planes": info["floor_inliers"] + info["ceiling_inliers"]})
        G.append({"cams": cams, "pts": pts, "bases": bases})
        print(f"  chunk {c['id']:2d} (model {c['model']}): {len(cams)} cameras, {len(pts):,} points, "
              f"bases {[(round(b['scale'], 2), b['ok']) for b in bases]} ({time.time() - t0:.0f} s)", flush=True)

    def search(k: int, prev: dict | None, nxt_end=None):
        """Best placements of chunk k: list of dicts, best first. prev = placed neighbour (for continuity)."""
        g = G[k]
        cands = []
        usable = [b for b in g["bases"] if b["ok"]] or g["bases"]
        for bi, b in enumerate(usable):
            c0 = mat_apply(b["M0"], g["cams"])
            for f in a.scales:
                cf = c0 * f
                for yaw in np.arange(0, 360, a.yaw_step):
                    Rz = Rotation.from_euler("z", yaw, degrees=True).as_matrix()
                    q = cf @ Rz.T
                    cc, n = corr_full(walk, path_map(q, ext, walk.shape))
                    if prev is not None:
                        # continuity: the start (or end) of this chunk should be near the neighbour's end (start)
                        gap = prev["gap_frames"]
                        radius = 1.5 + 0.45 * gap
                        anchor_pt = prev["point"]
                        mine = q[0] if prev["direction"] == "after" else q[-1]
                        want = anchor_pt - mine[:2]  # shift (metres) that puts my start on the neighbour's end
                        sx, sy = shift_grid(n)
                        bump = np.exp(-(((sx - want[0]) ** 2 + (sy - want[1]) ** 2) / (2 * (radius / 1.5) ** 2)))
                        cc = cc * bump + (bump - 1) * 0.5  # outside the radius the score drops, but stays comparable
                    k0 = np.unravel_index(int(np.argmax(cc)), cc.shape)
                    score = float(cc[k0])
                    shift = np.array([(k0[0] if k0[0] < n // 2 else k0[0] - n) * CELL, (k0[1] if k0[1] < n // 2 else k0[1] - n) * CELL])
                    h_pen = 0.0
                    if prev is not None and prev.get("heading") is not None:
                        hq = heading(q, end=(prev["direction"] == "before")) if True else None
                        if hq is not None:
                            h_pen = 0.25 * float(hq @ prev["heading"])
                    cands.append({"score": score + h_pen, "base": bi, "f": f, "yaw": float(yaw), "shift": shift, "usable": b})
        cands.sort(key=lambda x: -x["score"])
        picked = []
        for cnd in cands:
            if all(not (cnd["base"] == p["base"] and abs(((cnd["yaw"] - p["yaw"] + 180) % 360) - 180) < 12) for p in picked):
                picked.append(cnd)
            if len(picked) >= 3:
                break
        return picked

    def matrix(cnd) -> np.ndarray:
        Rz = Rotation.from_euler("z", cnd["yaw"], degrees=True).as_matrix()
        S = np.diag([cnd["f"]] * 3 + [1.0])
        Mz = np.eye(4)
        Mz[:3, :3] = Rz
        Mz[:3, 3] = np.r_[cnd["shift"], 0.0]
        return Mz @ S @ cnd["usable"]["M0"]

    # free search for every chunk: how distinctive is each placement? (anchor = the most distinctive one)
    free = {}
    for k in range(len(chunks)):
        if not G[k]["bases"] or len(G[k]["cams"]) < 10:
            continue
        free[k] = search(k, None)
        top = free[k]
        gap = (top[0]["score"] - top[1]["score"]) if len(top) > 1 else top[0]["score"]
        print(f"  free search chunk {k:2d}: best {top[0]['score']:.2f}, runner-up {top[1]['score'] if len(top) > 1 else float('nan'):.2f}, "
              f"margin {gap:.2f} ({time.time() - t0:.0f} s)", flush=True)
    anchor = a.anchor if a.anchor is not None else max(free, key=lambda k: (free[k][0]["score"] - (free[k][1]["score"] if len(free[k]) > 1 else 0)) * np.sqrt(len(G[k]["cams"])))
    print(f"anchor chunk: {anchor}", flush=True)

    placed: dict[int, dict] = {anchor: {"cand": free[anchor][0], "M": matrix(free[anchor][0])}}
    order = [("after", range(anchor + 1, len(chunks))), ("before", range(anchor - 1, -1, -1))]
    for direction, rng in order:
        last = anchor
        for k in rng:
            if k not in free:
                continue
            pl = placed[last]
            lc = mat_apply(pl["M"], G[last]["cams"])
            if direction == "after":
                gap = chunks[k]["first_index"] - chunks[last]["last_index"]
                prev = {"point": lc[-1][:2], "gap_frames": gap, "heading": heading(lc, end=True), "direction": "after"}
            else:
                gap = chunks[last]["first_index"] - chunks[k]["last_index"]
                prev = {"point": lc[0][:2], "gap_frames": gap, "heading": heading(lc, end=False), "direction": "before"}
            pick = search(k, prev)
            placed[k] = {"cand": pick[0], "M": matrix(pick[0]), "runner_up": pick[1]["score"] if len(pick) > 1 else None}
            last = k
            print(f"  placed chunk {k:2d} ({direction}): score {pick[0]['score']:.2f}, scale x{pick[0]['f']:.2f}, yaw {pick[0]['yaw']:.0f}, "
                  f"runner-up {pick[1]['score'] if len(pick) > 1 else float('nan'):.2f} ({time.time() - t0:.0f} s)", flush=True)

    out = []
    for k, pl in sorted(placed.items()):
        cams = mat_apply(pl["M"], G[k]["cams"])
        ix = ((cams[:, 0] - ext[0]) / CELL).astype(int)
        iy = ((cams[:, 1] - ext[2]) / CELL).astype(int)
        ok = (ix >= 0) & (ix < floor_m.shape[0]) & (iy >= 0) & (iy < floor_m.shape[1])
        over_floor = float(np.mean(floor_m[ix[ok], iy[ok]])) if ok.any() else 0.0
        in_wall = float(np.mean(wall_m[ix[ok], iy[ok]])) if ok.any() else 0.0
        out.append({"chunk": k, "model": chunks[k]["model"], "frames": [chunks[k]["first_frame"], chunks[k]["last_frame"]],
                    "M": pl["M"].tolist(), "score": pl["cand"]["score"], "over_floor": over_floor, "in_wall": in_wall,
                    "scale_factor": pl["cand"]["f"], "yaw": pl["cand"]["yaw"], "runner_up": pl.get("runner_up")})
    (a.out / "chain.json").write_text(json.dumps({"lidar_floor_z": floor_z, "lidar_origin": origin.tolist(), "chunks": out}))

    # overlay: LiDAR plan, every chunk's path in its own colour with its number
    res = CELL / 2
    W, H = int((ext[1] - ext[0]) / res), int((ext[3] - ext[2]) / res)
    img = np.zeros((H, W, 3), np.uint8)
    big = lambda m: cv2.resize(m.astype(np.uint8), (H, W), interpolation=cv2.INTER_NEAREST).T[::-1]  # noqa: E731
    img[big(floor_m) > 0] = (45, 45, 45)
    img[big(wall_m) > 0] = (150, 150, 150)
    rng = np.random.default_rng(3)
    colours = {k: tuple(int(v) for v in rng.integers(80, 255, 3)) for k in placed}
    for k, pl in sorted(placed.items()):
        cams = mat_apply(pl["M"], G[k]["cams"])
        px = np.stack([((cams[:, 0] - ext[0]) / res).astype(int), H - 1 - ((cams[:, 1] - ext[2]) / res).astype(int)], 1)
        for i, (x, y) in enumerate(px):
            if 0 <= x < W and 0 <= y < H:
                cv2.circle(img, (x, y), 3, colours[k], -1)
        x, y = px[0]
        cv2.putText(img, str(k), (int(x) + 5, int(y) - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.9, colours[k], 2)
    keep = np.abs(img.sum(axis=2)) > 0
    ys, xs = np.nonzero(keep)
    cv2.imwrite(str(a.out / "overlay.png"), img[max(ys.min() - 20, 0): ys.max() + 20, max(xs.min() - 20, 0): xs.max() + 20])
    print("\nchunk  model  frames                          over floor  in walls  score")
    for o in out:
        print(f"  {o['chunk']:3d}  {o['model']:>5}  {o['frames'][0]} .. {o['frames'][1]}   {o['over_floor']:9.0%} {o['in_wall']:8.0%}  {o['score']:.2f}")
    print(f"done ({time.time() - t0:.0f} s)", flush=True)


if __name__ == "__main__":
    main()
