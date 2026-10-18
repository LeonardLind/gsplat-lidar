"""Find the quaternion component order and direction (body->world vs world->body) of BLK2GO poses,
using gravity (accelerometer) and gyro-vs-trajectory body rates. Read-only."""
import pathlib
import sqlite3
import sys

import numpy as np
from scipy.spatial.transform import Rotation as R, Slerp

p = pathlib.Path(sys.argv[1]).resolve()
con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro&immutable=1", uri=True)
cur = con.cursor()
clock = 125e6
tdt = np.dtype([("ts", "<u8"), ("f", "<f4", (7,)), ("pad", "<u4")])
T = np.concatenate([np.frombuffer(b, dtype=tdt) for (b,) in cur.execute("SELECT points FROM bodytrajectories WHERE streamId='1' ORDER BY minTs")])
idt = np.dtype([("ts", "<u8"), ("v", "<f4", (6,)), ("id", "<u4")])
I = np.concatenate([np.frombuffer(b[4:4 + ((len(b) - 4) // 36) * 36], dtype=idt) for (b,) in cur.execute("SELECT points FROM imudata ORDER BY minTs")])
t = T["ts"] / clock; q = T["f"][:, 3:7].astype(float)
ti = I["ts"] / clock; acc = I["v"][:, :3].astype(float); gyr = I["v"][:, 3:6].astype(float)
m = (ti > t[0] + 1) & (ti < t[-1] - 1)
ti, acc, gyr = ti[m], acc[m], gyr[m]

orders = {"xyzw": q, "wxyz": np.c_[q[:, 1:4], q[:, 0]]}
for name, qq in orders.items():
    rot = R.from_quat(qq)
    sl = Slerp(t, rot)
    r_i = sl(ti)
    for direction in ("body->world", "world->body"):
        rr = r_i if direction == "body->world" else r_i.inv()
        wa = rr.apply(acc)                       # accel expressed in world
        # low-pass ~1 s to suppress walking accelerations
        k = 200
        wa_s = np.cumsum(wa, axis=0); wa_s = (wa_s[k:] - wa_s[:-k]) / k
        mean = wa_s.mean(0); spread = np.linalg.norm(wa_s - mean, axis=1).mean()
        # body angular rate from trajectory vs gyro (vector agreement after best-fit rotation)
        dt = 0.005
        r_a, r_b = sl(ti[:-2] + 0.010), sl(ti[:-2] + 0.010 + dt)   # include the ~10 ms internal lag
        rel = (r_a.inv() * r_b) if direction == "body->world" else (r_b * r_a.inv())
        w_body = rel.as_rotvec() / dt
        g = gyr[:-2]
        sel = np.linalg.norm(g, axis=1) > 0.3
        rot_fit, rssd = R.align_vectors(w_body[sel], g[sel])
        resid = np.linalg.norm(w_body[sel] - rot_fit.apply(g[sel]), axis=1)
        print(f"{name:5s} {direction:12s} gravity(world) mean={np.round(mean, 2)} |spread|={spread:.3f} m/s2 | "
              f"gyro->body rot {np.round(rot_fit.as_euler('xyz', degrees=True), 1)} deg, median resid {np.median(resid):.3f} rad/s")
