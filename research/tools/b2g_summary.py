"""One-screen summary of BLK2GO .b2g scans (read-only): capture time in UTC, duration, walking path
(length, extent, height range), image counts. Layout as decoded in research/b2g-findings.md.

    python b2g_summary.py <scan.b2g> [<scan2.b2g> ...] [--json out.json]
"""
import json
import pathlib
import sqlite3
import sys
from datetime import datetime, timezone

import numpy as np

TRAJ = np.dtype([("ts", "<u8"), ("f", "<f4", (7,)), ("pad", "<u4")])


def summary(path: pathlib.Path) -> dict:
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro&immutable=1", uri=True)
    cur = con.cursor()
    cfg = dict(cur.execute("SELECT key, value FROM config"))
    clock = float(cfg["ClockFrequency"])
    # Older firmware: "system-epoch-ns"; newer (2026-10 scans): "metadata/device/system-epoch-ns".
    key = lambda name: next(v for k, v in cfg.items() if k == name or k.endswith("/" + name))
    epoch_ns, fpga = int(key("system-epoch-ns")), int(key("main-fpga-ticks"))
    utc = lambda ticks: datetime.fromtimestamp((epoch_ns + (int(ticks) - fpga) * 1e9 / clock) / 1e9, timezone.utc)
    T = np.concatenate([np.frombuffer(b, dtype=TRAJ) for (b,) in
                        cur.execute("SELECT points FROM bodytrajectories WHERE streamId='1' ORDER BY minTs")])
    pos = T["f"][:, :3].astype(np.float64)  # position first, then quaternion (b2g-findings.md)
    step = np.linalg.norm(np.diff(pos[::20], axis=0), axis=1)  # 10 Hz
    tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    count = lambda t: cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] if t in tables else None
    out = {
        "file": path.name, "size_mb": round(path.stat().st_size / 1e6),
        "device": {k: cfg.get(k) for k in cfg if "serial" in k.lower() or "firmware" in k.lower()},
        "start_utc": utc(T["ts"][0]).isoformat(timespec="seconds"),
        "end_utc": utc(T["ts"][-1]).isoformat(timespec="seconds"),
        "duration_s": round(float((T["ts"][-1] - T["ts"][0]) / clock), 1),
        "poses": int(len(T)),
        "path_length_m": round(float(step.sum()), 1),
        "extent_m": [round(float(x), 2) for x in pos.max(0) - pos.min(0)],
        "height_range_m": round(float(np.percentile(pos[:, 2], 99) - np.percentile(pos[:, 2], 1)), 2),
        "pano_images": count("panoimagedata"), "detail_images": count("userimagedata"),
    }
    con.close()
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    out_json = None
    if "--json" in args:
        k = args.index("--json")
        out_json, args = args[k + 1], args[:k] + args[k + 2:]
    res = [summary(pathlib.Path(a)) for a in args]
    for r in res:
        print(json.dumps(r, indent=1))
    if out_json:
        pathlib.Path(out_json).write_text(json.dumps(res, indent=2))
