"""Render pictures of a viewer scene's splat from world-frame cameras (runs in the `gs` env).

    python -m app.tools.render_scene <scene_dir> <ply> <out.jpg> --at x,y,z --look x,y,z [--fov 70 --size 1280x720]
    python -m app.tools.render_scene <scene_dir> <ply> <out.jpg> --ring x,y,z   (8 views around a point, labelled by yaw)

Uses scene.json splat.transform (world = position + R * (scale * local)), +Z up.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import torch
from gsplat.rendering import rasterization
from scipy.spatial.transform import Rotation

from app.stages.scene_export import read_ply


def load_splat(ply_path: Path, transform: dict | None):
    ply = read_ply(ply_path)
    t = lambda k: torch.tensor(np.stack([ply[x] for x in k], 1), device="cuda", dtype=torch.float32)
    means, quats = t(["x", "y", "z"]), t(["rot_0", "rot_1", "rot_2", "rot_3"])
    scales = torch.exp(t(["scale_0", "scale_1", "scale_2"]))
    op = torch.sigmoid(torch.tensor(ply["opacity"], device="cuda", dtype=torch.float32))
    nrest = len([k for k in ply if k.startswith("f_rest_")]) // 3
    sh = torch.cat([t(["f_dc_0", "f_dc_1", "f_dc_2"])[:, None],
                    t([f"f_rest_{i}" for i in range(3 * nrest)]).reshape(-1, 3, nrest).transpose(1, 2)], 1)
    deg = int(round(np.sqrt(nrest + 1))) - 1
    m = np.eye(4)
    if transform:
        m[:3, :3] = transform["scale"] * Rotation.from_quat(transform["quaternion_xyzw"]).as_matrix()
        m[:3, 3] = transform["position"]
    return (means, quats, scales, op, sh, deg), m


def render(splat, local_to_world: np.ndarray, eye, target, size=(1280, 720), fov=70.0) -> np.ndarray:
    means, quats, scales, op, sh, deg = splat
    W, H = size
    eye, target = np.asarray(eye, float), np.asarray(target, float)
    z = target - eye
    z /= np.linalg.norm(z)
    x = np.cross(z, [0, 0, 1.0])
    x /= np.linalg.norm(x)
    y = np.cross(z, x)  # OpenCV camera: x right, y down, z forward (world +Z up)
    w2c = np.eye(4)
    w2c[:3, :3] = np.stack([x, y, z])
    w2c[:3, 3] = -w2c[:3, :3] @ eye
    view = w2c @ local_to_world  # camera from splat-local coordinates (includes the scale)
    s = np.cbrt(np.linalg.det(view[:3, :3]))
    view_n = view.copy()
    view_n[:3, :] /= s  # a pure rigid view; the scale is applied to the image distance instead
    f = W / 2 / np.tan(np.radians(fov) / 2)
    K = torch.tensor([[f, 0, W / 2], [0, f, H / 2], [0, 0, 1]], device="cuda", dtype=torch.float32)[None]
    with torch.no_grad():
        img, _, _ = rasterization(means, quats, scales, op, sh, torch.tensor(view_n, device="cuda", dtype=torch.float32)[None],
                                  K, W, H, sh_degree=deg, near_plane=0.01 / s)
    return (img[0].clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)[..., ::-1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("scene_dir", type=Path)
    ap.add_argument("ply", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--at")
    ap.add_argument("--look")
    ap.add_argument("--ring")
    ap.add_argument("--fov", type=float, default=70)
    ap.add_argument("--size", default="1280x720")
    a = ap.parse_args()
    scene = json.loads((a.scene_dir / "scene.json").read_text(encoding="utf-8"))
    splat, m = load_splat(a.ply, scene["splat"].get("transform"))
    size = tuple(int(v) for v in a.size.split("x"))
    if a.ring:
        c = np.array([float(v) for v in a.ring.split(",")])
        tiles = []
        for yaw in range(0, 360, 45):
            d = np.array([np.cos(np.radians(yaw)), np.sin(np.radians(yaw)), 0.0])
            im = render(splat, m, c, c + d, (480, 320), a.fov).copy()
            cv2.putText(im, f"yaw {yaw}", (8, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            tiles.append(im)
        cv2.imwrite(str(a.out), np.vstack([np.hstack(tiles[:4]), np.hstack(tiles[4:])]))
    else:
        at = [float(v) for v in a.at.split(",")]
        look = [float(v) for v in a.look.split(",")]
        cv2.imwrite(str(a.out), render(splat, m, at, look, size, a.fov), [cv2.IMWRITE_JPEG_QUALITY, 90])


if __name__ == "__main__":
    main()
