"""Turn a COLMAP model gravity-up (+Z up), centred on the camera path, at an approximate scale.

Without LiDAR, the SfM frame is arbitrary:
  * Up: the camera is held upright on its stick, so the image-down axis of the
    centre views (lens0_c, lens1_c), averaged over the walk, points along gravity.
  * Scale: unknown. Tested on clip 069: bundle adjustment with the 3.18 cm
    lens baseline held fixed does NOT pin the scale (starts at 0.15 / 0.3 / 0.6 m
    per step all stayed apart, same error), so the baseline is too short to be
    observable. An *approximate* scale is applied instead: the median step
    between kept frames is set to ``approx_step_m`` (walking pace). It is
    flagged as approximate. LiDAR or a measured distance sets the true scale.
With LiDAR, registration replaces this step (PLAN §1.6).

Applied with pycolmap (``Reconstruction.transform``), which moves cameras, rigs
and points consistently.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pycolmap

CENTRE_VIEWS = ("lens0_c/", "lens1_c/")


def _centres_and_downs(r: pycolmap.Reconstruction):
    centres, downs, path = [], [], {}
    for i in r.reg_image_ids():
        im = r.images[i]
        c = im.projection_center()
        centres.append(c)
        if im.name.startswith(CENTRE_VIEWS):
            rot = im.cam_from_world().rotation.matrix()
            downs.append(rot.T @ np.array([0.0, 1.0, 0.0]))
        if im.name.startswith("lens0_c/"):
            path[im.name] = c
    p = np.array([path[k] for k in sorted(path)])
    return np.array(centres), np.array(downs), p


def median_step(r: pycolmap.Reconstruction) -> float:
    _, _, p = _centres_and_downs(r)
    return float(np.median(np.linalg.norm(np.diff(p, axis=0), axis=1)))


def _rotation_to_minus_z(g: np.ndarray) -> np.ndarray:
    g = g / np.linalg.norm(g)
    target = np.array([0.0, 0.0, -1.0])
    axis = np.cross(g, target)
    s, c = np.linalg.norm(axis), float(g @ target)
    if s < 1e-12:
        return np.eye(3) if c > 0 else np.diag([1.0, -1.0, -1.0])
    k = axis / s
    kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    ang = np.arctan2(s, c)
    return np.eye(3) + np.sin(ang) * kx + (1 - np.cos(ang)) * kx @ kx


def drop_stray_frames(r: pycolmap.Reconstruction, factor: float = 6.0) -> dict:
    """Deregister 360 frames whose cameras sit far outside the rest of the walk.

    gsplat sets how fast the Gaussians may move from the farthest camera (the "scene scale"). Two frames registered
    1860 and 620 units away from a 50 m scene made that scale 2040 and the 068+069 training flew apart (2026-10-21).
    A camera farther from the median centre than ``factor`` x the 90th-percentile distance is a stray: unit-free,
    so it works before the scale is set."""
    ids = list(r.reg_image_ids())
    centres = np.array([r.images[i].projection_center() for i in ids])
    d = np.linalg.norm(centres - np.median(centres, axis=0), axis=1)
    thr = factor * float(np.percentile(d, 90))
    frames = sorted({r.images[i].frame_id for i, dist in zip(ids, d) if dist > thr})
    for f in frames:
        r.deregister_frame(f)
    return {"stray_frames_removed": len(frames), "stray_threshold": thr, "stray_max_distance": float(d.max()),
            "p90_distance": float(np.percentile(d, 90))}


def orient_model(model_dir: Path, out_dir: Path, approx_step_m: float | None = 0.3) -> dict:
    r = pycolmap.Reconstruction(str(model_dir))
    info: dict = {"scale": "approximate" if approx_step_m else "arbitrary (SfM)", "warnings": []}
    info.update(drop_stray_frames(r))
    if info["stray_frames_removed"]:
        info["warnings"].append(f"{info['stray_frames_removed']} stray frame(s) removed (up to "
                                f"{info['stray_max_distance'] / max(info['p90_distance'], 1e-9):.0f}x the usual camera distance)")
    if approx_step_m:
        s = approx_step_m / median_step(r)
        r.transform(pycolmap.Sim3d(s, pycolmap.Rotation3d(), np.zeros(3)))
        info["scale_factor"] = s
        info["median_step_m"] = approx_step_m

    centres, downs, _ = _centres_and_downs(r)
    g = downs.mean(axis=0)
    gn = g / np.linalg.norm(g)
    info["tilt_spread_deg"] = float(np.degrees(np.arccos(np.clip(downs @ gn, -1, 1))).mean())
    rot = _rotation_to_minus_z(g)
    t = -rot @ centres.mean(axis=0)
    r.transform(pycolmap.Sim3d(1.0, pycolmap.Rotation3d(rot), t))

    centres, _, _ = _centres_and_downs(r)
    pts = np.array([p.xyz for p in r.points3D.values()])
    info["camera_extent"] = np.ptp(centres, axis=0).tolist()
    info["camera_height_spread"] = float(np.std(centres[:, 2]))
    zr = np.percentile(centres[:, 2], [1, 99])
    info["camera_height_p1_p99"] = zr.tolist()
    if zr[1] - zr[0] > 12.0:  # metres (approximate scale): a walk on one floor does not climb a four-storey building
        info["warnings"].append(f"cameras span {zr[1] - zr[0]:.0f} m in height: the camera path is probably bent or "
                                f"drifted (a hand-held walk on one floor stays within a few metres)")
    info["points_pct5_95"] = np.percentile(pts, [5, 95], axis=0).tolist()
    info["mean_reproj_error_px"] = float(np.mean([p.error for p in r.points3D.values()]))
    out_dir.mkdir(parents=True, exist_ok=True)
    r.write(str(out_dir))
    return info
