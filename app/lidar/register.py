"""Register an SfM piece (arbitrary frame and scale) to the LiDAR scan: up axis, metric scale, yaw and position.

    python -m app.lidar.register <sparse model dir> <out dir> [--lidar office_lidar_5cm.npz]

The sparse SfM points of a dim office are noisy and full of outliers, so they are a poor thing to match against the
scan. The camera path is a clean signal: a person walked it, so every camera must be in free space, above the floor
and not inside a wall. That gives a score that can be searched exhaustively:

1. up and scale: floor and ceiling planes of the piece's points (RANSAC); the LiDAR gives the true floor-to-ceiling
   height, so the scale follows. Several "up" candidates are tried (both signs).
2. search: yaw (0-360 deg), a few scale factors around the plane-based scale, and position by FFT correlation of the
   camera-path map with the LiDAR's "walkable" map (floor minus 2 x walls). Score = mean value of that map under the
   cameras (1 = every camera over floor, negative = cameras inside walls).
3. refinement: ICP of the sparse points near the cameras onto the scan; kept only if the camera score does not drop.

Result: <out>/registration.json (4x4 similarity piece -> LiDAR frame with the floor at z = 0), overlay.png (top view).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np
import open3d as o3d
import pycolmap
from scipy.ndimage import binary_dilation, gaussian_filter
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

from app.stages.ply_scene import orient_room

CELL = 0.10  # m, top-down map resolution


def load_lidar(path: Path):
    d = np.load(path)
    xyz = d["xyz"].astype(np.float64)
    z = xyz[:, 2]
    h, e = np.histogram(z, bins=np.arange(z.min(), z.max() + 0.01, 0.01))
    lo = np.argmax(h[: len(h) // 3])
    hi = len(h) * 2 // 3 + np.argmax(h[len(h) * 2 // 3:])
    floor_z, ceil_z = (e[lo] + e[lo + 1]) / 2, (e[hi] + e[hi + 1]) / 2
    xyz[:, 2] -= floor_z
    return xyz, float(ceil_z - floor_z), float(floor_z), d["origin"]


def load_piece(model_dir: Path, min_track: int = 3, max_error: float = 2.0, limit: int = 400_000):
    r = pycolmap.Reconstruction(str(model_dir))
    pts = np.array([p.xyz for p in r.points3D.values() if p.track.length() >= min_track and p.error < max_error])
    if len(pts) > limit:
        pts = pts[np.random.default_rng(0).choice(len(pts), limit, replace=False)]
    centres, downs = [], []
    for i in r.reg_image_ids():
        im = r.images[i]
        if im.name.replace("\\", "/").startswith(("lens0_c/", "lens1_c/")):
            centres.append(im.projection_center())
            downs.append(im.cam_from_world().rotation.matrix().T @ np.array([0.0, 1.0, 0.0]))
    return pts, np.array(centres), np.array(downs)


def up_candidates(pts: np.ndarray, downs: np.ndarray) -> list[np.ndarray]:
    c = pts - np.median(pts, axis=0)
    w, v = np.linalg.eigh(np.cov(c[:: max(1, len(c) // 100000)].T))
    cands = [v[:, 0], -v[:, 0]]
    g = -downs.mean(axis=0)
    if np.linalg.norm(g) > 1e-6:
        cands.append(g / np.linalg.norm(g))
    out: list[np.ndarray] = []
    for u in cands:
        if all(np.degrees(np.arccos(np.clip(u @ o, -1, 1))) > 12 for o in out):
            out.append(u / np.linalg.norm(u))
    return out


def walkable_map(lid: np.ndarray, ext: tuple[float, float, float, float]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(score map, floor mask, wall mask): +1 over floor, -2 where something tall (wall, partition) stands."""
    x0, x1, y0, y1 = ext
    nx, ny = int((x1 - x0) / CELL), int((y1 - y0) / CELL)

    def grid(sel, minpts):
        h, _, _ = np.histogram2d(lid[sel, 0], lid[sel, 1], bins=[nx, ny], range=[[x0, x1], [y0, y1]])
        return h >= minpts

    floor = binary_dilation(grid(lid[:, 2] < 0.15, 1), iterations=1)
    wall = grid((lid[:, 2] > 1.0) & (lid[:, 2] < 2.3), 2)
    score = floor.astype(float) - 2.0 * binary_dilation(wall, iterations=1)
    return gaussian_filter(score, 1.5), floor, wall


def path_map(cams: np.ndarray, ext: tuple[float, float, float, float], shape) -> np.ndarray:
    x0, x1, y0, y1 = ext
    h, _, _ = np.histogram2d(cams[:, 0], cams[:, 1], bins=list(shape), range=[[x0, x1], [y0, y1]])
    return gaussian_filter(h, 1.0)


def correlate(walk: np.ndarray, pic: np.ndarray):
    """Raw cross-correlation of the walkable map with a path map; best score per camera and the shift in cells."""
    n = int(2 ** np.ceil(np.log2(max(walk.shape[0] + pic.shape[0], walk.shape[1] + pic.shape[1]))))
    cc = np.fft.irfft2(np.fft.rfft2(walk, (n, n)) * np.conj(np.fft.rfft2(pic, (n, n))), (n, n))
    k = np.unravel_index(int(np.argmax(cc)), cc.shape)
    shift = [k[0] if k[0] < n // 2 else k[0] - n, k[1] if k[1] < n // 2 else k[1] - n]
    return float(cc[k] / max(pic.sum(), 1e-9)), shift


def sim3_matrix(s: float, R: np.ndarray, t: np.ndarray) -> np.ndarray:
    M = np.eye(4)
    M[:3, :3] = s * R
    M[:3, 3] = t
    return M


def mat_apply(M: np.ndarray, xyz: np.ndarray) -> np.ndarray:
    return xyz @ M[:3, :3].T + M[:3, 3]


def camera_score(cams: np.ndarray, walk: np.ndarray, ext, lid_tree: cKDTree, lid: np.ndarray) -> tuple[float, int]:
    """(mean walkable value under the cameras, number of cameras within 25 cm of a wall/furniture point at their height)."""
    ix = ((cams[:, 0] - ext[0]) / CELL).astype(int)
    iy = ((cams[:, 1] - ext[2]) / CELL).astype(int)
    ok = (ix >= 0) & (ix < walk.shape[0]) & (iy >= 0) & (iy < walk.shape[1])
    val = np.full(len(cams), -1.0)
    val[ok] = walk[ix[ok], iy[ok]]
    body = lid[(lid[:, 2] > 0.3) & (lid[:, 2] < 2.45)]
    d, _ = cKDTree(body).query(cams, k=1)
    return float(val.mean()), int((d < 0.25).sum())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("model", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--lidar", type=Path, default=Path(r"C:\dev\gsl-data\data\processed\office_lidar_5cm.npz"))
    ap.add_argument("--room-height", type=float, default=None)
    ap.add_argument("--yaw-step", type=float, default=2.0)
    ap.add_argument("--scales", type=float, nargs="+", default=[0.9, 0.95, 1.0, 1.05, 1.1])
    ap.add_argument("--candidates", type=int, default=8)
    a = ap.parse_args()
    t0 = time.time()
    a.out.mkdir(parents=True, exist_ok=True)

    lid, room_h, floor_z, origin = load_lidar(a.lidar)
    room_h = a.room_height or room_h
    ext = (lid[:, 0].min() - 10, lid[:, 0].max() + 10, lid[:, 1].min() - 10, lid[:, 1].max() + 10)
    walk, floor_m, wall_m = walkable_map(lid, ext)
    target = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(lid))
    target.estimate_normals(o3d.geometry.KDTreeSearchParamKNN(30))
    tree = cKDTree(lid)
    pts, centres, downs = load_piece(a.model)
    print(f"LiDAR {len(lid):,} pts, room height {room_h:.2f} m; piece {len(pts):,} points, {len(centres)} cameras "
          f"({time.time() - t0:.0f} s)", flush=True)

    # 1+2: up candidates x scale factors x yaw -> best (position by FFT) per combination
    cands = []
    for ui, up in enumerate(up_candidates(pts, downs)):
        try:
            tr, info = orient_room(pts, up, room_h)
        except Exception as e:  # noqa: BLE001
            print(f"  up {ui}: no floor/ceiling pair ({e})", flush=True)
            continue
        M0 = sim3_matrix(tr["scale"], Rotation.from_quat(tr["quaternion_xyzw"]).as_matrix(), np.array(tr["position"]))
        c0 = mat_apply(M0, centres)
        print(f"  up {ui}: scale {tr['scale']:.3f}, planes {info['floor_inliers']}/{info['ceiling_inliers']} inliers, "
              f"{info['angle_floor_ceiling_deg']:.1f} deg apart, cameras {np.percentile(c0[:, 2], 5):.2f}.."
              f"{np.percentile(c0[:, 2], 95):.2f} m above the floor", flush=True)
        for f in a.scales:
            cf = c0 * f
            for yaw in np.arange(0, 360, a.yaw_step):
                Rz = Rotation.from_euler("z", yaw, degrees=True).as_matrix()
                q = cf @ Rz.T
                score, shift = correlate(walk, path_map(q, ext, walk.shape))
                cands.append((score, ui, f, float(yaw), shift, M0))
    cands.sort(key=lambda c: -c[0])
    picked = []
    for c in cands:
        if all(not (c[1] == p[1] and abs(c[2] - p[2]) < 1e-6 and abs(((c[3] - p[3] + 180) % 360) - 180) < 10) for p in picked):
            picked.append(c)
        if len(picked) >= a.candidates:
            break
    print(f"search done ({time.time() - t0:.0f} s); best camera scores: {[round(c[0], 2) for c in picked]}", flush=True)

    # 3: refine each candidate with ICP on the points near the cameras, keep it if the camera score does not drop
    results = []
    for score0, ui, f, yaw, shift, M0 in picked:
        Rz = Rotation.from_euler("z", yaw, degrees=True).as_matrix()
        S = np.diag([f, f, f, 1.0])
        Mz = np.eye(4)
        Mz[:3, :3] = Rz
        Mz[:3, 3] = np.r_[shift[0] * CELL, shift[1] * CELL, 0.0]
        # the shift is applied to positions already rotated about the origin; M = T(shift) R(yaw) S M0
        M1 = Mz @ S @ M0
        cams1 = mat_apply(M1, centres)
        p1 = mat_apply(M1, pts)
        near = cKDTree(cams1).query(p1, k=1)[0] < 4.0
        src = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(p1[near])).voxel_down_sample(0.08)
        M2 = M1.copy()
        T = np.eye(4)
        for thr in (0.6, 0.3, 0.15):
            reg = o3d.pipelines.registration.registration_icp(
                src, target, thr, np.eye(4), o3d.pipelines.registration.TransformationEstimationPointToPlane(),
                o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=30))
            src.transform(reg.transformation)
            T = reg.transformation @ T
        M2 = T @ M1
        s1, w1 = camera_score(cams1, walk, ext, tree, lid)
        s2, w2 = camera_score(mat_apply(M2, centres), walk, ext, tree, lid)
        use = M2 if (s2 >= s1 - 0.02 and w2 <= w1 + 5) else M1
        ev = o3d.pipelines.registration.evaluate_registration(src, target, 0.15, np.eye(4)) if use is M2 else None
        sc, inside = (s2, w2) if use is M2 else (s1, w1)
        results.append({"up": ui, "scale_factor": f, "yaw": yaw, "path_score": score0, "camera_score": sc,
                        "cameras_near_walls": inside, "icp_used": use is M2, "fitness15": ev.fitness if ev else None,
                        "M": use.tolist()})
        print(f"    up {ui} x{f:.2f} yaw {yaw:5.1f}: path score {score0:.2f} -> after ICP {sc:.2f}, cameras near walls "
              f"{inside}/{len(centres)}, ICP {'kept' if use is M2 else 'rejected'} ({time.time() - t0:.0f} s)", flush=True)

    results.sort(key=lambda x: -(x["camera_score"] - x["cameras_near_walls"] / len(centres)))
    best = results[0]
    M = np.array(best["M"])
    second = results[1] if len(results) > 1 else None
    out = {"model": str(a.model), "sim3_piece_to_lidar": best["M"], "scale": float(np.cbrt(abs(np.linalg.det(M[:3, :3])))),
           "camera_score": best["camera_score"], "cameras_near_walls": best["cameras_near_walls"],
           "n_cameras": int(len(centres)), "lidar_floor_z": floor_z, "lidar_origin": origin.tolist(),
           "runner_up_camera_score": second["camera_score"] if second else None,
           "runner_up_yaw_diff": (abs(((second["yaw"] - best["yaw"] + 180) % 360) - 180) if second else None),
           "all": [{k: v for k, v in x.items() if k != "M"} for x in results]}
    (a.out / "registration.json").write_text(json.dumps(out, indent=1))

    # overlay: LiDAR floor (dark), walls (grey), piece points near the cameras (red), cameras (green)
    res = CELL / 2
    W, H = int((ext[1] - ext[0]) / res), int((ext[3] - ext[2]) / res)
    img = np.zeros((H, W, 3), np.uint8)
    big = lambda m: cv2.resize(m.astype(np.uint8), (H, W), interpolation=cv2.INTER_NEAREST).T[::-1]  # noqa: E731
    img[big(floor_m) > 0] = (45, 45, 45)
    img[big(wall_m) > 0] = (140, 140, 140)
    cams = mat_apply(M, centres)
    pp = mat_apply(M, pts)
    near = cKDTree(cams).query(pp, k=1)[0] < 4.0
    for x, y in zip(((pp[near, 0] - ext[0]) / res).astype(int), H - 1 - ((pp[near, 1] - ext[2]) / res).astype(int)):
        if 0 <= x < W and 0 <= y < H:
            img[y, x] = (60, 60, 255)
    for x, y in zip(((cams[:, 0] - ext[0]) / res).astype(int), H - 1 - ((cams[:, 1] - ext[2]) / res).astype(int)):
        if 0 <= x < W and 0 <= y < H:
            cv2.circle(img, (x, y), 2, (80, 255, 80), -1)
    keep = (np.abs(img.sum(axis=2)) > 0)
    ys, xs = np.nonzero(keep)
    cv2.imwrite(str(a.out / "overlay.png"), img[max(ys.min() - 20, 0): ys.max() + 20, max(xs.min() - 20, 0): xs.max() + 20])
    print(f"BEST: camera score {best['camera_score']:.2f} (1 = all cameras over floor), cameras near walls "
          f"{best['cameras_near_walls']}/{len(centres)}, scale {out['scale']:.3f}, yaw {best['yaw']:.0f}; runner-up "
          f"{(second['camera_score'] if second else float('nan')):.2f} ({out['runner_up_yaw_diff']} deg apart) ({time.time() - t0:.0f} s)",
          flush=True)


if __name__ == "__main__":
    main()
