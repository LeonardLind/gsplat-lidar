"""Find places the walk revisits and list the view pairs to match there (loop closure without a vocabulary tree).

Sequential matching only links neighbouring frames, so a walk that is cut into pieces by a few near-empty links
(068+069 office run, 2026-10-21) has nothing tying the pieces together, although the capture passes the same
places twice. Here every 360 frame gets a place fingerprint (bag of visual words over all its ALIKED descriptors,
tf-idf weighted), frames that look alike but are far apart in the walk become candidates, and for each candidate
frame pair the best-looking view pairs are written out for `colmap matches_importer`.

Runs in the `gs` environment (torch, GPU for the clustering).

    python -m app.stages.sfm_revisits <database.db> <out pairs.txt> [--words 2048] [--top 3] [--min-gap 40]
                                      [--views-per-pair 6] [--keep-below-sim X]
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import time

import numpy as np
import torch

VIEWS = ["lens0_c", "lens0_r", "lens0_l", "lens0_u", "lens0_d", "lens1_c", "lens1_r", "lens1_l", "lens1_u", "lens1_d"]


def load(db: sqlite3.Connection):
    key = {}
    for i, n in db.execute("select image_id, name from images"):
        m = re.match(r"(lens\d_[a-z])/(\w+?)_(\d+)\.", n.replace("\\", "/"))
        key[i] = (m.group(1), m.group(2), int(m.group(3)))
    frames = sorted({(c, f) for _, c, f in key.values()})
    return key, frames


def descriptors(db: sqlite3.Connection, image_id: int, n: int, rng: np.random.Generator) -> np.ndarray:
    rows, cols, blob = db.execute("select rows, cols, data from descriptors where image_id=?", (image_id,)).fetchone()
    d = np.frombuffer(blob, dtype=np.float32).reshape(rows, -1) if cols == 512 else np.frombuffer(blob, dtype=np.uint8).reshape(rows, cols).astype(np.float32)
    if len(d) > n:
        d = d[rng.choice(len(d), n, replace=False)]
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("database")
    ap.add_argument("out")
    ap.add_argument("--words", type=int, default=2048)
    ap.add_argument("--per-image", type=int, default=600, help="descriptors per image used for the fingerprint")
    ap.add_argument("--top", type=int, default=3, help="most similar far-away frames kept per frame")
    ap.add_argument("--min-gap", type=int, default=40, help="candidates must be at least this many frames apart")
    ap.add_argument("--views-per-pair", type=int, default=6)
    ap.add_argument("--stride", type=int, default=2, help="query every n-th frame")
    a = ap.parse_args()
    t0 = time.time()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    db = sqlite3.connect(f"file:{a.database}?mode=ro", uri=True)
    rng = np.random.default_rng(0)
    key, frames = load(db)
    fpos = {f: k for k, f in enumerate(frames)}
    ids_by_frame: dict[int, dict[str, int]] = {}
    for i, (v, c, f) in key.items():
        ids_by_frame.setdefault(fpos[(c, f)], {})[v] = i
    n_frames = len(frames)
    print(f"{n_frames} frames, {len(key)} images", flush=True)

    # 1. vocabulary: k-means on descriptors of every 8th frame
    sample = []
    for k in range(0, n_frames, 8):
        for v, i in ids_by_frame[k].items():
            sample.append(descriptors(db, i, 60, rng))
    X = torch.from_numpy(np.concatenate(sample)).to(dev)
    X = torch.nn.functional.normalize(X, dim=1)
    print(f"vocabulary from {len(X):,} descriptors ({time.time() - t0:.0f} s)", flush=True)
    C = X[torch.randperm(len(X), device=dev)[: a.words]].clone()
    for it in range(15):
        assign = torch.cat([(X[i:i + 200_000] @ C.T).argmax(1) for i in range(0, len(X), 200_000)])
        newC = torch.zeros_like(C).index_add_(0, assign, X)
        cnt = torch.bincount(assign, minlength=a.words).clamp(min=1).unsqueeze(1)
        C = torch.nn.functional.normalize(newC / cnt, dim=1)
    print(f"k-means done ({time.time() - t0:.0f} s)", flush=True)

    # 2. a word histogram for every image
    H = np.zeros((max(key) + 1, a.words), dtype=np.float32)
    done = 0
    for i in key:
        d = torch.from_numpy(descriptors(db, i, a.per_image, rng)).to(dev)
        w = (torch.nn.functional.normalize(d, dim=1) @ C.T).argmax(1)
        H[i] = torch.bincount(w, minlength=a.words).float().cpu().numpy()
        done += 1
        if done % 2000 == 0:
            print(f"  {done}/{len(key)} images ({time.time() - t0:.0f} s)", flush=True)
    present = (H > 0).sum(axis=0)
    idf = np.log((len(key) + 1) / (present + 1)).astype(np.float32)
    H = np.sqrt(H) * idf  # sqrt-tf, idf

    # 3. fingerprints: one per view, one per frame (all views summed)
    def norm(M):
        return M / np.maximum(np.linalg.norm(M, axis=1, keepdims=True), 1e-9)

    view_vec = np.zeros((n_frames, len(VIEWS), a.words), dtype=np.float32)
    for k, d in ids_by_frame.items():
        for vi, v in enumerate(VIEWS):
            if v in d:
                view_vec[k, vi] = H[d[v]]
    F = norm(view_vec.sum(axis=1))
    S = F @ F.T
    clip = np.array([c for c, _ in frames])
    idx = np.arange(n_frames)
    far = (np.abs(idx[:, None] - idx[None, :]) >= a.min_gap) | (clip[:, None] != clip[None, :])
    S = np.where(far, S, -1.0)
    print(f"frame similarity: far-apart pairs p50 {np.percentile(S[S > -1], 50):.3f}, p99 {np.percentile(S[S > -1], 99):.3f}, max {S.max():.3f}", flush=True)

    # 4. candidates and the best view pairs
    cand = set()
    for k in range(0, n_frames, a.stride):
        for j in np.argsort(-S[k])[: a.top]:
            if S[k, j] > -1:
                cand.add((min(k, int(j)), max(k, int(j))))
    print(f"{len(cand)} candidate frame pairs", flush=True)
    V = norm(view_vec.reshape(-1, a.words)).reshape(n_frames, len(VIEWS), a.words)
    lines = []
    for k, j in sorted(cand):
        sv = V[k] @ V[j].T
        for flat in np.argsort(-sv, axis=None)[: a.views_per_pair]:
            va, vb = divmod(int(flat), len(VIEWS))
            lines.append(f"{VIEWS[va]}/{frames[k][0]}_{frames[k][1]:06d}.png {VIEWS[vb]}/{frames[j][0]}_{frames[j][1]:06d}.png")
    open(a.out, "w", encoding="ascii").write("\n".join(lines))
    print(f"{len(lines)} view pairs written to {a.out} ({time.time() - t0:.0f} s)", flush=True)
    np.save(a.out + ".sim.npy", S.astype(np.float16))


if __name__ == "__main__":
    main()
