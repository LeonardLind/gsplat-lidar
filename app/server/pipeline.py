"""Captures (clips that belong to one recording) and the pipeline steps that turn one into a splat.

A capture is a list of clips with trims; clips from one session (same camera and settings, a short
gap such as a battery swap) are suggested as one capture. Running a capture makes these steps, each
a `python -m app ...` command, skipped when its output is already up to date for the settings:

    frames (per clip) -> views (per clip) -> merge-views (2+ clips) -> sfm -> train -> export

Derived folders are cleared before a step reruns: COLMAP reads every image in a folder, so frames
left over from other settings would leak into the solve.
"""
from __future__ import annotations

import json
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from app.core.project import Project, read_json
from app.server import machine

SESSION_GAP_S = 30 * 60   # clips closer than this (same camera and settings) are one recording
SFM_RUN = "aliked_global"


# ---------------------------------------------------------------- probe and captures

def probe(p: Project, clip_id: str) -> dict | None:
    f = p.dir / "probe" / f"{clip_id}.json"
    return read_json(f) if f.exists() else None


def _start(pr: dict) -> float | None:
    ct = pr.get("creation_time")
    if not ct:
        return None
    return datetime.fromisoformat(ct.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()


def clip_summary(p: Project, clip: dict) -> dict:
    pr = probe(p, clip["id"]) or {}
    lens = (pr.get("lenses") or [{}])[0]
    start = _start(pr) if pr else None
    return {
        "id": clip["id"], "path": clip["path"], "name": Path(clip["path"]).name,
        "model": pr.get("model"), "fps": pr.get("fps"), "duration": pr.get("duration_s"),
        "width": lens.get("width"), "height": lens.get("height"), "codec": lens.get("codec"),
        "lenses": len(pr.get("lenses") or []), "size_bytes": pr.get("size_bytes"),
        "start": start, "end": start + pr["duration_s"] if start is not None else None,
        "problems": pr.get("problems", []), "probed": bool(pr),
    }


def _same_settings(a: dict, b: dict) -> bool:
    return (a["model"] == b["model"] and a["width"] == b["width"] and a["lenses"] == b["lenses"]
            and a["fps"] is not None and b["fps"] is not None and abs(a["fps"] - b["fps"]) < 0.01)


def suggest_captures(clips: list[dict]) -> tuple[list[dict], list[dict]]:
    """Group clips into recordings by camera, settings and time gap. Returns (captures, reasons)."""
    clips = sorted([c for c in clips if c["start"] is not None], key=lambda c: c["start"]) + \
        [c for c in clips if c["start"] is None]
    groups: list[list[dict]] = []
    reasons = []
    for c in clips:
        prev = groups[-1][-1] if groups else None
        if prev and prev["end"] is not None and c["start"] is not None and _same_settings(prev, c):
            gap = c["start"] - prev["end"]
            if 0 <= gap <= SESSION_GAP_S:
                groups[-1].append(c)
                reasons.append({"clips": [prev["id"], c["id"]], "gap_s": gap,
                                "text": f"{prev['id']} and {c['id']}: same camera and settings, "
                                        f"{gap / 60:.0f} min apart (battery swap or pause?)"})
                continue
        groups.append([c])
    caps = [{"id": "+".join(x["id"] for x in g), "name": " + ".join(x["id"] for x in g),
             "clips": [{"id": x["id"], "start": 0.0, "end": None} for x in g]} for g in groups]
    return caps, reasons


def captures(p: Project) -> tuple[list[dict], list[dict], bool]:
    """The project's captures (saved by the timeline), or a suggestion when none are saved yet."""
    data = p.load()
    clips = [clip_summary(p, c) for c in p.clips()]
    suggested, reasons = suggest_captures(clips)
    saved = data.get("captures")
    if saved:
        known = {c["id"] for c in clips}
        for cap in saved:
            cap["clips"] = [c for c in cap["clips"] if c["id"] in known]
        used = {c["id"] for cap in saved for c in cap["clips"]}
        saved = [cap for cap in saved if cap["clips"]]
        saved += [cap for cap in suggested if not any(c["id"] in used for c in cap["clips"])]
        return saved, reasons, False
    return suggested, reasons, True


def views_id(cap: dict) -> str:
    """Folder name of a capture's view set: the clip id for one clip, else the capture id."""
    ids = [c["id"] for c in cap["clips"]]
    return ids[0] if len(ids) == 1 else re.sub(r"[^A-Za-z0-9_+-]", "_", cap["id"])


# ---------------------------------------------------------------- steps

def _mtime(f: Path) -> float:
    return f.stat().st_mtime if f.exists() else 0.0


def _rm(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _frames_params(clip: dict, settings: dict) -> dict:
    return {"window_s": round(1.0 / settings["fps"], 4), "start_s": float(clip.get("start") or 0.0),
            "end_s": clip.get("end")}


def _frames_uptodate(p: Project, clip: dict, settings: dict) -> bool:
    f = p.dir / "frames" / clip["id"] / "frames.json"
    if not f.exists():
        return False
    have = read_json(f)["params"]
    want = _frames_params(clip, settings)
    return (abs(have["window_s"] - want["window_s"]) < 1e-3 and abs(have["start_s"] - want["start_s"]) < 1e-3
            and (have.get("end_s") or None) == (want["end_s"] or None))


def build_steps(p: Project, cap: dict, settings: dict) -> tuple[list[dict], dict]:
    """Steps for a capture. Each: {name, label, args, prepare, uptodate, kind}. Also returns run info."""
    vid = views_id(cap)
    steps: list[dict] = []
    for c in cap["clips"]:
        fp = _frames_params(c, settings)
        args = ["frames", p.name, "--clip", c["id"], "--window", f"{fp['window_s']}", "--start", f"{fp['start_s']}"]
        if fp["end_s"] is not None:
            args += ["--end", f"{fp['end_s']}"]
        steps.append({"name": f"frames:{c['id']}", "kind": "frames", "label": f"Pick sharp frames ({c['id']})",
                      "args": args, "clear": [str(p.dir / "frames" / c["id"])],
                      "uptodate": _frames_uptodate(p, c, settings), "clip": c["id"]})
        fj, vj = p.dir / "frames" / c["id"] / "frames.json", p.dir / "views" / c["id"] / "views.json"
        steps.append({"name": f"views:{c['id']}", "kind": "views", "label": f"Make pinhole views ({c['id']})",
                      "args": ["views", p.name, "--clip", c["id"]], "clear": [str(p.dir / "views" / c["id"])],
                      "uptodate": steps[-1]["uptodate"] and _mtime(vj) > _mtime(fj) > 0, "clip": c["id"]})
    if len(cap["clips"]) > 1:
        ids = [c["id"] for c in cap["clips"]]
        mj = p.dir / "views" / vid / "views.json"
        newest = max(_mtime(p.dir / "views" / i / "views.json") for i in ids)
        steps.append({"name": "merge", "kind": "merge", "label": f"Combine clips {' + '.join(ids)}",
                      "args": ["merge-views", p.name, "--clips", ",".join(ids), "--name", vid],
                      "clear": [str(p.dir / "views" / vid)],
                      "uptodate": all(s["uptodate"] for s in steps) and _mtime(mj) > newest > 0})
    vj = p.dir / "views" / vid / "views.json"
    vdir = p.dir / "views" / vid
    people = settings.get("people", True)
    if people:
        # Person detection on every view; SfM masks then hide all people (features on the static scene only).
        pj = vdir / "people.json"
        steps.append({"name": "people", "kind": "people", "label": "Find people (operator, passers-by)",
                      "args": ["people", p.name, "--views", vid], "clear": [str(vdir / "people"), str(pj)],
                      "uptodate": all(s["uptodate"] for s in steps) and _mtime(pj) > _mtime(vj) > 0})
    sfm_dir = p.dir / "sfm" / vid / SFM_RUN
    newest_input = max(_mtime(vj), _mtime(vdir / "people.json") if people else 0)
    sfm_args = ["sfm", p.name, "--views", vid, "--name", SFM_RUN]
    if settings.get("max_features"):  # fewer ALIKED features per image = less VRAM (8 GB cards)
        sfm_args += ["--max-features", str(int(settings["max_features"]))]
    steps.append({"name": "sfm", "kind": "sfm", "label": "Camera solve (SfM)", "args": sfm_args, "clear": [str(sfm_dir)],
                  "uptodate": all(s["uptodate"] for s in steps) and _mtime(sfm_dir / "sfm_report.json") > newest_input > 0,
                  "sfm_dir": str(sfm_dir)})
    if people:
        # With the camera poses: operator and moving people are cut from training, still people stay.
        lj = vdir / "people_labels.json"
        steps.append({"name": "people_classify", "kind": "people_classify", "label": "Keep still people, cut moving ones",
                      "args": ["people-classify", p.name, "--views", vid, "--sfm", SFM_RUN],
                      "clear": [str(vdir / "masks_train"), str(lj)],
                      "uptodate": all(s["uptodate"] for s in steps) and _mtime(lj) > _mtime(sfm_dir / "sfm_report.json") > 0})
    else:
        # Without people masks, training must not pick up training masks left from an earlier run.
        steps.append({"name": "no_people", "kind": "cleanup", "label": "Use the static masks only",
                      "args": ["--noop"], "clear": [str(vdir / "masks_train")], "uptodate": not (vdir / "masks_train").exists()})
    run = settings.get("run") or f"{settings['cap'] // 1000}k_{settings['steps'] // 1000}k_{time.strftime('%m%d-%H%M')}"
    run_dir = p.dir / "train" / vid / run
    targs = ["train", p.name, "--views", vid, "--sfm", SFM_RUN, "--name", run,
             "--steps", str(settings["steps"]), "--cap", str(settings["cap"])]
    if settings.get("viewer", True):
        targs.append("--viewer")
    steps.append({"name": "train", "kind": "train", "label": "Train the splat", "args": targs,
                  "clear": [], "uptodate": False, "run_dir": str(run_dir), "total_steps": settings["steps"]})
    steps.append({"name": "export", "kind": "export", "label": "Export for the viewer",
                  "args": ["export", p.name, "--views", vid, "--run", run, "--formats", "sog"],
                  "clear": [], "uptodate": False, "export_dir": str(p.dir / "export" / vid / run)})
    return steps, {"views_id": vid, "run": run, "run_dir": str(run_dir)}


def clear_outputs(step: dict) -> None:
    for d in step.get("clear", []):
        _rm(Path(d))


# ---------------------------------------------------------------- progress from logs

TQDM_RX = re.compile(r"(\w+):\s+(\d+)%\|[^|]*\|\s*(\d+)/(\d+)")


def _tail(path: Path, n: int = 64 * 1024) -> str:
    if not path.exists():
        return ""
    with open(path, "rb") as f:
        f.seek(max(0, path.stat().st_size - n))
        return f.read().decode("utf-8", errors="replace")


def read_train_progress(run_dir: Path, since: int = 0) -> dict:
    """Series from the launcher's progress.jsonl: loss, Gaussian count, val PSNR, and the latest step."""
    f = run_dir / "progress.jsonl"
    out = {"loss": [], "num_gs": [], "psnr": [], "ssim": [], "step": 0, "total": 0, "state": "run", "t0": None,
           "t_last": None, "rate": None}
    if not f.exists():
        return out
    beats = []
    with open(f, encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            tag, step, t = r.get("tag"), r.get("step"), r.get("t")
            out["t0"] = out["t0"] or t
            out["t_last"] = t
            if tag == "step":
                out["step"], out["total"] = max(out["step"], step or 0), r.get("total") or out["total"]
                beats.append((t, step))
                out["state"] = "run"
            elif tag == "train/loss":
                out["loss"].append([step, r["v"]])
            elif tag == "train/num_GS":
                out["num_gs"].append([step, r["v"]])
            elif tag == "val/psnr":
                out["psnr"].append([step, r["v"]])
            elif tag == "val/ssim":
                out["ssim"].append([step, r["v"]])
            elif tag in ("paused", "stopping", "done"):
                out["state"] = tag
                if step:
                    out["step"] = max(out["step"], step)
    # Speed over the last ~30 s of heartbeats.
    if len(beats) >= 2:
        recent = [b for b in beats if b[0] >= beats[-1][0] - 30] or beats[-2:]
        if len(recent) < 2:
            recent = beats[-2:]
        dt, ds = recent[-1][0] - recent[0][0], recent[-1][1] - recent[0][1]
        out["rate"] = ds / dt if dt > 0 and ds > 0 else None
    for k in ("loss", "num_gs"):  # keep the charts light
        s = out[k]
        if len(s) > 600:
            out[k] = s[:: len(s) // 600 + 1] + [s[-1]]
    return out


def step_progress(step: dict, log: Path) -> dict:
    """{"pct": 0-100 or None, "text": ...} for a running step."""
    kind = step["kind"]
    if kind in ("frames", "views", "merge"):
        hits = TQDM_RX.findall(_tail(log, 8192).replace("\r", "\n"))
        if hits:
            name, pct, i, n = hits[-1]
            if kind == "frames" and name == "write":
                return {"pct": 95 + 5 * int(pct) / 100, "text": f"writing {i}/{n} images"}
            return {"pct": int(pct) * (0.95 if kind == "frames" else 1), "text": f"{name} {i}/{n}"}
        return {"pct": None, "text": "starting"}
    if kind == "sfm":
        clog = Path(step["sfm_dir"]) / "colmap.log"
        text = _tail(clog, 16384)
        # The phase comes from the job log (sfm.py prints "=== colmap <phase>"): in colmap.log the header
        # scrolls out of the tail during long phases.
        phases = re.findall(r"=== colmap (\w+)", _tail(log, 65536))
        phase = phases[-1] if phases else "starting"
        weights = {"feature_extractor": (0, 40), "rig_configurator": (40, 41), "sequential_matcher": (41, 88),
                   "global_mapper": (88, 98), "model_converter": (98, 100)}
        lo, hi = weights.get(phase, (0, 0))
        if f"colmap.exe {phase}" in text:
            text = text.split(f"colmap.exe {phase}")[-1]  # only this phase's lines
        m = re.findall(r"(?:Processed file|Processing image) \[(\d+)/(\d+)\]", text)
        if m:
            i, n = map(int, m[-1])
            return {"pct": lo + (hi - lo) * i / max(n, 1), "text": f"{phase.replace('_', ' ')} {i}/{n}"}
        return {"pct": lo, "text": phase.replace("_", " ")}
    if kind == "people":
        m = re.findall(r"(\d+)/(\d+) images, ([\d.]+)/s", _tail(log, 8192))
        if m:
            i, n, r = m[-1]
            return {"pct": 100 * int(i) / max(int(n), 1), "text": f"{i}/{n} views checked, {r}/s"}
        return {"pct": None, "text": "loading the person detector"}
    if kind == "train":
        tp = read_train_progress(Path(step["run_dir"]))
        total = tp["total"] or step.get("total_steps") or 1
        txt = {"paused": "paused", "stopping": "stopping: saving the result", "done": "finishing"}.get(tp["state"], "")
        return {"pct": 100 * tp["step"] / total, "text": txt or f"step {tp['step']:,}/{total:,}", "rate": tp["rate"],
                "state": tp["state"]}
    return {"pct": None, "text": "working"}


def record_history(step: dict, seconds: float, log: Path) -> None:
    """After a step succeeds: store how fast it ran on this PC, for later estimates."""
    kind = step["kind"]
    try:
        if kind == "frames":
            fj = Path(step["clear"][0]) / "frames.json"
            machine.record_rate("frames", read_json(fj)["decoded_pairs"] / seconds)
        elif kind == "views":
            vj = Path(step["clear"][0]) / "views.json"
            machine.record_rate("views", len(read_json(vj)["frames"]) / seconds)
        elif kind == "sfm":
            sfm_dir = Path(step["sfm_dir"])
            n = read_json(sfm_dir / "sfm_report.json")["num_images"]
            text = log.read_text(encoding="utf-8", errors="replace")
            for phase, key in (("feature_extractor", "sfm_extract"), ("sequential_matcher", "sfm_match"),
                               ("global_mapper", "sfm_map")):
                m = re.search(rf"=== colmap {phase}.*?done in (\d+) s", text, re.S)
                if m and int(m[1]) > 0:
                    machine.record_rate(key, n / int(m[1]))
        elif kind == "people":
            m = re.findall(r"done: .* of (\d+) images \(([\d.]+) min\)", log.read_text(encoding="utf-8", errors="replace"))
            if m and float(m[-1][1]) > 0:
                machine.record_rate("people", int(m[-1][0]) / (float(m[-1][1]) * 60))
        elif kind == "train":
            tp = read_train_progress(Path(step["run_dir"]))
            # Small splats are dominated by fixed per-step costs (data loading) and would skew the scaling.
            if tp["rate"] and tp["num_gs"] and tp["num_gs"][-1][1] >= 200_000:
                machine.record_train(int(tp["num_gs"][-1][1]), 1.0 / tp["rate"])
        elif kind == "export":
            ply_gs = 0
            stats = Path(step["export_dir"]) / "stats.txt"
            m = re.search(r"(\d[\d,]*)\s*(?:splats|gaussians|rows)", _tail(stats, 4096), re.I)
            if m:
                ply_gs = int(m[1].replace(",", ""))
            if ply_gs:
                machine.record_rate("export_per_mgs", seconds / (ply_gs / 1e6))
    except Exception as e:  # noqa: BLE001  (history is best-effort)
        print(f"history not recorded for {step['name']}: {e}")
