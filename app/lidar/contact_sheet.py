"""One panel per chunk: its placed path (blue = start, red = end) over the LiDAR plan, with the user's clicks.

    python -m app.lidar.contact_sheet <placements.json dir> <locate.json> <chunk_geometry.pkl> <out.png>
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import cv2
import numpy as np

from app.lidar.register import CELL, load_lidar, mat_apply, walkable_map


def main() -> None:
    d, locate, geo, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
    pl = json.loads((d / "placements.json").read_text())
    marks = json.loads(locate.read_text())
    G = pickle.loads(geo.read_bytes())
    lid, room_h, floor_z, origin = load_lidar(Path(r"C:\dev\gsl-data\data\processed\office_lidar_5cm.npz"))
    ext = (lid[:, 0].min() - 10, lid[:, 0].max() + 10, lid[:, 1].min() - 10, lid[:, 1].max() + 10)
    _, floor_m, wall_m = walkable_map(lid, ext)
    P = 420  # panel size in pixels
    panels = []
    for c in pl["chunks"]:
        k = c["chunk"]
        cams = mat_apply(np.array(c["M"]), G[k]["cams"])
        pts = [np.array([m["x"], m["y"]]) for m in marks.get(str(k), {}).values()]
        allp = np.vstack([cams[:, :2]] + ([np.array(pts)] if pts else []))
        lo, hi = allp.min(axis=0) - 3, allp.max(axis=0) + 3
        size = float(max(hi - lo)) + 1e-6
        mid = (lo + hi) / 2
        x0, y0 = mid[0] - size / 2, mid[1] - size / 2
        img = np.zeros((P, P, 3), np.uint8)
        # plan masks sampled into the panel
        gx = ((x0 + (np.arange(P) + 0.5) * size / P - ext[0]) / CELL).astype(int)
        gy = ((y0 + (P - 1 - np.arange(P) + 0.5) * size / P - ext[2]) / CELL).astype(int)
        okx = (gx >= 0) & (gx < floor_m.shape[0])
        oky = (gy >= 0) & (gy < floor_m.shape[1])
        X, Y = np.meshgrid(np.clip(gx, 0, floor_m.shape[0] - 1), np.clip(gy, 0, floor_m.shape[1] - 1))
        valid = np.outer(oky, okx)
        img[(floor_m[X, Y] > 0) & valid] = (50, 50, 50)
        img[(wall_m[X, Y] > 0) & valid] = (170, 170, 170)

        def pix(xy):
            return int((xy[0] - x0) / size * P), int(P - 1 - (xy[1] - y0) / size * P)

        for i, p in enumerate(cams):
            t = i / max(len(cams) - 1, 1)
            col = (int(255 * (1 - t)), 80, int(255 * t))  # BGR: blue at the start, red at the end
            cv2.circle(img, pix(p[:2]), 3, col, -1)
        for label, m in marks.get(str(k), {}).items():
            col = {"start": (0, 255, 0), "middle": (0, 255, 255), "end": (0, 120, 255)}[label]
            cv2.circle(img, pix((m["x"], m["y"])), 9, col, 2)
            cv2.putText(img, label[0], (pix((m["x"], m["y"]))[0] + 10, pix((m["x"], m["y"]))[1] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1)
        cv2.putText(img, f"chunk {k}  score {c['score']:.2f}  clicks off {c['click_rms_m']:.1f} m", (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(img, f"{size:.0f} m wide", (6, P - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
        cv2.rectangle(img, (0, 0), (P - 1, P - 1), (90, 90, 90), 1)
        panels.append(img)
    cols = 4
    while len(panels) % cols:
        panels.append(np.zeros((P, P, 3), np.uint8))
    rows = [np.hstack(panels[i:i + cols]) for i in range(0, len(panels), cols)]
    cv2.imwrite(str(out), np.vstack(rows))
    print(f"{len(pl['chunks'])} panels -> {out}")


if __name__ == "__main__":
    main()
