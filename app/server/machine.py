"""This PC: GPU info, measured stage speeds (history), the GPU benchmark, and time/size estimates.

Every finished job step records how fast it ran (frames decoded per second, images per second for
each COLMAP phase, seconds per training step at a Gaussian count). Estimates use the median of the
last few measurements on this PC, the benchmark for training before any real run, and otherwise
the defaults below (measured on the home PC, RTX 3080, with the 069 office clip).
"""
from __future__ import annotations

import functools
import math
import socket
import statistics
import subprocess
from pathlib import Path

from app.core.project import PROJECTS_DIR, read_json, write_json

SERVER_DIR = PROJECTS_DIR / "_server"
HOST = socket.gethostname()
HISTORY = SERVER_DIR / f"machine-{HOST}.json"

# Defaults until this PC has its own measurements.
DEFAULT_RATES = {
    "frames": 40.0,          # decoded fisheye pairs per second (5.7K dual HEVC + sharpness)
    "views": 2.5,            # 360 frames per second turned into 10 pinhole views
    "sfm_extract": 0.82,     # images per second, ALIKED features (069: 1710 images in 35 min)
    "sfm_match": 0.56,       # images per second, LightGlue sequential matching (069: 51 min)
    "sfm_map": 12.0,         # images per second, global mapper (069: ~2.5 min)
    "export_per_mgs": 70.0,  # seconds per million Gaussians: SOG + collision
    "people": 6.0,           # views per second through Mask R-CNN at 1600 px (guess until measured)
}
# Training: seconds per step at N Gaussians on 1600 px views (069: 31-35 steps/s at 1 M).
DEFAULT_TRAIN_S_PER_STEP_1M = 0.030
TRAIN_OVERHEAD_S = 0.004
EVAL_SAVE_S = 40.0           # each evaluation + checkpoint + PLY save
BYTES_PER_FRAME = 2 * 7.7e6 + 10 * 2.8e6   # fisheye pair + 10 views (PNG), measured on 069
BYTES_PER_GAUSSIAN_PLY = 236               # SH degree 3


@functools.lru_cache(maxsize=1)
def gpu_info() -> dict:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5).stdout.strip().splitlines()[0]
        name, mem = [s.strip() for s in out.split(",")]
        return {"name": name, "vram_mb": int(mem)}
    except Exception:  # noqa: BLE001
        return {"name": "unknown", "vram_mb": 0}


def load() -> dict:
    return read_json(HISTORY) if HISTORY.exists() else {"host": HOST, "rates": {}, "train": [], "bench": None}


def record_rate(key: str, value: float) -> None:
    if not (value > 0 and math.isfinite(value)):
        return
    h = load()
    h.setdefault("rates", {}).setdefault(key, []).append(round(value, 4))
    h["rates"][key] = h["rates"][key][-8:]
    write_json(HISTORY, h)


def record_train(gaussians: int, s_per_step: float, size: int = 1600) -> None:
    if not (s_per_step > 0 and gaussians > 0):
        return
    h = load()
    h.setdefault("train", []).append({"gaussians": int(gaussians), "s_per_step": round(s_per_step, 5), "size": size})
    h["train"] = h["train"][-12:]
    write_json(HISTORY, h)


def save_bench(result: dict) -> None:
    h = load()
    h["bench"] = result
    write_json(HISTORY, h)


def rate(key: str) -> tuple[float, str]:
    vals = load().get("rates", {}).get(key)
    if vals:
        return statistics.median(vals), "measured"
    return DEFAULT_RATES[key], "default"


def train_s_per_step(gaussians: float) -> tuple[float, str]:
    """Seconds per training step at this Gaussian count. The curve's shape comes from the benchmark
    (or a default curve); real runs on this PC scale it to what training actually takes."""
    h = load()
    bench = h.get("bench")
    pts = sorted((bench or {}).get("points") or [], key=lambda p: p["gaussians"])

    def base(n: float) -> float:
        if len(pts) < 2:
            return DEFAULT_TRAIN_S_PER_STEP_1M * (n / 1e6) ** 0.85 + TRAIN_OVERHEAD_S
        xs = [math.log(p["gaussians"]) for p in pts]
        ys = [math.log(p["s_per_step"]) for p in pts]
        x = math.log(max(n, 1))
        i = 1 if x <= xs[1] else len(xs) - 1 if x >= xs[-2] else next(k for k in range(1, len(xs)) if xs[k] >= x)
        y = ys[i - 1] + (x - xs[i - 1]) * (ys[i] - ys[i - 1]) / (xs[i] - xs[i - 1])  # piecewise log-log
        return math.exp(y) + TRAIN_OVERHEAD_S

    runs = h.get("train") or []
    if runs:
        factor = statistics.median(r["s_per_step"] / base(r["gaussians"]) for r in runs)
        return base(gaussians) * factor, "measured"
    return base(gaussians), "benchmark" if len(pts) >= 2 else "default"


def recommended_steps(images: int) -> int:
    """About 15 looks at every training image, at least gsplat's standard 30k, rounded to 5k."""
    return int(min(200_000, max(30_000, math.ceil(15 * images / 5000) * 5000)))


def estimate(clips: list[dict], fps: float, steps: int | None, cap: int, views_per_frame: int = 10,
             init_points: int = 100_000, people: bool = True) -> dict:
    """clips: [{"duration": trimmed seconds, "video_fps": ...}]. Returns counts, sizes and per-stage times."""
    decoded = sum(c["duration"] * c["video_fps"] for c in clips)
    frames = int(sum(math.floor(c["duration"] * fps) for c in clips))
    images = frames * views_per_frame
    steps = steps or recommended_steps(images)

    r_frames, s_frames = rate("frames")
    r_views, s_views = rate("views")
    r_ext, s_ext = rate("sfm_extract")
    r_match, s_match = rate("sfm_match")
    r_map, s_map = rate("sfm_map")
    r_exp, s_exp = rate("export_per_mgs")

    # MCMC grows the Gaussian count ~5 % every 100 steps from the SfM points until the cap.
    grow_steps = min(steps, 100 * math.log(max(cap / init_points, 1)) / math.log(1.05)) if cap > init_points else 0
    train_s, src = 0.0, "default"
    n_seg = 20
    for k in range(n_seg):  # integrate s/step over the growth phase
        st = grow_steps * (k + 0.5) / n_seg
        n = min(cap, init_points * 1.05 ** (st / 100))
        s, src = train_s_per_step(n)
        train_s += s * grow_steps / n_seg
    s_cap, src = train_s_per_step(cap)
    train_s += s_cap * (steps - grow_steps) + 3 * EVAL_SAVE_S

    stages = [
        {"stage": "frames", "label": "Pick sharp frames", "seconds": decoded / r_frames, "source": s_frames},
        {"stage": "views", "label": "Make pinhole views", "seconds": frames / r_views, "source": s_views},
        *([{"stage": "people", "label": "Find people (operator, passers-by)", "seconds": images / rate("people")[0] + 30,
            "source": rate("people")[1]}] if people else []),
        {"stage": "sfm", "label": "Camera solve (SfM)",
         "seconds": images / r_ext + images / r_match + images / r_map * (max(images, 1) / 1700) ** 0.3,
         "source": "measured" if "measured" in (s_ext, s_match, s_map) else "default"},
        {"stage": "train", "label": "Train the splat", "seconds": train_s, "source": src,
         "detail": f"{steps:,} steps, up to {cap / 1e6:g} M Gaussians, ~{s_cap * 1000:.0f} ms/step at the cap"},
        {"stage": "export", "label": "Export for the viewer", "seconds": r_exp * cap / 1e6, "source": s_exp},
    ]
    return {
        "decoded_pairs": int(decoded),
        "frames": frames,
        "images": images,
        "steps": steps,
        "recommended_steps": recommended_steps(images),
        "looks_per_image": round(steps / max(images, 1), 1),
        "disk_bytes": frames * BYTES_PER_FRAME + cap * BYTES_PER_GAUSSIAN_PLY * 3,  # 3 PLY snapshots
        "stages": stages,
        "total_seconds": sum(s["seconds"] for s in stages),
        "host": HOST,
        "gpu": gpu_info(),
        "has_bench": bool(load().get("bench")),
        "train_runs_measured": len(load().get("train") or []),
    }
