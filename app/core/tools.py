"""Locations of external tools. Overridable with environment variables."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

DEV = Path(os.environ.get("GSL_DEV", r"C:\dev"))


def colmap_exe() -> Path:
    env = os.environ.get("GSL_COLMAP")
    candidates = [Path(env)] if env else []
    candidates.append(DEV / "tools" / "colmap-4.2.1" / "bin" / "colmap.exe")
    found = shutil.which("colmap")
    if found:
        candidates.append(Path(found))
    for c in candidates:
        if c.exists():
            return c
    raise SystemExit("COLMAP not found: set GSL_COLMAP or unpack COLMAP 4.2.1 into C:\\dev\\tools\\colmap-4.2.1")


CUDA12_BIN = Path(os.environ.get("GSL_CUDA12_BIN", r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8\bin"))


def colmap_env() -> dict:
    """Environment for colmap.exe: ONNX Runtime's CUDA provider (ALIKED, LightGlue, LoMa) needs the
    CUDA 12 runtime and cuDNN 9 DLLs. CUDA 12.8 is installed; cuDNN 9 comes with torch in the gs venv."""
    torch_lib = DEV / "envs" / "gs" / "Lib" / "site-packages" / "torch" / "lib"
    extra = [str(p) for p in (CUDA12_BIN, torch_lib) if p.exists()]
    return {**os.environ, "PATH": os.pathsep.join(extra + [os.environ.get("PATH", "")])}


def gs_python() -> Path:
    """Python of the training environment (torch + gsplat)."""
    p = Path(os.environ.get("GSL_GS_PYTHON", DEV / "envs" / "gs" / "Scripts" / "python.exe"))
    if not p.exists():
        raise SystemExit(f"training environment not found: {p}")
    return p
