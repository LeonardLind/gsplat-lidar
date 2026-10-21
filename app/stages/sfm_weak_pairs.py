"""Extra matching pairs around weak links between neighbouring 360 frames.

Sequential matching compares a view only with the same view of the next frames. When the operator turns, the front
view of one frame overlaps a *side* view of the next, so the link between two frames can look almost empty
(068+069 office run: 9 links with < 300 matches, 48 with < 1000, 2026-10-21). This lists, for every weak link,
all view-to-view pairs of the two frames (and of frames two apart) so that `colmap matches_importer` can add them
to the existing database. Pairs already in the database are skipped by COLMAP.

    python -m app.stages.sfm_weak_pairs <database.db> <out pairs.txt> [--below 1500]
"""
from __future__ import annotations

import argparse
import re
import sqlite3
from collections import defaultdict

VIEWS = ["lens0_c", "lens0_r", "lens0_l", "lens0_u", "lens0_d", "lens1_c", "lens1_r", "lens1_l", "lens1_u", "lens1_d"]


def weak_links(db_path: str, below: int) -> tuple[list[str], list[int]]:
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    key = {}
    for i, n in db.execute("select image_id, name from images"):
        m = re.match(r"lens\d_[a-z]/(\w+?)_(\d+)\.", n.replace("\\", "/"))
        key[i] = (m.group(1), int(m.group(2)))
    frames = sorted(set(key.values()))
    pos = {f: k for k, f in enumerate(frames)}
    strength: dict[int, int] = defaultdict(int)
    M = 2147483647
    for pid, rows, cfg in db.execute("select pair_id, rows, config from two_view_geometries where rows > 0"):
        if cfg not in (2, 3, 4, 5, 6, 8):
            continue
        a, b = divmod(pid, M)
        fa, fb = key[a], key[b]
        if fa[0] != fb[0] or fa == fb:
            continue
        ka, kb = sorted((pos[fa], pos[fb]))
        if kb - ka == 1:
            strength[ka] += rows
    names = [f"{c}_{n:06d}" for c, n in frames]
    clips = [c for c, _ in frames]
    weak = [k for k in range(len(frames) - 1) if strength.get(k, 0) < below and clips[k] == clips[k + 1]]
    return names, weak


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("database")
    ap.add_argument("out")
    ap.add_argument("--below", type=int, default=1500, help="a link with fewer inliers than this is weak")
    a = ap.parse_args()
    names, weak = weak_links(a.database, a.below)
    lines = []
    for k in weak:
        for off in (1, 2):
            if k + off >= len(names) or names[k][:3] != names[k + off][:3]:
                continue
            for va in VIEWS:
                for vb in VIEWS:
                    lines.append(f"{va}/{names[k]}.png {vb}/{names[k + off]}.png")
    open(a.out, "w", encoding="ascii").write("\n".join(lines))
    print(f"{len(weak)} weak links (< {a.below} inliers) -> {len(lines)} pairs")


if __name__ == "__main__":
    main()
