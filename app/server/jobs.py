"""Job queue: one job at a time (frames/views use the CPU, but SfM and training share one GPU, and
two GPU jobs at once ran out of memory before). A job is a list of steps; each step is one
`python -m app ...` command whose output goes to the job's log file. Jobs are saved as JSON, so the
studio shows them after a server restart; a step that was running when the server stopped is
marked "interrupted" and the job can be retried from that step.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from app.core.project import REPO_ROOT, read_json, write_json
from app.server import pipeline
from app.server.machine import SERVER_DIR

JOBS_DIR = SERVER_DIR / "jobs"


def _pid_alive(pid: int) -> bool:
    import ctypes
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(h)
    return code.value == 259  # STILL_ACTIVE


def _kill_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)


class JobQueue:
    def __init__(self):
        JOBS_DIR.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.jobs: dict[str, dict] = {}
        self.procs: dict[str, subprocess.Popen] = {}
        for f in sorted(JOBS_DIR.glob("*.json")):
            try:
                job = read_json(f)
            except Exception:  # noqa: BLE001
                continue
            if job["status"] in ("running", "paused"):
                job["status"] = "interrupted"
                for s in job["steps"]:
                    if s["status"] == "running":
                        s["status"] = "interrupted"
                        pid = s.get("pid")
                        if pid and _pid_alive(pid):
                            _kill_tree(pid)  # an orphan from the last server run would hold the GPU
            self.jobs[job["id"]] = job
        self.wake = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    # ------------------------------------------------------------ public

    def submit(self, project: str, title: str, steps: list[dict], meta: dict | None = None) -> dict:
        job = {"id": time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4], "project": project, "title": title,
               "status": "queued", "created": time.time(), "started": None, "ended": None, "meta": meta or {},
               "steps": [{**s, "status": "skipped" if s.get("uptodate") else "pending", "started": None,
                          "ended": None, "code": None, "progress": None} for s in steps]}
        job["log"] = str(JOBS_DIR / f"{job['id']}.log")
        with self.lock:
            self.jobs[job["id"]] = job
            self._save(job)
        self.wake.set()
        return job

    def list(self, project: str | None = None) -> list[dict]:
        with self.lock:
            jobs = [j for j in self.jobs.values() if project in (None, j["project"])]
            return sorted(jobs, key=lambda j: j["created"], reverse=True)

    def get(self, job_id: str) -> dict:
        with self.lock:
            if job_id not in self.jobs:
                raise KeyError(job_id)
            job = self.jobs[job_id]
            for s in job["steps"]:
                if s["status"] == "running":
                    s["progress"] = pipeline.step_progress(s, Path(job["log"]))
            return job

    def running(self) -> dict | None:
        with self.lock:
            return next((j for j in self.jobs.values() if j["status"] in ("running", "paused")), None)

    def control(self, job_id: str, action: str) -> dict:
        """pause / resume / stop (training: finish now and keep the result) / cancel / retry."""
        with self.lock:
            job = self.jobs[job_id]
            step = next((s for s in job["steps"] if s["status"] == "running"), None)
            if action in ("pause", "resume", "stop"):
                if not step or step["kind"] != "train":
                    raise ValueError("only a running training step can be paused or stopped")
                Path(step["control_file"]).write_text({"pause": "pause", "resume": "run", "stop": "stop"}[action])
                job["status"] = "paused" if action == "pause" else "running"
            elif action == "cancel":
                if job["status"] == "queued":
                    job["status"] = "cancelled"
                elif step:
                    job["cancel"] = True
                    proc = self.procs.get(job_id)
                    if proc:
                        _kill_tree(proc.pid)
            elif action == "retry":
                if job["status"] not in ("failed", "interrupted", "cancelled"):
                    raise ValueError("only a failed, interrupted or cancelled job can be retried")
                for s in job["steps"]:
                    if s["status"] in ("failed", "interrupted", "cancelled", "running"):
                        s["status"], s["code"], s["progress"] = "pending", None, None
                job.pop("cancel", None)
                job["status"], job["ended"] = "queued", None
                self.wake.set()
            else:
                raise ValueError(action)
            self._save(job)
            return job

    def delete(self, job_id: str) -> None:
        with self.lock:
            job = self.jobs[job_id]
            if job["status"] in ("running", "paused"):
                raise ValueError("cancel the job first")
            del self.jobs[job_id]
            for f in (JOBS_DIR / f"{job_id}.json", Path(job["log"])):
                f.unlink(missing_ok=True)

    # ------------------------------------------------------------ runner

    def _save(self, job: dict) -> None:
        write_json(JOBS_DIR / f"{job['id']}.json", job)

    def _loop(self) -> None:
        while True:
            self.wake.wait(2.0)
            self.wake.clear()
            with self.lock:
                if self.running():
                    continue
                queued = sorted((j for j in self.jobs.values() if j["status"] == "queued"), key=lambda j: j["created"])
            if queued:
                try:
                    self._run(queued[0])
                except Exception as e:  # noqa: BLE001
                    with self.lock:
                        queued[0]["status"] = "failed"
                        queued[0]["error"] = f"{type(e).__name__}: {e}"
                        self._save(queued[0])
                self.wake.set()

    def _run(self, job: dict) -> None:
        log = Path(job["log"])
        with self.lock:
            job["status"], job["started"] = "running", job["started"] or time.time()
            self._save(job)
        for step in job["steps"]:
            if step["status"] not in ("pending",):
                continue
            with self.lock:
                if job.get("cancel") or job["status"] == "cancelled":
                    break
                step["status"], step["started"] = "running", time.time()
                self._save(job)
            ok = self._run_step(job, step, log)
            with self.lock:
                step["ended"] = time.time()
                if job.get("cancel"):
                    step["status"] = "cancelled"
                    job["status"] = "cancelled"
                elif ok:
                    step["status"] = "done"
                    pipeline.record_history(step, step["ended"] - step["started"], log)
                else:
                    step["status"] = "failed"
                    job["status"] = "failed"
                step["progress"] = None
                self._save(job)
                if job["status"] in ("failed", "cancelled"):
                    break
        with self.lock:
            if job["status"] in ("running", "paused"):
                job["status"] = "done"
            job["ended"] = time.time()
            job.pop("cancel", None)
            self._save(job)

    def _run_step(self, job: dict, step: dict, log: Path) -> bool:
        pipeline.clear_outputs(step)
        if step["kind"] == "cleanup":  # only removes leftovers (its "clear" list); no command to run
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"\n\n##### {step['label']}\nremoved: {', '.join(step['clear'])}\n")
            return True
        env = {**os.environ, "PYTHONUNBUFFERED": "1", "GSL_TQDM_INTERVAL": "1"}
        if step["kind"] == "train":
            run_dir = Path(step["run_dir"])
            run_dir.mkdir(parents=True, exist_ok=True)
            step["control_file"] = str(run_dir / "control.txt")
            Path(step["control_file"]).write_text("run")
            (run_dir / "progress.jsonl").unlink(missing_ok=True)
            env["GSL_PROGRESS_FILE"] = str(run_dir / "progress.jsonl")
            env["GSL_CONTROL_FILE"] = step["control_file"]
        cmd = step.get("cmd") or [sys.executable, "-m", "app", *step["args"]]
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"\n\n##### {step['label']}\n$ {' '.join(cmd)}\n")
            f.flush()
            proc = subprocess.Popen(cmd, cwd=str(REPO_ROOT), env=env, stdout=f, stderr=subprocess.STDOUT,
                                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            with self.lock:
                self.procs[job["id"]] = proc
                step["pid"] = proc.pid
                self._save(job)
            code = proc.wait()
            with self.lock:
                self.procs.pop(job["id"], None)
                step["code"] = code
            f.write(f"\n##### exit {code}\n")
        return code == 0
