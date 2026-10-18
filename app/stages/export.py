"""Export a trained splat (gsplat PLY, SH3, Z-up metric frame) to delivery formats (PLAN §1.11).

Uses PlayCanvas splat-transform:
  * scene.sog        compressed web delivery (SOG), in the project frame (+Z up) for web/viewer
  * scene.spz        SPZ format v3 (v4 is unreadable by Spark 2.3.1 and Luciad), project frame
  * viewer.html      self-contained SuperSplat viewer for a quick look; PlayCanvas is Y-up, so
                     this copy is turned -90 deg about X

The master PLY is never modified.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from app.core.tools import DEV

ZUP_TO_YUP = ["-r", "-90,0,0"]


def splat_transform() -> Path:
    p = Path(os.environ.get("GSL_SPLAT_TRANSFORM",
                            DEV / "tools" / "splat-transform" / "node_modules" / ".bin" / "splat-transform.cmd"))
    if not p.exists():
        raise SystemExit(f"splat-transform not found: {p}")
    return p


def run(args: list[str]) -> None:
    print("splat-transform", " ".join(args), flush=True)
    subprocess.run([str(splat_transform()), "--no-tty", "-w", *args], check=True)


def export(ply: Path, out_dir: Path, formats: list[str]) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    outs = []
    for fmt in formats:
        if fmt == "sog":
            dst = out_dir / "scene.sog"
            run([str(ply), "-N", str(dst)])
        elif fmt == "spz":
            dst = out_dir / "scene.spz"
            run([str(ply), "-N", str(dst), "--spz-version", "3"])
        elif fmt == "html":
            dst = out_dir / "viewer.html"
            run([str(ply), "-N", *ZUP_TO_YUP, str(dst)])
        else:
            raise ValueError(fmt)
        outs.append(dst)
    stats = out_dir / "stats.txt"
    with open(stats, "w", encoding="utf-8") as f:
        subprocess.run([str(splat_transform()), "--no-tty", str(ply), "--stats", "text", "null"],
                       check=True, stdout=f, stderr=subprocess.STDOUT)
    outs.append(stats)
    return outs
