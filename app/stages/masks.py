"""Masks from person detections (app/vision/people.py): one set for SfM, one for training.

User decision (2026-10-17): cut out the operator and *moving* people; people who sit or
stand still stay in the splat.

* SfM masks (``masks/``): static rig/operator cone AND NOT any person (dilated). SfM only
  wants features on the static scene.
* Training masks (``masks_train/``): static cone AND NOT (operator or moving people).
  Classification needs the camera poses, so it runs after SfM:
    - each instance gives a 3D ray from the camera through its mask centroid;
    - operator: the ray points steeply down and the mask touches the bottom edge, or the
      triangulated point lies right at the camera (the operator moves with the camera);
    - still: rays from moments at least ``min_dt`` apart pass close to each other (within
      ``tol`` x camera height) and their crossing points agree. A moving person's rays
      from different times do not converge;
    - everything else is moving.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pycolmap

from app.core.project import read_json, write_json


@dataclass
class MaskParams:
    dilate_px: int = 15
    operator_down_deg: float = 35.0
    min_dt_frames: int = 4  # 4 kept frames = 1.6 s at 0.4 s per frame
    tol_frac: float = 0.12  # ray-crossing tolerance, fraction of the camera height
    min_partners: int = 2
    max_range_frac: float = 8.0  # ignore crossings further than this (x camera height)


def _kernel(px: int) -> np.ndarray:
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * px + 1, 2 * px + 1))


def _write_mask(path: Path, mask: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Replace, never write through: a merged view set hard-links its masks to the clips' files.
    path.unlink(missing_ok=True)
    cv2.imwrite(str(path), mask, [cv2.IMWRITE_PNG_COMPRESSION, 3])


def _static(views_dir: Path, folder: str) -> np.ndarray:
    return cv2.imread(str(views_dir / f"mask_{folder}.png"), cv2.IMREAD_GRAYSCALE)


def write_sfm_masks(views_dir: Path, p: MaskParams = MaskParams()) -> dict:
    meta = read_json(views_dir / "views.json")
    people = read_json(views_dir / "people.json")["images"]
    ext = meta["params"]["image_format"]
    k = _kernel(p.dilate_px)
    n_masked = 0
    for v in meta["views"]:
        static = _static(views_dir, v["folder"])
        for stem in meta["frames"]:
            name = f"{v['folder']}/{stem}"
            m = static.copy()
            if people.get(name):
                inst = cv2.imread(str(views_dir / "people" / v["folder"] / f"{stem}.png"), cv2.IMREAD_GRAYSCALE)
                m[cv2.dilate((inst > 0).astype(np.uint8), k) > 0] = 0
                n_masked += 1
            _write_mask(views_dir / "masks" / v["folder"] / f"{stem}.{ext}.png", m)
    return {"images_with_people": n_masked}


def classify_people(views_dir: Path, model_dir: Path, p: MaskParams = MaskParams()) -> dict:
    meta = read_json(views_dir / "views.json")
    people = read_json(views_dir / "people.json")["images"]
    ext = meta["params"]["image_format"]
    fx, fy, cx, cy = meta["camera"]["params"]
    frame_index = {s: i for i, s in enumerate(meta["frames"])}

    r = pycolmap.Reconstruction(str(model_dir))
    poses = {}
    for i in r.reg_image_ids():
        im = r.images[i]
        poses[im.name] = (im.cam_from_world().rotation.matrix(), im.projection_center())
    lens0 = np.array([c for n, (_, c) in poses.items() if n.startswith("lens0_c/")])
    pts = np.array([pt.xyz for pt in r.points3D.values()])
    floor = float(np.percentile(pts[:, 2], 3))
    cam_h = float(np.median(lens0[:, 2]) - floor) if len(lens0) else 1.5
    tol = p.tol_frac * cam_h

    rows = []  # (key, instance id, frame index, origin, direction, operator?)
    for name, recs in people.items():
        folder, stem = name.split("/")
        pose = poses.get(f"{folder}/{stem}.{ext}")
        if pose is None or not recs:
            continue
        rot, c = pose
        inst = cv2.imread(str(views_dir / "people" / folder / f"{stem}.png"), cv2.IMREAD_GRAYSCALE)
        for rec in recs:
            ys, xs = np.nonzero(inst == rec["id"])
            if len(xs) == 0:
                continue
            u, v = xs.mean() + 0.5, ys.mean() + 0.5
            d = rot.T @ np.array([(u - cx) / fx, (v - cy) / fy, 1.0])
            d /= np.linalg.norm(d)
            down = np.degrees(np.arcsin(-d[2]))
            operator = rec["touches"]["bottom"] and down > p.operator_down_deg
            rows.append((name, rec["id"], frame_index[stem], c, d, operator))

    labels: dict[str, dict[int, str]] = defaultdict(dict)
    cand = [i for i, row in enumerate(rows) if not row[5]]
    if cand:
        O = np.array([rows[i][3] for i in cand])
        D = np.array([rows[i][4] for i in cand])
        F = np.array([rows[i][2] for i in cand])
        for a_idx, ia in enumerate(cand):
            # Closest approach between ray a and all other rays.
            w0 = O[a_idx] - O
            b = D @ D[a_idx]
            dd = w0 @ D[a_idx]
            e = np.einsum("ij,ij->i", D, w0)
            den = 1 - b * b
            ok = (np.abs(F - F[a_idx]) >= p.min_dt_frames) & (den > 1e-4)
            sa = np.where(ok, (b * e - dd) / np.where(ok, den, 1), 0)
            sb = np.where(ok, (e - b * dd) / np.where(ok, den, 1), 0)
            pa = O[a_idx] + sa[:, None] * D[a_idx]
            pb = O + sb[:, None] * D
            gap = np.linalg.norm(pa - pb, axis=1)
            good = ok & (sa > 0.3 * cam_h) & (sb > 0.3 * cam_h) & (sa < p.max_range_frac * cam_h) & (gap < tol)
            name, iid = rows[ia][0], rows[ia][1]
            if good.sum() >= p.min_partners:
                mids = 0.5 * (pa[good] + pb[good])
                spread = np.linalg.norm(mids - np.median(mids, axis=0), axis=1)
                at_camera = np.linalg.norm(np.median(mids, axis=0) - O[a_idx]) < 0.5 * cam_h
                still = (spread < 2 * tol).sum() >= p.min_partners and not at_camera
                labels[name][iid] = "still" if still else ("operator" if at_camera else "moving")
            else:
                labels[name][iid] = "moving"
    for row in rows:
        if row[5]:
            labels[row[0]][row[1]] = "operator"
    counts = defaultdict(int)
    for d in labels.values():
        for lab in d.values():
            counts[lab] += 1
    out = {"floor_z": floor, "camera_height": cam_h, "counts": dict(counts),
           "labels": {k: {str(i): lab for i, lab in v.items()} for k, v in labels.items()}}
    write_json(views_dir / "people_labels.json", out)
    return out


def write_train_masks(views_dir: Path, p: MaskParams = MaskParams()) -> dict:
    meta = read_json(views_dir / "views.json")
    labels = read_json(views_dir / "people_labels.json")["labels"]
    ext = meta["params"]["image_format"]
    k = _kernel(p.dilate_px)
    for v in meta["views"]:
        static = _static(views_dir, v["folder"])
        for stem in meta["frames"]:
            name = f"{v['folder']}/{stem}"
            m = static.copy()
            lab = labels.get(name)
            if lab:
                inst = cv2.imread(str(views_dir / "people" / v["folder"] / f"{stem}.png"), cv2.IMREAD_GRAYSCALE)
                cut = np.isin(inst, [int(i) for i, l in lab.items() if l != "still"])
                m[cv2.dilate(cut.astype(np.uint8), k) > 0] = 0
            _write_mask(views_dir / "masks_train" / v["folder"] / f"{stem}.{ext}.png", m)
    return {"written": len(meta["frames"]) * len(meta["views"])}


def contact_sheet(views_dir: Path, out: Path, every: int = 20, size: int = 240) -> Path:
    """Every N-th frame, all views: SfM-masked area tinted red, training-masked area tinted blue."""
    meta = read_json(views_dir / "views.json")
    ext = meta["params"]["image_format"]
    rows = []
    for stem in meta["frames"][::every]:
        tiles = []
        for v in meta["views"]:
            img = cv2.resize(cv2.imread(str(views_dir / "images" / v["folder"] / f"{stem}.{ext}")), (size, size))
            for sub, color in (("masks", (0, 0, 255)), ("masks_train", (255, 120, 0))):
                f = views_dir / sub / v["folder"] / f"{stem}.{ext}.png"
                if f.exists():
                    m = cv2.resize(cv2.imread(str(f), cv2.IMREAD_GRAYSCALE), (size, size)) == 0
                    img[m] = (0.55 * img[m] + 0.45 * np.array(color)).astype(np.uint8)
            cv2.putText(img, f"{v['folder']} {stem}", (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
            tiles.append(img)
        rows.append(np.hstack(tiles))
    sheet = np.vstack(rows)
    cv2.imwrite(str(out), sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return out
