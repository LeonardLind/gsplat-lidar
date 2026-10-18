"""HTTP API of the studio server (all under /studio-api)."""
from __future__ import annotations

import _winapi
import os
import re
import string
import sys
import time
from pathlib import Path

from app.core.project import PROJECTS_DIR, REPO_ROOT, Project, read_json, write_json
from app.server import clean, machine, pipeline
from app.server.http import FileResponse, HttpError, Request, Router
from app.server.jobs import JobQueue
from app.server.machine import SERVER_DIR

router = Router()
queue: JobQueue | None = None
VIDEO_EXT = {".insv", ".mp4", ".mov"}
CURRENT_FILE = SERVER_DIR / "current.json"  # which project's export/current the explorer (Vite) serves


def _project(name: str) -> Project:
    p = Project(name)
    if not p.exists():
        raise HttpError(404, f"no project {name}")
    return p


def _q() -> JobQueue:
    assert queue is not None
    return queue


# ---------------------------------------------------------------- status, files

@router.route("GET", "/status")
def status(req: Request):
    h = machine.load()
    return {"host": machine.HOST, "gpu": machine.gpu_info(), "bench": h.get("bench"),
            "train_runs_measured": len(h.get("train") or []), "running": (_q().running() or {}).get("id"),
            "current": read_json(CURRENT_FILE) if CURRENT_FILE.exists() else None}


@router.route("GET", "/fs")
def list_dir(req: Request):
    """Browse this PC for video files (the studio runs locally, so it can use real paths, no uploads)."""
    path = req.query.get("path")
    if not path:
        drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
        home = Path.home()
        places = [str(x) for x in (REPO_ROOT / "data" / "raw", home / "Desktop", home / "Downloads", home / "Videos")
                  if x.exists()]
        return {"path": None, "parent": None, "dirs": [{"name": x, "path": x} for x in places + drives], "files": []}
    d = Path(path)
    if not d.is_dir():
        raise HttpError(404, f"not a folder: {path}")
    dirs, files = [], []
    try:
        entries = sorted(d.iterdir(), key=lambda x: x.name.lower())
    except PermissionError:
        raise HttpError(403, f"no access: {path}")
    for e in entries:
        try:
            if e.name.startswith(("$", ".")):
                continue
            if e.is_dir():
                dirs.append({"name": e.name, "path": str(e)})
            elif e.suffix.lower() in VIDEO_EXT:
                st = e.stat()
                files.append({"name": e.name, "path": str(e), "size": st.st_size, "mtime": st.st_mtime})
        except OSError:
            continue
    parent = str(d.parent) if d.parent != d else ""
    return {"path": str(d), "parent": parent, "dirs": dirs, "files": files}


# ---------------------------------------------------------------- projects and clips

@router.route("GET", "/projects")
def projects(req: Request):
    out = []
    for f in sorted(PROJECTS_DIR.glob("*/project.json")):
        data = read_json(f)
        out.append({"name": f.parent.name, "clips": len(data.get("sources", {}).get("insta360", {}).get("clips", []))})
    return out


@router.route("POST", "/projects")
def create_project(req: Request):
    name = (req.json().get("name") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,40}", name):
        raise HttpError(400, "use letters, digits, - and _ (max 40)")
    p = Project(name)
    if p.exists():
        raise HttpError(409, f"project {name} exists")
    p.save({"name": name, "sources": {"insta360": {"clips": []}}})
    return {"name": name}


@router.route("GET", "/projects/{name}")
def project(req: Request):
    p = _project(req.params["name"])
    caps, reasons, suggested = pipeline.captures(p)
    return {"name": p.name, "clips": [pipeline.clip_summary(p, c) for c in p.clips()],
            "captures": caps, "suggested": suggested, "reasons": reasons,
            "settings": p.load().get("studio_settings", {}), "exports": exports(p)}


@router.route("POST", "/projects/{name}/clips")
def add_clip(req: Request):
    from app.sources.insta360.probe import probe_clip

    p = _project(req.params["name"])
    path = Path(req.json().get("path", "")).resolve()
    if not path.is_file():
        raise HttpError(400, f"not found: {path}")
    data = p.load()
    clips = data.setdefault("sources", {}).setdefault("insta360", {"clips": []})["clips"]
    clip_id = path.stem.split("_")[-1] if path.suffix.lower() == ".insv" else path.stem
    clip_id = re.sub(r"[^A-Za-z0-9_-]", "_", clip_id)[:40]
    if any(c["path"] == str(path) for c in clips):
        raise HttpError(409, f"{path.name} is already in the project")
    base, k = clip_id, 2
    while any(c["id"] == clip_id for c in clips):
        clip_id, k = f"{base}_{k}", k + 1
    rep = probe_clip(path)
    write_json(p.stage_dir("probe") / f"{clip_id}.json", rep)
    clips.append({"id": clip_id, "path": str(path)})
    data.pop("captures", None)  # re-suggest the grouping with the new clip
    p.save(data)
    return pipeline.clip_summary(p, {"id": clip_id, "path": str(path)})


@router.route("DELETE", "/projects/{name}/clips/{clip}")
def remove_clip(req: Request):
    p = _project(req.params["name"])
    data = p.load()
    clips = data["sources"]["insta360"]["clips"]
    data["sources"]["insta360"]["clips"] = [c for c in clips if c["id"] != req.params["clip"]]
    for cap in data.get("captures", []):
        cap["clips"] = [c for c in cap["clips"] if c["id"] != req.params["clip"]]
    p.save(data)
    return {"ok": True}


@router.route("GET", "/projects/{name}/clips/{clip}/thumb/{i}")
def thumb(req: Request):
    """Filmstrip picture i of n (lens 0, centre crop), made on first request and cached."""
    import av
    import cv2

    p = _project(req.params["name"])
    clip = p.clip(req.params["clip"])
    n, i = int(req.query.get("n", 10)), int(req.params["i"])
    out = p.stage_dir("probe", "thumbs") / f"{clip['id']}_{n}_{i}.jpg"
    if not out.exists():
        dur = (pipeline.probe(p, clip["id"]) or {}).get("duration_s") or 1
        t = dur * (i + 0.5) / n
        with av.open(clip["path"]) as c:
            s = c.streams.video[0]
            s.thread_type = "AUTO"
            c.seek(int(t / s.time_base), stream=s, backward=True)
            frame = next(c.decode(s))
            img = frame.to_ndarray(format="bgr24")
        h, w = img.shape[:2]
        side = int(min(h, w) * 0.62)  # inside the fisheye circle
        y0, x0 = (h - side) // 2, (w - side) // 2
        img = cv2.resize(img[y0:y0 + side, x0:x0 + side], (160, 160), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(out), img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return FileResponse(out, "image/jpeg")


@router.route("PUT", "/projects/{name}/captures")
def save_captures(req: Request):
    p = _project(req.params["name"])
    body = req.json()
    data = p.load()
    known = {c["id"] for c in p.clips()}
    caps = []
    for cap in body.get("captures", []):
        clips = [{"id": c["id"], "start": max(0.0, float(c.get("start") or 0)),
                  "end": float(c["end"]) if c.get("end") is not None else None}
                 for c in cap.get("clips", []) if c["id"] in known]
        if clips:
            caps.append({"id": re.sub(r"[^A-Za-z0-9_+-]", "_", cap.get("id") or "+".join(c["id"] for c in clips)),
                         "name": cap.get("name") or " + ".join(c["id"] for c in clips), "clips": clips})
    data["captures"] = caps
    if "settings" in body:
        data["studio_settings"] = body["settings"]
    p.save(data)
    return {"captures": caps}


# ---------------------------------------------------------------- estimates and runs

def _capture(p: Project, cap_id: str) -> dict:
    caps, _, _ = pipeline.captures(p)
    cap = next((c for c in caps if c["id"] == cap_id), None)
    if not cap:
        raise HttpError(404, f"no capture {cap_id}")
    return cap


def _trimmed(p: Project, cap: dict) -> list[dict]:
    out = []
    for c in cap["clips"]:
        pr = pipeline.probe(p, c["id"]) or {}
        dur = pr.get("duration_s") or 0
        end = min(dur, c["end"]) if c.get("end") is not None else dur
        out.append({"duration": max(0.0, end - (c.get("start") or 0)), "video_fps": pr.get("fps") or 30})
    return out


@router.route("POST", "/projects/{name}/estimate")
def estimate(req: Request):
    p = _project(req.params["name"])
    body = req.json()
    cap = body.get("capture") or _capture(p, body["capture_id"])
    s = body.get("settings", {})
    people = bool(s.get("people", True))
    est = machine.estimate(_trimmed(p, cap), float(s.get("fps", 2.5)), s.get("steps"), int(s.get("cap", 1_000_000)),
                           people=people)
    steps, _ = pipeline.build_steps(p, cap, {"fps": float(s.get("fps", 2.5)), "steps": est["steps"],
                                             "cap": int(s.get("cap", 1_000_000)), "run": "estimate", "people": people})
    # Stages whose output is already there for these settings take no time.
    kinds_done = {st["kind"] for st in steps if st["uptodate"]}
    kinds_todo = {st["kind"] for st in steps if not st["uptodate"]}
    for stage in est["stages"]:
        stage["uptodate"] = stage["stage"] in kinds_done and stage["stage"] not in kinds_todo
    est["total_seconds"] = sum(st["seconds"] for st in est["stages"] if not st["uptodate"])
    return est


@router.route("POST", "/projects/{name}/run")
def run(req: Request):
    p = _project(req.params["name"])
    body = req.json()
    cap = _capture(p, body["capture_id"])
    s = body.get("settings", {})
    fps, capn = float(s.get("fps", 2.5)), int(s.get("cap", 1_000_000))
    people = bool(s.get("people", True))
    est = machine.estimate(_trimmed(p, cap), fps, s.get("steps"), capn, people=people)
    settings = {"fps": fps, "steps": int(s.get("steps") or est["steps"]), "cap": capn,
                "viewer": bool(s.get("viewer", True)), "people": people, "max_features": int(s.get("max_features") or 8192)}
    steps, info = pipeline.build_steps(p, cap, settings)
    if body.get("from_stage"):  # rerun from a stage even if its output is up to date
        hit = False
        for st in steps:
            hit = hit or st["kind"] == body["from_stage"]
            if hit:
                st["uptodate"] = False
    data = p.load()
    data["studio_settings"] = {**settings, "capture_id": cap["id"]}
    p.save(data)
    job = _q().submit(p.name, f"{cap['name']}: {fps:g} fps, {settings['cap'] / 1e6:g} M Gaussians, "
                              f"{settings['steps'] // 1000}k steps{'' if people else ', no people masks'}", steps,
                      {"capture": cap, "settings": settings, **info, "estimate": est})
    return job


@router.route("POST", "/bench")
def bench(req: Request):
    return _q().submit("_machine", "Measure this PC (training speed)",
                       [{"name": "bench", "kind": "bench", "label": "GPU benchmark", "args": ["bench"], "clear": []}])


# ---------------------------------------------------------------- jobs

@router.route("GET", "/jobs")
def jobs(req: Request):
    return [_job_view(j) for j in _q().list(req.query.get("project"))[:30]]


def _job_view(j: dict) -> dict:
    return {k: v for k, v in j.items() if k != "meta"} | {"meta": {k: v for k, v in j.get("meta", {}).items()
                                                                     if k in ("run", "run_dir", "views_id", "settings",
                                                                              "export")}}


@router.route("GET", "/jobs/{id}")
def job(req: Request):
    try:
        return _q().get(req.params["id"])
    except KeyError:
        raise HttpError(404, "no such job")


@router.route("GET", "/jobs/{id}/log")
def job_log(req: Request):
    j = _q().get(req.params["id"])
    f = Path(j["log"])
    text = pipeline._tail(f, int(req.query.get("bytes", 40000))) if f.exists() else ""
    # tqdm redraws with \r: keep only the last state of each line.
    return {"text": "\n".join(line.split("\r")[-1] for line in text.split("\n"))}


@router.route("GET", "/jobs/{id}/train")
def job_train(req: Request):
    j = _q().get(req.params["id"])
    step = next((s for s in j["steps"] if s["kind"] == "train"), None)
    if not step:
        raise HttpError(404, "this job has no training step")
    tp = pipeline.read_train_progress(Path(step["run_dir"]))
    return {**tp, "status": step["status"], "total": tp["total"] or step.get("total_steps"),
            "viewer": "--viewer" in step["args"], "settings": j.get("meta", {}).get("settings")}


@router.route("POST", "/jobs/{id}/{action}")
def job_control(req: Request):
    try:
        return _q().control(req.params["id"], req.params["action"])
    except ValueError as e:
        raise HttpError(400, str(e))


@router.route("DELETE", "/jobs/{id}")
def job_delete(req: Request):
    try:
        _q().delete(req.params["id"])
    except ValueError as e:
        raise HttpError(400, str(e))
    return {"ok": True}


# ---------------------------------------------------------------- exports and cleanup

def exports(p: Project) -> list[dict]:
    base = p.dir / "export"
    cur = (base / "current").resolve() if (base / "current").exists() else None
    out = []
    for f in sorted(base.glob("**/scene.json")):
        rel = f.parent.relative_to(base).as_posix()
        if rel.split("/")[0] == "current":
            continue
        s = read_json(f)
        sog = f.parent / s.get("splat", {}).get("url", "scene.sog")
        edits = f.parent / "clean" / "edits.json"
        out.append({"export": rel, "name": s.get("name"), "current": cur == f.parent.resolve(),
                    "size": sog.stat().st_size if sog.exists() else 0, "mtime": f.stat().st_mtime,
                    "cleanable": bool(s.get("splat", {}).get("source")),
                    "cleaned": read_json(edits) if edits.exists() else None})
    return sorted(out, key=lambda e: e["mtime"], reverse=True)


@router.route("POST", "/projects/{name}/current")
def set_current(req: Request):
    """Point the explorer (http://127.0.0.1:5173/) at one of the project's exports."""
    p = _project(req.params["name"])
    d = clean.export_dir(p, req.json()["export"])
    cur = p.dir / "export" / "current"
    if cur.exists():
        cur.rmdir()  # a junction: removes the link only
    _winapi.CreateJunction(str(d), str(cur))
    write_json(CURRENT_FILE, {"project": p.name, "export": req.json()["export"], "time": time.time()})
    return {"ok": True}


def _clean_target(req: Request) -> tuple[Project, str, Path]:
    p = _project(req.query["project"])
    rel = req.query["export"]
    return p, rel, clean.export_dir(p, rel)


@router.route("GET", "/clean/info")
def clean_info(req: Request):
    p, rel, d = _clean_target(req)
    return {**clean.info(d), "project": p.name, "export": rel}


@router.route("GET", "/clean/source.ply")
def clean_source(req: Request):
    _, _, d = _clean_target(req)
    return FileResponse(clean.scene_source(d))


@router.route("GET", "/clean/mask.bin")
def clean_mask(req: Request):
    _, _, d = _clean_target(req)
    return FileResponse(d / "clean" / "mask.bin")


@router.route("POST", "/clean/apply")
def clean_apply(req: Request):
    p, rel, d = _clean_target(req)
    res = clean.save_mask(d, req.body)
    job = _q().submit(p.name, f"Clean up {rel}: delete {res['deleted']:,} of {res['count']:,} Gaussians",
                      [{"name": "clean", "kind": "clean", "label": "Apply cleanup",
                        "args": ["clean-apply", p.name, "--export", rel], "clear": []}], {"export": rel})
    return {**res, "job": job["id"]}


@router.route("POST", "/clean/reset")
def clean_reset(req: Request):
    p, rel, _ = _clean_target(req)
    job = _q().submit(p.name, f"Undo all cleanup of {rel}",
                      [{"name": "clean", "kind": "clean", "label": "Restore the original splat",
                        "args": ["clean-apply", p.name, "--export", rel, "--reset"], "clear": []}], {"export": rel})
    return {"job": job["id"]}


def main(host: str, port: int) -> None:
    global queue
    from app.server.http import serve

    queue = JobQueue()
    print(f"python {sys.version.split()[0]}, projects in {PROJECTS_DIR}", flush=True)
    serve(router, host, port)
