"""Select sharp frame pairs from the two raw fisheye tracks of an .insv clip.

One pass over the video:
  * decode both lens tracks and pair the frames by timestamp;
  * score each lens with the variance of the Laplacian (a sharpness measure) on a
    downscaled grey copy, inside the image circle;
  * split time into windows of ``window_s`` and keep the pair with the best
    *weaker* lens score (both lenses must be sharp);
  * skip a window when the scene barely changed since the last kept pair (the
    operator standing still);
  * write the kept pairs losslessly (PNG) as lens0/<idx>.png and lens1/<idx>.png.

Frames are chosen by time here, not distance: splat-only projects have no
trajectory yet. With the BLK2GO, Run 1 can switch to distance along the
trajectory (PLAN §1.3).
"""
from __future__ import annotations

import csv
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import av
import cv2
import numpy as np
from tqdm import tqdm

from app.core.project import write_json

TQDM_INTERVAL = float(os.environ.get("GSL_TQDM_INTERVAL", 0.1 if sys.stderr.isatty() else 10.0))  # short logs off-terminal; the job server sets 1 s
SCORE_SIZE = 720  # sharpness is measured at this resolution
CHANGE_SIZE = 160  # still-detection resolution


@dataclass
class FrameParams:
    window_s: float = 0.4
    start_s: float = 0.0
    end_s: float | None = None
    min_change: float = 2.0  # mean abs grey difference (0-255) vs the last kept pair; 0 disables
    image_format: str = "png"


def _circle_mask(size: int, radius_frac: float) -> np.ndarray:
    yy, xx = np.mgrid[:size, :size]
    c = (size - 1) / 2
    return (xx - c) ** 2 + (yy - c) ** 2 <= (radius_frac * size) ** 2


SCORE_MASK = _circle_mask(SCORE_SIZE, 0.45)


def sharpness(gray: np.ndarray) -> float:
    lap = cv2.Laplacian(gray, cv2.CV_32F, ksize=3)
    return float(lap[SCORE_MASK].var())


@dataclass
class Candidate:
    idx: int
    t: float
    score: float
    s0: float
    s1: float
    small: np.ndarray  # stacked CHANGE_SIZE grey images of both lenses
    rgb0: np.ndarray
    rgb1: np.ndarray


def _write(path: Path, rgb: np.ndarray, fmt: str) -> None:
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    if fmt == "png":
        ok = cv2.imwrite(str(path), bgr, [cv2.IMWRITE_PNG_COMPRESSION, 1])
    else:
        ok = cv2.imwrite(str(path), bgr, [cv2.IMWRITE_JPEG_QUALITY, 97, cv2.IMWRITE_JPEG_SAMPLING_FACTOR, cv2.IMWRITE_JPEG_SAMPLING_FACTOR_444])
    if not ok:
        raise IOError(f"could not write {path}")


def select_frames(insv: Path, out_dir: Path, fps: float, params: FrameParams) -> dict:
    lens_dirs = [out_dir / "lens0", out_dir / "lens1"]
    for d in lens_dirs:
        d.mkdir(parents=True, exist_ok=True)

    container = av.open(str(insv))
    streams = [s for s in container.streams.video][:2]
    for s in streams:
        s.thread_type = "AUTO"
    tb = streams[0].time_base
    total = streams[0].frames or None
    window = max(1, round(params.window_s * fps))
    start_idx = round(params.start_s * fps)
    end_idx = round(params.end_s * fps) if params.end_s is not None else None
    if start_idx > 0:
        container.seek(int(params.start_s / tb), stream=streams[0], backward=True)

    pending: dict[int, dict[int, av.VideoFrame]] = {}
    scores_rows: list[tuple] = []
    kept: list[dict] = []
    best: Candidate | None = None
    current_window: int | None = None
    last_small: np.ndarray | None = None
    skipped_still = 0
    pool = ThreadPoolExecutor(max_workers=4)
    futures = []

    def flush(cand: Candidate) -> None:
        nonlocal last_small, skipped_still
        if params.min_change > 0 and last_small is not None:
            change = float(np.abs(cand.small.astype(np.int16) - last_small).mean())
            if change < params.min_change:
                skipped_still += 1
                return
        last_small = cand.small.astype(np.int16)
        name = f"{cand.idx:06d}.{params.image_format}"
        for lens, rgb in enumerate((cand.rgb0, cand.rgb1)):
            futures.append(pool.submit(_write, lens_dirs[lens] / name, rgb, params.image_format))
        kept.append({"idx": cand.idx, "t": round(cand.t, 6), "sharp0": round(cand.s0, 2),
                     "sharp1": round(cand.s1, 2), "file": name})

    bar = tqdm(total=(end_idx or total or 0) - start_idx or None, unit="frame", desc="decode", mininterval=TQDM_INTERVAL)
    stream_pos = {s.index: i for i, s in enumerate(streams)}
    for packet in container.demux(streams):
        for frame in packet.decode():
            if frame.pts is None:
                continue
            idx = round(float(Fraction(frame.pts) * tb) * fps)
            if idx < start_idx:
                continue
            pending.setdefault(idx, {})[stream_pos[packet.stream.index]] = frame
            if len(pending[idx]) < 2:
                continue
            pair = pending.pop(idx)
            # A lens track can run a frame ahead; drop pairs that will never complete.
            for stale in [k for k in pending if k < idx - 4]:
                del pending[stale]
            if end_idx is not None and idx >= end_idx:
                break
            bar.update(1)

            smalls, s = [], []
            for lens in (0, 1):
                g = pair[lens].reformat(width=SCORE_SIZE, height=SCORE_SIZE, format="gray").to_ndarray()
                s.append(sharpness(g))
                smalls.append(cv2.resize(g, (CHANGE_SIZE, CHANGE_SIZE), interpolation=cv2.INTER_AREA))
            t = float(Fraction(pair[0].pts) * tb)
            scores_rows.append((idx, round(t, 6), round(s[0], 2), round(s[1], 2)))

            w = (idx - start_idx) // window
            if current_window is not None and w != current_window and best is not None:
                flush(best)
                best = None
            current_window = w
            score = min(s)
            if best is None or score > best.score:
                best = Candidate(idx, t, score, s[0], s[1], np.stack(smalls),
                                 pair[0].to_ndarray(format="rgb24"), pair[1].to_ndarray(format="rgb24"))
        else:
            continue
        break
    if best is not None:
        flush(best)
    bar.close()
    container.close()
    for f in tqdm(futures, desc="write", unit="img", mininterval=TQDM_INTERVAL):
        f.result()
    pool.shutdown()

    with open(out_dir / "sharpness.csv", "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["idx", "t", "sharp0", "sharp1"])
        wr.writerows(scores_rows)

    all_scores = np.array([min(r[2], r[3]) for r in scores_rows]) if scores_rows else np.zeros(1)
    kept_scores = np.array([min(k["sharp0"], k["sharp1"]) for k in kept]) if kept else np.zeros(1)
    result = {
        "source": str(insv),
        "params": vars(params),
        "fps": fps,
        "decoded_pairs": len(scores_rows),
        "kept": len(kept),
        "skipped_still": skipped_still,
        "median_sharpness_all": float(np.median(all_scores)),
        "median_sharpness_kept": float(np.median(kept_scores)),
        "frames": kept,
    }
    write_json(out_dir / "frames.json", result)
    return result
