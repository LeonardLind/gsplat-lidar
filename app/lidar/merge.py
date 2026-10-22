"""Join the placed chunks of the walk into ONE COLMAP model in the LiDAR frame (metric, z up, floor at z = 0).

    python -m app.lidar.merge <sparse dir> <chunks.json> <placements dir> <out model dir> [--lidar office_lidar_5cm.npz]

Every placement from solve_clicks (a whole chunk, or one stretch of a split chunk) moves its images with its own
similarity. A frame that two placements contain keeps the better-scoring one. The starting points for training are
the LiDAR points with their colours (no tracks), so the splat starts from the true geometry instead of the bent SfM
points. Each image gets a trivial rig/frame: the trainer only needs poses and intrinsics.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pycolmap

from app.lidar.chain import load_models
from app.lidar.register import load_lidar


def stem_of(name: str) -> tuple[str, str]:
    n = name.replace("\\", "/")
    return n.split("/")[0], n.split("/")[-1].rsplit(".", 1)[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sparse", type=Path)
    ap.add_argument("chunks", type=Path)
    ap.add_argument("placements", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--lidar", type=Path, default=Path(r"C:\dev\gsl-data\data\processed\office_lidar_5cm.npz"))
    a = ap.parse_args()
    chunks = json.loads(a.chunks.read_text())
    pl = json.loads((a.placements / "placements.json").read_text())["chunks"]
    models = load_models(a.sparse, {p["model"] for p in pl})

    # which placement owns which frame (the better score wins where two overlap)
    owner: dict[str, int] = {}
    for pi, p in sorted(enumerate(pl), key=lambda kv: kv[1]["score"]):
        r = models[p["model"]]
        have = set()
        for i in r.reg_image_ids():
            view, stem = stem_of(r.images[i].name)
            if view == "lens0_c":
                have.add(stem)
        frames = [f for f in chunks[p["chunk"]]["frames"] if f in have]  # same order as chunk_geometry's cameras
        i0, i1 = p.get("range", [0, len(frames) - 1])
        for f in frames[i0:i1 + 1]:
            owner[f] = pi  # later (better) placements overwrite

    out = pycolmap.Reconstruction()
    cam_ids: dict[str, int] = {}
    n_img = 0
    for pi, p in enumerate(pl):
        r = models[p["model"]]
        A = np.array(p["M"])
        s = float(np.cbrt(np.linalg.det(A[:3, :3])))
        R, t = A[:3, :3] / s, A[:3, 3]
        for i in r.reg_image_ids():
            im = r.images[i]
            view, stem = stem_of(im.name)
            if owner.get(stem) != pi:
                continue
            if view not in cam_ids:
                c = r.cameras[im.camera_id]
                cid = len(cam_ids) + 1
                out.add_camera_with_trivial_rig(pycolmap.Camera(model=c.model, width=c.width, height=c.height,
                                                                params=c.params, camera_id=cid))
                cam_ids[view] = cid
            cw = im.cam_from_world()
            Rc, tc = cw.rotation.matrix(), np.asarray(cw.translation)
            # x' = s R x + t  =>  x_cam (scaled by s) = Rc R^T x' + (s tc - Rc R^T t)
            Rn = Rc @ R.T
            tn = s * tc - Rn @ t
            n_img += 1
            new = pycolmap.Image(name=im.name, camera_id=cam_ids[view], image_id=n_img)
            out.add_image_with_trivial_frame(new, pycolmap.Rigid3d(np.hstack([Rn, tn[:, None]])))

    lid, room_h, floor_z, origin = load_lidar(a.lidar)
    rgb = np.load(a.lidar)["rgb"]
    for xyz, col in zip(lid, rgb):
        out.add_point3D(xyz, pycolmap.Track(), col)
    a.out.mkdir(parents=True, exist_ok=True)
    out.write(str(a.out))
    centres = np.array([out.images[i].projection_center() for i in out.reg_image_ids()])
    info = {"images": n_img, "frames": len(owner), "cameras": len(cam_ids), "placements": len(pl),
            "lidar_points": int(len(lid)), "lidar_floor_z": floor_z, "room_height_m": room_h,
            "camera_z_p5_p95": [float(np.percentile(centres[:, 2], 5)), float(np.percentile(centres[:, 2], 95))],
            "camera_extent_m": (centres.max(axis=0) - centres.min(axis=0)).round(1).tolist(),
            "mean_lidar_rgb": rgb.mean(axis=0).round(1).tolist()}
    (a.out.parent / "merge_info.json").write_text(json.dumps(info, indent=1))
    # what the export reads next to an oriented model: this one is in metres (LiDAR frame), z up, floor at 0
    (a.out.parent / f"{a.out.name}_orient.json").write_text(json.dumps({"scale": "metric", "frame": "lidar", "lidar_npz": str(a.lidar), **info}, indent=1))
    print(json.dumps(info))


if __name__ == "__main__":
    main()
