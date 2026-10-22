"""Refine every placement from solve_clicks by snapping its own SfM points onto the LiDAR points (trimmed ICP, 7 DoF).

    python -m app.lidar.refine_icp <sparse dir> <chunks.json> <placements dir> <out dir>

The click solver fixes where a piece lies on the plan, but its height and scale come from noisy floor/ceiling planes
(camera heights over the floor ranged from -0.06 to 2.6 m in solve3). Starting from that placement, ICP pulls the
piece's points onto the nearest LiDAR points (distance threshold shrinking 1.0 -> 0.25 m, the closest 70 % of
pairs). Check: the camera was carried at one height, so after a good refinement the pieces' camera heights agree.

Writes <out>/placements.json (same format) and a table with camera heights before / after.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from app.lidar.chain import load_models
from app.lidar.merge import stem_of
from app.lidar.register import load_lidar, mat_apply
from app.lidar.solve_clicks import parse_heights


def umeyama(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    mu_s, mu_d = src.mean(axis=0), dst.mean(axis=0)
    xs, xd = src - mu_s, dst - mu_d
    U, S, Vt = np.linalg.svd(xd.T @ xs / len(src))
    D = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        D[2, 2] = -1
    R = U @ D @ Vt
    s = float(np.trace(np.diag(S) @ D) / (xs ** 2).sum(axis=1).mean())
    T = np.eye(4)
    T[:3, :3] = s * R
    T[:3, 3] = mu_d - s * R @ mu_s
    return T


def icp(pts: np.ndarray, M: np.ndarray, tree: cKDTree, lid: np.ndarray, iters: int = 40):
    M = M.copy()
    for it in range(iters):
        thr = max(0.25, 1.0 - it * 0.03)
        q = mat_apply(M, pts)
        d, j = tree.query(q, distance_upper_bound=thr)
        ok = np.isfinite(d)
        if ok.sum() < 50:
            break
        keep = np.argsort(d[ok])[: int(0.7 * ok.sum())]
        src, dst = q[ok][keep], lid[j[ok][keep]]
        T = umeyama(src, dst)
        M = T @ M
        if np.abs(T - np.eye(4)).max() < 1e-4:
            break
    q = mat_apply(M, pts)
    d, _ = tree.query(q, distance_upper_bound=0.15)
    return M, float(np.isfinite(d).mean())


def height_search(pts: np.ndarray, cams: np.ndarray, M: np.ndarray, tree: cKDTree, n: int = 8000) -> np.ndarray:
    """Brute-force the height offset and a scale factor (about the camera centroid) before ICP: the SfM floor and
    ceiling planes are too noisy to set the height (the two up candidates often swap floor and ceiling)."""
    rng = np.random.default_rng(0)
    sub = pts[rng.choice(len(pts), min(n, len(pts)), replace=False)]
    q0, c0 = mat_apply(M, sub), np.median(mat_apply(M, cams), axis=0)
    best = (-1.0, M)
    for f in (0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.17, 1.25):
        qf = c0 + f * (q0 - c0)
        for dz in np.arange(-2.5, 2.51, 0.05):
            d, _ = tree.query(qf + [0.0, 0.0, dz], distance_upper_bound=0.10)
            v = float(np.isfinite(d).mean())
            if v > best[0]:
                T = np.eye(4)
                T[:3, :3] *= f
                T[:3, 3] = c0 - f * c0 + [0.0, 0.0, dz]
                best = (v, T @ M)
    return best[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sparse", type=Path)
    ap.add_argument("chunks", type=Path)
    ap.add_argument("placements", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--heights", default="", help="as in solve_clicks: keep ICP only if the camera height stays within 0.3 m")
    ap.add_argument("--lidar", type=Path, default=Path(r"C:\dev\gsl-data\data\processed\office_lidar_5cm.npz"))
    a = ap.parse_args()
    chunks = json.loads(a.chunks.read_text())
    src = json.loads((a.placements / "placements.json").read_text())
    pl = src["chunks"]
    models = load_models(a.sparse, {p["model"] for p in pl})
    lid, room_h, floor_z, origin = load_lidar(a.lidar)
    tree = cKDTree(lid)
    heights = parse_heights(a.heights)
    out = []
    for p in pl:
        r = models[p["model"]]
        have, ids_by_stem, cam_by_stem = set(), {}, {}
        for i in r.reg_image_ids():
            view, stem = stem_of(r.images[i].name)
            ids_by_stem.setdefault(stem, []).append(i)
            if view == "lens0_c":
                have.add(stem)
                cam_by_stem[stem] = r.images[i].projection_center()
        frames = [f for f in chunks[p["chunk"]]["frames"] if f in have]
        i0, i1 = p["range"]
        mine = frames[i0:i1 + 1]
        img_ids = {i for f in mine for i in ids_by_stem[f]}
        pts = np.array([q.xyz for q in r.points3D.values() if q.error < 2.0 and q.track.length() >= 3
                        and any(e.image_id in img_ids for e in q.track.elements)])
        cams = np.array([cam_by_stem[f] for f in mine])
        M0 = np.array(p["M"])
        H = heights.get(p["chunk"])
        M1, inl = icp(pts, M0 if H is not None else height_search(pts, cams, M0, tree), tree, lid)
        if H is not None and abs(np.median(mat_apply(M1, cams)[:, 2]) - H) > 0.3:
            print(f"  chunk {p['chunk']:2d} [{p['range'][0]:3d}-{p['range'][1]:3d}]: ICP left the pass height, kept the click placement")
            M1 = M0
            inl = icp(pts, M0, tree, lid, iters=0)[1]
        z0, z1 = np.median(mat_apply(M0, cams)[:, 2]), np.median(mat_apply(M1, cams)[:, 2])
        ds = np.cbrt(np.linalg.det(M1[:3, :3]) / np.linalg.det(M0[:3, :3]))
        moved = np.median(np.linalg.norm(mat_apply(M1, cams) - mat_apply(M0, cams), axis=1))
        print(f"  chunk {p['chunk']:2d} [{i0:3d}-{i1:3d}] {len(pts):6d} pts: camera height {z0:5.2f} -> {z1:5.2f} m, "
              f"scale x{ds:.2f}, cameras moved {moved:.2f} m, points within 15 cm of LiDAR {inl:.0%}", flush=True)
        out.append({**p, "M": M1.tolist(), "icp_inliers": inl, "camera_height_m": float(z1), "icp_moved_m": float(moved)})
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "placements.json").write_text(json.dumps({**src, "chunks": out}))
    h = np.array([p["camera_height_m"] for p in out])
    print(f"camera heights after ICP: median {np.median(h):.2f} m, p10 {np.percentile(h, 10):.2f}, p90 {np.percentile(h, 90):.2f}")


if __name__ == "__main__":
    main()
