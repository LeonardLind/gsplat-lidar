"""gsplat COLMAP dataset with per-image masks and hold-out by 360 frame.

A subclass in its own module, not a monkeypatch: on Windows the DataLoader
workers are spawned processes that unpickle the dataset by class name, so the
class must be importable with its changes in place. Settings come from
environment variables, which the workers inherit:

    GSL_MASK_DIR       masks/<image name>.png (255 = use), or ../mask_<view folder>.png
    GSL_HOLDOUT_EVERY  every N-th 360 frame goes to the test split with all its views
    GSL_ONLY_PREFIX    debugging: keep only view folders with these prefixes (comma list)
    GSL_EVAL_PREFIX    evaluate only on view folders with these prefixes (comparable PSNR across view sets)
    GSL_DEPTH_POINTS   npz from app/lidar/visibility.py: the LiDAR points each image sees become the depth-loss
                       targets (parser.point_indices); use with --depth-loss
"""
from __future__ import annotations

import os
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
import torch
from datasets import colmap as gs_colmap

MASK_DIR = Path(os.environ["GSL_MASK_DIR"]) if os.environ.get("GSL_MASK_DIR") else None
HOLDOUT_EVERY = int(os.environ.get("GSL_HOLDOUT_EVERY", "0"))
ONLY_PREFIX = tuple(p for p in os.environ.get("GSL_ONLY_PREFIX", "").split(",") if p)
EVAL_PREFIX = tuple(p for p in os.environ.get("GSL_EVAL_PREFIX", "").split(",") if p)
DEPTH_POINTS = os.environ.get("GSL_DEPTH_POINTS", "")


def use_depth_points(parser, path: str) -> None:
    """Replace the SfM-track based point_indices with the LiDAR points each image sees (once per parser)."""
    if getattr(parser, "_gsl_depth_points", None) == path:
        return
    d = np.load(path)
    names, off, idx = d["names"], d["offsets"], d["indices"]
    known = set(parser.image_names)
    parser.point_indices = {str(n): idx[off[k]:off[k + 1]] for k, n in enumerate(names) if str(n) in known}
    missing = len(known) - len(parser.point_indices)
    if missing:
        raise SystemExit(f"GSL_DEPTH_POINTS: {missing} images have no LiDAR depth points ({path})")
    parser._gsl_depth_points = path
    print(f"[gsl] depth targets: LiDAR points per image from {path} "
          f"(median {int(np.median(np.diff(off)))} points per image)")

_static_masks: dict[str, np.ndarray | None] = {}


def load_mask(image_name: str) -> np.ndarray | None:
    if MASK_DIR is None:
        return None
    per_image = MASK_DIR / f"{image_name}.png"
    if per_image.exists():
        return imageio.imread(per_image) > 127
    folder = image_name.replace("\\", "/").split("/")[0]
    if folder not in _static_masks:
        static = MASK_DIR.parent / f"mask_{folder}.png"
        _static_masks[folder] = imageio.imread(static) > 127 if static.exists() else None
    return _static_masks[folder]


class GslDataset(gs_colmap.Dataset):
    def __init__(self, parser, split="train", patch_size=None, load_depths=False):
        if DEPTH_POINTS and load_depths:
            use_depth_points(parser, DEPTH_POINTS)
        super().__init__(parser, split, patch_size, load_depths)
        if HOLDOUT_EVERY > 0:
            frames = [Path(n).stem for n in parser.image_names]
            order = {f: i for i, f in enumerate(sorted(set(frames)))}
            is_test = np.array([order[f] % HOLDOUT_EVERY == 0 for f in frames])
            idx = np.arange(len(frames))
            self.indices = idx[~is_test] if split == "train" else idx[is_test]
        if ONLY_PREFIX:
            self.indices = np.array([i for i in self.indices if parser.image_names[i].startswith(ONLY_PREFIX)])
        if EVAL_PREFIX and split != "train":
            self.indices = np.array([i for i in self.indices if parser.image_names[i].startswith(EVAL_PREFIX)])
        print(f"[gsl] {split}: {len(self.indices)} images"
              f"{f' (every {HOLDOUT_EVERY}th frame held out)' if HOLDOUT_EVERY else ''}; masks: {MASK_DIR}")

    def __getitem__(self, item):
        data = super().__getitem__(item)
        if self.patch_size is None:
            mask = load_mask(self.parser.image_names[self.indices[item]])
            if mask is not None:
                m = torch.from_numpy(mask)
                if "mask" in data:
                    m = m & data["mask"]
                data["mask"] = m
        return data
