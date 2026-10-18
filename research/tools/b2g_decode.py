"""Decode BLK2GO .b2g trajectory + IMU (read-only) and sanity-check them against each other.

Hypothesised layouts (from blob inspection):
  bodytrajectories.points : N x 40 B = u64 ts | 7 x f32 (3 position + 4 quaternion, order TBD) | u32 pad
  imudata.points          : u32 header | N x 36 B = u64 ts | 6 x f32 (accel xyz, gyro xyz) | u32 id
"""
import json
import pathlib
import sqlite3
import sys

import numpy as np

p = pathlib.Path(sys.argv[1]).resolve()
con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro&immutable=1", uri=True)
cur = con.cursor()
cfg = dict(cur.execute("SELECT key, value FROM config"))
clock = float(cfg["ClockFrequency"])
print("ClockFrequency", clock)
ns = cfg.get("scan/navigation-solutions/1")
if ns:
    print("navigation-solution JSON:\n", ns[:3000])

# ---- trajectory
traj_dt = np.dtype([("ts", "<u8"), ("f", "<f4", (7,)), ("pad", "<u4")])
chunks = []
for (blob,) in cur.execute("SELECT points FROM bodytrajectories WHERE streamId='1' ORDER BY minTs"):
    assert len(blob) % 40 == 0, len(blob)
    chunks.append(np.frombuffer(blob, dtype=traj_dt))
T = np.concatenate(chunks)
t = T["ts"].astype(np.float64) / clock
F = T["f"].astype(np.float64)
print(f"\ntrajectory poses {len(T)}  span {t[-1]-t[0]:.2f} s  median dt {np.median(np.diff(t))*1e3:.3f} ms  pad unique {np.unique(T['pad'])[:5]}")
print("monotonic ts:", bool(np.all(np.diff(T['ts']) > 0)))
for i in range(7):
    print(f"  f{i}: min {F[:, i].min():9.4f} max {F[:, i].max():9.4f} mean {F[:, i].mean():9.4f}")
qn_a = np.linalg.norm(F[:, 3:7], axis=1)
qn_b = np.linalg.norm(F[:, 0:4], axis=1)
print("norm f3..f6 (pos-first layout): min %.6f max %.6f" % (qn_a.min(), qn_a.max()))
print("norm f0..f3 (quat-first layout): min %.6f max %.6f" % (qn_b.min(), qn_b.max()))
pos = F[:, 0:3] if abs(qn_a.mean() - 1) < abs(qn_b.mean() - 1) else F[:, 4:7]
quat = F[:, 3:7] if abs(qn_a.mean() - 1) < abs(qn_b.mean() - 1) else F[:, 0:4]
step = np.linalg.norm(np.diff(pos, axis=0), axis=1)
print("path length %.1f m | bbox %s | start %s | end %s" % (step.sum(), np.round(pos.max(0) - pos.min(0), 2), np.round(pos[0], 3), np.round(pos[-1], 3)))
print("speed median %.2f m/s, p95 %.2f m/s" % (np.median(step / np.diff(t)), np.percentile(step / np.diff(t), 95)))

# angular rate from quaternions: try both component orders (x,y,z,w) and (w,x,y,z)
from scipy.spatial.transform import Rotation as R

def ang_rate(qxyzw):
    rot = R.from_quat(qxyzw)
    rel = rot[:-1].inv() * rot[1:]
    return np.linalg.norm(rel.as_rotvec(), axis=1) / np.diff(t)

w_xyzw = ang_rate(quat)                                   # stored as x,y,z,w
w_wxyz = ang_rate(np.c_[quat[:, 1:4], quat[:, 0]])          # stored as w,x,y,z
print("traj |omega| (if x,y,z,w): median %.3f p99 %.3f rad/s" % (np.median(w_xyzw), np.percentile(w_xyzw, 99)))
print("traj |omega| (if w,x,y,z): median %.3f p99 %.3f rad/s" % (np.median(w_wxyz), np.percentile(w_wxyz, 99)))

# ---- IMU
imu_dt = np.dtype([("ts", "<u8"), ("v", "<f4", (6,)), ("id", "<u4")])
ich = []
for (blob,) in cur.execute("SELECT points FROM imudata ORDER BY minTs"):
    body = blob[4:]
    n = len(body) // 36
    ich.append(np.frombuffer(body[: n * 36], dtype=imu_dt))
I = np.concatenate(ich)
ti = I["ts"].astype(np.float64) / clock
V = I["v"].astype(np.float64)
print(f"\nIMU samples {len(I)}  span {ti[-1]-ti[0]:.2f} s  median dt {np.median(np.diff(ti))*1e3:.3f} ms  ids {np.unique(I['id'])}")
for i, nm in enumerate(["v0", "v1", "v2", "v3", "v4", "v5"]):
    print(f"  {nm}: min {V[:, i].min():9.4f} max {V[:, i].max():9.4f} mean {V[:, i].mean():9.4f}")
acc_n = np.linalg.norm(V[:, 0:3], axis=1); gyr_n = np.linalg.norm(V[:, 3:6], axis=1)
print("|v0..2| median %.3f (gravity-like ~9.8?) | |v3..5| median %.4f p99 %.3f" % (np.median(acc_n), np.median(gyr_n), np.percentile(gyr_n, 99)))

# ---- consistency: correlate |gyro| with trajectory |omega| (both on the same clock)
for name, w in (("x,y,z,w", w_xyzw), ("w,x,y,z", w_wxyz)):
    tm = 0.5 * (t[:-1] + t[1:])
    g_on_traj = np.interp(tm, ti, gyr_n)
    m = np.isfinite(w) & (tm > ti[0]) & (tm < ti[-1])
    c = np.corrcoef(w[m], g_on_traj[m])[0, 1]
    # lag search +-200 ms
    best = (None, -1)
    for lag in np.arange(-0.2, 0.2001, 0.005):
        gl = np.interp(tm[m] + lag, ti, gyr_n)
        cc = np.corrcoef(w[m], gl)[0, 1]
        if cc > best[1]:
            best = (lag, cc)
    print(f"corr(|gyro|, traj |omega| as {name}) = {c:.3f}; best lag {best[0]*1e3:+.0f} ms -> {best[1]:.3f}")

# ---- clock anchor
epoch_ns = int(cfg["metadata/device/system-epoch-ns"]); fpga = int(cfg["metadata/device/main-fpga-ticks"])
import datetime as dt
def utc(ticks):
    return dt.datetime.fromtimestamp((epoch_ns + (ticks - fpga) * 1e9 / clock) / 1e9, dt.timezone.utc)
print("\nclock anchor: tick", fpga, "->", utc(fpga).isoformat())
print("trajectory start", utc(int(T['ts'][0])).isoformat(), "end", utc(int(T['ts'][-1])).isoformat())
print("config scan time-started", cfg.get("metadata/scan/time-started"), "time-finished", cfg.get("metadata/scan/time-finished"))
for ts, et in cur.execute("SELECT ts, eventType FROM timestampedevents"):
    print("event", et, "at", utc(ts).isoformat(), f"(t={ts/clock:.3f} s)")
for ts, et, d in cur.execute("SELECT ts, eventType, eventDescription FROM slamevents"):
    print("slam event", d, "at", f"t={ts/clock:.3f} s")
