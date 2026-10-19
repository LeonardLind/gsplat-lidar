"""Detect people in the pinhole views (runs in the `gs` environment: torch + torchvision).

    python -m app.vision.people <views_dir> [--score 0.6] [--batch 4]

For every view image it writes an instance map ``people/<folder>/<frame>.png`` (uint8:
0 = no person, k = instance k) and ``people.json`` with one entry per instance (score,
box, area, whether it touches the image border). Detector: torchvision Mask R-CNN v2
(COCO "person"). Classifying instances as operator / still / moving needs the camera poses
and happens later, in app/stages/masks.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import torch
import torchvision
from torchvision.models.detection import MaskRCNN_ResNet50_FPN_V2_Weights, maskrcnn_resnet50_fpn_v2

PERSON = 1  # COCO category id


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("views_dir", type=Path)
    ap.add_argument("--score", type=float, default=0.6)
    ap.add_argument("--mask-threshold", type=float, default=0.5)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--min-area", type=float, default=0.002, help="ignore instances smaller than this image fraction")
    a = ap.parse_args()

    meta = json.loads((a.views_dir / "views.json").read_text())
    ext = meta["params"]["image_format"]
    items = [(v["folder"], f) for v in meta["views"] for f in meta["frames"]]
    out_root = a.views_dir / "people"
    for v in meta["views"]:
        (out_root / v["folder"]).mkdir(parents=True, exist_ok=True)

    torch.hub.set_dir(os.environ.get("TORCH_HOME", r"C:\dev\cache\torch"))
    weights = MaskRCNN_ResNet50_FPN_V2_Weights.DEFAULT
    model = maskrcnn_resnet50_fpn_v2(weights=weights, box_score_thresh=a.score).cuda().eval()
    print(f"torchvision {torchvision.__version__}; {len(items)} images", flush=True)

    def load(item):
        folder, frame = item
        img = cv2.imread(str(a.views_dir / "images" / folder / f"{frame}.{ext}"), cv2.IMREAD_COLOR)
        return item, cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    def save(path: Path, inst: np.ndarray) -> None:
        cv2.imwrite(str(path), inst, [cv2.IMWRITE_PNG_COMPRESSION, 3])

    records: dict[str, list[dict]] = {}
    t0 = time.time()
    io = ThreadPoolExecutor(max_workers=6)
    batches = [items[i:i + a.batch] for i in range(0, len(items), a.batch)]

    def prefetched(ahead: int = 12):
        """Decode batches in the I/O threads, at most `ahead` batches in front of the GPU. (ThreadPoolExecutor.map
        starts every batch at once; the GPU is the slower side, so the decoded 1600x1600 images piled up in RAM:
        ~7.7 MB each, over 100 GB for the 15 000 views of the 068+069 run.)"""
        queue: deque = deque()
        for b in batches:
            queue.append(io.submit(lambda b=b: [load(x) for x in b]))
            if len(queue) >= ahead:
                yield queue.popleft().result()
        while queue:
            yield queue.popleft().result()

    done = 0
    for batch in prefetched():
        tensors = [torch.from_numpy(img).permute(2, 0, 1).cuda().float() / 255 for _, img in batch]
        with torch.no_grad(), torch.autocast("cuda", dtype=torch.float16):
            outs = model(tensors)
        for ((folder, frame), img), o in zip(batch, outs):
            h, w = img.shape[:2]
            keep = (o["labels"] == PERSON) & (o["scores"] >= a.score)
            masks = (o["masks"][keep, 0] > a.mask_threshold).cpu().numpy()
            scores, boxes = o["scores"][keep].float().cpu().numpy(), o["boxes"][keep].float().cpu().numpy()
            inst = np.zeros((h, w), np.uint8)
            recs = []
            for k, (m, s, b) in enumerate(sorted(zip(masks, scores, boxes), key=lambda x: -x[1])[:250], start=1):
                area = float(m.mean())
                if area < a.min_area:
                    continue
                inst[m & (inst == 0)] = len(recs) + 1
                ys, xs = np.nonzero(m)
                recs.append({"id": len(recs) + 1, "score": round(float(s), 3), "box": [round(float(x), 1) for x in b],
                             "area": round(area, 5), "bottom_px": [float(xs[ys.argmax()]), float(ys.max())],
                             "touches": {"bottom": bool(ys.max() >= h - 2), "top": bool(ys.min() <= 1),
                                         "left": bool(xs.min() <= 1), "right": bool(xs.max() >= w - 2)}})
            name = f"{folder}/{frame}"
            records[name] = recs
            io.submit(save, out_root / folder / f"{frame}.png", inst)
        done += len(batch)
        if done % 200 < a.batch:
            rate = done / (time.time() - t0)
            print(f"  {done}/{len(items)} images, {rate:.1f}/s, eta {(len(items) - done) / rate / 60:.1f} min", flush=True)
    io.shutdown(wait=True)
    (a.views_dir / "people.json").write_text(json.dumps({"detector": "maskrcnn_resnet50_fpn_v2 (COCO)", "score": a.score,
                                                          "images": records}))
    n_inst = sum(len(v) for v in records.values())
    print(f"done: {n_inst} person instances in {sum(1 for v in records.values() if v)} of {len(records)} images "
          f"({(time.time() - t0) / 60:.1f} min)", flush=True)


if __name__ == "__main__":
    sys.exit(main())
