# BLK2GO `.b2g` file: decoded contents

Sample: `laz-testdata/hq-office.b2g`: BLK2GO, firmware 4.3.0, "Scan 011" of "Job 001", 2026-06-08 11:30–11:38 UTC, an indoor office walk.
Analysed 2026-10-07, **read-only** (SQLite opened with `mode=ro&immutable=1`). Scripts: `research/tools/b2g_schema.py`, `b2g_peek.py`, `b2g_decode.py`, `b2g_convention.py`.

**Bottom line: a `.b2g` is a plain SQLite 3 database holding the raw sensor streams.** The on-device SLAM trajectory at **200 Hz with full orientation**, the **raw IMU at 200 Hz**, and the timestamped panoramic images can all be read with Python's built-in `sqlite3` + NumPy, with no Leica SDK and no Cyclone step. Every value is on one documented clock: **`ClockFrequency = 125000000`** (8 ns ticks).

## Tables

| Table | Rows | Content (decoded) |
|---|---|---|
| `config` | 37 | Key/value metadata. Clock frequency, chunk-format versions, device model/serial/firmware, scan start/end times, `system-epoch-ns` + `main-fpga-ticks` (UTC clock anchor), navigation-solution JSON (`NS_TYPE_DRAFT`, lidar pose stream) |
| `configfiles` | 2 | `config.yml`: pano images allowed (H264 storage setting), `pointFilterConfig: NoFilter` (full density), `slamInitMode: Static` |
| `calibration` | 3 | Protobuf blobs: `alster.calibration.lidarcalibration.ScanSysParam` (2.2 KB), `…imucalibration.ImuSysParam` (272 B), `…cameracalibration.CamSysParam` (≈ 1 MB: camera intrinsics/extrinsics, schema not public) |
| **`bodytrajectories`** | 74 chunks | **91,389 poses at exactly 200 Hz** (5.000 ms). Record = 40 B: `u64 ts` · `f32 px, py, pz` (m) · `f32 qw, qx, qy, qz` · `u32 0` |
| `posestreams` | 1 | One initial pose (same 40 B layout) |
| **`imudata`** | 69 chunks | **94,633 samples at 200 Hz.** Chunk = `u32` header + records of 36 B: `u64 ts` · `f32 ax, ay, az` (m/s², \|a\| median 9.812) · `f32 gx, gy, gz` (rad/s) · `u32 id` (= 1) |
| `edmdata`, `fastaxisangledata`, `slowaxisangledata` | 12,416 / 285 / 114 | Raw laser ranges and mirror/base angles (≈ 640 MB). Cyclone turns these into points; we don't need to |
| `panoimagedata` | 1,593 | Panoramic-camera JPEGs, **1456 × 1088**, ≈ 3.4 images/s (3 cameras × ~1.1 Hz), each with a timestamp + 52 B metadata |
| `userimagedata` | 2 | Detail-camera JPEGs, **4056 × 3040** (button presses) |
| `imagefeaturesdata`, `maskdata` | 2,262 / 4 | Visual-SLAM features; static camera masks |
| `slamevents` | 2 | "Static initialization start/finish" (t = 86.95 → 92.45 s since boot) |
| `timestampedevents` | 4 | `user-requested-pano-triplet` button presses, with exact ticks |
| `slammetricdata` | 10 chunks | SLAM confidence metrics (e.g. `trajectory/lidar/confidence`, `visual/objectPointsCount`) |

## Verified conventions (internal consistency checks)

| Item | Finding | Evidence |
|---|---|---|
| Clock | **125 MHz ticks** since device boot (scan ticks ≈ 77–551 s) | `config.ClockFrequency = 125000000`; matches the 296-tick point spacing and the 1.25 M-tick sweep period of the 3DR LAS sample |
| UTC mapping | `utc_ns = system-epoch-ns + (ticks − main-fpga-ticks) · 8` | Gives trajectory start 11:30:28.26 / end 11:38:05.20 UTC vs config `time-started 11:30:29` / `time-finished 11:38:06` |
| Pose layout | position (m) = f0..f2; quaternion = f3..f6 in **(w, x, y, z)** order, **body → world** | Quaternion norm exactly 1.000000. Only this reading makes world-frame specific force constant: (0.03, −0.06, **+9.82**) m/s², spread 0.20 m/s² (the other readings: 1.1–9.6) |
| World frame | **Local, gravity-aligned, Z up, origin = start pose** | Trajectory starts at (0, 0, 0) and ends at (−0.012, −0.035, −0.001) m: a closed loop, 3.7 cm |
| IMU frame vs body | ≈ identical (best-fit rotation ≈ (−1.0°, 1.2°, 3.1°)) | `Rotation.align_vectors` of gyro vs trajectory body rates |
| Trajectory vs IMU timing | \|gyro\| vs trajectory \|ω\| correlation **0.997** at a **+10 ms** lag (trajectory lags the IMU) | Lag search in 5 ms steps; refine to sub-ms in Phase 0 |
| Walk statistics | 456.9 s, 179.8 m, median speed 0.40 m/s (p95 0.87), median \|ω\| 0.33 rad/s | — |

## What this answers (open questions from PLAN §6 / gap research)

1. **Trajectory content, time base, rate, orientation:** answered for the B2G itself: 200 Hz, full 6-DOF, 8 ns device ticks, (w, x, y, z) body→world, gravity-aligned local frame. The BLK Live CSV is no longer needed.
2. **Raw IMU accessible:** **yes**, 200 Hz accelerometer + gyro. The Insta360 1 kHz gyro can be cross-correlated **directly against the BLK2GO's own gyro**, which is cleaner than a differentiated trajectory. Sync method **A is confirmed feasible.**
3. **Clock shared with the points:** the 3DR LAS per-point `gps_time` values are in the same tick units and range, so this is very likely the same clock (verify with one walk exported from 3DR).
4. **Timestamped BLK2GO images:** 1,593 pano frames on the same clock. These are usable as metrically posed anchors (pose = trajectory at image time × camera extrinsic from `CamSysParam`, once decoded) and as a visual cross-check of sync.
5. **A coarse wall-clock anchor (≈ 1 s)** exists through `system-epoch-ns`. It narrows the search window for the fine gyro correlation.

## Caveats

- **Undocumented, reverse-engineered format.** The reader must assert the chunk-format versions it was written for (`BodyTrajectoryChunkFormat = 1.0`, `ImuChunkFormat = 2.0`, `SchemaVersion = 1.0.0`), and fail loudly if they change with firmware.
- **On-device trajectory = `NS_TYPE_DRAFT`.** Cyclone's *Re-Run SLAM* / *Re-observation* can produce a refined trajectory and point cloud.
  - For **time sync** the draft is fine (rotation rates are not affected by cm-level refinement).
  - For **registration**, use the trajectory that matches the exported point cloud: either export without re-running SLAM, or take the final trajectory from Cyclone 3DR (`STrajectory`) and compare.
- Physical reference point of the body frame: still undocumented. Estimate the extrinsic from data, plus the static-height test (PLAN §3.4).
- This is an office walk (flat, 0.74 m height range). Forest walks use the same format; the IMU/trajectory decoding needs no change.
