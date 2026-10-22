"""Position priors and spatial image pairs for one consistent camera solve in the LiDAR frame (roadmap Phase 2).

    python -m app.lidar.prior_pairs <database.db> <merged model dir> <pairs.txt> [--radius 2.5] [--max-pairs 250000]

The original matching was sequential only, so the low and high passes and the revisits were never compared, and
weak links cut the walk into 42 models. The joined model (app/lidar/merge.py + rigid_models.py) now gives every
registered image a position and viewing direction in the LiDAR frame. This tool

1. writes a position prior (LiDAR frame, metres) for every frame into the database, on the frame's reference image
   (lens0_c): frames of the joined model with std 0.5 m; frames missing from it, interpolated in time between the
   nearest known frames (gap up to 12 frames) with std 1.5 m; others get none;
2. lists image pairs to match: cameras closer than --radius, view axes within 55 degrees, more than 2 frames apart,
   not already in the database's matches. Cross-pass / revisit pairs (far apart in time) and close pairs come first;
   at most --max-pairs and at most --per-image new partners per image. Matched afterwards with `colmap matches_importer --match_type pairs` (GPU, ~0.15 s / pair).

The database must be a copy (it is modified): sfm/068+069/aliked_prior.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import numpy as np
import pycolmap
from scipy.spatial import cKDTree

MAX_ID = 2147483647


def pair_id(a: int, b: int) -> int:
    a, b = min(a, b), max(a, b)
    return a * MAX_ID + b


def frame_order(name: str) -> tuple[int, int]:
    stem = name.replace("\\", "/").split("/")[-1].rsplit(".", 1)[0]  # 068_003340
    clip, idx = stem.split("_")
    return int(clip), int(idx)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("database", type=Path)
    ap.add_argument("model", type=Path)
    ap.add_argument("pairs", type=Path)
    ap.add_argument("--radius", type=float, default=2.5)
    ap.add_argument("--max-angle", type=float, default=55.0)
    ap.add_argument("--max-pairs", type=int, default=250_000)
    ap.add_argument("--per-image", type=int, default=40, help="at most this many new partners per image (even coverage)")
    ap.add_argument("--std-known", type=float, default=0.5)
    ap.add_argument("--std-interp", type=float, default=1.5)
    a = ap.parse_args()

    r = pycolmap.Reconstruction(str(a.model))
    pose = {}  # image name -> (centre, view axis) in the LiDAR frame
    for i in r.reg_image_ids():
        im = r.images[i]
        R = im.cam_from_world().rotation.matrix()
        pose[im.name.replace("\\", "/")] = (im.projection_center(), R[2])  # camera z axis in world = R^T e3 = R[2]

    db = pycolmap.Database.open(str(a.database))
    imgs = {im.image_id: im for im in db.read_all_images()}
    frames = db.read_all_frames()
    # 1) priors, one per frame on its reference image
    ref_of = {}
    for f in frames:
        ids = [d.id for d in f.data_ids]
        names = {imgs[i].name.replace("\\", "/"): i for i in ids}
        ref = next((i for n, i in names.items() if n.startswith("lens0_c/")), ids[0])
        ref_of[f.frame_id] = (ref, imgs[ref].name.replace("\\", "/"))
    order = sorted(ref_of.values(), key=lambda x: frame_order(x[1]))
    known = {n: pose[n][0] for _, n in order if n in pose}
    keys = [frame_order(n) for _, n in order]
    db.clear_pose_priors()
    n_known = n_interp = 0
    for k, (img_id, n) in enumerate(order):
        if n in known:
            pos, std = known[n], a.std_known
            n_known += 1
        else:
            clip, idx = keys[k]
            prev = next(((keys[j], known[order[j][1]]) for j in range(k - 1, -1, -1) if order[j][1] in known and keys[j][0] == clip), None)
            nxt = next(((keys[j], known[order[j][1]]) for j in range(k + 1, len(order)) if order[j][1] in known and keys[j][0] == clip), None)
            if not prev or not nxt:
                continue
            (_, i0), p0 = prev
            (_, i1), p1 = nxt
            step = (keys[k + 1][1] - idx) if k + 1 < len(keys) and keys[k + 1][0] == clip else 1  # frame spacing in the clip
            if (i1 - i0) > 12 * max(step, 1):
                continue
            w = (idx - i0) / max(i1 - i0, 1)
            pos, std = (1 - w) * p0 + w * p1, a.std_interp
            n_interp += 1
        pp = pycolmap.PosePrior(position=np.asarray(pos, float), position_covariance=np.eye(3) * std ** 2,
                                coordinate_system=pycolmap.PosePriorCoordinateSystem.CARTESIAN,
                                corr_data_id=pycolmap.data_t(pycolmap.sensor_t(pycolmap.SensorType.CAMERA, imgs[img_id].camera_id), img_id))
        db.write_pose_prior(pp)
    print(f"priors: {n_known} frames from the joined model (std {a.std_known} m), {n_interp} interpolated "
          f"(std {a.std_interp} m), {len(order) - n_known - n_interp} without", flush=True)
    db.close()

    # 2) spatial pairs, not yet matched
    con = sqlite3.connect(str(a.database))
    have = {row[0] for row in con.execute("SELECT pair_id FROM matches WHERE rows > 0")}
    con.close()
    id_of = {im.name.replace("\\", "/"): i for i, im in imgs.items()}
    names = [n for n in pose if n in id_of]
    C = np.array([pose[n][0] for n in names])
    V = np.array([pose[n][1] for n in names])
    T = np.array([frame_order(n) for n in names])
    tnum = T[:, 0] * 100000 + T[:, 1]
    tree = cKDTree(C)
    cand = tree.query_pairs(a.radius, output_type="ndarray")
    i, j = cand[:, 0], cand[:, 1]
    cos = (V[i] * V[j]).sum(axis=1)
    # "more than 2 frames apart" in walking order (clip 068 before 069)
    uniq = np.unique(tnum)
    rank = np.searchsorted(uniq, tnum)
    sep = np.abs(rank[i] - rank[j])
    keep = (cos > np.cos(np.radians(a.max_angle))) & (sep > 2)
    i, j, sep = i[keep], j[keep], sep[keep]
    pid = np.array([pair_id(id_of[names[x]], id_of[names[y]]) for x, y in zip(i, j)], dtype=np.int64)
    new = ~np.isin(pid, np.fromiter(have, np.int64, len(have)))
    i, j, sep = i[new], j[new], sep[new]
    d = np.linalg.norm(C[i] - C[j], axis=1)
    # cross-pass and revisits first (far apart in walking order), then closer pairs
    prio = np.where(sep > 30, 0, 1) * 10 + d
    sel, count = [], np.zeros(len(names), int)
    for k in np.argsort(prio):  # closest cross-pass partners first, but no image gets more than --per-image
        x, y = i[k], j[k]
        if count[x] < a.per_image and count[y] < a.per_image:
            sel.append(k)
            count[x] += 1
            count[y] += 1
            if len(sel) == a.max_pairs:
                break
    sel = np.array(sel, int)
    with open(a.pairs, "w", encoding="utf-8") as f:
        for x, y in zip(i[sel], j[sel]):
            f.write(f"{names[x]} {names[y]}\n")
    far = int((sep[sel] > 30).sum())
    print(f"pairs: {len(cand)} within {a.radius} m, {keep.sum()} with overlapping views and > 2 frames apart, "
          f"{new.sum()} not matched yet; wrote {len(sel)} ({far} cross-pass / revisit, i.e. > 30 frames apart) -> {a.pairs}")


if __name__ == "__main__":
    main()
