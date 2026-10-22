"""Clean a LiDAR-frame splat with the LiDAR: delete Gaussians outside the scanned building and the invisible ones.

    python -m app.lidar.clean_splat <project> --export 068+069/<run> [--min-opacity 0.01] [--margin 0.5] [--dry-run]

Deleted: Gaussians outside the LiDAR's bounding box (+ margin; 0.3 m below the floor / above the ceiling) and
Gaussians with opacity below --min-opacity. In the first joined runs 35 % lay outside the building (faded before
MCMC's relocation stopped at 25k, then left where the noise put them) and 80 % had opacity < 1 %, while inside the
box almost no opaque Gaussian is far from a LiDAR surface (0.09 % farther than 1 m), so this costs nothing visible.
Uses the cleanup machinery of app/server/clean.py: the master PLY is never touched, <export>/clean/cleaned.ply
and a rebuilt scene.sog are written, and `python -m app clean-apply <project> --export ... --reset` undoes it.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from app.core.project import Project, read_json
from app.lidar.register import load_lidar
from app.server.clean import apply, export_dir, ply_layout, save_mask, scene_source


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--export", required=True)
    ap.add_argument("--min-opacity", type=float, default=0.01)
    ap.add_argument("--margin", type=float, default=0.5)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    p = Project(a.project)
    d = export_dir(p, a.export)
    scene = read_json(d / "scene.json")
    if not scene.get("lidar"):
        raise SystemExit("this export has no LiDAR layer (not a LiDAR-frame scene)")
    lid, *_ = load_lidar(Path(scene["lidar"].get("source", r"C:\dev\gsl-data\data\processed\office_lidar_5cm.npz")))
    lo = lid.min(axis=0) - [a.margin, a.margin, 0.3]
    hi = lid.max(axis=0) + [a.margin, a.margin, 0.3]
    src = scene_source(d)
    head, n, dtype, _ = ply_layout(src)
    rows = np.memmap(src, dtype=dtype, mode="r", offset=head, shape=(n,))
    xyz = np.stack([rows["x"], rows["y"], rows["z"]], axis=1)
    opacity = 1 / (1 + np.exp(-np.asarray(rows["opacity"], np.float64)))
    outside = ~np.all((xyz >= lo) & (xyz <= hi), axis=1)
    faint = opacity < a.min_opacity
    delete = outside | faint
    print(f"{n:,} Gaussians: {outside.sum():,} outside the LiDAR box, {faint.sum():,} with opacity < {a.min_opacity}; "
          f"deleting {delete.sum():,} ({delete.mean():.1%}), keeping {(~delete).sum():,}")
    if a.dry_run:
        return
    save_mask(d, np.packbits(delete, bitorder="little").tobytes())
    apply(p, a.export)


if __name__ == "__main__":
    main()
