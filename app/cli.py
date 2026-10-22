"""Command line for the pipeline stages.

    python -m app init <project> --insv <clip.insv> [--insv <clip2.insv>]
    python -m app probe <project>
    python -m app frames <project> [--clip ID] [--window 0.4] [--start S] [--end S]
    python -m app views <project> [--clip ID] [--layout 5] [--size 1600]
    python -m app merge-views <project> --clips 068,069 --name all
    python -m app sfm <project> [--clip ID] [--features sift|aliked] [--mapper global|incremental]
    python -m app train <project> [--clip ID] [--sfm RUN] [--steps 30000] [--cap 1000000] [--name RUN]
    python -m app export <project> [--clip ID] --run RUN [--formats sog,html,spz]
    python -m app people <project> [--clip ID]            (person detection + SfM masks, before sfm)
    python -m app people-classify <project> [--clip ID] --sfm RUN   (training masks, after sfm)
    python -m app serve [--port 8765]                    (job server for the browser studio)
    python -m app bench                                  (training speed of this PC, for estimates)
    python -m app clean-apply <project> --export REL [--reset]   (apply a cleanup made in the studio)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.project import Project, write_json


def cmd_init(a: argparse.Namespace) -> None:
    p = Project(a.project)
    data = p.load() if p.exists() else {"name": a.project, "sources": {}}
    clips = data["sources"].setdefault("insta360", {"clips": []})["clips"]
    for path in a.insv:
        path = Path(path).resolve()
        if not path.exists():
            raise SystemExit(f"not found: {path}")
        clip_id = path.stem.split("_")[-1]  # VID_20261016_141637_00_068 -> 068
        if any(c["id"] == clip_id for c in clips):
            print(f"clip {clip_id} already in project")
            continue
        clips.append({"id": clip_id, "path": str(path)})
        print(f"added clip {clip_id}: {path}")
    p.save(data)


def cmd_probe(a: argparse.Namespace) -> None:
    from app.sources.insta360.probe import probe_clip

    p = Project(a.project)
    for clip in p.clips():
        rep = probe_clip(Path(clip["path"]))
        write_json(p.stage_dir("probe") / f"{clip['id']}.json", rep)
        lens = rep["lenses"][0] if rep["lenses"] else {}
        print(f"[{clip['id']}] {rep['model']}  {len(rep['lenses'])}x {lens.get('width')}x{lens.get('height')} "
              f"{rep['fps']:.3f} fps  {rep['duration_s']:.1f} s  calib strings: {len(rep['offset_strings'])}")
        for prob in rep["problems"]:
            print(f"   WARNING: {prob}")


def cmd_frames(a: argparse.Namespace) -> None:
    from app.sources.insta360.probe import probe_clip
    from app.stages.frames import FrameParams, select_frames

    p = Project(a.project)
    clip = p.clip(a.clip)
    probe_file = p.dir / "probe" / f"{clip['id']}.json"
    rep = json.loads(probe_file.read_text()) if probe_file.exists() else probe_clip(Path(clip["path"]))
    params = FrameParams(window_s=a.window, start_s=a.start, end_s=a.end,
                         min_change=a.min_change, image_format=a.format)
    out = p.stage_dir("frames", clip["id"])
    res = select_frames(Path(clip["path"]), out, rep["fps"], params)
    print(f"kept {res['kept']} of {res['decoded_pairs']} frame pairs "
          f"({res['skipped_still']} windows skipped as still); "
          f"median sharpness kept {res['median_sharpness_kept']:.1f} vs all {res['median_sharpness_all']:.1f}")
    print(f"-> {out}")


def cmd_views(a: argparse.Namespace) -> None:
    from app.stages.views import ViewParams, make_views

    p = Project(a.project)
    clip = p.clip(a.clip)
    probe = json.loads((p.dir / "probe" / f"{clip['id']}.json").read_text())
    params = ViewParams(layout=a.layout, size=a.size, fov_deg=a.fov,
                        operator_cone_deg=a.operator_cone, image_format=a.format)
    out = p.stage_dir("views", clip["id"])
    res = make_views(p.dir / "frames" / clip["id"], probe, out, params)
    print(f"{len(res['frames'])} frames x {len(res['views'])} views -> {out}")
    for v in res["views"]:
        print(f"   {v['folder']:<10} usable {v['valid_fraction']:.0%}")


def _views_id(p: Project, a: argparse.Namespace) -> str:
    """A view set: one clip's views, or a merged set (see merge-views)."""
    return a.views if getattr(a, "views", None) else p.clip(a.clip)["id"]


def cmd_merge_views(a: argparse.Namespace) -> None:
    from app.stages.views import merge_views

    p = Project(a.project)
    ids = a.clips.split(",")
    res = merge_views({c: p.dir / "views" / c for c in ids}, p.stage_dir("views", a.name))
    print(f"merged {len(ids)} clips -> views/{a.name}: {len(res['frames'])} frames x {len(res['views'])} views")


def cmd_sfm(a: argparse.Namespace) -> None:
    from app.stages.sfm import SfmParams, run_sfm

    p = Project(a.project)
    clip = {"id": _views_id(p, a)}
    params = SfmParams(features=a.features, max_features=a.max_features, overlap=a.overlap,
                       **({"extract_cpu": True} if a.extract_cpu else {}),
                       **({"solver_cpu": True} if a.solver_cpu else {}),
                       loop_detection=a.vocab_tree is not None, vocab_tree=a.vocab_tree,
                       expand_rig=a.expand_rig, rig_verification=a.rig_verification, resume_from=a.resume_from,
                       mapper=a.mapper, refine_rig=a.refine_rig, refine_intrinsics=a.refine_intrinsics,
                       lens1_yaw_deg=a.lens1_yaw)
    out = p.stage_dir("sfm", clip["id"], a.name or f"{a.features}_{a.mapper}")
    rep = run_sfm(p.dir / "views" / clip["id"], out, params)
    print(f"\n{rep['num_images']} images in; {len(rep['models'])} model(s)")
    for m in rep["models"]:
        print(f"   {m['registered_images']} registered {m['registered_per_lens']}, {m['points3D']} points, "
              f"reproj error mean {m['mean_reproj_error_px']:.3f} px, track length median {m['track_length_median']:.0f}, "
              f"path jitter {m.get('path_jitter_ratio', 0):.2f}  ({m['path']})")
        for w in m["warnings"]:
            print(f"      WARNING: {w}")


def _oriented_model(p: Project, vid: str, sfm: str) -> Path:
    """Best model of an SfM run, oriented gravity-up at approximate scale (made once, then reused)."""
    from app.core.project import read_json
    from app.stages.orient import orient_model

    sfm_dir = p.dir / "sfm" / vid / sfm
    rep = read_json(sfm_dir / "sfm_report.json")
    if not rep["models"]:
        raise SystemExit(f"SfM run {sfm_dir} produced no model")
    best = Path(rep["models"][0]["path"])
    oriented = sfm_dir / "oriented" / best.name
    if not (oriented / "images.bin").exists():
        info = orient_model(best, oriented)
        write_json(oriented.parent / f"{best.name}_orient.json", info)
        print(f"oriented model {best.name}: camera tilt spread {info['tilt_spread_deg']:.1f} deg, "
              f"camera extent {[round(x, 2) for x in info['camera_extent']]}, "
              f"reproj {info['mean_reproj_error_px']:.3f} px")
        for w in info.get("warnings", []):
            print(f"WARNING: {w}", flush=True)
    return oriented


def cmd_orient(a: argparse.Namespace) -> None:
    p = Project(a.project)
    print(_oriented_model(p, _views_id(p, a), a.sfm))


def cmd_train(a: argparse.Namespace) -> None:
    from app.stages.train import TrainParams, train

    p = Project(a.project)
    clip = {"id": _views_id(p, a)}
    oriented = _oriented_model(p, clip["id"], a.sfm)
    params = TrainParams(steps=a.steps, cap_max=a.cap, sh_degree=a.sh, holdout_every=a.holdout_every,
                         ppisp=a.ppisp, antialiased=a.antialiased, packed=a.packed, viewer=a.viewer,
                         visible_adam=not a.no_visible_adam)
    run = a.name or f"{a.sfm}_{a.cap // 1000}k_{a.steps // 1000}k"
    code = train(p.dir / "views" / clip["id"], oriented, p.stage_dir("train", clip["id"], run), params)
    raise SystemExit(code)


def _explorer_follows(p: Project, out: Path) -> None:
    """The explorer (Vite) serves the export/current of the project named in projects/_server/current.json
    (set by the studio's "Open in explorer"); point it at this project so a fresh export is what it shows."""
    import time

    from app.core.project import PROJECTS_DIR

    rel = out.resolve().relative_to((p.dir / "export").resolve()).as_posix()
    write_json(PROJECTS_DIR / "_server" / "current.json", {"project": p.name, "export": rel, "time": time.time()})


DEFAULT_LIDAR = r"C:\dev\gsl-data\data\processed\office_lidar_5cm.npz"


def cmd_export(a: argparse.Namespace) -> None:
    import _winapi

    from app.core.project import read_json
    from app.stages.export import export
    from app.stages.scene_export import write_scene

    p = Project(a.project)
    clip = {"id": _views_id(p, a)}
    run_dir = p.dir / "train" / clip["id"] / a.run
    plys = sorted((run_dir / "result" / "ply").glob("*.ply"),
                  key=lambda f: int("".join(ch for ch in f.stem if ch.isdigit()) or 0))
    if not plys:
        raise SystemExit("no PLY found for that run")
    ply = plys[-1]
    out = p.stage_dir("export", clip["id"], a.run)
    formats = a.formats.split(",")
    for f in export(ply, out, formats):
        print(f"   {f}  ({f.stat().st_size / 1e6:.1f} MB)")
    sparse = Path(read_json(run_dir / "train_params.json")["sparse"])
    orient = read_json(sparse.parent / f"{sparse.name}_orient.json")
    splat_file = "scene.sog" if "sog" in formats else "scene.spz"
    info = write_scene(out, f"{p.name} {clip['id']} {a.run}", splat_file, sparse, ply,
                       orient.get("scale") if orient.get("scale") in ("approximate", "metric") else "arbitrary",
                       views_dir=p.dir / "views" / clip["id"],
                       lidar=Path(orient.get("lidar_npz", DEFAULT_LIDAR)) if orient.get("frame") == "lidar" else None)
    print(f"   scene.json + collision.json: floor z {info['floor_z']:.2f}, camera height {info['camera_height']:.2f}, "
          f"voxel {info['voxel']:.3f}, {info['occupied']} solid voxels ({info['carved']} carved along the camera path)")
    current = p.dir / "export" / "current"
    if current.exists():
        current.rmdir()  # a junction: removes the link only
    _winapi.CreateJunction(str(out.resolve()), str(current))
    _explorer_follows(p, out)
    print(f"   export/current -> {out}")
    print("   view it:  cd web/viewer && npm run dev   (then open http://127.0.0.1:5173)")


def cmd_people(a: argparse.Namespace) -> None:
    import os
    import subprocess

    from app.core.project import REPO_ROOT
    from app.core.tools import DEV, gs_python
    from app.stages.masks import write_sfm_masks

    p = Project(a.project)
    vid = _views_id(p, a)
    views = p.dir / "views" / vid
    env = {**os.environ, "TORCH_HOME": str(DEV / "cache" / "torch"), "PYTHONUNBUFFERED": "1"}
    subprocess.run([str(gs_python()), "-m", "app.vision.people", str(views), "--score", str(a.score)],
                   check=True, cwd=str(REPO_ROOT), env=env)
    print("SfM masks:", write_sfm_masks(views))


def cmd_people_classify(a: argparse.Namespace) -> None:
    from app.stages.masks import classify_people, contact_sheet, write_train_masks

    p = Project(a.project)
    vid = _views_id(p, a)
    views = p.dir / "views" / vid
    res = classify_people(views, _oriented_model(p, vid, a.sfm))
    print(f"people: {res['counts']}  (camera height {res['camera_height']:.2f})")
    write_train_masks(views)
    sheet = contact_sheet(views, views / "mask_sheet.jpg")
    print(f"training masks written; review the contact sheet: {sheet}")


def cmd_import_ply(a: argparse.Namespace) -> None:
    """A downloaded/pretrained splat PLY (no cameras) -> viewer scene in export/<name>, made current."""
    import _winapi

    from app.stages.export import export
    from app.stages.ply_scene import build_scene

    p = Project(a.project)
    out = p.stage_dir("export", "imported", a.name)
    ply = Path(a.ply).resolve()
    for f in export(ply, out, ["sog"]):
        print(f"   {f}  ({f.stat().st_size / 1e6:.1f} MB)")
    if a.outdoor:  # no ceiling: --ceiling is then the collision height cap (head height), not a room height
        info = build_scene(ply, out, a.name, up_hint=a.up, ceiling_m=a.cap, voxel=a.voxel, outdoor=True,
                           canopy_m=a.canopy, title=a.title, note=a.note)
        print(f"   up axis used {info.get('up_axis_used', a.up)}")
    else:
        info = build_scene(ply, out, a.name, up_hint=a.up, ceiling_m=a.ceiling, title=a.title, note=a.note)
    print(f"   floor normal {[round(x, 3) for x in info['floor_normal']]}, scale {info['scale']:.3f}, "
          f"{info['occupied']} solid voxels, start clearance {info['start_clearance_m']:.2f} m")
    current = p.dir / "export" / "current"
    if current.exists():
        current.rmdir()  # a junction: removes the link only
    _winapi.CreateJunction(str(out.resolve()), str(current))
    _explorer_follows(p, out)
    print(f"   export/current -> {out}  (reload http://127.0.0.1:5173)")


def cmd_serve(a: argparse.Namespace) -> None:
    from app.server.api import main as serve_main

    serve_main(a.host, a.port)


def cmd_bench(a: argparse.Namespace) -> None:
    import subprocess

    from app.core.project import REPO_ROOT, read_json
    from app.core.tools import gs_python
    from app.server import machine

    out = machine.SERVER_DIR / "bench.tmp.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(gs_python()), str(REPO_ROOT / "app" / "trainers" / "bench.py"), str(out), "--size", str(a.size)],
                   check=True)
    machine.save_bench(read_json(out))
    out.unlink()
    print(f"saved to {machine.HISTORY}")


def cmd_clean_apply(a: argparse.Namespace) -> None:
    from app.server.clean import cli

    cli(a.project, a.export, a.reset)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="app")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create a project or add clips to it")
    s.add_argument("project")
    s.add_argument("--insv", action="append", required=True)
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("probe", help="inspect the project's clips")
    s.add_argument("project")
    s.set_defaults(func=cmd_probe)

    s = sub.add_parser("frames", help="select sharp fisheye frame pairs")
    s.add_argument("project")
    s.add_argument("--clip")
    s.add_argument("--window", type=float, default=0.4, help="seconds per selection window")
    s.add_argument("--start", type=float, default=0.0, help="skip the first S seconds")
    s.add_argument("--end", type=float, default=None, help="stop at S seconds")
    s.add_argument("--min-change", type=float, default=2.0, help="skip near-identical windows (0 = off)")
    s.add_argument("--format", choices=["png", "jpg"], default="png")
    s.set_defaults(func=cmd_frames)

    s = sub.add_parser("views", help="reproject fisheye frames into pinhole views")
    s.add_argument("project")
    s.add_argument("--clip")
    s.add_argument("--layout", choices=["5", "7"], default="5", help="views per lens")
    s.add_argument("--size", type=int, default=1600, help="view width = height in pixels")
    s.add_argument("--fov", type=float, default=90.0)
    s.add_argument("--operator-cone", type=float, default=40.0, help="mask rays within N deg of image-down (0 = off)")
    s.add_argument("--format", choices=["png", "jpg"], default="png")
    s.set_defaults(func=cmd_views)

    s = sub.add_parser("merge-views", help="combine the views of several clips for one joint SfM")
    s.add_argument("project")
    s.add_argument("--clips", required=True, help="comma list of clip ids, e.g. 068,069")
    s.add_argument("--name", required=True, help="name of the merged view set")
    s.set_defaults(func=cmd_merge_views)

    s = sub.add_parser("sfm", help="COLMAP structure from motion on the views (rig)")
    s.add_argument("project")
    s.add_argument("--clip")
    s.add_argument("--views", help="view set id instead of a clip (e.g. a merged set)")
    s.add_argument("--name", help="run folder name (default <features>_<mapper>)")
    s.add_argument("--features", choices=["sift", "aliked"], default="aliked")
    s.add_argument("--max-features", type=int, default=8192)
    s.add_argument("--extract-cpu", action="store_true", help="feature extraction on the CPU (default: env GSL_EXTRACT_CPU=1)")
    s.add_argument("--solver-cpu", action="store_true", help="global mapper: positioning and bundle adjustment on the CPU (default: env GSL_SOLVER_CPU=1)")
    s.add_argument("--overlap", type=int, default=15)
    s.add_argument("--vocab-tree", help="vocab tree file (must match the features); enables loop detection")
    s.add_argument("--expand-rig", action="store_true", help="match all view pairs of neighbouring frames (slow)")
    s.add_argument("--rig-verification", action="store_true", help="re-verify matches against the rig (slow, CPU)")
    s.add_argument("--resume-from", choices=["mapper"], help="reuse this run's database and only map again")
    s.add_argument("--mapper", choices=["global", "incremental"], default="global")
    s.add_argument("--refine-rig", action="store_true", help="let bundle adjustment refine the rig")
    s.add_argument("--refine-intrinsics", action="store_true")
    s.add_argument("--lens1-yaw", type=float, default=180.0)
    s.set_defaults(func=cmd_sfm)

    s = sub.add_parser("train", help="train a Gaussian splat with gsplat (MCMC)")
    s.add_argument("project")
    s.add_argument("--clip")
    s.add_argument("--views", help="view set id instead of a clip")
    s.add_argument("--sfm", default="aliked_global", help="SfM run folder name")
    s.add_argument("--name", help="training run name")
    s.add_argument("--steps", type=int, default=30_000)
    s.add_argument("--cap", type=int, default=1_000_000, help="maximum number of Gaussians (MCMC cap_max)")
    s.add_argument("--sh", type=int, default=3, help="spherical harmonics degree")
    s.add_argument("--holdout-every", type=int, default=10, help="hold out every N-th 360 frame (0 = off)")
    s.add_argument("--ppisp", action="store_true", help="exposure/ISP compensation (PPISP)")
    s.add_argument("--antialiased", action="store_true")
    s.add_argument("--packed", action="store_true", help="less VRAM, slightly slower")
    s.add_argument("--viewer", action="store_true", help="live viser viewer on port 8080")
    s.add_argument("--no-visible-adam", action="store_true",
                   help="plain Adam for all Gaussians (collapses on 360 captures; for comparison only)")
    s.set_defaults(func=cmd_train)

    s = sub.add_parser("export", help="export the latest PLY of a training run")
    s.add_argument("project")
    s.add_argument("--clip")
    s.add_argument("--views", help="view set id instead of a clip")
    s.add_argument("--run", required=True)
    s.add_argument("--formats", default="sog,html", help="comma list of sog, spz, html")
    s.set_defaults(func=cmd_export)

    s = sub.add_parser("import-ply", help="make a viewer scene from a downloaded splat PLY (no cameras)")
    s.add_argument("project")
    s.add_argument("--ply", required=True)
    s.add_argument("--name", required=True)
    s.add_argument("--up", default="-y", help="rough up axis of the PLY: +x -x +y -y +z -z (COLMAP scenes: -y); "
                                              "with --outdoor also 'auto' (tries all six)")
    s.add_argument("--ceiling", type=float, default=2.6, help="assumed ceiling height in metres (sets the scale)")
    s.add_argument("--outdoor", action="store_true", help="no ceiling: ground plane only (forest, street)")
    s.add_argument("--canopy", type=float, default=12.0, help="outdoor: assumed height of the canopy top (98th percentile) in metres (sets the scale)")
    s.add_argument("--cap", type=float, default=2.5, help="outdoor: collision height cap in metres")
    s.add_argument("--voxel", type=float, default=0.15, help="outdoor: collision voxel size in metres")
    s.add_argument("--title", help="title of the first demo marker")
    s.add_argument("--note", help="text of the first demo marker (e.g. the credit line)")
    s.set_defaults(func=cmd_import_ply)

    s = sub.add_parser("orient", help="gravity-up + approximate scale for an SfM run (train does this too)")
    s.add_argument("project")
    s.add_argument("--clip")
    s.add_argument("--views", help="view set id instead of a clip")
    s.add_argument("--sfm", default="aliked_global")
    s.set_defaults(func=cmd_orient)

    s = sub.add_parser("people", help="detect people in the views and write SfM masks (GPU)")
    s.add_argument("project")
    s.add_argument("--clip")
    s.add_argument("--views", help="view set id instead of a clip")
    s.add_argument("--score", type=float, default=0.6)
    s.set_defaults(func=cmd_people)

    s = sub.add_parser("people-classify", help="label people operator/still/moving and write training masks")
    s.add_argument("project")
    s.add_argument("--clip")
    s.add_argument("--views", help="view set id instead of a clip")
    s.add_argument("--sfm", default="aliked_global", help="SfM run whose oriented model gives the poses")
    s.set_defaults(func=cmd_people_classify)

    s = sub.add_parser("serve", help="job server for the browser studio (web/viewer/studio.html)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("bench", help="measure training speed on this PC's GPU (for the studio's estimates)")
    s.add_argument("--size", type=int, default=1600)
    s.set_defaults(func=cmd_bench)

    s = sub.add_parser("clean-apply", help="apply a cleanup mask saved by the studio to an export")
    s.add_argument("project")
    s.add_argument("--export", required=True, help="export folder relative to export/, e.g. 069/test_10k")
    s.add_argument("--reset", action="store_true", help="restore the original splat")
    s.set_defaults(func=cmd_clean_apply)

    a = ap.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
