# Sample data findings

Analysed 2026-10-07 with laspy 2.7 + lazrs (scratch environment). Scripts: `research/tools/inspect_las.py`, `inspect_time.py`, `inspect_full.py`, `inspect_scene.py`.

## Summary: the export path decides which fields survive

| | Sample 1: `Pointloud_Full_Points inside Rectangle 1.laz` | Sample 2: `mac-1.las` |
|---|---|---|
| Exporter | **Cyclone 3DR** (`3DReshaper Lib (C)TECHNODIGIT`) | Unknown (no system/software strings, no creation date). To confirm with the user |
| Format | LAS 1.2, point format **3** | LAS 1.2, point format **2** |
| Points | 46.07 M (685 MB LAZ) | 56.07 M (1.46 GB uncompressed LAS) |
| Extent | 20.3 × 20.3 × 25.4 m | 47.8 × 69.0 × 33.8 m |
| Frame / scales | Local, no CRS; scales ≈ 5e-9 (full int32 range) | Local, no CRS; scales 0.001 (mm) |
| **Per-point time** | ✅ non-zero; apparent **8 ns device ticks** | ❌ **none** (format 2 has no time field) |
| **Intensity** | ❌ **0 everywhere** | ✅ 0–65534, 97.7% non-zero, informative |
| RGB | ✅ 16-bit, 99.86% coloured | ✅ 16-bit (8-bit × 256), 99.8% coloured |
| Classification / returns | All 0 / all single return | All 0 / all single return |

**Neither export has both time and intensity.** Phase 0 must find an export path that keeps both. Candidates:
- REGISTER 360 E57 or PTS;
- a Cyclone 3DR LAS 1.4 export with the timestamps attribute and intensity (3DR ≥ 2024.1 keeps intensity as a proper attribute).

Fallback: join the two exports of the same walk point by point (nearest neighbour, same coordinates) to merge time and intensity.

## Sample 1 (Brazil, Cyclone 3DR LAZ): details

| Property | Value | Implication |
|---|---|---|
| Intensity | **0 for every point** | Targets cannot be found by reflectivity in this export path. Use **geometric targets** (spheres, 3D shapes), or an export path that keeps intensity (sample 2 shows one exists) |
| Classification | All 0 | Ground classification must be done by us (PDAL CSF/SMRF) |
| Returns | return_number = number_of_returns = 1 | PDAL ground filters proceed normally |
| **gps_time** | Non-zero but **not GPS time**: 4.09e10 … 1.09e11. Points are not stored in time order | Per-point timestamps exist |
| Time-step structure | Smallest step between consecutive time-sorted points = **296 units** (also 300); sweeps through the crop recur every **1,250,000 units** exactly; 23,430 sweep segments of ≈ 1,300 points | Consistent with a **125 MHz (8 ns) device tick counter**: 296 × 8 ns = 2.37 µs per point = 422 k pts/s (spec 420 k); 1.25e6 ticks = 10 ms = one 100 Hz mirror revolution (BLK2GO manual). **Hypothesis**, to be confirmed in Phase 0 |
| Time span | 6.82e10 units ≈ **545 s (≈ 9 min)** at 8 ns; start ≈ 330 s, end ≈ 870 s after device start | A typical single walk. The histogram has a long dip (the walker left the crop and came back) |

## Sample 2 (`mac-1.las`): details

From a 5% random sample (2.8 M points), with a crude ground estimate taken as the 2nd percentile of z per 1 m cell:

| Property | Value | Implication |
|---|---|---|
| Coverage | 1,183 of 3,168 one-metre cells in the bounding box are occupied (≈ 37%) | The walk covers an irregular corridor, not the whole box. The **support mask** for navigation matters |
| Terrain relief | Ground z from −8.7 m to +12.5 m, **≈ 21 m relief over ~70 m** | **Steep terrain.** Ground filtering needs slope handling (CSF `bSloopSmooth`, SMRF slope parameter). A RANSAC plane is useless here |
| Height above ground | 0–0.3 m: 9% · 0.3–1 m: 18% · **1–2 m: 23% · 2–5 m: 30%** · 5–10 m: 16% · 10–15 m: 3% · max ≈ 16 m | **Dense understory**: about half of all points are at 1–5 m. That is the hard case for CSF/SMRF (shrubs absorbed into the ground) and for viewer collision (shrubs must stay passable) |
| Colour | Mean RGB ≈ 61 / 75 / 50 (dark, shaded); 69% of points vegetation-green (excess green > 20) | Forest under canopy; the splat-initialisation colours are usable |
| Intensity | Median: ground ≈ 10.7 k, 1–5 m ≈ 6.6 k, > 5 m ≈ 2.4 k; top 0.5% above ≈ p99.5 | Intensity separates ground from foliage (a useful extra feature for ground filtering), and bright retro-reflective targets should stand out in this export path |
| Density | ≈ 17 k pts/m² in plan view (bounding box) | 56 M points needs Potree LoD for the web (point budget 0.5–3 M per frame) |

## Consequences for the plan

1. **Export audit (Phase 0.2) gets sharper:** export the *same* walk through every path (REGISTER 360 LAS / E57 / PTS, 3DR LAS 1.4) and tabulate which keeps time, intensity and RGB. Pick one path that keeps all three, or merge two.
2. **Targets:** geometric design stays the default (it works with any export). Intensity-based detection (retro tape, Leica B&W auto-extraction) is a bonus where the export keeps intensity.
3. **Ground and navigation testing can start now on real data:**
   - `mac-1.las` = a steep slope with dense understory: the hard case.
   - Sample 1 = tropical, shorter.

   Run the CSF / SMRF parameter sweep, the support mask and stem extraction on both in Phase 0, before any capture.
4. Per-point time (sample 1) enables time-based pass splitting and operator / moving-object filtering, once the clock is confirmed.
5. Both samples are good Potree / web stress tests (46–56 M points).
