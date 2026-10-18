"""End-to-end test of the studio job server: a throwaway project with a short trimmed clip goes through
every stage (frames, views, SfM, a short training, export), with pause/resume and stop-and-keep tried
on the training step.

    C:\\dev\\envs\\pipe\\Scripts\\python.exe tools/test_pipeline.py <insv> [--project studio-test]
"""
import argparse
import json
import time
import urllib.error
import urllib.request

B = "http://127.0.0.1:8765/studio-api"


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
    req = urllib.request.Request(B + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path}: {e.code} {e.read().decode()[:300]}")


ap = argparse.ArgumentParser()
ap.add_argument("insv")
ap.add_argument("--project", default="studio-test")
ap.add_argument("--start", type=float, default=20)
ap.add_argument("--end", type=float, default=35)
ap.add_argument("--fps", type=float, default=2)
ap.add_argument("--steps", type=int, default=3000)
a = ap.parse_args()

if a.project not in [p["name"] for p in call("GET", "/projects")]:
    call("POST", "/projects", {"name": a.project})
proj = call("GET", f"/projects/{a.project}")
if not proj["clips"]:
    print("added:", call("POST", f"/projects/{a.project}/clips", {"path": a.insv})["id"])
proj = call("GET", f"/projects/{a.project}")
cid = proj["clips"][0]["id"]
cap = {"id": cid, "name": "test", "clips": [{"id": cid, "start": a.start, "end": a.end}]}
settings = {"fps": a.fps, "cap": 300_000, "steps": a.steps, "viewer": True}
call("PUT", f"/projects/{a.project}/captures", {"captures": [cap], "settings": settings})
est = call("POST", f"/projects/{a.project}/estimate", {"capture_id": cid, "settings": settings})
print(f"estimate: {est['frames']} frames, {est['images']} images, total {est['total_seconds'] / 60:.1f} min:",
      ", ".join(f"{s['stage']} {s['seconds'] / 60:.1f}" for s in est["stages"]))
job = call("POST", f"/projects/{a.project}/run", {"capture_id": cid, "settings": settings})
jid = job["id"]
print("job", jid, "steps:", [s["name"] for s in job["steps"]])

t0 = time.time()
last_print = 0
paused_checked = stopped = False
while True:
    j = call("GET", f"/jobs/{jid}")
    run = next((s for s in j["steps"] if s["status"] == "running"), None)
    if time.time() - last_print > 20 or j["status"] not in ("queued", "running", "paused"):
        last_print = time.time()
        prog = run and run.get("progress") or {}
        print(f"[{(time.time() - t0) / 60:5.1f} min] {j['status']:<8} "
              f"{run['name'] if run else '-':<12} {prog.get('pct') or 0:5.1f}% {prog.get('text', '')}", flush=True)
    if j["status"] not in ("queued", "running", "paused"):
        break
    if run and run["kind"] == "train":
        tp = call("GET", f"/jobs/{jid}/train")
        if not paused_checked and tp["step"] > 600:
            call("POST", f"/jobs/{jid}/pause")
            time.sleep(6)
            s1 = call("GET", f"/jobs/{jid}/train")["step"]
            time.sleep(5)
            tp2 = call("GET", f"/jobs/{jid}/train")
            print(f"   pause: step {s1} -> {tp2['step']} after 5 s, state {tp2['state']}  (should not move)")
            call("POST", f"/jobs/{jid}/resume")
            time.sleep(6)
            print(f"   resumed: step {call('GET', f'/jobs/{jid}/train')['step']}")
            paused_checked = True
        elif paused_checked and not stopped and tp["step"] > 1500:
            print(f"   stop-and-keep at step {tp['step']} of {tp['total']}")
            call("POST", f"/jobs/{jid}/stop")
            stopped = True
    time.sleep(2)

j = call("GET", f"/jobs/{jid}")
for s in j["steps"]:
    dur = f"{s['ended'] - s['started']:.0f} s" if s.get("started") and s.get("ended") else ""
    print(f"  {s['name']:<12} {s['status']:<9} {dur}")
tp = call("GET", f"/jobs/{jid}/train")
print("train series:", {k: len(tp[k]) for k in ("loss", "num_gs", "psnr")}, "last psnr:", tp["psnr"][-1:] if tp["psnr"] else None,
      "state:", tp["state"], "step:", tp["step"])
proj = call("GET", f"/projects/{a.project}")
print("exports:", [(e["export"], e["size"]) for e in proj["exports"]])
