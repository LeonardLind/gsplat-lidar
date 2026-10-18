"""Reproject selected fisheye frames into pinhole views (PLAN §1.3, primary path).

Each lens track is cut into a fixed set of square pinhole views that share the
lens's optical centre. The layout is the same for every frame, so COLMAP can
treat all views of one moment as one rig frame with known relative rotations.

Lens frame convention (OpenCV): x right, y down, z along the optical axis, as
seen in the lens track image. A view is defined by yaw (about lens y, positive
turns right) and pitch (about lens x, positive tilts down).

Outputs (COLMAP-ready):
    views/<clip>/images/lens<L>_<view>/<frame>.png
    views/<clip>/masks/lens<L>_<view>/<frame>.png.png    (255 = use, 0 = ignore)
    views/<clip>/views.json                             camera + rotation per view
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np
from tqdm import tqdm

from app.core.project import read_json, write_json
from app.sources.insta360.lens import MeiLens, SensorToTrack, best_offset_string, parse_offset_string

TQDM_INTERVAL = float(os.environ.get("GSL_TQDM_INTERVAL", 0.1 if sys.stderr.isatty() else 10.0))  # short logs off-terminal; the job server sets 1 s

LAYOUTS = {
    # name: [(view name, yaw deg, pitch deg)]; side views at +-50 deg (PLAN §1.3)
    "5": [("c", 0, 0), ("r", 50, 0), ("l", -50, 0), ("u", 0, -50), ("d", 0, 50)],
    # quality-first variant: 7 views, the side ring at 55 deg plus two diagonals upwards
    "7": [("c", 0, 0), ("r", 55, 0), ("l", -55, 0), ("u", 0, -55), ("d", 0, 55),
          ("ur", 45, -40), ("ul", -45, -40)],
}


@dataclass
class ViewParams:
    layout: str = "5"
    size: int = 1600
    fov_deg: float = 90.0
    operator_cone_deg: float = 40.0  # static mask: rays within this angle of image-down; 0 = off
    max_off_axis_deg: float = 100.0  # beyond this the lens image is unreliable
    image_format: str = "png"
    sensor_to_track: SensorToTrack = field(default_factory=SensorToTrack)


def rot_yaw_pitch(yaw_deg: float, pitch_deg: float) -> np.ndarray:
    """Rotation lens_from_view for a view turned by yaw (about y) then pitch (about x)."""
    y, p = np.radians(yaw_deg), np.radians(pitch_deg)
    ry = np.array([[np.cos(y), 0, np.sin(y)], [0, 1, 0], [-np.sin(y), 0, np.cos(y)]])
    # positive pitch tilts the view axis towards +y (image down)
    rx = np.array([[1, 0, 0], [0, np.cos(p), np.sin(p)], [0, -np.sin(p), np.cos(p)]])
    return ry @ rx


def view_rays(size: int, fov_deg: float) -> tuple[np.ndarray, float]:
    f = (size / 2) / np.tan(np.radians(fov_deg) / 2)
    c = (size - 1) / 2
    u, v = np.meshgrid(np.arange(size, dtype=np.float64), np.arange(size, dtype=np.float64))
    rays = np.stack([(u - c) / f, (v - c) / f, np.ones_like(u)], axis=-1)
    return rays / np.linalg.norm(rays, axis=-1, keepdims=True), f


@dataclass
class ViewMap:
    lens: int
    name: str
    yaw: float
    pitch: float
    lens_from_view: np.ndarray
    map_x: np.ndarray
    map_y: np.ndarray
    mask: np.ndarray  # uint8, 255 = valid and not operator

    @property
    def folder(self) -> str:
        return f"lens{self.lens}_{self.name}"


def build_maps(lenses: list[MeiLens], p: ViewParams) -> tuple[list[ViewMap], float]:
    rays, f = view_rays(p.size, p.fov_deg)
    down = np.array([0.0, 1.0, 0.0])
    track = p.sensor_to_track.track_size
    maps = []
    for li, lens in enumerate(lenses):
        for name, yaw, pitch in LAYOUTS[p.layout]:
            r = rot_yaw_pitch(yaw, pitch)
            lr = rays @ r.T  # ray directions in the lens frame
            uv, ok = lens.project(lr)
            off_axis = np.degrees(np.arccos(np.clip(lr[..., 2], -1, 1)))
            inside = ok & (off_axis <= p.max_off_axis_deg)
            inside &= (uv[..., 0] >= 0) & (uv[..., 0] <= track - 1) & (uv[..., 1] >= 0) & (uv[..., 1] <= track - 1)
            keep = inside.copy()
            if p.operator_cone_deg > 0:
                keep &= np.degrees(np.arccos(np.clip(lr @ down, -1, 1))) > p.operator_cone_deg
            mx = np.where(inside, uv[..., 0], -1).astype(np.float32)
            my = np.where(inside, uv[..., 1], -1).astype(np.float32)
            maps.append(ViewMap(li, name, yaw, pitch, r, mx, my, (keep * 255).astype(np.uint8)))
    return maps, f


def make_views(frames_dir: Path, probe: dict, out_dir: Path, p: ViewParams) -> dict:
    frames = read_json(frames_dir / "frames.json")["frames"]
    lenses = [p.sensor_to_track.apply(l, i)
              for i, l in enumerate(parse_offset_string(best_offset_string(probe["offset_strings"])))]
    maps, f = build_maps(lenses, p)

    img_root, mask_root = out_dir / "images", out_dir / "masks"
    for m in maps:
        (img_root / m.folder).mkdir(parents=True, exist_ok=True)
        (mask_root / m.folder).mkdir(parents=True, exist_ok=True)

    # The mask is identical for every frame (static rig + operator cone); write one copy per image
    # because COLMAP looks masks up by image name. Encoded once, written as bytes.
    mask_png = {m.folder: cv2.imencode(".png", m.mask)[1].tobytes() for m in maps}
    for m in maps:
        cv2.imwrite(str(out_dir / f"mask_{m.folder}.png"), m.mask)

    def work(fr: dict) -> None:
        stem = Path(fr["file"]).stem
        src = [cv2.imread(str(frames_dir / f"lens{i}" / fr["file"]), cv2.IMREAD_COLOR) for i in (0, 1)]
        for m in maps:
            img = cv2.remap(src[m.lens], m.map_x, m.map_y, cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT)
            name = f"{stem}.{p.image_format}"
            params = [cv2.IMWRITE_PNG_COMPRESSION, 1] if p.image_format == "png" else [cv2.IMWRITE_JPEG_QUALITY, 97]
            cv2.imwrite(str(img_root / m.folder / name), img, params)
            (mask_root / m.folder / f"{name}.png").write_bytes(mask_png[m.folder])

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(tqdm(pool.map(work, frames), total=len(frames), desc="views", unit="frame", mininterval=TQDM_INTERVAL))

    c = (p.size - 1) / 2
    result = {
        "params": {**asdict(p), "sensor_to_track": asdict(p.sensor_to_track)},
        "camera": {"model": "PINHOLE", "width": p.size, "height": p.size, "params": [f, f, c + 0.5, c + 0.5]},
        "lenses": [asdict(l) for l in lenses],
        "views": [{"folder": m.folder, "lens": m.lens, "yaw": m.yaw, "pitch": m.pitch,
                   "lens_from_view": m.lens_from_view.tolist(),
                   "valid_fraction": float((m.mask > 0).mean())} for m in maps],
        "frames": [Path(fr["file"]).stem for fr in frames],
    }
    write_json(out_dir / "views.json", result)
    return result


def merge_views(view_dirs: dict[str, Path], out_dir: Path) -> dict:
    """Combine the views of several clips of one capture into one set for a joint SfM.

    Files are hard-linked (same volume, no extra disk space) and renamed
    <clip>_<frame>, so each 360 frame stays one COLMAP rig frame and names stay
    unique. All clips must share the view layout and camera.
    """
    metas = {cid: read_json(d / "views.json") for cid, d in view_dirs.items()}
    first = next(iter(metas.values()))
    for cid, m in metas.items():
        if m["camera"] != first["camera"] or [v["folder"] for v in m["views"]] != [v["folder"] for v in first["views"]]:
            raise SystemExit(f"clip {cid} has a different view layout or camera; regenerate its views first")
    frames = []
    for cid, d in view_dirs.items():
        m = metas[cid]
        for v in m["views"]:
            folder = v["folder"]
            for sub, suffix in (("images", ""), ("masks", ".png")):
                (out_dir / sub / folder).mkdir(parents=True, exist_ok=True)
                for stem in m["frames"]:
                    ext = m["params"]["image_format"]
                    src = d / sub / folder / f"{stem}.{ext}{suffix}"
                    dst = out_dir / sub / folder / f"{cid}_{stem}.{ext}{suffix}"
                    if not dst.exists():
                        os.link(src, dst)
            static = d / f"mask_{folder}.png"
            if static.exists() and not (out_dir / static.name).exists():
                os.link(static, out_dir / static.name)
        frames += [f"{cid}_{s}" for s in m["frames"]]
    merged = {**first, "frames": frames, "merged_from": {cid: str(d) for cid, d in view_dirs.items()}}
    write_json(out_dir / "views.json", merged)
    return merged
