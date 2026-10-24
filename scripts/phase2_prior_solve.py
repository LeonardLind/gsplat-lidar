"""Roadmap Phase 2 (unattended): match the spatial pairs, then solve the whole walk again with the new matches.

    C:\\dev\\envs\\pipe\\Scripts\\python.exe scripts\\phase2_prior_solve.py [--wait-queue <queue.json>]

Works in sfm/068+069/aliked_prior (a copy of aliked_cpu with position priors, app/lidar/prior_pairs.py):
1. waits until the training queue is idle (one GPU job at a time),
2. matches pairs_spatial.txt (ALIKED + LightGlue on the GPU, ~10 h for 245k pairs) -> log match.log,
3. global_mapper -> sparse_global (fast; uses the new cross-pass matches, ignores the priors),
4. pose_prior_mapper -> sparse_prior (incremental with the LiDAR-frame position priors; slow),
and writes the path checks of app.stages.sfm.model_quality for each model into phase2_report.json. Each step is
skipped when its output already exists, so the script can simply be started again after an interruption.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COLMAP = Path(r"C:\dev\tools\colmap-4.2.1\bin\colmap.exe")
D = Path(r"C:\dev\gsl-data\projects\office-x4\sfm\068+069\aliked_prior")
IMAGES = Path(r"C:\dev\gsl-data\projects\office-x4\views\068+069\images")


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M')} {msg}"
    print(line, flush=True)
    with open(D / "phase2.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(args: list, logname: str) -> int:
    log(f"run: {' '.join(map(str, args[:2]))} ... (log {logname})")
    import sys
    sys.path.insert(0, str(REPO))
    from app.core.tools import colmap_env  # CUDA 12 + cuDNN on PATH for ONNX Runtime's CUDA provider (LightGlue)

    with open(D / logname, "a", encoding="utf-8") as f:
        return subprocess.run([str(a) for a in args], stdout=f, stderr=subprocess.STDOUT, env=colmap_env()).returncode


def queue_idle(queue: Path) -> bool:
    status = queue.with_suffix(".status.json")
    if not status.exists():
        return True
    states = [v.get("state") for v in json.loads(status.read_text()).values()]
    jobs = [j["name"] for j in json.loads(queue.read_text())["jobs"]]
    done = json.loads(status.read_text())
    return "running" not in states and all(done.get(n, {}).get("state") in ("done", "diverged", "failed", "skip") for n in jobs)


def report(sparse: Path) -> list:
    import sys
    sys.path.insert(0, str(REPO))
    from app.stages.sfm import model_quality
    import pycolmap

    out = []
    for m in sorted((d for d in sparse.iterdir() if d.is_dir() and d.name.isdigit()), key=lambda d: int(d.name)):
        r = pycolmap.Reconstruction(str(m))
        out.append({"model": m.name, "images": r.num_reg_images(), "frames": r.num_reg_frames(), "points": r.num_points3D(),
                    **{k: v for k, v in model_quality(m).items() if not isinstance(v, (list, dict)) or k == "warnings"}})
    out.sort(key=lambda x: -x["images"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait-queue", type=Path, default=Path(r"C:\dev\gsl-data\projects\office-x4\lidar\queue.json"))
    ap.add_argument("--dir", type=Path, help="work folder (default aliked_prior); round 2: aliked_prior2")
    ap.add_argument("--skip-prior-mapper", action="store_true", help="global_mapper only (it uses the priors too; 30 min vs ~20 h)")
    a = ap.parse_args()
    global D
    if a.dir:
        D = a.dir
    while not queue_idle(a.wait_queue):
        time.sleep(120)
    log("training queue idle: GPU free")
    db = D / "database.db"
    if not (D / "match.done").exists():
        code = run([COLMAP, "matches_importer", "--database_path", db, "--match_list_path", D / "pairs_spatial.txt",
                    "--match_type", "pairs", "--FeatureMatching.type", "ALIKED_LIGHTGLUE", "--FeatureMatching.use_gpu", "1",
                    "--FeatureMatching.rig_verification", "0"], "match.log")
        if code != 0:
            log(f"matching failed (exit {code}); stopping")
            return
        (D / "match.done").write_text(time.strftime("%Y-%m-%d %H:%M"))
        log("matching done")
    rep = json.loads((D / "phase2_report.json").read_text()) if (D / "phase2_report.json").exists() else {}
    common = ["--database_path", db, "--image_path", IMAGES]
    steps = (
        ("sparse_global", "global_mapper", ["--GlobalMapper.refine_sensor_from_rig", "0", "--GlobalMapper.ba_refine_focal_length", "0",
                                            "--GlobalMapper.ba_refine_principal_point", "0", "--GlobalMapper.ba_refine_extra_params", "0"]),
        ("sparse_prior", "pose_prior_mapper", ["--Mapper.ba_refine_sensor_from_rig", "0", "--Mapper.ba_refine_focal_length", "0",
                                               "--Mapper.ba_refine_principal_point", "0", "--Mapper.ba_refine_extra_params", "0",
                                               "--use_robust_loss_on_prior_position", "1"]),
    )
    for name, cmd, extra in steps[:1] if a.skip_prior_mapper else steps:
        out = D / name
        if (out / "done").exists():
            continue
        out.mkdir(exist_ok=True)
        t0 = time.time()
        code = run([COLMAP, cmd, *common, "--output_path", out, *extra], f"{name}.log")
        rep[name] = {"exit": code, "minutes": round((time.time() - t0) / 60, 1)}
        if code == 0:
            rep[name]["models"] = report(out)
            (out / "done").write_text(time.strftime("%Y-%m-%d %H:%M"))
        (D / "phase2_report.json").write_text(json.dumps(rep, indent=1))
        best = rep[name].get("models", [{}])[0]
        log(f"{name}: exit {code} after {rep[name]['minutes']} min; largest model {best}")
    log("phase 2 COLMAP steps finished")


if __name__ == "__main__":
    main()
