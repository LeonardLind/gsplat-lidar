"""Held-out PSNR per chunk of the walk and per view, from a training run's saved evaluation renders.

    python -m app.lidar.eval_chunks <run dir> <sparse model> <chunks.json> [--step 6999] [--holdout 10]

The renders (result/renders/val_step<step>_<k>.png, ground truth left, render right) are in the order of the
held-out images: image names sorted, every N-th 360 frame (app/trainers/gsplat_fork/gsl_dataset.py). Shows where
a joined scene is soft (seams, bent pieces) instead of one number for the whole office.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import pycolmap


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("sparse", type=Path)
    ap.add_argument("chunks", type=Path)
    ap.add_argument("--step", type=int, default=6999)
    ap.add_argument("--holdout", type=int, default=10)
    a = ap.parse_args()
    r = pycolmap.Reconstruction(str(a.sparse))
    names = sorted(r.images[i].name for i in r.reg_image_ids())
    frames = [Path(n).stem for n in names]
    order = {f: i for i, f in enumerate(sorted(set(frames)))}
    val = [n for n, f in zip(names, frames) if order[f] % a.holdout == 0]
    f2c = {f: c["id"] for c in json.loads(a.chunks.read_text()) for f in c["frames"]}
    per, per_view = defaultdict(list), defaultdict(list)
    for k, n in enumerate(val):
        im = cv2.imread(str(a.run / "result" / "renders" / f"val_step{a.step}_{k:04d}.png"))
        if im is None:
            continue
        im = im.astype(np.float32) / 255
        w = im.shape[1] // 2
        p = float(-10 * np.log10(((im[:, :w] - im[:, w:]) ** 2).mean() + 1e-10))
        per[f2c.get(Path(n).stem, -1)].append(p)
        per_view[n.replace("\\", "/").split("/")[0]].append(p)
    print(f"{sum(map(len, per.values()))} held-out images at step {a.step}")
    for c in sorted(per):
        print(f"  chunk {c:2d}: {np.mean(per[c]):5.1f} dB ({len(per[c])} images)")
    side = [p for v, x in per_view.items() if not v.endswith("_d") for p in x]
    print("  per view: " + ", ".join(f"{v} {np.mean(x):.1f}" for v, x in sorted(per_view.items())))
    print(f"  all views except the two looking down (mostly the masked operator): {np.mean(side):.1f} dB")


if __name__ == "__main__":
    main()
