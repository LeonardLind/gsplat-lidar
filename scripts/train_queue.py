"""Run training jobs on LiDAR-frame scenes one after another, with a divergence watchdog (unattended use).

    C:\\dev\\envs\\pipe\\Scripts\\python.exe scripts\\train_queue.py <queue.json>

queue.json: {"jobs": [{"name": "...", "model": "<merged sparse/0>", "steps": 150000, "cap": 1600000,
              "extra": "--depth-loss ...", "env": {"GSL_DEPTH_POINTS": "..."}, "holdout": 10}, ...]}
holdout -10 = train on every frame (final deliverable); its score then measures views seen in training.
Each job trains (app.stages.train.train via a child process), exports itself (sog + LiDAR layer; export/current is
left alone: choosing the scene the explorer shows is a decision, `python -m app use-export`) and is scored with
app.lidar.eval_chunks on its last evaluation. Jobs already in the status file (<queue>.status.json) as done /
diverged / failed are skipped, so the queue can be restarted after a reboot. Jobs added to queue.json while it runs
are picked up.

Watchdog: once past step 3000, if the median of the last 300 logged losses exceeds 1.0 (healthy runs: 0.05-0.3;
the run of 2026-10-22 went 0.1 -> 17 between steps 60k and 63k with Gaussians at 1e12 m), the job is killed and
marked "diverged".
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = Path(r"C:\dev\envs\pipe\Scripts\python.exe")
PROJ = REPO / "projects" / "office-x4"
LINGER_S = 3600  # an empty queue waits this long for new jobs before the runner exits
LOSS = re.compile(r"loss=([0-9.]+)\|.*?\|\s*(\d+)/(\d+)")


def run_one(job: dict, log: Path) -> str:
    env_lines = "".join(f"os.environ[{k!r}] = {v!r}\n" for k, v in job.get("env", {}).items())
    code = (
        "import os, sys\n"
        f"sys.path.insert(0, {str(REPO)!r})\n"
        f"os.environ['GSL_TRAIN_EXTRA'] = {job.get('extra', '')!r}\n" + env_lines +
        "from pathlib import Path\n"
        "from app.stages.train import TrainParams, train\n"
        f"proj = Path({str(PROJ)!r})\n"
        f"sys.exit(train(proj / 'views' / '068+069', Path({job['model']!r}), proj / 'train' / '068+069' / {job['name']!r}, "
        f"TrainParams(steps={int(job['steps'])}, cap_max={int(job['cap'])}, holdout_every={int(job.get('holdout', 10))})))\n")
    with open(log, "w", encoding="utf-8") as f:
        proc = subprocess.Popen([str(PY), "-c", code], stdout=f, stderr=subprocess.STDOUT, cwd=str(REPO))
    losses: deque[float] = deque(maxlen=300)
    pos = 0
    while proc.poll() is None:
        time.sleep(20)
        with open(log, "rb") as f:
            f.seek(pos)
            chunk = f.read().decode("utf-8", "replace")
            pos = f.tell()
        step = 0
        for m in LOSS.finditer(chunk.replace("\r", "\n")):
            losses.append(float(m.group(1)))
            step = int(m.group(2))
        if step > 3000 and len(losses) == losses.maxlen and sorted(losses)[len(losses) // 2] > 1.0:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
            return f"diverged at step {step} (median loss {sorted(losses)[len(losses) // 2]:.2f})"
    if proc.returncode != 0:
        return f"failed (exit {proc.returncode})"
    ex = subprocess.run([str(PY), "-m", "app", "export", "office-x4", "--views", "068+069", "--run", job["name"], "--formats", "sog", "--keep-current"],
                        cwd=str(REPO), capture_output=True, text=True)
    if ex.returncode != 0:
        return f"trained, export failed: {ex.stdout[-300:]}{ex.stderr[-300:]}"
    return "done"


def score(job: dict) -> str:
    run = PROJ / "train" / "068+069" / job["name"]
    steps = sorted(int(p.stem.split("step")[1]) for p in (run / "result" / "stats").glob("val_step*.json"))
    if not steps:
        return ""
    s = steps[-1]
    psnr = json.loads((run / "result" / "stats" / f"val_step{s}.json").read_text())["psnr"]
    ev = subprocess.run([str(PY), "-m", "app.lidar.eval_chunks", str(run), job["model"],
                         r"C:\dev\gsl-data\projects\office-x4\lidar\chunks.json", "--step", str(s)],
                        cwd=str(REPO), capture_output=True, text=True)
    side = [l for l in ev.stdout.splitlines() if "except the two" in l]
    return f"step {s + 1}: PSNR {psnr:.2f} dB; {side[0].strip() if side else ev.stderr[-200:]}"


def main() -> None:
    qfile = Path(sys.argv[1])
    sfile = qfile.with_suffix(".status.json")
    status = json.loads(sfile.read_text()) if sfile.exists() else {}
    idle_since = None
    while True:
        jobs = json.loads(qfile.read_text())["jobs"]
        todo = [j for j in jobs if status.get(j["name"], {}).get("state") not in ("done", "diverged", "failed", "skip")]
        if not todo:
            # wait a while for jobs added after the last one finished (2026-10-24: a job queued 2 min late sat idle)
            idle_since = idle_since or time.time()
            if time.time() - idle_since > LINGER_S:
                print("queue empty", flush=True)
                return
            time.sleep(60)
            continue
        idle_since = None
        job = todo[0]
        log = qfile.parent / f"train_{job['name']}.log"
        status[job["name"]] = {"state": "running", "start": time.strftime("%Y-%m-%d %H:%M"), "log": str(log)}
        sfile.write_text(json.dumps(status, indent=1))
        print(f"{time.strftime('%H:%M')} start {job['name']}", flush=True)
        result = run_one(job, log)
        st = {"state": "done" if result == "done" else ("diverged" if result.startswith("diverged") else "failed"),
              "result": result, "start": status[job["name"]]["start"], "end": time.strftime("%Y-%m-%d %H:%M"), "log": str(log)}
        st["score"] = score(job)
        status[job["name"]] = st
        sfile.write_text(json.dumps(status, indent=1))
        print(f"{time.strftime('%H:%M')} {job['name']}: {result}; {st['score']}", flush=True)


if __name__ == "__main__":
    main()
