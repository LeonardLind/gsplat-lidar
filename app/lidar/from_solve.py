"""Bring a new whole-walk COLMAP solve (roadmap Phase 2) into the LiDAR frame and make it trainable.

    python -m app.lidar.from_solve <solved sparse/N> <reference model> <out dir> [--lidar office_lidar_5cm.npz]

reference model: the current LiDAR-frame model (lidar/merged_rigid/sparse/0); its camera centres are the targets.
1. similarity from the solve's camera centres to the reference's (Umeyama, refitted 3x without the worst 20 %),
2. ICP of the solve's own points onto the LiDAR (7 DoF, app.lidar.refine_icp.icp); kept only if the cameras stay
   within 0.3 m (median) of the reference heights,
3. checks: registered frames, distance to the reference cameras (median / p90), camera height spread, the path
   checks of app.stages.sfm.model_quality,
4. writes <out>/sparse/0: the transformed solve with its own points replaced by the LiDAR points (ids 1..N in LiDAR
   order, as app/lidar/merge.py), plus 0_orient.json (frame lidar, metric) and from_solve.json (the checks).
Then: python -m app.lidar.visibility <out>/sparse/0 <out>/depth_points.npz, and train like merged_rigid.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pycolmap
from scipy.spatial import cKDTree

from app.lidar.refine_icp import icp, umeyama
from app.lidar.register import load_lidar, mat_apply


def centres(r: pycolmap.Reconstruction) -> dict[str, np.ndarray]:
    return {r.images[i].name.replace("\\", "/"): r.images[i].projection_center() for i in r.reg_image_ids()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("solve", type=Path)
    ap.add_argument("reference", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--lidar", type=Path, default=Path(r"C:\dev\gsl-data\data\processed\office_lidar_5cm.npz"))
    a = ap.parse_args()
    r = pycolmap.Reconstruction(str(a.solve))
    ref = centres(pycolmap.Reconstruction(str(a.reference)))
    mine = centres(r)
    common = sorted(set(mine) & set(ref))
    if len(common) < 50:
        raise SystemExit(f"only {len(common)} images in common with the reference: cannot place the solve")
    X = np.array([mine[n] for n in common])
    Y = np.array([ref[n] for n in common])
    keep = np.ones(len(X), bool)
    for _ in range(3):
        M = umeyama(X[keep], Y[keep])
        res = np.linalg.norm(mat_apply(M, X) - Y, axis=1)
        keep = res <= np.percentile(res, 80)
    res0 = np.linalg.norm(mat_apply(M, X) - Y, axis=1)

    lid, *_ = load_lidar(a.lidar)
    tree = cKDTree(lid)
    pts = np.array([p.xyz for p in r.points3D.values() if p.error < 2.0 and p.track.length() >= 3])
    if len(pts) > 400_000:
        pts = pts[np.random.default_rng(0).choice(len(pts), 400_000, replace=False)]
    M1, inl = icp(pts, M, tree, lid)
    dz = np.median(np.abs(mat_apply(M1, X)[:, 2] - Y[:, 2]))
    used_icp = bool(dz <= 0.3)
    if not used_icp:
        M1, inl = M, icp(pts, M, tree, lid, iters=0)[1]
    res1 = np.linalg.norm(mat_apply(M1, X) - Y, axis=1)

    s = float(np.cbrt(np.linalg.det(M1[:3, :3])))
    r.transform(pycolmap.Sim3d(s, pycolmap.Rotation3d(M1[:3, :3] / s), M1[:3, 3]))
    from app.stages.sfm import model_quality

    a.out.mkdir(parents=True, exist_ok=True)
    tmp = a.out / "solve_lidar_frame"
    tmp.mkdir(exist_ok=True)
    r.write(str(tmp))
    quality = {k: v for k, v in model_quality(tmp).items() if not isinstance(v, (list, dict)) or k == "warnings"}
    cz = np.array([c[2] for c in centres(r).values()])
    r.delete_all_points2D_and_points3D()
    rgb = np.load(a.lidar)["rgb"]
    for xyz, col in zip(lid, rgb):
        r.add_point3D(xyz, pycolmap.Track(), col)
    model = a.out / "sparse" / "0"
    model.mkdir(parents=True, exist_ok=True)
    r.write(str(model))
    info = {"solve": str(a.solve), "registered_images": r.num_reg_images(), "registered_frames": r.num_reg_frames(),
            "common_with_reference": len(common), "reference_images": len(ref),
            "to_reference_umeyama_m": {"median": float(np.median(res0)), "p90": float(np.percentile(res0, 90))},
            "to_reference_final_m": {"median": float(np.median(res1)), "p90": float(np.percentile(res1, 90))},
            "icp_used": used_icp, "icp_points_within_15cm": float(inl), "sim3_scale": s,
            "camera_z_p5_p50_p95": np.percentile(cz, [5, 50, 95]).round(2).tolist(), "quality": quality,
            "lidar_points": int(len(lid)), "lidar_npz": str(a.lidar)}
    (a.out / "from_solve.json").write_text(json.dumps(info, indent=1))
    (model.parent / "0_orient.json").write_text(json.dumps({**info, "scale": "metric", "frame": "lidar"}, indent=1))
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()
