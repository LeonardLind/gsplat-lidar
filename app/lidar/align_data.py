"""Data for the 2D alignment page (web/viewer/align.html): LiDAR floor plan image + a piece's path and points.

    python -m app.lidar.align_data <registration dir with registration.json> <piece name> [--out web/viewer/public/align]

Writes <out>/plan.png (once), <out>/<piece>.json. The piece is given in its own "base frame" (up axis, metric scale
from the floor and ceiling planes, floor at z = 0, centred) so that only yaw, a shift and a mirror remain to be set
by hand; the page starts from the automatic result.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

from app.lidar.register import CELL, load_lidar, load_piece, mat_apply, up_candidates
from app.stages.ply_scene import orient_room

REPO = Path(__file__).resolve().parents[2]
RES = 0.05  # m per pixel of the plan image


def base_frames(model: Path, room_h: float):
    pts, centres, downs = load_piece(model)
    out = []
    for up in up_candidates(pts, downs):
        try:
            tr, _ = orient_room(pts, up, room_h)
        except Exception:  # noqa: BLE001
            continue
        R = Rotation.from_quat(tr["quaternion_xyzw"]).as_matrix()
        M = np.eye(4)
        M[:3, :3] = tr["scale"] * R
        M[:3, 3] = tr["position"]
        out.append(M)
    return pts, centres, out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("regdir", type=Path)
    ap.add_argument("name")
    ap.add_argument("--out", type=Path, default=REPO / "web" / "viewer" / "public" / "align")
    ap.add_argument("--lidar", type=Path, default=Path(r"C:\dev\gsl-data\data\processed\office_lidar_5cm.npz"))
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    reg = json.loads((a.regdir / "registration.json").read_text())
    lid, room_h, floor_z, origin = load_lidar(a.lidar)

    # plan image: floor dark, walls and furniture (0.3-2.3 m) light; bounds in LiDAR metres
    pad = 6.0
    x0, x1 = lid[:, 0].min() - pad, lid[:, 0].max() + pad
    y0, y1 = lid[:, 1].min() - pad, lid[:, 1].max() + pad
    W, H = int((x1 - x0) / RES), int((y1 - y0) / RES)
    img = np.zeros((H, W, 3), np.uint8)

    def pix(xyz):
        return ((xyz[:, 0] - x0) / RES).astype(int), H - 1 - ((xyz[:, 1] - y0) / RES).astype(int)

    for sel, col in (((lid[:, 2] < 0.15), (50, 50, 50)), ((lid[:, 2] > 0.3) & (lid[:, 2] < 2.3), (200, 200, 200))):
        xs, ys = pix(lid[sel])
        ok = (xs >= 0) & (xs < W) & (ys >= 0) & (ys < H)
        img[ys[ok], xs[ok]] = col
    cv2.imwrite(str(a.out / "plan.png"), img)

    pts, centres, Ms = base_frames(Path(reg["model"]), room_h)
    best = reg["all"][0]
    # Which "up" to start from: for a short walk every placement scores 1.0, so the automatic choice means nothing.
    # Take the first candidate whose cameras are all above the floor (5th percentile >= 0.3 m) and whose floor and
    # ceiling planes are well supported (the camera-down candidate, with planes > 5 deg apart, is the last resort).
    up_i = best["up"]
    for i, M in enumerate(Ms):
        z = mat_apply(M, centres)[:, 2]
        flat = abs(float(np.linalg.det(M[:3, :3]))) > 0 and np.percentile(z, 95) < room_h
        if i < 2 and flat and np.percentile(z, 5) >= 0.3:
            up_i = i
            break
    M0 = Ms[up_i]
    cams = mat_apply(M0, centres)
    p = mat_apply(M0, pts)
    near = cKDTree(cams[:, :2]).query(p[:, :2], k=1)[0] < 4.0
    p = p[near & (p[:, 2] > 0.3) & (p[:, 2] < 2.3)]
    p = p[np.random.default_rng(0).permutation(len(p))[:25000]]
    # the automatic result in the base frame: x_lidar = f * Rz(yaw) * x_base + shift (shift as found by the search)
    M = np.array(reg["sim3_piece_to_lidar"])
    if up_i == best["up"]:  # the automatic result is in this base frame: start the page from it
        Mb = M @ np.linalg.inv(M0)  # base frame -> LiDAR frame
        s = float(np.cbrt(abs(np.linalg.det(Mb[:3, :3]))))
        yaw = float(np.degrees(np.arctan2(Mb[1, 0], Mb[0, 0])))
        tx, ty = float(Mb[0, 3]), float(Mb[1, 3])
    else:  # otherwise start in the middle of the plan
        s, yaw, tx, ty = 1.0, 0.0, float((x0 + x1) / 2), float((y0 + y1) / 2)
    data = {"name": a.name, "room_height": room_h,
            "plan": {"url": "plan.png", "x0": x0, "x1": x1, "y0": y0, "y1": y1, "res": RES},
            "cams": np.round(cams[:, :3], 3).tolist(), "pts": np.round(p[:, :2], 3).tolist(),
            "up_candidates": len(Ms), "init_up": up_i,
            "init": {"yaw": yaw, "scale": s, "tx": tx, "ty": ty, "mirror": False},
            "model": reg["model"]}
    (a.out / f"{a.name}.json").write_text(json.dumps(data))
    print(f"plan {W}x{H}px; piece {a.name}: {len(cams)} cameras, {len(p):,} points; up candidate {up_i}; initial yaw "
          f"{yaw:.1f}, scale {s:.3f}, shift ({tx:.2f}, {ty:.2f}) -> {a.out}")


if __name__ == "__main__":
    main()
