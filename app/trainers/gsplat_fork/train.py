"""Thin launcher around gsplat's examples/simple_trainer.py (runs in the `gs` environment).

Instead of forking the trainer it swaps in our dataset class (gsl_dataset.py:
per-image masks, hold-out by 360 frame) and fixes Windows path separators in
gsplat's image listing, then runs simple_trainer unchanged. All arguments go
straight to simple_trainer (tyro CLI), for example:

    python train.py mcmc --data-dir ... --result-dir ... --data-factor 1

For the browser studio (app/server) two optional hooks, set by environment variables:
  * GSL_PROGRESS_FILE: every TensorBoard scalar (loss, num_GS, val PSNR, ...) is also appended
    to this JSON-lines file, plus a {"tag": "step"} line every 2 s, so progress can be read live.
  * GSL_CONTROL_FILE: a file holding "run", "pause" or "stop". Pause holds the training loop;
    stop jumps to the last step, so the final checkpoint, PLY and evaluation are written as usual.
At the end the process exits instead of keeping gsplat's live viewer open forever.
"""
from __future__ import annotations

import json
import os
import runpy
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GSPLAT_EXAMPLES = Path(os.environ.get("GSL_GSPLAT_EXAMPLES", r"C:\dev\src\gsplat\examples"))
sys.path.insert(0, str(GSPLAT_EXAMPLES))
sys.path.insert(0, str(HERE))

from datasets import colmap as gs_colmap  # noqa: E402

from gsl_dataset import GslDataset  # noqa: E402

_orig_rel_paths = gs_colmap._get_rel_paths


def _rel_paths_posix(path_dir: str) -> list[str]:
    # COLMAP image names use "/", os.walk on Windows gives "\"; nested view folders need them equal.
    return [p.replace("\\", "/") for p in _orig_rel_paths(path_dir)]


gs_colmap._get_rel_paths = _rel_paths_posix
# simple_trainer does `from datasets.colmap import Dataset`, so replace it before the trainer imports it.
gs_colmap.Dataset = GslDataset

# --visible-adam: simple_trainer (main 512d366) passes fused=True to every optimizer, which gsplat's own
# SelectiveAdam does not accept. Drop the argument (SelectiveAdam has its own fused kernel).
from gsplat.optimizers import SelectiveAdam  # noqa: E402

_selective_adam_init = SelectiveAdam.__init__


def _selective_adam_init_compat(self, *args, fused=None, **kwargs):
    _selective_adam_init(self, *args, **kwargs)


SelectiveAdam.__init__ = _selective_adam_init_compat

# --depth-loss: gsplat's depth_l1_loss computes 1/depth inside torch.where, so where the rendered depth is 0 (no
# surface yet) the backward pass is inf * 0 = NaN and poisons every Gaussian (LiDAR depth run of 2026-10-22: loss
# nan at step 600, then MCMC's multinomial asserted). Clamp the rendered depth to 10 cm before inverting and
# ignore targets where nothing has been rendered yet.
import torch  # noqa: E402
import gsplat.losses as gs_losses  # noqa: E402


def _depth_l1_loss_safe(pred_depth, gt_depth, scene_scale: float = 1.0):
    valid = (pred_depth > 1e-3) & (gt_depth > 0)
    disp = 1.0 / pred_depth.clamp(min=0.1)
    disp_gt = 1.0 / gt_depth.clamp(min=0.1)
    err = torch.where(valid, (disp - disp_gt).abs(), torch.zeros_like(disp))
    return err.sum() / valid.sum().clamp(min=1) * scene_scale


gs_losses.depth_l1_loss = _depth_l1_loss_safe

# GSL_BOX="xmin,ymin,zmin,xmax,ymax,zmax" (LiDAR frame): every 100 steps, Gaussians outside the box get opacity
# ~0, so MCMC relocates them onto live ones (until refine_stop_iter) and they cannot hang in front of the cameras.
# Section training of 2026-10-27: in 4 of 16 sections (windows, few anchors) the Gaussians drifted up to 8 m above
# and below the building, grew, and every view turned into one flat blob (PSNR 17 -> 13 dB) with a normal loss.
BOX = os.environ.get("GSL_BOX")
if BOX:
    from gsplat.strategy import DefaultStrategy, MCMCStrategy

    _box = torch.tensor([float(v) for v in BOX.split(",")])
    print(f"[gsl] box guard: Gaussians outside {BOX} are switched off every 100 steps", flush=True)

    def _boxed(orig):
        def step_post_backward(self, params, optimizers, state, step, info, *args, **kwargs):
            if step % 100 == 0:
                with torch.no_grad():
                    b = _box.to(params["means"].device)
                    out = ((params["means"] < b[:3]) | (params["means"] > b[3:])).any(dim=1)
                    params["opacities"].data[out] = -10.0  # sigmoid(-10) = 5e-5, below MCMC's min_opacity 0.005
            return orig(self, params, optimizers, state, step, info, *args, **kwargs)
        return step_post_backward

    MCMCStrategy.step_post_backward = _boxed(MCMCStrategy.step_post_backward)
    DefaultStrategy.step_post_backward = _boxed(DefaultStrategy.step_post_backward)

PROGRESS = os.environ.get("GSL_PROGRESS_FILE")
CONTROL = os.environ.get("GSL_CONTROL_FILE")


def _progress(**rec) -> None:
    if PROGRESS:
        with open(PROGRESS, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": round(time.time(), 3), **rec}) + "\n")


def _control() -> str:
    try:
        return Path(CONTROL).read_text(encoding="utf-8").strip() if CONTROL else "run"
    except OSError:
        return "run"


def _install_hooks() -> None:
    import tqdm
    from torch.utils.tensorboard import SummaryWriter

    orig_add_scalar = SummaryWriter.add_scalar

    def add_scalar(self, tag, value, global_step=None, *args, **kwargs):
        orig_add_scalar(self, tag, value, global_step, *args, **kwargs)
        try:
            _progress(tag=tag, step=int(global_step) if global_step is not None else None, v=float(value))
        except (TypeError, ValueError):
            pass

    SummaryWriter.add_scalar = add_scalar

    class ControlledTqdm(tqdm.tqdm):
        """The training loop is the one tqdm over a range of steps; give it pause/stop and a heartbeat."""

        def __iter__(self):
            it = self.iterable
            if not isinstance(it, range) or len(it) < 100:
                yield from super().__iter__()
                return
            last_beat = last_check = 0.0
            state = "run"
            for step in super().__iter__():
                now = time.time()
                if now - last_check > 0.5:
                    last_check, state = now, _control()
                    while state == "pause":
                        _progress(tag="paused", step=step)
                        time.sleep(1.0)
                        state = _control()
                if state == "stop":
                    _progress(tag="stopping", step=step)
                    yield it[-1]  # the last step saves the checkpoint and PLY and runs the evaluation
                    return
                if now - last_beat > 2.0:
                    last_beat = now
                    _progress(tag="step", step=step, total=it[-1] + 1)
                yield step

    tqdm.tqdm = ControlledTqdm

    # simple_trainer keeps its live viewer open with time.sleep(1000000) after training; exit instead.
    orig_sleep = time.sleep

    def sleep(seconds):
        if seconds >= 10000:
            _progress(tag="done")
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(0)
        orig_sleep(seconds)

    time.sleep = sleep


if __name__ == "__main__":
    if PROGRESS or CONTROL:
        _install_hooks()
    sys.argv[0] = str(GSPLAT_EXAMPLES / "simple_trainer.py")
    runpy.run_path(str(GSPLAT_EXAMPLES / "simple_trainer.py"), run_name="__main__")
    _progress(tag="done")
