"""Insta360 factory lens calibration (Mei / unified omnidirectional model).

The trailer of an X4 .insv holds an "offset" string such as::

    2_<lens0: 17 values>_16000_6000_71_<lens1: 17 values>_16000_6000_71_<id>

with, per lens::

    xi  fx  fy  cx  cy  yaw  pitch  roll  tx  ty  tz  k1  k2  k3  p1  p2   (then W H <tag>)

Pixel coordinates refer to a reference canvas of W x H = 16000 x 6000. That is
two 8000 x 6000 sensor frames side by side: lens1's cx is about 8000 + 4000.
Each 2880 x 2880 lens track in the video is mapped to that frame by
``SensorToTrack`` (by default: centred square crop, then scaling).

Projection of a unit ray (x, y, z) in the lens frame (z along the optical axis,
x right, y down in the image), following Mei 2007 / OpenCV ``omnidir``:

    m = (x / (z + xi * |X|), y / (z + xi * |X|))
    r2 = mx^2 + my^2
    radial = 1 + k1 r2 + k2 r2^2 + k3 r2^3
    md = m * radial + tangential(p1, p2)
    u = fx * mdx + cx,  v = fy * mdy + cy          (sensor-frame pixels)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

LENS_FIELDS = ("xi", "fx", "fy", "cx", "cy", "yaw", "pitch", "roll",
               "tx", "ty", "tz", "k1", "k2", "k3", "p1", "p2")


@dataclass
class MeiLens:
    xi: float
    fx: float
    fy: float
    cx: float
    cy: float
    k1: float
    k2: float
    k3: float
    p1: float
    p2: float
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    t: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def scaled(self, s: float, dx: float, dy: float) -> "MeiLens":
        """Same lens with pixel coordinates mapped by u' = s * (u - dx)."""
        d = asdict(self)
        d.update(fx=self.fx * s, fy=self.fy * s, cx=(self.cx - dx) * s, cy=(self.cy - dy) * s)
        return MeiLens(**d)

    def project(self, rays: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """rays: (..., 3) in the lens frame. Returns u, v (pixels) and validity."""
        x, y, z = rays[..., 0], rays[..., 1], rays[..., 2]
        n = np.sqrt(x * x + y * y + z * z)
        den = z + self.xi * n
        valid = den > 1e-9
        den = np.where(valid, den, 1.0)
        mx, my = x / den, y / den
        r2 = mx * mx + my * my
        radial = 1 + self.k1 * r2 + self.k2 * r2 * r2 + self.k3 * r2 * r2 * r2
        dx = 2 * self.p1 * mx * my + self.p2 * (r2 + 2 * mx * mx)
        dy = self.p1 * (r2 + 2 * my * my) + 2 * self.p2 * mx * my
        u = self.fx * (mx * radial + dx) + self.cx
        v = self.fy * (my * radial + dy) + self.cy
        return np.stack([u, v], axis=-1), valid


@dataclass
class SensorToTrack:
    """How a lens track's pixels relate to its calibration frame (sensor_w x sensor_h)."""
    sensor_w: float = 8000.0
    sensor_h: float = 6000.0
    track_size: int = 2880

    def apply(self, lens: MeiLens, lens_index: int) -> MeiLens:
        crop = min(self.sensor_w, self.sensor_h)
        dx = lens_index * self.sensor_w + (self.sensor_w - crop) / 2
        dy = (self.sensor_h - crop) / 2
        return lens.scaled(self.track_size / crop, dx, dy)


def parse_offset_string(s: str) -> list[MeiLens]:
    """Parse the long (17 values per lens) X4/X5 offset string."""
    vals = s.split("_")
    if vals[0] != "2":
        raise ValueError("expected a 2-lens offset string")
    nums = [float(v) for v in vals[1:]]
    per_lens = len(LENS_FIELDS) + 3  # + W, H, tag
    if len(nums) < 2 * per_lens:
        raise ValueError(f"offset string too short for the Mei layout ({len(nums)} values)")
    lenses = []
    for i in range(2):
        d = dict(zip(LENS_FIELDS, nums[i * per_lens: i * per_lens + len(LENS_FIELDS)]))
        lenses.append(MeiLens(xi=d["xi"], fx=d["fx"], fy=d["fy"], cx=d["cx"], cy=d["cy"],
                              k1=d["k1"], k2=d["k2"], k3=d["k3"], p1=d["p1"], p2=d["p2"],
                              yaw=d["yaw"], pitch=d["pitch"], roll=d["roll"],
                              t=(d["tx"], d["ty"], d["tz"])))
    return lenses


def best_offset_string(candidates: list[str]) -> str:
    """Pick the longest string that parses with the Mei layout."""
    for s in sorted(candidates, key=len, reverse=True):
        try:
            parse_offset_string(s)
            return s
        except ValueError:
            continue
    raise ValueError("no Mei-model calibration string found")
