"""Review content for the imported playroom scene: image cards, audio markers, ambient sounds.

    C:\\dev\\envs\\gs\\Scripts\\python.exe -m app.tools.demo_playroom <scene_dir> <ply> [--photo DSC05572.jpg]

Markers are placed where a horizontal ray from the start position hits the collision voxels,
pulled back towards the start. Card pictures are rendered from the splat itself. Overwrites the
scene's markers and sounds (blocks are kept).
"""
from __future__ import annotations

import argparse
import base64
import json
import shutil
from pathlib import Path

import cv2
import numpy as np

from app.stages.scene_export import _write_wav
from app.tools.render_scene import load_splat, render


def grid(scene_dir: Path):
    c = json.loads((scene_dir / "collision.json").read_text())
    bits = np.unpackbits(np.frombuffer(base64.b64decode(c["data"]), np.uint8), bitorder="little")
    nx, ny, nz = c["dims"]
    occ = bits[: nx * ny * nz].reshape(nz, ny, nx).astype(bool)
    return occ, np.array(c["origin"]), c["voxel"]


def cast(occ, origin, voxel, start, yaw_deg, z, max_d=8.0):
    d = np.array([np.cos(np.radians(yaw_deg)), np.sin(np.radians(yaw_deg)), 0.0])
    for t in np.arange(0.3, max_d, voxel / 2):
        p = np.array([start[0], start[1], z]) + t * d
        i, j, k = ((p - origin) / voxel).astype(int)
        if 0 <= i < occ.shape[2] and 0 <= j < occ.shape[1] and 0 <= k < occ.shape[0] and occ[k, j, i]:
            return p, t
    return np.array([start[0], start[1], z]) + max_d * d, max_d


def music_box(path: Path, rate=44100) -> None:
    """A gentle 16 s music-box loop (pentatonic notes with bell-like decay)."""
    notes = [523.3, 587.3, 659.3, 784.0, 880.0, 784.0, 659.3, 587.3, 523.3, 659.3, 784.0, 1046.5, 880.0, 784.0, 659.3, 587.3]
    n = 16 * rate
    x = np.zeros(n + rate)
    t = np.arange(int(1.6 * rate)) / rate
    for k, f in enumerate(notes):
        tone = (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t)) * np.exp(-t * 3.5) * 0.22
        i = k * rate
        x[i:i + len(tone)] += tone[: len(x) - i]
    x[:rate] += x[n:]  # wrap the tail so the loop is seamless
    _write_wav(path, x[:n], rate)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("scene_dir", type=Path)
    ap.add_argument("ply", type=Path)
    ap.add_argument("--photo", type=Path)
    a = ap.parse_args()
    sd = a.scene_dir
    assets = sd / "assets"
    assets.mkdir(exist_ok=True)
    scene = json.loads((sd / "scene.json").read_text(encoding="utf-8"))
    start = np.array(scene["start"]["position"], float)
    eye = start + np.array([0, 0, 1.5])
    occ, origin, voxel = grid(sd)
    splat, m = load_splat(a.ply, scene["splat"].get("transform"))

    def place(yaw, z=1.1, back=0.35, max_d=2.5):
        hit, dist = cast(occ, origin, voxel, start, yaw, z, max_d=max_d)
        d = np.array([np.cos(np.radians(yaw)), np.sin(np.radians(yaw)), 0.0])
        return hit - back * d, hit, dist

    def shots(name, target, yaw):
        """Three pictures of a target from safe spots near the start: wide, then two zoom levels."""
        out = []
        d = np.array([np.cos(np.radians(yaw)), np.sin(np.radians(yaw)), 0.0])
        side = np.array([-d[1], d[0], 0.0])
        for k, (cam, fov) in enumerate(((eye, 75), (eye + 0.3 * side, 45), (eye - 0.3 * side - np.array([0, 0, 0.3]), 28))):
            img = render(splat, m, cam, target, (1280, 720), fov)
            rel = f"assets/{name}_{k + 1}.jpg"
            cv2.imwrite(str(sd / rel), img, [cv2.IMWRITE_JPEG_QUALITY, 88])
            out.append(rel)
        return out

    markers, sounds = [], []
    pos, hit, _ = place(5, z=0.9)
    markers.append({"id": "play-corner", "kind": "info", "position": pos.tolist(), "radius": 1.6,
                    "title": "The play corner",
                    "text": "A small table with two chairs, a red bean bag and a foam alphabet mat.\n\n"
                            "This card shows how an info point works: pictures on top (use the arrows, the dots or "
                            "the thumbnails, or open them full screen), a title and scrollable text below.\n\n"
                            "The pictures were rendered from the splat itself, so they show exactly what is in the scene.",
                    "images": shots("play_corner", hit + np.array([0, 0, -0.4]), 5), "audio": "chime.wav", "spatial": True})
    pos, hit, _ = place(55, z=1.2)
    markers.append({"id": "reading-shelf", "kind": "info", "position": pos.tolist(), "radius": 1.6,
                    "title": "Reading shelf",
                    "text": "Picture books on a wall shelf next to the desk.\n\nIn edit mode (Tab), select this marker "
                            "and use 'Upload images / audio from this PC' to replace these pictures with your own.",
                    "images": shots("reading_shelf", hit, 55)})
    pos, hit, _ = place(270, z=1.3)
    markers.append({"id": "staircase", "kind": "audio", "position": pos.tolist(), "radius": 1.8,
                    "title": "Staircase (voice note)", "text": "", "audio": "assets/staircase.wav"})
    pos, hit, _ = place(180, z=1.2)
    photo = []
    if a.photo and a.photo.exists():
        shutil.copy(a.photo, assets / a.photo.name)
        photo = [f"assets/{a.photo.name}"]
    markers.append({"id": "about", "kind": "info", "position": pos.tolist(), "radius": 1.6,
                    "title": "About this scene",
                    "text": "Deep Blending 'playroom', trained by the authors of 3D Gaussian Splatting (Inria, 2023); "
                            "1.9 million Gaussians, shown in the browser with Spark (three.js).\n\n"
                            "Licence: research / non-commercial. Fine for this personal test; do not publish it.\n\n"
                            "Scale is approximate: the ceiling was set to 2.6 m.",
                    "images": photo + shots("pram", hit, 180)[:2]})
    markers.append({"id": "welcome", "kind": "audio", "position": (eye + np.array([0.6, 0.6, -0.2])).tolist(), "radius": 1.2,
                    "title": "Welcome (voice)", "text": "", "audio": "assets/welcome.wav"})

    music_box(assets / "music_box.wav")
    corner = place(5, z=0.6)[1]
    sounds.append({"id": "music-box", "position": corner.tolist(), "url": "assets/music_box.wav", "volume": 0.5, "refDistance": 1.2})
    sounds.append({"id": "room-tone", "position": eye.tolist(), "url": "ambient_room.wav", "volume": 0.25, "refDistance": 3.0})
    scene["markers"], scene["sounds"] = markers, sounds
    scene["start"]["yawDeg"] = 20.0
    (sd / "scene.json").write_text(json.dumps(scene, indent=2), encoding="utf-8")
    for mk in markers:
        print(f"{mk['kind']:<5} {mk['title']:<26} at {np.round(mk['position'], 2).tolist()}  images {len(mk.get('images', []))}")


if __name__ == "__main__":
    main()
