"""Structure from motion with COLMAP 4.2 on the pinhole views, as one rig (PLAN §1.4).

Every 360 frame is one COLMAP *frame* of one *rig*. The rig's sensors are the
pinhole views of both lenses. Their relative rotations are exact by
construction (views.py). Lens 1 faces backwards from lens 0; its pose comes
from the factory calibration (``lens1_from_lens0``), with a 180 deg turn about
the image-down axis and the lens-to-lens baseline along the optical axis. The
~3 cm baseline gives the reconstruction an approximately metric scale.

Steps: feature_extractor -> rig_configurator -> sequential_matcher -> mapper.
The sparse model is written in binary and text form plus a JSON report.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from app.core.project import read_json, write_json
from app.core.tools import colmap_env, colmap_exe

FEATURES = {
    "sift": ("SIFT", "SIFT_BRUTEFORCE"),
    "aliked": ("ALIKED_N16ROT", "ALIKED_LIGHTGLUE"),
}
# Office test (clip 069, 2026-10-17): SIFT found ~120 inliers between frames 0.4 s apart
# and none at 1.6 s; ALIKED + LightGlue found 708 and 127. SIFT tracks were too short
# (median 4) and the global mapper scrambled the camera positions. ALIKED is the default.


@dataclass
class SfmParams:
    features: str = "aliked"
    max_features: int = 8192
    # Run the ALIKED feature extraction on the CPU (COLMAP's ONNX Runtime). On the Blackwell office PC (RTX 5060) the
    # GPU path takes ~16 s/image, the 24-core CPU ~2 s/image with the same keypoints (2026-10-19). Default: GSL_EXTRACT_CPU=1.
    extract_cpu: bool = field(default_factory=lambda: os.environ.get("GSL_EXTRACT_CPU") == "1")
    # Run the global mapper's global positioning and bundle adjustment on the CPU instead of the GPU (COLMAP's default).
    solver_cpu: bool = field(default_factory=lambda: os.environ.get("GSL_SOLVER_CPU") == "1")
    overlap: int = 15  # neighbouring frames matched in sequence (rig expansion adds all views)
    quadratic_overlap: bool = True
    rig_verification: bool = False
    resume_from: str | None = None  # "mapper": reuse the database (features + matches) of this run folder
    expand_rig: bool = False  # match all 10x10 view pairs of two frames (slow; most face apart)
    loop_detection: bool = False
    vocab_tree: str | None = None
    mapper: str = "global"  # or "incremental"
    refine_rig: bool = False
    refine_intrinsics: bool = False
    lens1_yaw_deg: float = 180.0  # nominal turn of lens 1 relative to lens 0 about image-down
    baseline_m: float | None = None  # None: from factory calibration


def _quat_wxyz(r: np.ndarray) -> list[float]:
    x, y, z, w = Rotation.from_matrix(r).as_quat()
    return [float(w), float(x), float(y), float(z)]


def lens1_from_lens0(yaw_deg: float) -> np.ndarray:
    y = np.radians(yaw_deg)
    return np.array([[np.cos(y), 0, np.sin(y)], [0, 1, 0], [-np.sin(y), 0, np.cos(y)]])


def rig_config(views: dict, p: SfmParams) -> list[dict]:
    """COLMAP rig_configurator JSON: the rig frame is lens 0's frame (lens0_c is the reference)."""
    lenses = views["lenses"]
    baseline = p.baseline_m if p.baseline_m is not None else float(np.linalg.norm(lenses[1]["t"]))
    r_l_from_0 = [np.eye(3), lens1_from_lens0(p.lens1_yaw_deg)]
    centre_in_0 = [np.zeros(3), np.array([0.0, 0.0, -baseline])]
    cams = []
    for v in views["views"]:
        r_cam_from_lens = np.array(v["lens_from_view"]).T
        r = r_cam_from_lens @ r_l_from_0[v["lens"]]
        t = -r @ centre_in_0[v["lens"]]
        cam = {"image_prefix": v["folder"] + "/"}
        if v["folder"] == "lens0_c":
            cam["ref_sensor"] = True
        else:
            cam["cam_from_rig_rotation"] = _quat_wxyz(r)
            cam["cam_from_rig_translation"] = [float(x) for x in t]
        cams.append(cam)
    cams.sort(key=lambda c: not c.get("ref_sensor", False))
    return [{"cameras": cams}]


class Colmap:
    def __init__(self, log_path: Path):
        self.exe = colmap_exe()
        self.log_path = log_path

    def __call__(self, cmd: str, **opts) -> None:
        args = [str(self.exe), cmd]
        for k, v in opts.items():
            if v is None:
                continue
            if isinstance(v, bool):
                v = int(v)
            args += [f"--{k.replace('__', '.')}", str(v)]
        print(f"\n=== colmap {cmd}", flush=True)
        t0 = time.time()
        with open(self.log_path, "a", encoding="utf-8") as log:
            log.write(f"\n\n=== {' '.join(args)}\n")
            log.flush()
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                    encoding="utf-8", errors="replace", env=colmap_env())
            last = 0.0
            for line in proc.stdout:
                log.write(line)
                # Echo warnings, errors and a throttled progress line.
                noisy = "ScatterND" in line  # harmless ONNX Runtime warning, repeated per image
                if (re.search(r"error|warn|fail", line, re.I) and not noisy) or time.time() - last > 15:
                    print("   " + line.rstrip()[:200], flush=True)
                    last = time.time()
            if proc.wait() != 0:
                raise SystemExit(f"colmap {cmd} failed (exit {proc.returncode}); see {self.log_path}")
        print(f"    done in {time.time() - t0:.0f} s", flush=True)


def run_sfm(views_dir: Path, out_dir: Path, p: SfmParams) -> dict:
    views = read_json(views_dir / "views.json")
    out_dir.mkdir(parents=True, exist_ok=True)
    db = out_dir / "database.db"
    rig_path = out_dir / "rig_config.json"
    colmap = Colmap(out_dir / "colmap.log")
    if p.resume_from == "mapper":
        if not db.exists():
            raise SystemExit(f"--resume-from mapper needs an existing {db}")
        _map_and_report(views, views_dir, out_dir, db, colmap, p)
        return read_json(out_dir / "sfm_report.json")
    if db.exists():
        db.unlink()  # a fresh database per run: never mix feature types
    write_json(rig_path, rig_config(views, p))
    extract_type, match_type = FEATURES[p.features]
    cam = views["camera"]

    colmap("feature_extractor",
           database_path=db, image_path=views_dir / "images",
           ImageReader__mask_path=views_dir / "masks",
           ImageReader__camera_model=cam["model"],
           ImageReader__single_camera_per_folder=True,
           ImageReader__camera_params=",".join(f"{x:.6f}" for x in cam["params"]),
           FeatureExtraction__type=extract_type,
           FeatureExtraction__use_gpu=False if p.extract_cpu else None,
           SiftExtraction__max_num_features=p.max_features if p.features == "sift" else None,
           AlikedExtraction__max_num_features=p.max_features if p.features == "aliked" else None)
    colmap("rig_configurator", database_path=db, rig_config_path=rig_path)
    colmap("sequential_matcher",
           database_path=db,
           FeatureMatching__type=match_type,
           # Rig verification re-checks every pair against the rig on the CPU; with ALIKED on clip 069
           # it ran > 30 min after matching had finished, so it is off unless asked for.
           FeatureMatching__rig_verification=p.rig_verification,
           SequentialMatching__overlap=p.overlap,
           SequentialMatching__quadratic_overlap=p.quadratic_overlap,
           SequentialMatching__expand_rig_images=p.expand_rig,
           SequentialMatching__loop_detection=p.loop_detection,
           SequentialMatching__vocab_tree_path=p.vocab_tree)
    _map_and_report(views, views_dir, out_dir, db, colmap, p)
    return read_json(out_dir / "sfm_report.json")


def _map_and_report(views: dict, views_dir: Path, out_dir: Path, db: Path, colmap: "Colmap", p: SfmParams) -> dict:
    sparse = out_dir / "sparse"
    sparse.mkdir(exist_ok=True)
    refine = p.refine_intrinsics
    if p.mapper == "global":
        colmap("global_mapper", database_path=db, image_path=views_dir / "images", output_path=sparse,
               GlobalMapper__gp_use_gpu=False if p.solver_cpu else None,
               GlobalMapper__ba_ceres_use_gpu=False if p.solver_cpu else None,
               GlobalMapper__refine_sensor_from_rig=p.refine_rig,
               GlobalMapper__ba_refine_focal_length=refine,
               GlobalMapper__ba_refine_principal_point=False,
               GlobalMapper__ba_refine_extra_params=False)
    else:
        colmap("mapper", database_path=db, image_path=views_dir / "images", output_path=sparse,
               Mapper__ba_refine_sensor_from_rig=p.refine_rig,
               Mapper__ba_refine_focal_length=refine,
               Mapper__ba_refine_principal_point=False,
               Mapper__ba_refine_extra_params=False)

    models = sorted(d for d in sparse.iterdir() if d.is_dir())
    report = {"params": asdict(p), "num_images": len(views["frames"]) * len(views["views"]), "models": []}
    for m in models:
        txt = m.parent / f"{m.name}_txt"
        txt.mkdir(exist_ok=True)
        colmap("model_converter", input_path=m, output_path=txt, output_type="TXT")
        report["models"].append({"path": str(m), **model_stats(txt), **model_quality(m)})
    report["models"].sort(key=lambda s: s["registered_images"], reverse=True)
    write_json(out_dir / "sfm_report.json", report)
    return report


def model_stats(txt_dir: Path) -> dict:
    """Registered images (per lens), points and mean reprojection error from a TXT model."""
    lines = [l for l in (txt_dir / "images.txt").read_text().splitlines() if l and not l.startswith("#")]
    names = [l.split()[-1] for l in lines[0::2]]
    per_lens = {"lens0": sum(n.startswith("lens0") for n in names), "lens1": sum(n.startswith("lens1") for n in names)}
    errs, n_pts = [], 0
    for l in (txt_dir / "points3D.txt").read_text().splitlines():
        if l and not l.startswith("#"):
            errs.append(float(l.split()[7]))
            n_pts += 1
    return {"registered_images": len(names), "registered_per_lens": per_lens, "points3D": n_pts,
            "mean_reproj_error_px": float(np.mean(errs)) if errs else None,
            "median_reproj_error_px": float(np.median(errs)) if errs else None}


def model_quality(model_dir: Path) -> dict:
    """Checks that caught the scrambled SIFT trajectory (2026-10-17):
    * track length: points seen by few images give weak, locally fitted geometry;
    * smoothness: for a walked camera, the second difference of consecutive frame centres
      is much smaller than the step. A ratio near 1 means the positions jump randomly."""
    import pycolmap

    r = pycolmap.Reconstruction(str(model_dir))
    tl = np.array([p.track.length() for p in r.points3D.values()])
    centres = {}
    for i in r.reg_image_ids():
        im = r.images[i]
        if im.name.startswith("lens0_c/"):
            centres[im.name] = im.projection_center()
    p = np.array([centres[k] for k in sorted(centres)])
    # Jumps: a walked camera moves a small, steady step per frame. The 068+069 global solve (2026-10-21) had 52
    # steps of 10x the typical step or more among 1531 frames (three of 2000x) yet passed the checks below, which
    # only look at medians. Steps are compared within one clip (names "<clip>_<frame>"): the gap between two
    # clips of a capture can legitimately be large.
    clip_of = [Path(k).stem.split("_")[0] if "_" in Path(k).stem else "" for k in sorted(centres)]
    q: dict = {"track_length_median": float(np.median(tl)) if len(tl) else 0.0,
               "track_length_mean": float(tl.mean()) if len(tl) else 0.0}
    if len(p) >= 3:
        d1 = np.linalg.norm(np.diff(p, axis=0), axis=1)
        d2 = np.linalg.norm(p[2:] - 2 * p[1:-1] + p[:-2], axis=1)
        q["path_jitter_ratio"] = float(np.median(d2) / max(np.median(d1), 1e-12))
        q["path_length_over_extent"] = float(d1.sum() / max(np.ptp(p, axis=0).max(), 1e-12))
        same = np.array([clip_of[k] == clip_of[k + 1] for k in range(len(d1))])
        med = float(np.median(d1[same])) if same.any() else float(np.median(d1))
        rel = d1[same] / max(med, 1e-12)
        q["path_jumps_10x"] = int((rel > 10).sum())
        q["path_largest_jump_x"] = float(rel.max()) if len(rel) else 0.0
    q["warnings"] = []
    if q.get("path_jumps_10x", 0) > max(2, 0.005 * len(p)) or q.get("path_largest_jump_x", 0) > 200:
        q["warnings"].append(f"camera path has {q.get('path_jumps_10x', 0)} jumps of 10x the usual step or more "
                             f"(largest {q.get('path_largest_jump_x', 0):.0f}x): the solve split or drifted, positions are wrong")
    # Calibrated on clip 069: scrambled SIFT model 18.9 / 0.87, good ALIKED model 6.5 / 0.68
    # (a hand-held camera on a stick sways, so some jitter is normal; median track length was 4 in both).
    if q.get("path_length_over_extent", 0) > 12 or q.get("path_jitter_ratio", 0) > 0.8:
        q["warnings"].append("camera path is a scribble, not a walk: positions are probably wrong")
    if q["track_length_median"] < 3:
        q["warnings"].append("very short tracks: weak geometry (try ALIKED features, denser frames)")
    return q
