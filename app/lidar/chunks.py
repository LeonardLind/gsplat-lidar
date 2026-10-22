"""Cut the incremental models into continuous chunks of the walk.

A model of the incremental mapper can hold several separate stretches of the walk (e.g. frames 780-960 and
1140-1530), joined only through revisit links, and such a join is not rigid. A chunk is a run of consecutive frames
(in walking order) of one model with no larger gap than --max-gap frames. Inside a chunk the geometry is the SfM
solve of one continuous video, which is what a single rigid transform to the LiDAR can fit.

    python -m app.lidar.chunks <sparse dir with the models> <views.json> <out.json> [--min-frames 25]

Every frame belongs to the largest model that contains it. Output: a list of chunks in walking order with the model,
the frame range and the image names.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pycolmap


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sparse", type=Path)
    ap.add_argument("views", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--min-frames", type=int, default=25)
    ap.add_argument("--max-gap", type=int, default=4, help="largest run of missing frames inside one chunk")
    a = ap.parse_args()
    frames = [str(f) for f in json.loads(a.views.read_text())["frames"]]
    pos = {f: i for i, f in enumerate(frames)}

    models = {}
    for d in sorted((p for p in a.sparse.iterdir() if p.name.isdigit()), key=lambda p: int(p.name)):
        try:
            r = pycolmap.Reconstruction(str(d))
        except Exception:  # noqa: BLE001
            continue
        fs = set()
        for i in r.reg_image_ids():
            m = re.match(r"lens0_c/(\w+?_\d+)\.", r.images[i].name.replace("\\", "/"))
            if m:
                fs.add(m.group(1))
        models[d.name] = fs
    # each frame -> the largest model that has it
    owner = {}
    for name in sorted(models, key=lambda n: -len(models[n])):
        for f in models[name]:
            owner.setdefault(f, name)
    chunks = []
    cur = None
    for f in frames:
        o = owner.get(f)
        if o is None:
            continue
        i = pos[f]
        if cur and cur["model"] == o and i - cur["last"] <= a.max_gap + 1 and f.split("_")[0] == cur["frames"][-1].split("_")[0]:
            cur["frames"].append(f)
            cur["last"] = i
        else:
            if cur:
                chunks.append(cur)
            cur = {"model": o, "frames": [f], "first": i, "last": i}
    if cur:
        chunks.append(cur)
    keep = [c for c in chunks if len(c["frames"]) >= a.min_frames]
    out = [{"id": k, "model": c["model"], "first_index": c["first"], "last_index": c["last"], "n_frames": len(c["frames"]),
            "first_frame": c["frames"][0], "last_frame": c["frames"][-1], "frames": c["frames"]} for k, c in enumerate(keep)]
    a.out.write_text(json.dumps(out))
    tot = sum(c["n_frames"] for c in out)
    print(f"{len(chunks)} chunks, {len(out)} with >= {a.min_frames} frames covering {tot} of {len(frames)} frames")
    for c in out:
        print(f"  chunk {c['id']:2d}: model {c['model']:>3}, frames {c['first_index']:4d}-{c['last_index']:4d} "
              f"({c['first_frame']} .. {c['last_frame']}), {c['n_frames']} frames")


if __name__ == "__main__":
    main()
