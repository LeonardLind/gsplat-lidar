"""Train a Gaussian splat with gsplat (MCMC) on an oriented SfM model.

The run folder holds a gsplat-style data directory made of junctions (no copies):
    train/<run>/data/images   -> views/<clip>/images
    train/<run>/data/sparse/0 -> the oriented sparse model
gsplat trains in that frame (normalize_world_space off), so the exported PLY is
gravity-up and keeps the SfM scale (PLAN §1.5).
"""
from __future__ import annotations

import _winapi
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from app.core.project import REPO_ROOT, write_json
from app.core.tools import gs_python

LAUNCHER = REPO_ROOT / "app" / "trainers" / "gsplat_fork" / "train.py"


@dataclass
class TrainParams:
    steps: int = 30_000
    cap_max: int = 1_000_000
    sh_degree: int = 3
    holdout_every: int = 10  # every N-th 360 frame is held out for evaluation (0 = trainer default)
    ppisp: bool = False
    antialiased: bool = False
    packed: bool = False
    data_factor: int = 1
    viewer: bool = False
    # Update only the Gaussians seen in the current image. Without it, MCMC's opacity regulariser alone moves
    # every unseen Gaussian at full Adam step size; in 360 captures (each view sees a small part of the
    # scene) the splat fades into fog after ~2k steps (069 at 8k steps: 13.8 dB, mean opacity 0.001).
    visible_adam: bool = True


def junction(link: Path, target: Path) -> None:
    if link.exists():
        return
    link.parent.mkdir(parents=True, exist_ok=True)
    _winapi.CreateJunction(str(target.resolve()), str(link))


def train(views_dir: Path, sparse_model: Path, run_dir: Path, p: TrainParams) -> int:
    data = run_dir / "data"
    junction(data / "images", views_dir / "images")
    junction(data / "sparse" / "0", sparse_model)
    result = run_dir / "result"
    result.mkdir(parents=True, exist_ok=True)

    steps = [s for s in (7_000, p.steps // 2, p.steps) if s <= p.steps]
    steps = sorted(set(steps))
    args = [str(gs_python()), str(LAUNCHER), "mcmc",
            "--data-dir", str(data), "--result-dir", str(result),
            "--data-factor", str(p.data_factor),
            "--no-normalize-world-space",
            "--max-steps", str(p.steps),
            "--strategy.cap-max", str(p.cap_max),
            "--sh-degree", str(p.sh_degree),
            "--save-ply", "--ply-steps", *map(str, steps),
            "--save-steps", *map(str, steps),
            "--eval-steps", *map(str, steps),
            "--disable-video"]
    if not p.viewer:
        args.append("--disable-viewer")
    if p.ppisp:
        args += ["--post-processing", "ppisp"]
    if p.antialiased:
        args.append("--antialiased")
    if p.packed:
        args.append("--packed")
    if p.visible_adam:
        args.append("--visible-adam")
    # Experiments: extra simple_trainer options, e.g. GSL_TRAIN_EXTRA="--opacity-reg 0.001"
    args += os.environ.get("GSL_TRAIN_EXTRA", "").split()

    env = {**os.environ,
           # Training masks hide only the operator and moving people (app/stages/masks.py).
           "GSL_MASK_DIR": str((views_dir / ("masks_train" if (views_dir / "masks_train").exists() else "masks")).resolve()),
           "GSL_HOLDOUT_EVERY": str(p.holdout_every),
           "PYTHONUNBUFFERED": "1"}
    write_json(run_dir / "train_params.json", {"params": asdict(p), "args": args,
                                                "views": str(views_dir), "sparse": str(sparse_model)})
    print("running:", " ".join(args), flush=True)
    t0 = time.time()
    with open(run_dir / "train.log", "a", encoding="utf-8") as log:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, text=True,
                                encoding="utf-8", errors="replace", cwd=str(run_dir))
        for line in proc.stdout:
            log.write(line)
            log.flush()
            sys.stdout.write(line)
        code = proc.wait()
    print(f"training finished with exit {code} after {(time.time() - t0) / 60:.1f} min", flush=True)
    return code
