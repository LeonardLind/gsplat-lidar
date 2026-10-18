"""Viewer scene from a bare splat PLY with no cameras (e.g. a downloaded pretrained model).

Finds the floor and ceiling planes with RANSAC on opaque Gaussian centres, then a transform
that puts the floor at z = 0 with +Z up and scales the room to a typical ceiling height
(approximate scale). The splat file itself is not re-encoded: the viewer applies the transform
to the SplatMesh (scene.json splat.transform). Collision voxels and the start pose are computed
in the transformed (world) frame.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import distance_transform_edt
from scipy.spatial.transform import Rotation

from app.core.project import write_json
from app.stages.scene_export import demo_content, placeholder_audio, read_ply


def _ransac_plane(p: np.ndarray, rng, iters=600, tol=0.01, near: np.ndarray | None = None, max_angle_deg=30.0):
    """Best plane (unit normal n, offset d with n.x = d) by inlier count; optionally normals near `near`."""
    best, best_n, best_d = 0, None, 0.0
    for _ in range(iters):
        a, b, c = p[rng.choice(len(p), 3, replace=False)]
        n = np.cross(b - a, c - a)
        if np.linalg.norm(n) < 1e-12:
            continue
        n /= np.linalg.norm(n)
        if near is not None:
            if abs(n @ near) < np.cos(np.radians(max_angle_deg)):
                continue
            n = n if n @ near > 0 else -n
        d = n @ a
        cnt = int((np.abs(p @ n - d) < tol).sum())
        if cnt > best:
            best, best_n, best_d = cnt, n, d
    if best_n is None:
        raise RuntimeError("no plane found")
    # Refine with a least-squares fit on the inliers.
    inl = p[np.abs(p @ best_n - best_d) < tol]
    c = inl.mean(axis=0)
    n = np.linalg.svd(inl - c, full_matrices=False)[2][-1]
    n = n if n @ best_n > 0 else -n
    return n, float(n @ c), len(inl)


def orient_room(xyz: np.ndarray, up_hint: np.ndarray, ceiling_m: float = 2.6, seed: int = 0) -> tuple[dict, dict]:
    rng = np.random.default_rng(seed)
    extent = np.percentile(xyz, 95, axis=0) - np.percentile(xyz, 5, axis=0)
    tol = 0.004 * float(np.linalg.norm(extent))
    sample = xyz[rng.choice(len(xyz), min(len(xyz), 200_000), replace=False)]
    # Planes roughly perpendicular to the up hint: the lowest big one is the floor, the highest the ceiling.
    h = sample @ up_hint
    lo_band = sample[h < np.percentile(h, 35)]
    hi_band = sample[h > np.percentile(h, 65)]
    n_floor, d_floor, k_floor = _ransac_plane(lo_band, rng, iters=2000, tol=tol, near=up_hint, max_angle_deg=15)
    n_ceil, d_ceil, k_ceil = _ransac_plane(hi_band, rng, iters=2000, tol=tol, near=n_floor, max_angle_deg=10)
    height = d_ceil - d_floor
    if height <= 0:
        raise RuntimeError("ceiling below floor: wrong up hint?")
    s = ceiling_m / height
    # Rotation taking the floor normal to +Z.
    rot, _ = Rotation.align_vectors([[0, 0, 1]], [n_floor])
    R = rot.as_matrix()
    world = s * (xyz @ R.T)
    t = np.array([-np.median(world[:, 0]), -np.median(world[:, 1]), -s * d_floor])
    transform = {"scale": s, "quaternion_xyzw": rot.as_quat().tolist(), "position": t.tolist()}
    info = {"floor_normal": n_floor.tolist(), "floor_inliers": k_floor, "ceiling_inliers": k_ceil,
            "room_height_units": height, "scale": s, "ceiling_m": ceiling_m,
            "angle_floor_ceiling_deg": float(np.degrees(np.arccos(np.clip(abs(n_floor @ n_ceil), -1, 1))))}
    return transform, info


def apply(transform: dict, xyz: np.ndarray) -> np.ndarray:
    R = Rotation.from_quat(transform["quaternion_xyzw"]).as_matrix()
    return transform["scale"] * (xyz @ R.T) + np.array(transform["position"])


def room_collision(ply: dict, transform: dict, out_dir: Path, ceiling_m: float = 2.6,
                   voxel: float = 0.08) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Collision voxels of a splat placed with `transform` (floor at z=0) -> collision.json; returns (occ, lo, dims).
    Also used after cleanup, with the scene's existing transform, so deleted floaters stop blocking the way."""
    xyz = np.stack([ply["x"], ply["y"], ply["z"]], axis=1).astype(np.float64)
    opacity = 1 / (1 + np.exp(-ply["opacity"]))
    scale = np.exp(np.stack([ply["scale_0"], ply["scale_1"], ply["scale_2"]], axis=1)).max(axis=1)
    w = apply(transform, xyz)
    wscale = scale * transform["scale"]
    keep = (opacity > 0.4) & (wscale < 0.15)
    lo = np.percentile(w[keep], 1, axis=0) - 0.5
    hi = np.percentile(w[keep], 99, axis=0) + 0.5
    lo[2], hi[2] = -0.2, ceiling_m + 0.3
    dims = np.ceil((hi - lo) / voxel).astype(int)
    inside = keep & np.all((w >= lo) & (w < hi), axis=1)
    ijk = ((w[inside] - lo) / voxel).astype(int)
    counts = np.bincount(ijk[:, 0] + dims[0] * (ijk[:, 1] + dims[1] * ijk[:, 2]), minlength=int(np.prod(dims)))
    occ = (counts >= 3).reshape(dims[2], dims[1], dims[0])  # [z, y, x]
    bits = np.packbits(occ.reshape(-1), bitorder="little")
    write_json(out_dir / "collision.json", {"origin": lo.tolist(), "voxel": voxel, "dims": dims.tolist(), "floorZ": 0.0,
                                            "encoding": "bitset-base64", "data": base64.b64encode(bits.tobytes()).decode()})
    return occ, lo, dims


def build_scene(ply_path: Path, out_dir: Path, name: str, up_hint: str = "-y", ceiling_m: float = 2.6,
                voxel: float = 0.08, splat_file: str = "scene.sog") -> dict:
    ply = read_ply(ply_path)
    xyz = np.stack([ply["x"], ply["y"], ply["z"]], axis=1).astype(np.float64)
    opacity = 1 / (1 + np.exp(-ply["opacity"]))
    scale = np.exp(np.stack([ply["scale_0"], ply["scale_1"], ply["scale_2"]], axis=1)).max(axis=1)
    sign = -1.0 if up_hint.startswith("-") else 1.0
    hint = np.zeros(3)
    hint["xyz".index(up_hint[-1])] = sign
    solid = (opacity > 0.5) & (scale < np.percentile(scale, 90))
    transform, info = orient_room(xyz[solid], hint, ceiling_m)

    occ, lo, dims = room_collision(ply, transform, out_dir, ceiling_m, voxel)

    # Start: the floor spot with the most clearance from obstacles between knee and head height.
    zs = lo[2] + (np.arange(dims[2]) + 0.5) * voxel
    body = occ[(zs > 0.35) & (zs < 1.8)].any(axis=0)  # [y, x]
    floor = occ[(zs > -0.15) & (zs < 0.15)].any(axis=0)
    clearance = distance_transform_edt(~body) * voxel
    clearance[~floor] = 0
    jy, ix = np.unravel_index(int(np.argmax(clearance)), clearance.shape)
    start = [float(lo[0] + (ix + 0.5) * voxel), float(lo[1] + (jy + 0.5) * voxel), 0.0]

    scene_file = out_dir / "scene.json"
    old = json.loads(scene_file.read_text(encoding="utf-8")) if scene_file.exists() else {}
    placeholder_audio(out_dir)
    if not old.get("markers") and not old.get("sounds"):
        # Demo markers on a small circle around the start, at eye height.
        ring = np.array([[start[0] + 1.2 * np.cos(a), start[1] + 1.2 * np.sin(a), 1.2] for a in np.linspace(0, 2 * np.pi, 4)[:-1]])
        old["markers"], old["sounds"] = demo_content(ring, 0.0, 1.5, [])
        old["markers"][0]["title"] = "Playroom (pretrained 3DGS model)"
        old["markers"][0]["text"] = ("Demo scene: the Deep Blending 'playroom', trained by the original 3D Gaussian Splatting "
                                     "authors (Inria). Research / non-commercial licence: fine for this personal test, "
                                     "not for publishing. Scale is approximate (ceiling set to 2.6 m).")
    scene = {
        "schema_version": 1, "name": name,
        "frame": {"up": "+Z", "units": "m", "scale": "approximate", "ceiling_m": ceiling_m,
                  "note": f"floor/ceiling found by RANSAC; ceiling height set to {ceiling_m} m"},
        "splat": {"url": splat_file, "transform": transform, "source": str(ply_path.resolve()), "voxel": voxel},
        "collision": {"url": "collision.json"},
        "start": {"position": start, "yawDeg": 0.0},
        "player": {"eyeHeight": 1.6, "radius": 0.25, "stepHeight": 0.3},
        "markers": old.get("markers", []), "blocks": old.get("blocks", []), "sounds": old.get("sounds", []),
    }
    write_json(scene_file, scene)
    info.update({"voxel": voxel, "dims": dims.tolist(), "occupied": int(occ.sum()), "start": start,
                 "start_clearance_m": float(clearance.max())})
    write_json(out_dir / "scene_info.json", info)
    return info
