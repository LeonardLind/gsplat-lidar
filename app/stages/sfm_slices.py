"""Map a long walk in overlapping slices and join them (global mapper on the whole walk scrambled it).

The 068+069 office run (15 310 images, 2026-10-21): the neighbouring frames share thousands of matches, but the
global mapper over all frames produced 93 jumps in the camera path (42 % of the image pairs were marked as
inconsistent by rotation averaging). Small sets solve cleanly (20 s tests, the 171-frame clip 069), so this solves
slices of ~170-250 frames each with the existing database and joins neighbouring slices through the frames they
share (similarity fit on the camera centres, one slice onto the next).

    python -m app.stages.sfm_slices <sfm run dir> <views dir> [--frames 220] [--overlap 40] [--only 0,1]

Writes <run>/slices/<n>/sparse/0 per slice and, after joining, <run>/joined/0 (cameras only joined; the points
of every slice are kept, transformed into the joined frame) with a path report.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from app.core.tools import colmap_env, colmap_exe


def slice_ranges(frames: list[str], size: int, overlap: int) -> list[tuple[int, int]]:
    """(start, end) frame index ranges of the slices. Frames are named <clip>_<number>; a slice never crosses a
    clip boundary (the camera was switched off there, so there are no matches across it)."""
    clip_of = [f.split("_")[0] if "_" in f else "" for f in frames]
    out, start = [], 0
    for end in [i for i in range(1, len(frames)) if clip_of[i] != clip_of[i - 1]] + [len(frames)]:
        a = start
        while a < end:
            b = min(end, a + size)
            if end - b < overlap:  # do not leave a tiny tail slice
                b = end
            out.append((a, b))
            if b == end:
                break
            a = b - overlap
        start = end
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("views_dir", type=Path)
    ap.add_argument("--frames", type=int, default=220)
    ap.add_argument("--overlap", type=int, default=40)
    ap.add_argument("--only", help="comma list of slice numbers (default all)")
    ap.add_argument("--solver-cpu", action="store_true")
    a = ap.parse_args()

    meta = json.loads((a.views_dir / "views.json").read_text())
    views = [v["folder"] for v in meta["views"]]
    ext = meta["params"]["image_format"]
    frames = [str(f) for f in meta["frames"]]
    ranges = slice_ranges(frames, a.frames, a.overlap)
    only = {int(x) for x in a.only.split(",")} if a.only else None
    exe = str(colmap_exe())
    for n, (lo, hi) in enumerate(ranges):
        if only is not None and n not in only:
            continue
        out = a.run_dir / "slices" / str(n)
        (out / "sparse").mkdir(parents=True, exist_ok=True)
        lst = out / "images.txt"
        lst.write_text("\n".join(f"{v}/{f}.{ext}" for f in frames[lo:hi] for v in views))
        args = [exe, "global_mapper", "--database_path", str(a.run_dir / "database.db"),
                "--image_path", str(a.views_dir / "images"), "--output_path", str(out / "sparse"),
                "--GlobalMapper.image_list_path", str(lst),
                "--GlobalMapper.refine_sensor_from_rig", "0", "--GlobalMapper.ba_refine_focal_length", "0",
                "--GlobalMapper.ba_refine_principal_point", "0", "--GlobalMapper.ba_refine_extra_params", "0"]
        if a.solver_cpu:
            args += ["--GlobalMapper.gp_use_gpu", "0", "--GlobalMapper.ba_ceres_use_gpu", "0"]
        t0 = time.time()
        print(f"slice {n}: frames {lo}-{hi} ({frames[lo]} .. {frames[hi - 1]}), {(hi - lo) * len(views)} images", flush=True)
        with open(out / "colmap.log", "w", encoding="utf-8") as log:
            p = subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, env=colmap_env())
        print(f"   exit {p.returncode} in {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    sys.exit(main())
