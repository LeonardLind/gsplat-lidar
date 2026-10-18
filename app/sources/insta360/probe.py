"""Probe an Insta360 .insv clip: streams (ffprobe) plus model and calibration strings from the trailer.

The .insv is an MP4 with two square HEVC fisheye tracks (one per lens) and a
binary trailer after the media data. Only the human-readable parts of the
trailer are read here (camera model, firmware, the factory "offset"
calibration string). The binary IMU and exposure records come later.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

TRAILER_SCAN_BYTES = 8 * 1024 * 1024
# Factory calibration: "<lens count>_<v>_<v>_..." with at least 12 numeric fields.
OFFSET_RE = re.compile(rb"(?<![\d_.])2(?:_-?\d+(?:\.\d+)?){12,}")
MODEL_RE = re.compile(rb"Insta360 [A-Za-z0-9 ]{2,20}")
FIRMWARE_RE = re.compile(rb"v\d+\.\d+\.\d+(?:\.\d+)?(?:_[A-Za-z0-9]+)*")


def ffprobe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout
    return json.loads(out)


def read_trailer_strings(path: Path) -> dict:
    size = path.stat().st_size
    with open(path, "rb") as f:
        f.seek(max(0, size - TRAILER_SCAN_BYTES))
        tail = f.read()
    model = MODEL_RE.search(tail)
    offsets = sorted({m.group().decode() for m in OFFSET_RE.finditer(tail)}, key=len, reverse=True)
    firmware = sorted({m.group().decode() for m in FIRMWARE_RE.finditer(tail)})
    return {
        "model": model.group().decode().strip() if model else None,
        "offset_strings": offsets,
        "firmware_candidates": firmware[:10],
    }


def probe_clip(path: Path) -> dict:
    info = ffprobe(path)
    video = [s for s in info["streams"] if s["codec_type"] == "video"]
    audio = [s for s in info["streams"] if s["codec_type"] == "audio"]
    num, den = (int(x) for x in video[0]["avg_frame_rate"].split("/"))
    report = {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "duration_s": float(info["format"]["duration"]),
        "creation_time": info["format"].get("tags", {}).get("creation_time"),
        "fps": num / den,
        "fps_rational": [num, den],
        "lenses": [
            {
                "stream_index": s["index"],
                "codec": s["codec_name"],
                "width": s["width"],
                "height": s["height"],
                "nb_frames": int(s.get("nb_frames", 0)),
                "pix_fmt": s.get("pix_fmt"),
                "color_transfer": s.get("color_transfer"),
            }
            for s in video
        ],
        "has_audio": bool(audio),
        **read_trailer_strings(path),
    }
    problems = []
    if len(video) != 2:
        problems.append(f"expected 2 fisheye tracks, found {len(video)} (stitched export?)")
    if any(s["width"] != s["height"] for s in video):
        problems.append("lens tracks are not square")
    if len({int(s.get('nb_frames', 0)) for s in video}) > 1:
        problems.append("lens tracks have different frame counts")
    if not report["offset_strings"]:
        problems.append("no factory calibration string found in trailer")
    report["problems"] = problems
    return report
