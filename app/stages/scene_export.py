"""Viewer scene from a trained splat: collision voxels, floor, start pose and scene.json.

Splat-only mode (no LiDAR, PLAN §1.10 fallback): collision comes from the splat itself, but only
as coarse occupancy voxels, never per-splat:
  * a voxel is solid when it holds at least ``min_count`` opaque, compact Gaussians;
  * the floor is the densest layer of Gaussians below the camera path;
  * everything the camera passed through is free space, so a cylinder around the camera path
    (above step height) is cleared. That removes floaters where people walk.
The scale is approximate without LiDAR, so player sizes derive from the camera height above
the floor instead of fixed metres.
"""
from __future__ import annotations

import base64
import json
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pycolmap

from app.core.project import write_json


@dataclass
class CollisionParams:
    voxel_frac: float = 0.05  # voxel edge as a fraction of the camera height above the floor
    min_opacity: float = 0.4
    max_scale_frac: float = 0.15  # ignore Gaussians larger than this (fraction of camera height)
    min_count: int = 3
    margin_frac: float = 1.5  # grid extends this far (x camera height) around the camera path
    carve_radius_frac: float = 0.12
    voxel_m: float | None = None  # fixed voxel edge in metres (metric scenes); overrides voxel_frac


LIDAR_COLLISION = CollisionParams(min_opacity=0.0, max_scale_frac=1e9, min_count=2, voxel_m=0.08, carve_radius_frac=0.15)


def lidar_as_ply(xyz: np.ndarray) -> dict[str, np.ndarray]:
    """LiDAR points in the shape build_collision expects from a splat PLY: opaque, 3 cm Gaussians."""
    n = len(xyz)
    return {"x": xyz[:, 0], "y": xyz[:, 1], "z": xyz[:, 2], "opacity": np.full(n, 10.0, np.float32),
            **{f"scale_{i}": np.full(n, np.log(0.03), np.float32) for i in range(3)}}


def write_lidar_layer(out_dir: Path, xyz: np.ndarray, rgb: np.ndarray, intensity: np.ndarray) -> dict:
    """lidar.bin for the viewer's LiDAR layer (web/viewer/src/lidar.ts): little-endian uint32 count, then
    float32 xyz (count x 3), uint8 rgb (count x 3), uint8 intensity (count; 1st-99th percentile stretched)."""
    lo, hi = np.percentile(intensity, [1, 99])
    inten = np.clip((intensity.astype(np.float32) - lo) / max(hi - lo, 1) * 255, 0, 255).astype(np.uint8)
    n = len(xyz)
    with open(out_dir / "lidar.bin", "wb") as f:
        f.write(np.uint32(n).tobytes())
        f.write(np.ascontiguousarray(xyz, dtype="<f4").tobytes())
        f.write(np.ascontiguousarray(rgb, dtype=np.uint8).tobytes())
        f.write(inten.tobytes())
    return {"url": "lidar.bin", "count": int(n), "bounds": [xyz.min(axis=0).round(3).tolist(), xyz.max(axis=0).round(3).tolist()]}


def read_ply(path: Path) -> dict[str, np.ndarray]:
    """Binary little-endian 3DGS PLY (gsplat export) -> columns."""
    with open(path, "rb") as f:
        header, props, n = [], [], 0
        while True:
            line = f.readline().decode("ascii").strip()
            header.append(line)
            if line.startswith("element vertex"):
                n = int(line.split()[-1])
            elif line.startswith("property"):
                _, typ, name = line.split()
                props.append((name, {"float": "<f4", "double": "<f8", "uchar": "u1", "int": "<i4"}[typ]))
            elif line == "end_header":
                break
        if "format binary_little_endian 1.0" not in header:
            raise ValueError("only binary little-endian PLY is supported")
        data = np.frombuffer(f.read(), dtype=np.dtype(props), count=n)
    return {name: np.asarray(data[name]) for name, _ in props}


def camera_path(model_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    """Centres and forward directions of the lens0_c views, in frame order."""
    r = pycolmap.Reconstruction(str(model_dir))
    rows = []
    for i in r.reg_image_ids():
        im = r.images[i]
        if im.name.startswith("lens0_c/"):
            rot = im.cam_from_world().rotation.matrix()
            rows.append((im.name, im.projection_center(), rot.T @ np.array([0.0, 0.0, 1.0])))
    rows.sort(key=lambda x: x[0])
    return np.array([x[1] for x in rows]), np.array([x[2] for x in rows])


def detect_floor(z: np.ndarray, cam_z: np.ndarray) -> float:
    """Densest horizontal layer of Gaussians below (almost) all camera positions."""
    below = z[z < np.percentile(cam_z, 5)]
    if len(below) < 100:
        return float(np.percentile(z, 2))
    lo = np.percentile(below, 1)
    hist, edges = np.histogram(below, bins=200, range=(lo, below.max()))
    k = int(np.argmax(hist))
    return float(0.5 * (edges[k] + edges[k + 1]))


def build_collision(ply: dict[str, np.ndarray], cams: np.ndarray, p: CollisionParams) -> tuple[dict, dict]:
    xyz = np.stack([ply["x"], ply["y"], ply["z"]], axis=1)
    opacity = 1 / (1 + np.exp(-ply["opacity"]))
    scale = np.exp(np.stack([ply["scale_0"], ply["scale_1"], ply["scale_2"]], axis=1)).max(axis=1)
    floor_z = detect_floor(xyz[:, 2], cams[:, 2])
    cam_h = float(np.median(cams[:, 2] - floor_z))
    voxel = p.voxel_m or p.voxel_frac * cam_h

    lo = cams.min(axis=0) - p.margin_frac * cam_h
    hi = cams.max(axis=0) + p.margin_frac * cam_h
    lo[2] = floor_z - 2 * voxel
    hi[2] = cams[:, 2].max() + 0.8 * cam_h  # up to roughly the ceiling
    dims = np.ceil((hi - lo) / voxel).astype(int)

    keep = (opacity > p.min_opacity) & (scale < p.max_scale_frac * cam_h)
    keep &= np.all((xyz >= lo) & (xyz < hi), axis=1)
    ijk = ((xyz[keep] - lo) / voxel).astype(int)
    flat = ijk[:, 0] + dims[0] * (ijk[:, 1] + dims[1] * ijk[:, 2])
    counts = np.bincount(flat, minlength=int(np.prod(dims)))
    occ = (counts >= p.min_count).reshape(dims[2], dims[1], dims[0])  # [z, y, x]

    # Free space: a vertical cylinder around every camera position, from step height up.
    step = 0.2 * cam_h
    rad = p.carve_radius_frac * cam_h
    xs = lo[0] + (np.arange(dims[0]) + 0.5) * voxel
    ys = lo[1] + (np.arange(dims[1]) + 0.5) * voxel
    zs = lo[2] + (np.arange(dims[2]) + 0.5) * voxel
    carved_before = int(occ.sum())
    dense = np.linspace(0, 1, 4)[:-1]  # also carve between consecutive positions
    path = [cams[0]] + [a + t * (b - a) for a, b in zip(cams[:-1], cams[1:]) for t in dense[1:]] + list(cams[1:])
    for c in path:
        ix = np.nonzero(np.abs(xs - c[0]) <= rad)[0]
        iy = np.nonzero(np.abs(ys - c[1]) <= rad)[0]
        iz = np.nonzero((zs > floor_z + step) & (zs < c[2] + 0.15 * cam_h))[0]
        if len(ix) and len(iy) and len(iz):
            sub = (xs[ix][None, :] - c[0]) ** 2 + (ys[iy][:, None] - c[1]) ** 2 <= rad ** 2
            occ[np.ix_(iz, iy, ix)] &= ~sub[None, :, :]
    # Pack x fastest, then y, then z, LSB-first bits (matches web/viewer/src/collision.ts).
    bits = np.packbits(occ.reshape(-1), bitorder="little")
    collision = {"origin": lo.tolist(), "voxel": voxel, "dims": dims.tolist(), "floorZ": floor_z,
                 "encoding": "bitset-base64", "data": base64.b64encode(bits.tobytes()).decode("ascii")}
    info = {"floor_z": floor_z, "camera_height": cam_h, "voxel": voxel, "dims": dims.tolist(),
            "occupied": int(occ.sum()), "carved": carved_before - int(occ.sum()),
            "gaussians_used": int(keep.sum()), "gaussians_total": int(len(xyz))}
    return collision, info


def _write_wav(path: Path, samples: np.ndarray, rate: int = 44100) -> None:
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def placeholder_audio(out_dir: Path) -> None:
    """Synthetic sounds so the viewer's audio works before real recordings exist."""
    rate = 44100
    rng = np.random.default_rng(0)
    if not (out_dir / "ambient_room.wav").exists():
        # 12 s of soft brown noise with a faint 100 Hz hum; the ends cross-fade so it loops cleanly.
        n = 12 * rate
        brown = np.cumsum(rng.normal(size=n + rate))
        brown -= np.convolve(brown, np.ones(2000) / 2000, mode="same")
        brown /= np.abs(brown).max()
        t = np.arange(n + rate) / rate
        x = 0.25 * brown + 0.04 * np.sin(2 * np.pi * 100 * t)
        fade = np.linspace(0, 1, rate)
        x[:rate] = x[:rate] * fade + x[n:] * (1 - fade)
        _write_wav(out_dir / "ambient_room.wav", 0.6 * x[:n], rate)
    if not (out_dir / "narration.wav").exists():
        # 20 s placeholder "voice": a slow, soft arpeggio. Replace with a real recording in edit mode.
        notes = [261.6, 329.6, 392.0, 523.3, 392.0, 329.6]
        x = np.zeros(20 * rate)
        for k in range(40):
            f = notes[k % len(notes)]
            t = np.arange(int(1.2 * rate)) / rate
            tone = 0.18 * np.sin(2 * np.pi * f * t) * np.exp(-t * 2.5)
            i = int(k * 0.5 * rate)
            x[i:i + len(tone)] += tone[: max(0, len(x) - i)]
        _write_wav(out_dir / "narration.wav", x, rate)
    if not (out_dir / "chime.wav").exists():
        t = np.arange(int(2.5 * rate)) / rate
        x = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * d) for f, a, d in ((880, 0.5, 2.2), (1320, 0.3, 3.0), (1760, 0.15, 4.0)))
        _write_wav(out_dir / "chime.wav", 0.7 * x, rate)


def demo_images(views_dir: Path | None, out_dir: Path, n: int = 3) -> list[str]:
    """A few views from the capture as card images (assets/demo_<k>.jpg)."""
    if views_dir is None or not (views_dir / "views.json").exists():
        return []
    import cv2

    meta = json.loads((views_dir / "views.json").read_text(encoding="utf-8"))
    ext = meta["params"]["image_format"]
    frames = meta["frames"]
    (out_dir / "assets").mkdir(exist_ok=True)
    paths = []
    for k in range(n):
        stem = frames[int((k + 0.5) / n * (len(frames) - 1))]
        img = cv2.imread(str(views_dir / "images" / "lens0_c" / f"{stem}.{ext}"))
        if img is None:
            continue
        h, w = img.shape[:2]
        crop = img[int(h * 0.2): int(h * 0.76), :]  # 16:9-ish band around the horizon
        crop = cv2.resize(crop, (1280, int(1280 * crop.shape[0] / w)), interpolation=cv2.INTER_AREA)
        rel = f"assets/demo_{k + 1}.jpg"
        cv2.imwrite(str(out_dir / rel), crop, [cv2.IMWRITE_JPEG_QUALITY, 88])
        paths.append(rel)
    return paths


def demo_content(cams: np.ndarray, floor_z: float, cam_h: float, images: list[str]) -> tuple[list, list]:
    """Three markers along the camera path (image card, text card, audio) and one ambient sound."""
    eye = floor_z + 0.9 * cam_h
    picks = [cams[int(f * (len(cams) - 1))] for f in (0.2, 0.5, 0.8)]
    specs = [
        {"kind": "info", "title": "The office, as a Gaussian splat",
         "text": "Captured on 16 October 2026 with an Insta360 X4 on a stick, in two passes at different heights.\n\n"
                 "Every frame was cut into ten pinhole views, the camera path was solved with COLMAP "
                 "(ALIKED + LightGlue features), and gsplat trained the splat.\n\n"
                 "These pictures are frames from the capture.", "images": images},
        {"kind": "info", "title": "Info point",
         "text": "Markers like this one are placed in edit mode: press Tab, choose tool 2 and click a surface. "
                 "Add a title, text, images and a sound in the side panel, then Ctrl+S saves scene.json."},
        {"kind": "audio", "title": "Audio point (placeholder narration)", "text": "", "audio": "narration.wav"},
    ]
    markers = []
    for k, (c, spec) in enumerate(zip(picks, specs)):
        markers.append({"id": f"demo-{k + 1}", "position": [float(c[0]), float(c[1]), float(eye)],
                        "radius": round(0.9 * cam_h, 2), **spec})
    mid = cams[len(cams) // 2]
    sounds = [{"id": "demo-ambient", "position": [float(mid[0]), float(mid[1]), float(eye)],
               "url": "ambient_room.wav", "volume": 0.35, "refDistance": round(1.5 * cam_h, 2)}]
    return markers, sounds


def write_scene(out_dir: Path, name: str, splat_file: str, model_dir: Path, ply_path: Path,
                scale: str, views_dir: Path | None = None, p: CollisionParams = CollisionParams(),
                source_ply: Path | None = None, lidar: Path | None = None) -> dict:
    """scene.json + collision.json for a trained splat. ply_path is what collision is built from (a cleaned
    copy after cleanup); source_ply is the untouched master (defaults to ply_path).

    lidar: the LiDAR npz (app/lidar/downsample.py) of a scene trained in the LiDAR frame (app/lidar/merge.py):
    collision then comes from the LiDAR points (true geometry, no floaters), the viewer gets a LiDAR layer
    (lidar.bin) and the player uses real sizes."""
    cams, fwd = camera_path(model_dir)
    lidar_entry = None
    if lidar is not None:
        from app.lidar.register import load_lidar

        xyz, *_ = load_lidar(lidar)  # the merge frame: floor at z = 0
        d = np.load(lidar)
        lidar_entry = write_lidar_layer(out_dir, xyz.astype(np.float32), d["rgb"], d["intensity"])
        collision, info = build_collision(lidar_as_ply(xyz), cams, LIDAR_COLLISION if p == CollisionParams() else p)
    else:
        collision, info = build_collision(read_ply(ply_path), cams, p)
    write_json(out_dir / "collision.json", collision)
    h = info["camera_height"]
    start = cams[0]
    yaw = float(np.degrees(np.arctan2(fwd[0][1], fwd[0][0])))
    scene_file = out_dir / "scene.json"
    old = json.loads(scene_file.read_text(encoding="utf-8")) if scene_file.exists() else {}
    placeholder_audio(out_dir)
    if not old.get("markers") and not old.get("sounds"):
        old["markers"], old["sounds"] = demo_content(cams, info["floor_z"], h, demo_images(views_dir, out_dir))
    scene = {
        "schema_version": 1,
        "name": name,
        "frame": {"up": "+Z", "units": "m", "scale": scale,
                  "note": "approximate scale: median camera step set to 0.3 m; measure one distance to fix"
                  if scale == "approximate" else ""},
        # source: the master PLY this export (and the cleanup tool) works from; sparse: for rebuilding collision.
        "splat": {"url": splat_file, "source": str(source_ply or ply_path), "sparse": str(model_dir)},
        "collision": {"url": "collision.json"},
        "start": {"position": [float(start[0]), float(start[1]), info["floor_z"]], "yawDeg": yaw},
        # Player sizes: real ones in a metric scene, else relative to the camera height above the floor.
        "player": {"eyeHeight": 1.6, "radius": 0.25, "stepHeight": 0.3} if scale == "metric"
        else {"eyeHeight": round(h, 3), "radius": round(0.15 * h, 3), "stepHeight": round(0.2 * h, 3)},
        "markers": old.get("markers", []),  # keep what was placed in edit mode
        "blocks": old.get("blocks", []),
        "sounds": old.get("sounds", []),
    }
    if lidar_entry:
        scene["lidar"] = lidar_entry
    write_json(scene_file, scene)
    write_json(out_dir / "collision_info.json", info)
    return info
