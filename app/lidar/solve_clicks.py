"""Place every chunk of the walk into the LiDAR frame from the user's clicks (web/viewer/locate.html).

    python -m app.lidar.solve_clicks <sparse dir> <chunks.json> <locate.json> <out dir>

A click says where the start, middle or end photo of a chunk was taken (an optional drag adds the direction the
front picture looks). With two or more such points a chunk has few possible placements left: for every up axis,
scale and yaw the translation is the least-squares fit to the clicks, a small neighbourhood is searched, and the
placement whose camera path stays over the floor and out of walls and closest to the clicks wins.

Writes <out>/placements.json (4x4 similarity per chunk: model frame -> LiDAR frame), overlay.png, and a table.
"""
from __future__ import annotations

import argparse
import json
import pickle
import time
from pathlib import Path

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from app.lidar.chain import CELL, chunk_geometry, load_models
from app.lidar.register import load_lidar, mat_apply, sim3_matrix, up_candidates, walkable_map
from app.stages.ply_scene import orient_room


def bases_for(cams, pts, room_h):
    out = []
    if len(pts) > 200:
        for ui, up in enumerate(up_candidates(pts, np.array([[0.0, 1.0, 0.0]]))[:2]):
            try:
                tr, info = orient_room(pts, up, room_h)
            except Exception:  # noqa: BLE001
                continue
            M0 = sim3_matrix(tr["scale"], Rotation.from_quat(tr["quaternion_xyzw"]).as_matrix(), np.array(tr["position"]))
            z = mat_apply(M0, cams)[:, 2]
            ok = info["angle_floor_ceiling_deg"] < 6 and np.percentile(z, 5) > 0.2 and np.percentile(z, 95) < room_h + 0.3
            out.append({"M0": M0, "ok": bool(ok), "scale": float(tr["scale"])})
    return out


def lookup(walk, ext, xy):
    ix = ((xy[..., 0] - ext[0]) / CELL).astype(int)
    iy = ((xy[..., 1] - ext[2]) / CELL).astype(int)
    ok = (ix >= 0) & (ix < walk.shape[0]) & (iy >= 0) & (iy < walk.shape[1])
    v = np.full(xy.shape[:-1], -1.0)
    v[ok] = walk[ix[ok], iy[ok]]
    return v


def solve_chunk(cams_raw, bases, marks, walk, ext, room_h):
    n = len(cams_raw)
    idx = {"start": 0, "middle": n // 2, "end": n - 1}
    pts = [(idx[l], np.array([m["x"], m["y"]]), m.get("heading")) for l, m in marks.items() if l in idx]
    if len(pts) < 2:
        return None
    ii = np.array([p[0] for p in pts])
    clicks = np.array([p[1] for p in pts])
    heads = [(p[0], p[2]) for p in pts if p[2] is not None]
    dc = np.linalg.norm(clicks[-1] - clicks[0]) if len(pts) > 1 else 0.0
    best = None
    shifts = np.array([[dx, dy] for dx in np.arange(-1.0, 1.01, 0.5) for dy in np.arange(-1.0, 1.01, 0.5)])
    for bi, b in enumerate(bases):
        cb = mat_apply(b["M0"], cams_raw)
        dp = np.linalg.norm(cb[ii[-1], :2] - cb[ii[0], :2])
        scales = [f for f in (0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15)] if b["ok"] else []
        if dp > 3 and dc > 3:
            fc = float(np.clip(dc / dp, 0.4, 2.5))
            scales += [fc * k for k in (0.9, 1.0, 1.1)]
        for f in scales:
            cf = cb * f
            for yaw in np.arange(0, 360, 3.0):
                Rz = Rotation.from_euler("z", yaw, degrees=True).as_matrix()
                q = cf @ Rz.T
                t0 = (clicks - q[ii, :2]).mean(axis=0)
                resid0 = np.sqrt(((clicks - (q[ii, :2] + t0)) ** 2).sum(axis=1).mean())
                if resid0 > 6.0:  # the clicks and the path shape disagree strongly: not worth scoring
                    continue
                cand = t0[None, :] + shifts  # (S, 2)
                xy = q[None, :, :2] + cand[:, None, :]  # (S, N, 2)
                walk_score = lookup(walk, ext, xy).mean(axis=1)  # (S,)
                res = np.sqrt(((clicks[None] - (q[ii, :2][None] + cand[:, None, :])) ** 2).sum(axis=2).mean(axis=1))
                h_term = np.zeros(len(cand))
                for i, h in heads:
                    j0, j1 = max(i - 3, 0), min(i + 3, n - 1)
                    d = q[j1, :2] - q[j0, :2]
                    if np.linalg.norm(d) > 0.3:
                        h_term += 0.15 * float(np.cos(np.arctan2(d[1], d[0]) - h))
                total = walk_score - 0.12 * res + h_term
                k = int(np.argmax(total))
                if best is None or total[k] > best["score"]:
                    M = np.eye(4)
                    M[:3, :3] = Rz
                    M[:3, 3] = np.r_[cand[k], 0.0]
                    S = np.diag([f, f, f, 1.0])
                    best = {"score": float(total[k]), "walk": float(walk_score[k]), "click_rms_m": float(res[k]),
                            "M": M @ S @ b["M0"], "yaw": float(yaw), "f": float(f), "base": bi, "ok": b["ok"]}
    return best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sparse", type=Path)
    ap.add_argument("chunks", type=Path)
    ap.add_argument("locate", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--lidar", type=Path, default=Path(r"C:\dev\gsl-data\data\processed\office_lidar_5cm.npz"))
    a = ap.parse_args()
    t0 = time.time()
    a.out.mkdir(parents=True, exist_ok=True)
    chunks = json.loads(a.chunks.read_text())
    marks = json.loads(a.locate.read_text())
    lid, room_h, floor_z, origin = load_lidar(a.lidar)
    ext = (lid[:, 0].min() - 10, lid[:, 0].max() + 10, lid[:, 1].min() - 10, lid[:, 1].max() + 10)
    walk, floor_m, wall_m = walkable_map(lid, ext)

    cache = a.out.parent / "chunk_geometry.pkl"
    if cache.exists():
        G = pickle.loads(cache.read_bytes())
    else:
        models = load_models(a.sparse, {c["model"] for c in chunks})
        G = []
        for c in chunks:
            cams, pts = chunk_geometry(models[c["model"]], c["frames"])
            G.append({"cams": cams, "bases": bases_for(cams, pts, room_h)})
            print(f"  geometry chunk {c['id']}: {len(cams)} cameras ({time.time() - t0:.0f} s)", flush=True)
        cache.write_bytes(pickle.dumps(G))

    placed = {}
    for c in chunks:
        k = c["id"]
        mk = marks.get(str(k))
        if not mk or not G[k]["bases"]:
            print(f"  chunk {k:2d}: {'no clicks' if not mk else 'no base frame'}, skipped")
            continue
        r = solve_chunk(G[k]["cams"], G[k]["bases"], mk, walk, ext, room_h)
        if r is None:
            print(f"  chunk {k:2d}: needs at least two clicks, skipped")
            continue
        placed[k] = r
        print(f"  chunk {k:2d}: score {r['score']:.2f}, over-floor value {r['walk']:.2f}, clicks off by {r['click_rms_m']:.1f} m, "
              f"scale x{r['f']:.2f} ({'planes' if r['ok'] else 'clicks'}), yaw {r['yaw']:.0f} ({time.time() - t0:.0f} s)", flush=True)

    out = [{"chunk": k, "model": chunks[k]["model"], "frames": [chunks[k]["first_frame"], chunks[k]["last_frame"]],
            "M": r["M"].tolist(), "score": r["score"], "walk": r["walk"], "click_rms_m": r["click_rms_m"]} for k, r in sorted(placed.items())]
    (a.out / "placements.json").write_text(json.dumps({"lidar_floor_z": floor_z, "lidar_origin": origin.tolist(), "chunks": out}))

    res = CELL / 2
    W, H = int((ext[1] - ext[0]) / res), int((ext[3] - ext[2]) / res)
    img = np.zeros((H, W, 3), np.uint8)
    big = lambda m: cv2.resize(m.astype(np.uint8), (H, W), interpolation=cv2.INTER_NEAREST).T[::-1]  # noqa: E731
    img[big(floor_m) > 0] = (45, 45, 45)
    img[big(wall_m) > 0] = (150, 150, 150)
    for k, r in sorted(placed.items()):
        col = tuple(int(x) for x in cv2.cvtColor(np.uint8([[[(k * 137) % 180, 200, 255]]]), cv2.COLOR_HSV2BGR)[0, 0])
        cams = mat_apply(r["M"], G[k]["cams"])
        px = np.stack([((cams[:, 0] - ext[0]) / res).astype(int), H - 1 - ((cams[:, 1] - ext[2]) / res).astype(int)], 1)
        for x, y in px:
            if 0 <= x < W and 0 <= y < H:
                cv2.circle(img, (x, y), 3, col, -1)
        x, y = px[0]
        cv2.putText(img, str(k), (int(x) + 5, int(y) - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.9, col, 2)
        for l, m in marks.get(str(k), {}).items():  # the user's clicks as white rings
            cx, cy = int((m["x"] - ext[0]) / res), H - 1 - int((m["y"] - ext[2]) / res)
            cv2.circle(img, (cx, cy), 7, (255, 255, 255), 1)
    keep = np.abs(img.sum(axis=2)) > 0
    ys, xs = np.nonzero(keep)
    cv2.imwrite(str(a.out / "overlay.png"), img[max(ys.min() - 20, 0): ys.max() + 20, max(xs.min() - 20, 0): xs.max() + 20])
    print(f"done: {len(placed)} chunks placed ({time.time() - t0:.0f} s) -> {a.out}")


if __name__ == "__main__":
    main()
