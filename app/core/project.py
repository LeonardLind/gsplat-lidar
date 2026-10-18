"""Project folder layout and small JSON helpers.

A project lives in ``projects/<name>/``. Raw inputs stay where they are and are
only referenced by path. Every stage writes into its own subfolder:

    projects/<name>/
        project.json        user intent: sources and their raw files
        probe/              per-clip probe reports
        frames/<clip>/      selected fisheye frames, lens0/ and lens1/
        views/              pinhole views reprojected from the fisheye frames
        sfm/                COLMAP database, sparse model
        train/              gsplat runs
        export/             delivery files
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECTS_DIR = REPO_ROOT / "projects"
SCHEMA_VERSION = 1


def project_dir(name: str) -> Path:
    return PROJECTS_DIR / name


def write_json(path: Path, obj: Any) -> None:
    """Write JSON atomically (temp file + os.replace) so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class Project:
    def __init__(self, name: str):
        self.name = name
        self.dir = project_dir(name)
        self.file = self.dir / "project.json"

    def exists(self) -> bool:
        return self.file.exists()

    def load(self) -> dict:
        if not self.exists():
            raise SystemExit(f"No project '{self.name}'. Create it with: python -m app init {self.name} --insv <file>")
        return read_json(self.file)

    def save(self, data: dict) -> None:
        data["schema_version"] = SCHEMA_VERSION
        write_json(self.file, data)

    def clips(self) -> list[dict]:
        return self.load().get("sources", {}).get("insta360", {}).get("clips", [])

    def clip(self, clip_id: str | None) -> dict:
        clips = self.clips()
        if not clips:
            raise SystemExit("Project has no Insta360 clips.")
        if clip_id is None:
            if len(clips) > 1:
                ids = ", ".join(c["id"] for c in clips)
                raise SystemExit(f"Project has several clips ({ids}); pass --clip.")
            return clips[0]
        for c in clips:
            if c["id"] == clip_id:
                return c
        raise SystemExit(f"Unknown clip '{clip_id}'.")

    def stage_dir(self, *parts: str) -> Path:
        d = self.dir.joinpath(*parts)
        d.mkdir(parents=True, exist_ok=True)
        return d
