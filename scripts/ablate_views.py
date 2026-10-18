"""Which views make training collapse? Short runs on one SfM model with growing view sets, all scored
on the same held-out lens0_c images (GSL_EVAL_PREFIX), plus the mean opacity of the result (it falls
towards zero in the "fog" failure).

    C:\\dev\\envs\\pipe\\Scripts\\python.exe scripts/ablate_views.py [--project office --views 069 --steps 3000]
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.stages.scene_export import read_ply  # noqa: E402

SETS = {
    "c0": "lens0_c",
    "c01": "lens0_c,lens1_c",
    "lr0": "lens0_c,lens0_l,lens0_r",
    "all0": "lens0_",
    "ring01": "lens0_c,lens0_l,lens0_r,lens1_c,lens1_l,lens1_r",
    "all": "",
}

ap = argparse.ArgumentParser()
ap.add_argument("--project", default="office")
ap.add_argument("--views", default="069")
ap.add_argument("--sfm", default="aliked_global")
ap.add_argument("--steps", type=int, default=3000)
ap.add_argument("--cap", type=int, default=500_000)
ap.add_argument("--sets", default=",".join(SETS))
ap.add_argument("--tag", default="abl")
ap.add_argument("--extra", default="", help="extra env, e.g. GSL_X=1;GSL_Y=2")
a = ap.parse_args()

results = []
for name in a.sets.split(","):
    run = f"{a.tag}_{name}"
    env = {**os.environ, "GSL_ONLY_PREFIX": SETS[name], "GSL_EVAL_PREFIX": "lens0_c", "PYTHONUNBUFFERED": "1"}
    for kv in filter(None, a.extra.split(";")):
        k, v = kv.split("=", 1)
        env[k] = v
    t0 = time.time()
    code = subprocess.run([sys.executable, "-m", "app", "train", a.project, "--views", a.views, "--sfm", a.sfm,
                           "--name", run, "--steps", str(a.steps), "--cap", str(a.cap)],
                          cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT).returncode
    rd = ROOT / "projects" / a.project / "train" / a.views / run / "result"
    vals = sorted((rd / "stats").glob("val_step*.json"), key=lambda f: int("".join(c for c in f.stem if c.isdigit())))
    val = json.loads(vals[-1].read_text()) if vals else {}
    plys = sorted((rd / "ply").glob("*.ply"), key=lambda f: int("".join(c for c in f.stem if c.isdigit()) or 0))
    op = float(np.mean(1 / (1 + np.exp(-read_ply(plys[-1])["opacity"])))) if plys else float("nan")
    r = {"set": name, "views": SETS[name] or "all 10", "exit": code, "psnr_lens0c": val.get("psnr"), "ssim": val.get("ssim"),
         "gaussians": val.get("num_GS"), "mean_opacity": round(op, 3), "minutes": round((time.time() - t0) / 60, 1)}
    results.append(r)
    print(json.dumps(r), flush=True)

out = ROOT / "projects" / a.project / "train" / a.views / f"{a.tag}_results.json"
out.write_text(json.dumps(results, indent=2))
print("->", out)
