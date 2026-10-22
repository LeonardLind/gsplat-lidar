"""Thin a big LAS/LAZ point cloud to a voxel grid, in chunks (113 M points do not fit comfortably in memory).

    python -m app.lidar.downsample <in.las> <out.npz> [--voxel 0.05]

Writes xyz (float32, metres, scene coordinates minus `origin`), rgb (uint8), intensity (uint16) and the origin
(float64) that was subtracted so that float32 keeps millimetre precision.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import laspy
import numpy as np


def voxel_unique(xyz: np.ndarray, voxel: float) -> np.ndarray:
    """Indices of one point per occupied voxel."""
    k = np.floor(xyz / voxel).astype(np.int64)
    k -= k.min(axis=0)
    dims = k.max(axis=0) + 1
    key = (k[:, 0] * dims[1] + k[:, 1]) * dims[2] + k[:, 2]
    _, idx = np.unique(key, return_index=True)
    return idx


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--voxel", type=float, default=0.05)
    ap.add_argument("--chunk", type=int, default=5_000_000)
    a = ap.parse_args()
    t0 = time.time()
    xyzs, rgbs, ints = [], [], []
    with laspy.open(a.src) as f:
        total = f.header.point_count
        origin = (np.array(f.header.mins) + np.array(f.header.maxs)) / 2
        done = 0
        for pts in f.chunk_iterator(a.chunk):
            xyz = np.stack([pts.x, pts.y, pts.z], axis=1) - origin
            idx = voxel_unique(xyz, a.voxel)
            xyzs.append(xyz[idx].astype(np.float32))
            rgbs.append((np.stack([pts.red, pts.green, pts.blue], axis=1)[idx] >> 8).astype(np.uint8))
            ints.append(np.asarray(pts.intensity)[idx].astype(np.uint16))
            done += len(pts)
            print(f"  {done:,} / {total:,} read, {sum(len(x) for x in xyzs):,} kept ({time.time() - t0:.0f} s)", flush=True)
    xyz, rgb, inten = np.concatenate(xyzs), np.concatenate(rgbs), np.concatenate(ints)
    idx = voxel_unique(xyz.astype(np.float64), a.voxel)  # points of neighbouring chunks that share a voxel
    xyz, rgb, inten = xyz[idx], rgb[idx], inten[idx]
    np.savez_compressed(a.out, xyz=xyz, rgb=rgb, intensity=inten, origin=origin, voxel=a.voxel)
    print(f"{len(xyz):,} points at {a.voxel * 100:.0f} cm -> {a.out} ({time.time() - t0:.0f} s); "
          f"extent {np.ptp(xyz, axis=0).round(1)} m", flush=True)


if __name__ == "__main__":
    main()
