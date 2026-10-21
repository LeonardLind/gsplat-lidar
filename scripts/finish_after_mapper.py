"""Unattended: wait for a COLMAP mapper run to end, check the camera path, and only then train and export.

    C:\\dev\\envs\\pipe\\Scripts\\python.exe scripts\\finish_after_mapper.py --project office-x4 --views 068+069 --sfm aliked_inc2

1. waits until no colmap.exe is running on that SfM run folder;
2. picks the largest model in <run>/sparse, writes <run>/sfm_report.json (what `app sfm` writes after the mapper);
3. the path must pass the jump test (after dropping stray frames) and cover >= --min-coverage of the images;
4. then: people-classify, train, export through the app CLI, logging to <project>/finish_after_mapper.log.
Progress and the verdict are in <project>/finish_after_mapper_status.json.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from app.core.project import PROJECTS_DIR, write_json  # noqa: E402
from app.stages.orient import drop_stray_frames  # noqa: E402
from app.stages.sfm import Colmap, SfmParams, model_quality, model_stats  # noqa: E402

PY = sys.executable


def running(sfm_name: str) -> bool:
    cmd = ("(Get-CimInstance Win32_Process -Filter \"Name='colmap.exe'\" | "
           f"Where-Object {{ $_.CommandLine -match '{sfm_name}' }} | Measure-Object).Count")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True).stdout.strip()
    return out not in ("", "0")


def jumps_after_strays(model_dir: Path, factor: float = 30.0) -> dict:
    import pycolmap

    r = pycolmap.Reconstruction(str(model_dir))
    info = drop_stray_frames(r)
    rows = []
    for i in r.reg_image_ids():
        im = r.images[i]
        m = re.match(r"lens0_c/(\w+?)_(\d+)\.", im.name.replace("\\", "/"))
        if m:
            rows.append((m.group(1), int(m.group(2)), np.array(im.projection_center())))
    rows.sort(key=lambda x: (x[0], x[1]))
    P = np.array([x[2] for x in rows])
    same = np.array([rows[k][0] == rows[k + 1][0] for k in range(len(rows) - 1)])
    st = np.linalg.norm(np.diff(P, axis=0), axis=1)
    rel = st[same] / max(float(np.median(st[same])), 1e-12)
    return {"strays_removed": info["stray_frames_removed"], "frames_left": len(rows),
            "jumps_30x": int((rel > factor).sum()), "jumps_10x": int((rel > 10).sum()),
            "largest_jump_x": float(rel.max()) if len(rel) else 0.0}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--views", required=True)
    ap.add_argument("--sfm", required=True)
    ap.add_argument("--steps", type=int, default=150_000)
    ap.add_argument("--cap", type=int, default=1_500_000)
    ap.add_argument("--min-coverage", type=float, default=0.6)
    ap.add_argument("--max-jumps-30x", type=int, default=10)
    a = ap.parse_args()
    proj = PROJECTS_DIR / a.project
    sfm_dir = proj / "sfm" / a.views / a.sfm
    status_file = proj / "finish_after_mapper_status.json"
    log = open(proj / "finish_after_mapper.log", "a", encoding="utf-8")
    status: dict = {"stage": "waiting for the mapper", "started": time.strftime("%Y-%m-%d %H:%M:%S")}

    def save(**kw):
        status.update(kw, updated=time.strftime("%Y-%m-%d %H:%M:%S"))
        write_json(status_file, status)
        print(json.dumps(status), file=log, flush=True)

    save()
    while running(a.sfm):
        time.sleep(60)
    time.sleep(20)
    save(stage="checking the camera solve")

    views = json.loads((proj / "views" / a.views / "views.json").read_text())
    n_images = len(views["frames"]) * len(views["views"])
    models = sorted(d for d in (sfm_dir / "sparse").iterdir() if d.is_dir()) if (sfm_dir / "sparse").exists() else []
    if not models:
        save(stage="stopped", verdict="the mapper produced no model")
        return
    colmap = Colmap(sfm_dir / "colmap.log")
    report = {"params": asdict(SfmParams(mapper="incremental")), "num_images": n_images, "models": []}
    for m in models:
        txt = m.parent / f"{m.name}_txt"
        txt.mkdir(exist_ok=True)
        colmap("model_converter", input_path=m, output_path=txt, output_type="TXT")
        report["models"].append({"path": str(m), **model_stats(txt), **model_quality(m)})
    report["models"].sort(key=lambda s: s["registered_images"], reverse=True)
    write_json(sfm_dir / "sfm_report.json", report)
    best = report["models"][0]
    coverage = best["registered_images"] / n_images
    check = jumps_after_strays(Path(best["path"]))
    save(models=[(Path(m["path"]).name, m["registered_images"]) for m in report["models"][:8]],
         best_model=Path(best["path"]).name, coverage=round(coverage, 3), path_check=check)
    if coverage < a.min_coverage or check["jumps_30x"] > a.max_jumps_30x:
        save(stage="stopped", verdict=(f"not good enough to train: the largest model covers {coverage:.0%} of the images "
                                       f"(need {a.min_coverage:.0%}) and its path has {check['jumps_30x']} jumps of 30x the "
                                       f"usual step (allowed {a.max_jumps_30x})"))
        return

    steps = [
        ("classifying people (moving ones are cut from training)",
         [PY, "-m", "app", "people-classify", a.project, "--views", a.views, "--sfm", a.sfm]),
        ("training", [PY, "-m", "app", "train", a.project, "--views", a.views, "--sfm", a.sfm,
                      "--name", f"{a.sfm}_{a.cap // 1000}k_{a.steps // 1000}k", "--steps", str(a.steps), "--cap", str(a.cap)]),
        ("exporting", [PY, "-m", "app", "export", a.project, "--views", a.views,
                       "--run", f"{a.sfm}_{a.cap // 1000}k_{a.steps // 1000}k", "--formats", "sog"]),
    ]
    for name, cmd in steps:
        save(stage=name)
        code = subprocess.run(cmd, cwd=str(REPO), stdout=log, stderr=subprocess.STDOUT).returncode
        if code != 0:
            save(stage="stopped", verdict=f"{name} failed with exit code {code}; see finish_after_mapper.log")
            return
    save(stage="done", verdict=f"trained and exported ({coverage:.0%} of the images); the explorer shows project {a.project}")


if __name__ == "__main__":
    main()
