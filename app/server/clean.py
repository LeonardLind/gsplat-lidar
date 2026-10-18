"""Splat cleanup: apply the browser's deletions to an export, never touching the master PLY.

The cleanup page (web/viewer/clean.html) loads the export's master PLY (scene.json splat.source),
lets the user select and delete Gaussians, and sends a bitmask (bit i set = Gaussian i deleted, in
PLY order). Applying it writes <export>/clean/cleaned.ply and mask.bin, rebuilds scene.sog from the
cleaned copy (the first original is kept as scene.orig.sog) and rebuilds collision.json, so deleted
floaters no longer block walking. Reset puts the original back.

    python -m app clean-apply <project> --export 069/test_10k [--reset]
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import numpy as np

from app.core.project import Project, read_json, write_json

PLY_TYPES = {"float": "<f4", "double": "<f8", "uchar": "u1", "char": "i1", "short": "<i2", "ushort": "<u2",
             "int": "<i4", "uint": "<u4", "float32": "<f4", "uint8": "u1", "int32": "<i4"}


def export_dir(p: Project, rel: str) -> Path:
    d = (p.dir / "export" / rel).resolve()  # export/current is a junction to one of the exports
    if ".." in Path(rel).parts or p.dir.resolve() not in d.parents or not (d / "scene.json").exists():
        raise SystemExit(f"no exported scene at export/{rel}")
    return d


def scene_source(d: Path) -> Path:
    s = read_json(d / "scene.json")
    src = s.get("splat", {}).get("source")
    if not src or not Path(src).exists():
        raise SystemExit("this export does not record its source PLY (re-export it)")
    return Path(src)


def ply_layout(path: Path) -> tuple[int, int, np.dtype, list[str]]:
    """(header bytes, vertex count, row dtype, header lines) of a binary little-endian PLY."""
    with open(path, "rb") as f:
        lines, props, n = [], [], 0
        while True:
            line = f.readline()
            if not line:
                raise ValueError("PLY header has no end_header")
            text = line.decode("ascii").strip()
            lines.append(text)
            if text.startswith("element vertex"):
                n = int(text.split()[-1])
            elif text.startswith("element") and n:
                raise ValueError("only PLYs with a single vertex element are supported")
            elif text.startswith("property"):
                parts = text.split()
                if parts[1] == "list":
                    raise ValueError("list properties are not supported")
                props.append((parts[2], PLY_TYPES[parts[1]]))
            elif text == "end_header":
                break
        if "format binary_little_endian 1.0" not in lines:
            raise ValueError("only binary little-endian PLY is supported")
        return f.tell(), n, np.dtype(props), lines


def info(d: Path) -> dict:
    """What the cleanup page needs: source size and sample centres (to check Spark's order), saved mask."""
    src = scene_source(d)
    head, n, dtype, _ = ply_layout(src)
    rows = np.memmap(src, dtype=dtype, mode="r", offset=head, shape=(n,))
    idx = sorted({0, n // 3, n // 2, (2 * n) // 3, n - 1})
    samples = [{"i": int(i), "xyz": [float(rows[i]["x"]), float(rows[i]["y"]), float(rows[i]["z"])]} for i in idx]
    clean = d / "clean"
    edits = read_json(clean / "edits.json") if (clean / "edits.json").exists() else None
    scene = read_json(d / "scene.json")
    return {"count": n, "source": str(src), "source_bytes": src.stat().st_size, "samples": samples,
            "has_mask": (clean / "mask.bin").exists(), "edits": edits,
            "transform": scene.get("splat", {}).get("transform"), "name": scene.get("name"),
            # Where the explorer starts: the cleanup view opens there too (inside the scene).
            "start": scene.get("start"), "eye_height": scene.get("player", {}).get("eyeHeight", 1.6)}


def save_mask(d: Path, mask: bytes) -> dict:
    n = info(d)["count"]
    if len(mask) != (n + 7) // 8:
        raise SystemExit(f"mask has {len(mask)} bytes, the splat needs {(n + 7) // 8}")
    (d / "clean").mkdir(exist_ok=True)
    (d / "clean" / "mask.pending.bin").write_bytes(mask)
    deleted = int(np.unpackbits(np.frombuffer(mask, np.uint8), bitorder="little")[:n].sum())
    return {"count": n, "deleted": deleted}


def apply(p: Project, rel: str, reset: bool = False) -> dict:
    from app.stages.export import export as export_formats
    from app.stages.ply_scene import room_collision
    from app.stages.scene_export import read_ply, write_scene

    d = export_dir(p, rel)
    src = scene_source(d)
    clean = d / "clean"
    scene = read_json(d / "scene.json")
    sog = d / scene["splat"]["url"]
    backup = d / f"{sog.stem}.orig{sog.suffix}"
    if reset:
        if backup.exists():
            shutil.copyfile(backup, sog)
        shutil.rmtree(clean, ignore_errors=True)
        ply_for_collision, deleted, n = src, 0, ply_layout(src)[1]
        print("cleanup reset: original splat restored")
    else:
        pending = clean / "mask.pending.bin"
        if not pending.exists():
            raise SystemExit("nothing to apply: no saved mask")
        head, n, dtype, lines = ply_layout(src)
        rows = np.memmap(src, dtype=dtype, mode="r", offset=head, shape=(n,))
        bits = np.unpackbits(np.fromfile(pending, np.uint8), bitorder="little")[:n].astype(bool)
        keep = ~bits
        deleted = int(bits.sum())
        out = clean / "cleaned.ply"
        header = "\n".join(f"element vertex {int(keep.sum())}" if l.startswith("element vertex") else l
                           for l in lines) + "\n"
        with open(out.with_suffix(".tmp"), "wb") as f:
            f.write(header.encode("ascii"))
            for a in range(0, n, 1 << 20):  # in chunks: 1 M rows at a time
                f.write(np.ascontiguousarray(rows[a:a + (1 << 20)][keep[a:a + (1 << 20)]]).tobytes())
        out.with_suffix(".tmp").replace(out)
        pending.replace(clean / "mask.bin")
        print(f"cleaned PLY: {n - deleted:,} of {n:,} Gaussians kept ({deleted:,} deleted) -> {out}")
        if not backup.exists():
            shutil.copyfile(sog, backup)
        tmp = clean / "sog"
        export_formats(out, tmp, ["sog"])
        shutil.copyfile(tmp / "scene.sog", sog)
        shutil.rmtree(tmp, ignore_errors=True)
        ply_for_collision = out
        write_json(clean / "edits.json", {"source": str(src), "count": n, "deleted": deleted, "time": time.time()})

    # Collision from the (cleaned) splat, in the scene's existing frame: floaters removed = no invisible walls.
    sp = scene["splat"]
    if sp.get("transform"):
        room_collision(read_ply(ply_for_collision), sp["transform"], d, scene["frame"].get("ceiling_m", 2.6),
                       sp.get("voxel", 0.08))
    elif sp.get("sparse"):
        write_scene(d, scene["name"], sp["url"], Path(sp["sparse"]), ply_for_collision, scene["frame"]["scale"],
                    source_ply=src)
    else:
        print("collision not rebuilt: the export does not record its SfM model")
    print("collision rebuilt")
    return {"count": n, "deleted": deleted}


def cli(project: str, rel: str, reset: bool) -> None:
    res = apply(Project(project), rel, reset)
    print(json.dumps(res))
