"""Which LiDAR points each training image sees: depth targets for gsplat's depth loss (roadmap step C).

    python -m app.lidar.visibility <merged model dir> <out.npz> [--lidar office_lidar_5cm.npz] [--per-image 4000]

The merged model's points ARE the LiDAR points (app/lidar/merge.py), in the same order, but without tracks, so
gsplat's depth loss (which projects parser.points[point_indices[image]]) has nothing to use. For every image the
LiDAR points are projected, a z-buffer at 1/4 resolution keeps only the front surface (nothing behind walls), and
up to --per-image of the visible points are kept (spread over the picture). The trainer's dataset
(app/trainers/gsplat_fork/gsl_dataset.py, GSL_DEPTH_POINTS=<out.npz>) puts them into parser.point_indices.

out.npz: names (image names), offsets (len names + 1), indices (int32, concatenated point ids).
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pycolmap

from app.lidar.register import load_lidar


def visible_points(xyz: np.ndarray, R: np.ndarray, t: np.ndarray, K: np.ndarray, w: int, h: int,
                   down: int = 4, max_depth: float = 20.0, tol: float = 0.04) -> np.ndarray:
    pc = xyz @ R.T + t
    z = pc[:, 2]
    front = np.nonzero((z > 0.1) & (z < max_depth))[0]
    pc, z = pc[front], z[front]
    u = K[0, 0] * pc[:, 0] / z + K[0, 2]
    v = K[1, 1] * pc[:, 1] / z + K[1, 2]
    inside = (u >= 0) & (u < w) & (v >= 0) & (v < h)
    front, z, u, v = front[inside], z[inside], u[inside], v[inside]
    W = (w + down - 1) // down
    pix = (v // down).astype(np.int64) * W + (u // down).astype(np.int64)
    zbuf = np.full(W * ((h + down - 1) // down), np.inf)
    np.minimum.at(zbuf, pix, z)
    keep = z <= zbuf[pix] * (1 + tol) + 0.03  # the front surface of each cell, not what lies behind it
    return front[keep]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("model", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--lidar", type=Path, default=Path(r"C:\dev\gsl-data\data\processed\office_lidar_5cm.npz"))
    ap.add_argument("--per-image", type=int, default=4000)
    a = ap.parse_args()
    t0 = time.time()
    r = pycolmap.Reconstruction(str(a.model))
    xyz, *_ = load_lidar(a.lidar)
    if r.num_points3D() != len(xyz):
        raise SystemExit(f"the model has {r.num_points3D()} points, the LiDAR {len(xyz)}: not a merge.py model of this LiDAR")
    # gsplat's parser orders the points by id; merge.py / from_solve.py added them in LiDAR order with consecutive
    # ids (1..N, or k+1..k+N when the model had points before), so LiDAR row = parser index
    ids = np.sort(np.fromiter(r.point3D_ids(), np.int64))
    if not np.array_equal(ids, np.arange(ids[0], ids[0] + len(xyz))):
        raise SystemExit("point ids are not consecutive: the LiDAR points were not added in order")
    rng = np.random.default_rng(0)
    names, chunks, counts = [], [], []
    ids = sorted(r.reg_image_ids(), key=lambda i: r.images[i].name)
    for k, i in enumerate(ids):
        im = r.images[i]
        cam = r.cameras[im.camera_id]
        cw = im.cam_from_world()
        vis = visible_points(xyz, cw.rotation.matrix(), np.asarray(cw.translation), cam.calibration_matrix(), cam.width, cam.height)
        counts.append(len(vis))
        if len(vis) > a.per_image:
            vis = rng.choice(vis, a.per_image, replace=False)
        names.append(im.name)
        chunks.append(np.sort(vis).astype(np.int32))
        if k % 1000 == 0:
            print(f"  {k}/{len(ids)} images, {len(vis)} points for {im.name} ({time.time() - t0:.0f} s)", flush=True)
    offsets = np.concatenate([[0], np.cumsum([len(c) for c in chunks])])
    a.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(a.out, names=np.array(names), offsets=offsets, indices=np.concatenate(chunks))
    c = np.array(counts)
    print(f"done: {len(names)} images, visible LiDAR points per image median {np.median(c):.0f} "
          f"(p10 {np.percentile(c, 10):.0f}), kept up to {a.per_image}; {(c < 200).sum()} images see < 200 points "
          f"({time.time() - t0:.0f} s) -> {a.out}")


if __name__ == "__main__":
    main()
