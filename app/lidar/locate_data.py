"""Data for the "where was this?" page (web/viewer/locate.html): photos from the key moments of every chunk of the walk
and the LiDAR floor plan. The user clicks on the plan where each photo was taken.

    python -m app.lidar.locate_data <chunks.json> <views dir> [--out web/viewer/public/locate]

Writes <out>/plan.png (same plan as the alignment page), <out>/chunks.json and thumbnails <out>/t/<chunk>_<k>_<view>.jpg.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import cv2

REPO = Path(__file__).resolve().parents[2]
VIEWS = ["lens0_l", "lens0_c", "lens0_r", "lens1_c"]  # left, front, right, back of the operator
LABELS = ["left", "front", "right", "back"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("chunks", type=Path)
    ap.add_argument("views", type=Path)
    ap.add_argument("--out", type=Path, default=REPO / "web" / "viewer" / "public" / "locate")
    ap.add_argument("--size", type=int, default=300)
    ap.add_argument("--placements", type=Path, help="folder with placements.json from solve_clicks: draws the current guess")
    ap.add_argument("--geometry", type=Path, help="chunk_geometry.pkl (camera positions per chunk)")
    ap.add_argument("--flag", default="", help="comma list of chunk ids to check first (they get five photo moments)")
    a = ap.parse_args()
    flagged = {int(x) for x in a.flag.split(",") if x.strip()}
    placed = {}
    if a.placements and a.geometry:
        import pickle

        import numpy as np

        from app.lidar.register import mat_apply

        G = pickle.loads(a.geometry.read_bytes())
        for pc in json.loads((a.placements / "placements.json").read_text())["chunks"]:
            cams = mat_apply(np.array(pc["M"]), G[pc["chunk"]]["cams"])
            placed[pc["chunk"]] = {"path": np.round(cams[::2, :2], 2).tolist(), "score": round(pc["score"], 2),
                                   "click_rms_m": round(pc["click_rms_m"], 1)}
    (a.out / "t").mkdir(parents=True, exist_ok=True)
    plan = REPO / "web" / "viewer" / "public" / "align" / "plan.png"
    shutil.copy(plan, a.out / "plan.png")
    chunks = json.loads(a.chunks.read_text())
    out = []
    for c in chunks:
        fr = c["frames"]
        picks = [("start", fr[0]), ("middle", fr[len(fr) // 2]), ("end", fr[-1])]
        if c["id"] in flagged:  # five moments for the chunks to check: start, quarter, middle, three quarters, end
            picks = [("start", fr[0]), ("quarter", fr[len(fr) // 4]), ("middle", fr[len(fr) // 2]),
                     ("three-quarters", fr[3 * len(fr) // 4]), ("end", fr[-1])]
        moments = []
        for label, frame in picks:
            thumbs = []
            for v, vl in zip(VIEWS, LABELS):
                src = a.views / "images" / v / f"{frame}.png"
                img = cv2.imread(str(src))
                if img is None:
                    continue
                img = cv2.resize(img, (a.size, a.size), interpolation=cv2.INTER_AREA)
                name = f"{c['id']}_{label}_{vl}.jpg"
                cv2.imwrite(str(a.out / "t" / name), img, [cv2.IMWRITE_JPEG_QUALITY, 82])
                thumbs.append({"view": vl, "url": f"t/{name}"})
            moments.append({"label": label, "frame": frame, "thumbs": thumbs})
        out.append({"id": c["id"], "model": c["model"], "n_frames": c["n_frames"], "first_index": c["first_index"],
                    "last_index": c["last_index"], "moments": moments, "check": c["id"] in flagged,
                    "guess": placed.get(c["id"])})
    plan_meta = json.loads((REPO / "web" / "viewer" / "public" / "align" / "m1.json").read_text())["plan"]
    (a.out / "chunks.json").write_text(json.dumps({"plan": plan_meta, "chunks": out}))
    print(f"{len(out)} chunks, {sum(len(m['thumbs']) for c in out for m in c['moments'])} thumbnails -> {a.out}")


if __name__ == "__main__":
    main()
