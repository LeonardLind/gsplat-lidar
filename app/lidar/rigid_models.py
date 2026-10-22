"""Place every SfM model as ONE rigid piece in the LiDAR frame (instead of one placement per chunk / stretch).

    python -m app.lidar.rigid_models <sparse dir> <chunks.json> <placements dir> <out dir> --heights 0-8:1.13,9-14:2.22

Why: the stretch-wise placements (solve_clicks --split + refine_icp) put each stretch where the clicks say, but with
its own scale, so neighbouring views disagree by decimetres and the joined splat blurs (held-out PSNR 15 dB at 7k
steps vs 17-19 dB for the same frames trained as one SfM model). An SfM model may be bent in metres but is
photometrically consistent in itself, which is what training needs.

For each model: one similarity that best maps the model-frame cameras of all its chunks onto their current
placements (Umeyama), then 7-DoF ICP of the model's points onto the LiDAR, kept only if the camera heights stay
within 0.3 m of the pass height. Writes <out>/placements.json in the solve_clicks format (one entry per chunk, all
chunks of a model share the matrix), plus a table of how far each chunk moves from its own placement.
"""
from __future__ import annotations

import argparse
import json
import pickle
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from app.lidar.chain import load_models
from app.lidar.merge import stem_of
from app.lidar.refine_icp import icp, umeyama
from app.lidar.register import load_lidar, mat_apply
from app.lidar.solve_clicks import parse_heights


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sparse", type=Path)
    ap.add_argument("chunks", type=Path)
    ap.add_argument("placements", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--heights", default="")
    ap.add_argument("--lidar", type=Path, default=Path(r"C:\dev\gsl-data\data\processed\office_lidar_5cm.npz"))
    a = ap.parse_args()
    chunks = json.loads(a.chunks.read_text())
    src = json.loads((a.placements / "placements.json").read_text())
    G = pickle.loads((a.placements.parent / "chunk_geometry.pkl").read_bytes())
    heights = parse_heights(a.heights)
    lid, *_ = load_lidar(a.lidar)
    tree = cKDTree(lid)

    by_model = defaultdict(list)
    for p in src["chunks"]:
        by_model[p["model"]].append(p)
    models = load_models(a.sparse, set(by_model))
    out = []
    for name, parts in sorted(by_model.items(), key=lambda kv: min(p["chunk"] for p in kv[1])):
        ks = sorted({p["chunk"] for p in parts})
        raw = np.vstack([G[p["chunk"]]["cams"][p["range"][0]:p["range"][1] + 1] for p in parts])
        placed = np.vstack([mat_apply(np.array(p["M"]), G[p["chunk"]]["cams"][p["range"][0]:p["range"][1] + 1]) for p in parts])
        M0 = umeyama(raw, placed)
        # points seen by the images of this model's chunks
        r = models[name]
        want = {f for k in ks for f in chunks[k]["frames"]}
        ids = {i for i in r.reg_image_ids() if stem_of(r.images[i].name)[1] in want}
        pts = np.array([q.xyz for q in r.points3D.values() if q.error < 2.0 and q.track.length() >= 3
                        and any(e.image_id in ids for e in q.track.elements)])
        H = np.array([heights.get(k, np.nan) for k in ks])
        M1, inl = icp(pts, M0, tree, lid)
        z1 = {k: float(np.median(mat_apply(M1, G[k]["cams"])[:, 2])) for k in ks}
        bad = [k for k in ks if k in heights and abs(z1[k] - heights[k]) > 0.3]
        if bad:
            M1, inl = M0, icp(pts, M0, tree, lid, iters=0)[1]
        z = {k: float(np.median(mat_apply(M1, G[k]["cams"])[:, 2])) for k in ks}
        moved = np.linalg.norm(mat_apply(M1, raw) - placed, axis=1)
        print(f"model {name:>3} (chunks {','.join(map(str, ks))}): {len(raw)} cameras, {len(pts)} pts, "
              f"{'ICP kept' if not bad else f'ICP dropped (height off for chunks {bad})'}, points within 15 cm {inl:.0%}, "
              f"cameras vs stretch placements: median {np.median(moved):.2f} m, p90 {np.percentile(moved, 90):.2f} m; "
              f"camera heights " + ", ".join(f"{k}: {z[k]:.2f}" for k in ks), flush=True)
        for k in ks:
            n = len(G[k]["cams"])
            out.append({"chunk": k, "range": [0, n - 1], "model": name, "frames": [chunks[k]["first_frame"], chunks[k]["last_frame"]],
                        "M": M1.tolist(), "score": float(inl), "walk": 0.0, "click_rms_m": float(np.median(moved)),
                        "camera_height_m": z[k], "icp_inliers": float(inl)})
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "placements.json").write_text(json.dumps({**src, "chunks": sorted(out, key=lambda p: p["chunk"])}))
    print(f"{len(by_model)} models, {len(out)} chunks -> {a.out}")


if __name__ == "__main__":
    main()
