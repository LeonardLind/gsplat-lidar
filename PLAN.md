# Fused LiDAR + Gaussian-splat explorer: research summary and plan

**Status:** draft for review. No code written yet.
**Date:** 2026-10-07. Revision 2 adds your answers (personal non-commercial project, camera not X6, Luciad available, OneDrive off, Cyclone EPP licence that covers personal use), the sample-data analysis ([research/sample-data-findings.md](research/sample-data-findings.md)) and the gap-fill research. Revision 2.1 corrects the hardware: it is a **desktop RTX 3080 with 10 GB VRAM**, not a 16 GB laptop GPU (details in §2.10). Revision 2.5 decodes your `.b2g` file: SQLite with a 200 Hz trajectory, 200 Hz raw IMU and pano images on a confirmed 125 MHz clock ([b2g-findings](research/b2g-findings.md)). Revision 2.4 adds the second LiDAR sample (`mac-1.las`: intensity but no timestamps; a steep, dense forest). Revision 2.3 explains the data tiers and viewer quality presets (§0.1) and records that Cyclone is on both PCs and that the project folder stays in place. Revision 2.2 compares the home and office PCs (§2.10a) and adds a **quality-first policy and a list of provisional decisions**, each settled at **checkpoint D1** before the first real test (§0.1).
**Evidence:** 18 research topics, each fact-checked by a second agent against primary sources (GitHub repos and LICENSE files, vendor manuals, release notes, regulator pages, papers). The full trail, with every URL and every correction, is in [research/digest/](research/digest/). Raw results are in [research/raw/](research/raw/).

**How to read this document**

| § | Content |
|---|---|
| 0 | Decisions at a glance, and where I recommend changing your starting assumptions |
| 1 | Research summary: recommended stack, alternatives, trade-offs, licences |
| 2 | Architecture and step-by-step pipeline, including the modular capture sources and UI flow |
| 3 | Capture protocol and field checklist for the 10×10 m test, including sync and offset measurement |
| 4 | Risks and unknowns, each with a cheap test |
| 5 | Phased plan with milestones and acceptance criteria |
| 6 | Clarifying questions |
| 7 | Key sources |

> **Confidence note.** Many details changed during fact-checking: stale PyPI releases, file-format version traps, and Luciad changing owner. This plan uses the corrected versions. Search capacity ran out partway through the research, so some claims were verified only by fetching known primary pages. Items still marked **(verify day 0)** are cheaper to settle with your own hardware than with more research, and Phase 0 is built around them.

---

## 0. Decisions at a glance

| Area | Your starting point | Recommendation | Main reason |
|---|---|---|---|
| 360 video → training images | Blender virtual cameras + FFmpeg | **Use the raw `.insv` lens tracks, not stitched video.** Extract each fisheye track losslessly with FFmpeg. In Python, reproject each lens into a few pinhole views (factory calibration) and declare all of them to COLMAP as one fixed **rig** (2 lenses × N views). Fallback: a Studio equirect export with all stabilisation off, cut into COLMAP's 12-view rig (fork of `pycolmap.panorama`), accepted only after a static-marker test. | Raw X5 lens tracks are confirmed body-fixed (no in-camera 360 stabilisation). Studio exports showed an undocumented heading and a start trim, plus seam parallax at trunk distance. Blender adds blur, colour and axis-convention pitfalls with no geometric benefit. |
| Run 2 (camera only, held higher) | Second loop with LiDAR stopped | **Keep the BLK2GO scanning through every pass**: one continuous scan of ≤ 10 min with 3+ passes at different heights, including interior paths, starting and ending at a staked point. | Every frame then gets metric pose information in the same LiDAR frame, the LiDAR gets a second pass, and the extrinsic gets more data. A camera-only pass still works (through joint SfM) but is the weaker option. |
| Time sync | Clap | **Cross-correlate angular rate.** Use the Insta360's 1 kHz gyro (stored in the .insv) against angular rate derived from the BLK2GO trajectory, with deliberate twists at start and end to estimate offset and clock drift. The clap stays as a marker on the Insta360's own timeline only. | The BLK2GO records no audio. Rotation is sensed by both devices and is frame-independent. **Confirmed from your `.b2g` file:** it is a plain SQLite database. It holds the BLK2GO **trajectory at 200 Hz with full orientation** and the **raw IMU at 200 Hz**, on a stated 125 MHz clock, all readable directly in Python ([b2g-findings](research/b2g-findings.md)). So the Insta360 gyro can be correlated against the BLK2GO's own gyro. The Cyclone 3DR `STrajectory` script becomes the cross-check for the final processed trajectory. |
| SfM | COLMAP / GLOMAP | **COLMAP 4.2.1.** GLOMAP has been merged into COLMAP as `global_mapper`. Use rig mode and the official Windows CUDA build via CLI. | BSD licence, rigs, learned features, pose priors and a built-in 360 workflow in one tool. |
| Splat trainer | Free/open, no watermark | **gsplat** (Apache-2.0) in a thin project fork. Backups: Brush (Apache-2.0), NVIDIA 3DGRUT (Apache-2.0), LichtFeld Studio (GPL-3). Because this is a **personal non-commercial project**, research-licensed tools (Inria 3DGS family, WildGaussians, Hierarchical 3DGS, MASt3R, VGGT) are also usable for comparison or for specific problems (§1.14). | Scriptable from Python, hard splat-count cap (MCMC), masks, LiDAR depth and initialisation hooks, exposure compensation (PPISP). gsplat already reimplements most research ideas, so it stays primary. |
| LiDAR ↔ splat alignment | Measured offset as prior; software estimate; compare | A **staged estimator**: 1. coarse similarity transform from time-synced trajectories; 2. robust ICP on *ground + tree trunks*; 3. per-frame extrinsic; 4. joint least squares over transform, extrinsic, time offset and drift. Your **tape measurement is held out** and compared with a PASS/WARN/FAIL report. Afterwards, a **LiDAR-anchored bundle adjustment** (position priors from the BLK2GO) produces the final training poses. | Geometry fixes all 7 degrees of freedom, vertical included, without depending on sync. The trajectory gives the initial guess and the extrinsic. Where they disagree, the pattern says *why*. Every forest study that worked well anchored its camera poses to LiDAR or RTK; prior-free SfM is kept only for the independent check. |
| Splat coordinate frame | n/a | **Train directly in the LiDAR metric frame.** Transform the COLMAP model first, then train with gsplat's `normalize_world_space` off. | The splat is metric and aligned from the start, with no fragile post-hoc transform of SH coefficients. |
| Splat output format | `.splat` | Keep **`.ply` (SH3) as master**. Deliver **Spark `.rad`** (LoD streaming) with **SOG** as fallback. Use glTF `KHR_gaussian_splatting` in 3D Tiles for Luciad/Cesium. **`.splat` is obsolete** (no SH, no LoD, larger than SOG). | Compression and LoD streaming matter more for the web than anything else here. |
| Viewer | Three.js welcome | **Vite + TypeScript + three.js + Spark 2.3** for splats, plus **Potree 2.0** for LiDAR. Collision runs against a LiDAR-derived ground model and trunk cylinders, never against the splat. | Spark is MIT-licensed, has LoD and runs on WebGL2 phones. Its splats composite correctly with ordinary three.js geometry. |
| Luciad | Probably can load large splats | **Second viewer, via a 3D Tiles export.** You have access to any version and contact with the team. Luciad is now **"Octave Alto"** (spun off from Hexagon on 28 May 2026); LuciadRIA has had splats since **2026.1**, via 3D Tiles. | It is **WebGPU-only**, which excludes older phones, so the three.js viewer stays primary. Your contact with the Luciad team can settle open details (SH rendering, SPZ version, deployment terms). |
| Training splat budget | n/a | One master at **2 M splats (SH3)**. A 3 M "high" variant needs `packed` and possibly 1440 px views on the **10 GB** RTX 3080. Deliver with LoD: phones **0.5–1 M**, desktop **≈2.5 M**, SH1–2. | Quality gains flatten beyond 1–2 M (measured: +0.12 dB from 2 to 3 M), and phones handle about 1 M. |
| Drone | Idea | **Option (c): a separate aerial layer, optional, only if the viewer should offer above-canopy views.** Reject (b), merging into one splat. **Phase 1 stays ground-only.** Free Lantmäteriet open data (CC0/CC BY) provides the surrounding context. If you do buy a drone: **DJI Mini 5 Pro** (C0, ≈ 9–13 k SEK). | No measured gain at walking height. Aerial↔ground SfM fails in forests. A Swedish publishing permit (~65 working days) is needed for anything drone-derived, including private git, cloud and shared web pages (§1.13). |
| **Which computer** | Home PC or office PC | **Provisional: home PC** (RTX 3080, 10 GB) for the whole pipeline, with the final decision at checkpoint D1 (§0.1). Cyclone is installed on both PCs, so the office PC is not needed for this project. | The GPU decides this project. The home RTX 3080 has 25% more VRAM (10 vs 8 GB) and roughly 1.5–1.7× the bandwidth and compute of the office RTX 5060, and Ampere is the most broadly supported architecture. The office PC only wins on CPU and RAM (§2.10a). |
| 360 camera model | TBD | **Not the X6** (your answer), so plan for the **X5**, which has the best open tooling. The X4 family works too: telemetry-parser master reads X4 and X5. | The X5 has 1 kHz IMU data, per-frame exposure records and factory calibration in the `.insv`, all parseable with open tools. |

**Answered on 2026-10-07:**
- Personal non-commercial project.
- Camera is not the X6.
- Luciad is available.
- OneDrive is off.
- Cyclone REGISTER 360 PLUS and 3DR are available via the EPP licence.
- The sample LAZ shows **per-point timestamps** (an apparent 8 ns device clock) and **zero intensity** ([findings](research/sample-data-findings.md)).

**Still most useful from you** (§6):
1. ~~A short BLK2GO walk~~. **Done:** `hq-office.b2g` received and decoded ([b2g-findings](research/b2g-findings.md)). Optional next: the same walk exported from Cyclone 3DR as LAS (with timestamps), to prove the point clock equals the B2G clock.
2. X5 or X4 exactly.
3. ~~Laptop RAM and driver~~. Answered: a desktop PC with Ryzen 7 7800X3D, 32 GB RAM, **RTX 3080 10 GB**, driver 596.36, VS 2022 Community 17.14 with MSVC 14.44 already installed.

### 0.1 Quality-first policy and provisional decisions

**Your priority (stated 2026-10-07): quality first, time does not matter.** Leaving a training run on for hours or days is fine. What this changes:

- **GPU memory, not time, is the hard limit.** Running longer does not let a 10 GB card hold more splats. Quality comes from spending time on more careful processing, and from *working around* the memory limit.
- **SfM: spend the time on accuracy.**
  - Learned features (LoMa, ALIKED + LightGlue) as the default rather than SIFT-first.
  - Richer matching: sequential + vocab tree + spatial priors, plus exhaustive matching within windows.
  - Run both the incremental and the global mapper and keep the better reconstruction.
  - Denser frames (0.2–0.25 m) and more views per frame (7 per lens instead of 5).
- **Training: spend the time on more steps and comparisons.**
  - 60–100 k steps instead of 30 k.
  - A small sweep of configurations and seeds, picking the best by held-out PSNR/LPIPS plus visual inspection.
  - Full ~1600 px views where VRAM allows.
  - PPISP and the LiDAR depth loss on by default.
  - Rolling-shutter-aware training (3DGUT path) and surface-aware variants (2DGS/RaDe-GS, allowed under the non-commercial licence) as A/B tests for trunk geometry.
- **Tiled training even for the small plot** is the main way to get more total detail out of a 10 GB card:
  - split the scene into overlapping tiles;
  - train each tile with the full VRAM budget (≈ 2–3 M splats);
  - merge, then serve through Spark LoD. The desktop paging pool holds up to ~16.7 M splats, and LoD draws ≈ 2.5 M per frame.

  The 4-tile seam test (§4) decides whether this works.
- **Research option to exceed VRAM: CPU-offload training.** CLM-GS keeps Gaussians in system RAM, about 8 GB of RAM per 10 M Gaussians. It is Inria non-commercial (OK here) and Linux-only, so it would run under WSL2. More RAM helps here, and that is the one scenario where the office PC's 64 GB could matter.
- **Capture:**
  - slower walking (0.3–0.4 m/s);
  - an extra pass;
  - test captures in both **8K30 and 5.7K60** to settle resolution vs rolling shutter empirically.
- **Multi-day runs need some operations care:**
  - checkpoint every few thousand steps, with automatic resume;
  - set Windows Update active hours / pause updates so the PC does not auto-restart;
  - power plan with no sleep;
  - logs to disk; one GPU job at a time; no gaming on the GPU during a run;
  - optionally a UPS.
- **Web delivery limits do not change.** Phones still draw only 0.5–1 M splats. Quality-first mostly improves the desktop and close-up experience, and gives LoD a better master to simplify.

**Nothing is thrown away: four tiers of data.** Your "graphics settings" picture is right for *viewing*. It is not quite right for *training*:

| Tier | What | Quality limited by | Lost forever? |
|---|---|---|---|
| 1. Raw capture | `.insv` video, BLK2GO `.b2g` / LGSx / E57 | Only the camera and the scanner | **No.** It is never deleted; the permanent source of truth |
| 2. Processed data | Frames, masks, SfM poses, registration, LiDAR ground and stems | Nothing GPU-related | **No.** It can be rerun any time |
| 3. Trained master splat | The PLY (SH3), the "full quality" file | **The training GPU's memory**: all splats being optimised must fit on the card at once, so about 2–3 M per model and ~1600 px views on 10 GB | **No.** It can be retrained from tiers 1–2 at any time on a bigger GPU. Tiling or CPU offload lift the limit even on this card |
| 4. Delivery versions | LoD `.rad` / SOG, SH0–SH1 phone files | The *viewing* device. These are the "graphics settings" | **No.** They are derived from the master in minutes, and the master is never modified |

- **Viewing works exactly like game graphics settings.** The LoD file keeps the full master. The viewer chooses how many splats to draw per frame, which SH level to use and what resolution to render at. Turning the setting up shows more detail; nothing in the data changes.
  - The viewer gets **Low / Medium / High / Ultra presets**, auto-selected per device and switchable by the user. They control the LoD splat budget (`lodSplatScale`), the SH level (loads the SH0/1 or SH3 file), the pixel ratio and the LiDAR point budget, similar to Luciad's quality profiles.
- **Training is different.** The 10 GB card sets a ceiling on how detailed *one trained model* can be. That is a limit on what gets **created**, not a display setting. It is not permanent:
  - **(a) Tiled training** gives each part of the scene the full card, so the combined master exceeds what fits at once. The viewer then streams it with LoD; Spark pages up to ~16.7 M splats on desktop.
  - **(b) CPU-offload training** is a research option.
  - **(c) A bigger GPU later** can retrain a better master from the very same raw capture.

  The only things truly limited by the hardware are *how good today's master is* and *how fast you get it*. The data stays complete.

**Provisional decisions.** These are the *current best assumptions*. Each gets a **final decision at checkpoint D1**: end of Phase 0, after the backyard rehearsal data exists and before the Swedish forest capture is processed. Results go into `docs/decisions.md`, with the measurements behind each choice.

| # | Decision | Current assumption | How the final decision is made at D1 |
|---|---|---|---|
| P1 | **Which computer** | **Home PC** (RTX 3080 10 GB) | Run the same benchmark on both PCs: peak VRAM at max cap, the largest cap that fits, held-out quality at equal steps. With quality first, **VRAM capacity and software maturity weigh most and speed least**. The office PC (8 GB) could only win if CPU-offload training on its 64 GB RAM proves clearly better |
| P2 | Image path | Raw per-lens fisheye → pinhole rig | A/B against Studio equirect → 12-view rig: reprojection error, LiDAR cloud-to-cloud distance on trunks, held-out PSNR |
| P3 | Video mode | 8K30 | 8K30 vs 5.7K60 test clips: sharpness, rolling-shutter skew, final splat quality |
| P4 | Trainer | gsplat (patched main) | gsplat vs Faster-GS vs LichtFeld vs Inria/Taming at equal splat count, judged on quality only |
| P5 | Splat count and tiling | 2 M single model (3 M with `packed`) | Single model vs 4-tile split at the max per-tile budget; check seams |
| P6 | Features and mapper | LoMa / ALIKED + LightGlue; incremental and global both tried | All combinations on the rehearsal data: % registered, components, reprojection error |
| P7 | Sync method | A: gyro vs 3DR trajectory poses | After the Phase 0 BLK2GO export audit |

After D1, reopen a decision only if the Swedish forest test fails on it.

---

## 1. Research summary

### 1.1 Recommended stack (as of October 2026)

| Layer | Choice | Version / date | Licence | Windows notes |
|---|---|---|---|---|
| 360 camera | **Insta360 X5** (you confirmed it is not the X6; X4 also workable) | X5 Apr 2025 | proprietary hardware | Keep the raw `.insv` files |
| Insta360 metadata | Own Python trailer parser following **GyroView `FORMAT.md`**, cross-checked against **telemetry-parser** built from master | GyroView X6 support 1 Oct 2026; telemetry-parser PyPI 0.3.0 is from **Jan 2024** (stale) | MIT / MIT-or-Apache | telemetry-parser: build with maturin; Windows wheels stop at Python 3.12 |
| Decode | FFmpeg | 8.1 / 9.0 | LGPL/GPL | `-fps_mode passthrough`; keep presentation timestamps (PTS) |
| Reprojection | **OpenCV-contrib `omnidir` / NumPy remap of the raw per-lens fisheye tracks** (primary); fork of `pycolmap.panorama` (stitched fallback) | COLMAP 4.2.1 | Apache-2.0 / BSD-3 | Factory Mei calibration from the trailer; add user masks and timestamped naming |
| BLK2GO poses | **Cyclone 3DR script** (`STrajectory.GetPoseInfo` → timestamp + 4×4 pose; `Save()` to CSV) on the LGSx published by REGISTER 360 PLUS. Fallback: REGISTER 360 *Pano images* pose TXT (x, y, z, qw, qx, qy, qz) at WayPoints | 3DR ≥ 2024.1 | Leica (your EPP licence) | Needs no WORKFLOW option; the CSV layout is only learned after the first export |
| Masks | **SAM 2.1** video propagation; SAM 3 optional | SAM 2.1 Sep 2024; SAM 3.1 Mar 2026 | Apache-2.0; SAM 3 uses its own licence (commercial OK, military/ITAR banned) | |
| SfM | **COLMAP 4.2.1** `colmap.exe` (CUDA) + pycolmap (CPU) for I/O and alignment | 29 Sep 2026 | BSD-3 | The official zip carries its own CUDA 13 runtime and needs only a **driver ≥ 580** (install R595+, skip 595.59). For learned features, start it from a `colmap_gpu.bat` that puts CUDA 12.8 + cuDNN 9 first on PATH. Run LoMa in FP32 |
| Registration | Open3D, small_gicp, SciPy, pycolmap; evo as CLI only | Open3D 0.20 (Sep 2026) | MIT / MIT / BSD / BSD; evo GPL | All have cp312 Windows wheels |
| LiDAR I/O | laspy + lazrs, pye57; PDAL (conda-forge) | laspy 2.7, lazrs 0.8.2, pye57 0.4.19, PDAL 2.10 | BSD-2 / MIT / MIT / BSD | Read E57 per scan with pye57; PDAL merges every cloud in the file |
| Ground / navigation | PDAL `filters.csf` / `filters.smrf`, GDAL; 3DFin as a standalone cross-check | PDAL 2.10 | BSD; 3DFin GPL | |
| Splat training | **gsplat main**, pinned commit (e.g. `512d366`) **plus the MSVC fixes from PR #1055** (main does not build with MSVC as-is) | main Sep 2026; PyPI 1.5.3 Jul 2025 | Apache-2.0 | **Python 3.11, torch 2.8.0+cu128, CUDA 12.8.1, VS 2022 Build Tools 17.14 (MSVC 14.44)**. torch 2.9–2.11 break the fused-ssim build on Windows. Speed option: **Faster-GS** (Apache-2.0, Windows, MCMC, ~3–4× faster). Quick fallback: prebuilt `1.5.3+pt24cu124` (Python 3.10) |
| Exposure compensation | PPISP (NVIDIA) | v1.2.1 | Apache-2.0 | Small CUDA extension; no Windows issues reported, but untested (verify day 0) |
| Splat post-processing | PlayCanvas **splat-transform**; Spark **build-lod** | splat-transform 3.10 | MIT / MIT | Node ≥ 22; Rust toolchain for build-lod |
| Web viewer | three.js ≥ r180, **Spark 2.3.1**, PotreeConverter 2.1 + Potree loader, three-mesh-bvh | Spark 1 Oct 2026 | MIT / BSD-2 / Apache-2.0 / MIT | Pin Spark ≥ 2.1: older versions break on Chrome 149+ |
| Backend and UI (Phase 3) | FastAPI ≥ 0.135 (native server-sent events), Starlette ≥ 1.7, Pydantic v2; Vite/TypeScript UI | 2026 | MIT | Stages run as subprocesses inside Windows Job Objects |
| Environment | **pixi** (conda-forge, for PDAL) + **uv** venvs for the CUDA stacks: `pipe`, `gs`, optional `3dgrut` and `inria` | 2026 | BSD-3 / MIT | **One CUDA toolkit (12.8.1)**. Each venv's activation script sets CUDA_HOME, PATH, `TORCH_CUDA_ARCH_LIST=8.6`, `DISTUTILS_USE_SDK=1`. The project stays in `Desktop\Code\Gsplat+Lidar`. Only compiled tool builds, venvs and caches go in a short space-free folder (`C:\dev\`) |
| Optional Luciad/Cesium | py3dtiles (LiDAR → PNTS); splat GLB via splat-transform; Niantic `spz` library for SPZ | py3dtiles 12.1.1 | Apache-2.0 / MIT | py3dtiles on Windows unverified |

### 1.2 Insta360 cameras: video, gyro and export formats

**Current lineup.**
- **X6** (12 Aug 2026, US$700): 1/1.1″ sensors, 8K at up to 50 fps, 6K60, 10-bit H.265 (even in Standard colour mode), 120 MP stills, 196 g. About 140 min at 8K30 but only about 79 min at 8K50.
- **X5** (Apr 2025): 1/1.28″ sensors, 8K30 / 5.7K60, 180 Mbps, 72 MP stills, about 200 g, about 93 min at 8K30.
- X4 Air and X4 are older and have smaller sensors. The ONE RS 1-inch is discontinued. The DJI Osmo 360 is a viable alternative, and telemetry-parser added support for it in Jun 2026.

**File format.** One `.insv` per clip. It is an MP4 container with **two square HEVC fisheye tracks**, AAC 48 kHz audio and a binary **trailer** holding:
- factory dual-lens calibration: a Mei/"unified" omnidirectional model per lens plus the lens-to-lens transform. The baseline is about 30 mm. X5 uses `offset_v3`; X6 uses `v6`, which has 27 tokens per lens.
- raw gyro and accelerometer data. On the X5 this is **1 kHz with microsecond timestamps**.
- **per-frame exposure records**: the time of the frame's middle row plus the exposure duration.
- a rolling-shutter readout field, and GPS.

The IMU and the exposure records share one clock, so sub-millisecond frame timing is possible. The X5 rolling-shutter readout (trailer tag 25) is **about 21 ms at 8K30** (GyroView measures a 10.6 ms *half*-readout; insv-stitch uses 21.24 ms) and **about 8 ms at 5.7K60**. That gives up to about 1° of skew at 100°/s. Read the value from each file.

**Tooling reality.**
- Insta360's own Media/Camera SDKs are C++, available only by application, and list models up to X5. Do not depend on them.
- telemetry-parser master handles X4 and X5, not X6. GyroView (MIT) documents X3–X6 and is the best public specification.
- ExifTool gives correct timestamps but **wrong IMU units** for the X4–X6 raw layout.
- Gyroflow does not support 360 cameras.
- **Plan:** write a small Python trailer parser (about 300–500 lines) based on GyroView's `FORMAT.md`, and validate it against telemetry-parser on X5 files.

**Timing pitfalls.**
- Get frame times from the exposure records, never from frame index ÷ fps. One third-party observation found the X5 capture clock drifts against the video track by more than one frame in about 4 minutes.
- "30 fps" may really be 29.97. Confusing the two is a 0.1% error, about 0.5 s over a 9-minute walk. Check with ffprobe and tag 78.
- GyroView measured gyro-to-frame residuals per file from +0.4 to −11 ms. Estimate the offset per recording; don't hard-code it.
- Check that the gyro record is present in every file. A damaged camera once wrote none.

**Stitched vs raw.**
- Stitched equirectangular video is not a single-centre projection. An open-source X5 stitcher reports about 18 px of seam ghosting for objects closer than 3 m, which is trunk distance. Optical-flow stitching changes that warp from frame to frame.
- FlowState, Direction Lock and horizon correction re-rotate every frame. Horizon correction is **on by default** in 360 mode and in Studio exports. Any of these destroys the constant camera-to-LiDAR extrinsic.
- **Confirmed:** Insta360's official table says in-camera FlowState is "Not Supported" in 360 modes on X5, X4 and X4 Air. The raw lens tracks are body-fixed.
- Studio exports are *not* proven identical in timing or rotation. One export started 2.98 s into the recording, and Studio's default heading on an X5 was −168.8°. That is why the raw tracks are the primary input (§1.3).

**Settings for splat capture.**
- **360 Video mode, 8K at 25/30 fps.** At the same 180 Mbps cap this gives more bits per frame than 8K50.
- **Manual shutter 1/500 s** (1/250 floor under dark canopy, 1/1000 in good light), **fixed ISO, fixed white balance in Kelvin**, sharpness low or medium.
- Turn off AdaptiveTone, Active HDR, PureVideo and **Jitter Blur Reduction**. AdaptiveTone exposes the two lenses *independently* and disables manual control.
- **5.7K60** is a valid alternative for fast handheld motion: about 2.6× less rolling-shutter skew and twice the frames, at lower resolution.
- X5: Standard or Flat colour (I-Log is unavailable at 8K).
- X6: tracks are 10-bit HLG/BT.2020, so plan a deterministic HLG→SDR conversion. X6 Video mode is "HDR by default" and may not be switchable, so test its frame-to-frame consistency.
- Lens guards off. Use the same lens set for every session; X5 lenses are swappable and swapping changes the calibration. The file records the lens/guard state (tags 68/104), and our ingest logs it. Re-run calibration after any change.
- Timelapse/interval modes exist, but whether they record audio and IMU data is unverified. Do not use them for synced passes.
- Insta360 "Spatial Capture" is proprietary, in-app and quota-limited, so it is excluded.

### 1.3 360 video → SfM and training images

**Your Blender idea, compared with the alternatives.** All of these do the same pinhole (gnomonic) reprojection. The differences are in rig handling, masks, timestamps and exactness.

| Approach | Verdict |
|---|---|
| **Raw dual-fisheye → pinhole crops per lens** (OpenCV `omnidir` / NumPy remap with the factory Mei calibration), declared as one rig: 2 lenses × N views, lens-to-lens translation ≈ 30 mm from the calibration | **Primary (revised after the gap research).** Raw tracks are body-fixed and their frame↔timestamp mapping is direct. No stitch seams, no Studio heading or trim uncertainty. Start with 5 views per lens (one along the axis, four at ±50°, 90° FOV) to cover each ~190° lens. Self-calibrate the intrinsics in COLMAP as a check against the factory values. |
| **Fork of `pycolmap.panorama`** (COLMAP's own 360 pipeline; BSD) on a Studio export with everything off | **Fallback.** 12 SIMPLE_PINHOLE views per frame (4 yaws × pitch −35°/0°/+35°, 90°×90° FOV, 1920 px from 8K). Writes ownership masks so each panorama pixel yields features once, and sets up a rig with zero translation, fixed intrinsics and fixed rig in bundle adjustment. On Windows, use only its *render* function: pycolmap is CPU-only there, the feature type is hard-coded to SIFT and the rig config lives only in memory. Write `rig_config.json` yourself and run `colmap.exe`. The fork adds user masks and timestamped file names. |
| **lichtfeld-360-plugin** (GPL-3, Windows) | **Benchmark.** Reads X5/X4 `.insv` directly, picks sharp frames, masks with SAM 3, solves in COLMAP 4.1 (fisheye, dual-fisheye or equirect). Cannot use LiDAR or external poses. A free end-to-end comparison for our own path. |
| Native fisheye training (gsplat 3DGUT, 3DGRUT, LichtFeld `--gut`) | **Research branch.** The stock gsplat COLMAP loader *undistorts* fisheye images to pinhole, so a custom loader is needed. Many web viewers render 3DGUT-trained splats incorrectly. Delivery splats should be trained on pinhole views. |
| FFmpeg `v360` | Fallback reframer for equirectangular input only. It ignores fisheye intrinsics (it models FOV only), and its yaw and pixel-centre conventions must be checked against the rig. |
| COLMAP 4.1 SPHERICAL camera model | Quick look only. COLMAP itself calls it faster but less accurate than perspective rigs. |
| nerfstudio `ns-process-data` (equirect) / AliceVision Split360 | Stale and without a rig / yaw ring only. Not recommended. |
| LichtFeld 360 plugin (GPL-3, SAM 3 masks, rigs) | A good **GUI benchmark** to compare against. |
| Blender | Not needed. |

**Layout.**
- Raw path: 5 pinhole views per lens (10 per frame). Stitched fallback: COLMAP's 12-view layout, moving to 16 views (8 at the horizon, 4 at +40°, 4 at −40°) only if registration gaps or holes appear.
- Drop dedicated zenith and nadir views: those are where the BLK2GO, your hand and the operator are.
- Use 1920 px views for SfM and train at about 1600 px.

**Frame rate and frame count.**
- Video is dense, so select frames by **distance moved**, not at a fixed fps.
- Decode candidates at about 6 fps and keep the **sharpest frame per 0.3–0.4 m** of path. Score sharpness with Laplacian variance or Tenengrad on masked, downscaled frames.
- After time sync, Run 1 frames can be chosen by distance along the BLK2GO trajectory. Drop stationary segments.
- Expect **about 100–200 panoramas per pass**, which is 1.2–2.4 k virtual views per pass at 12 views. A 3-pass capture gives about **3–6 k training images**.
- The 0.3–0.4 m baseline gives roughly 10–20° of parallax on trunks 1–2 m away.
- Keep the full frame rate only for the sync and calibration segments, and exclude those segments from training.

**Masking** (operator + BLK2GO). Excluding pixels from SfM features and ignoring them in the training loss are separate jobs.
1. **Static rig mask** (BLK2GO body + hand + mount): painted once, remapped into every view with nearest-neighbour sampling and dilated about 15 px. This is valid only because the mount is rigid and stabilisation is off.
2. **Operator masks per frame**: SAM 2.1 video propagation, prompted with a person box from a detector, or SAM 3 with the text prompt "person". Dilate 10–20% and include the shadow.
3. **SfM mask** = NOT(operator ∪ rig) ∧ ownership mask → COLMAP `--ImageReader.mask_path`.
4. **Training mask** = NOT(operator ∪ rig), in **ignore-in-loss** mode. gsplat main already masks L1 and SSIM when the dataset supplies `data['mask']`. Equivalents: Brush `masks/`, LichtFeld `--mask-mode ignore`, 3DGRUT `*_mask.png`. **Never** use alpha or "segment" modes: they carve transparent holes.
5. A **sky mask** for SfM and for the LiDAR depth loss. Optionally also a background model during training.

### 1.4 SfM front end

**COLMAP releases since 2026:**
- **4.0** (Mar 2026): absorbed GLOMAP as `global_mapper` (the standalone repo is archived) and added ALIKED + LightGlue via ONNX.
- **4.1** (Jun 2026): spherical and EUCM camera models, plus Caspar GPU bundle adjustment. Caspar is not in the official Windows zip; the third-party `lyehe/build_gpu_colmap` builds include it.
- **4.2** (Aug/Sep 2026): LoMa learned features and a multi-component global mapper.
- Latest: **4.2.1** (29 Sep 2026).

**Recipe.**
- **Rig:** each 360 frame is a *frame* of a *rig* whose virtual cameras share one optical centre (zero translation, fixed rotations).
- **Matching:** sequential matcher with **loop detection on** and `quadratic_overlap=0`. Its 2^i offsets create about 2,300 pairs per frame once rig expansion is applied. Add vocab-tree matching (or MegaLoc retrieval, MIT) for pairs across passes. Optionally add a spatial matcher using LiDAR position priors.
- **Mapping:** `global_mapper` first, with `refine_sensor_from_rig` and intrinsics refinement **explicitly off**; the command-line defaults differ from those in `panorama.py`. Fall back to the incremental mapper. Use `pose_prior_mapper` with LiDAR priors only if SfM fragments (it is incremental; the global mapper ignores priors).
- **Keep one prior-free reconstruction** so the extrinsic estimate stays independent.
- **Features:** start with SIFT. If fewer than about 95% of images register, or the model splits, switch to ALIKED_N16ROT + LightGlue or LoMa. Never mix feature types in one database.

**Licence traps (do not use in Hexagon work).** All of these have non-commercial weights: SuperPoint/SuperGlue, MASt3R(-SfM), VGGSfM, Pi3/Pi3X, the original VGGT-1B, **VGGT-Ω**, InstantSfM, and Depth Anything 3 Giant/Large. Commercially usable alternatives exist: MapAnything-apache, VGGT-1B-Commercial (gated, no military use) and DA3 Base/Small. Use them only as initialisation for chunks that fail, then finish with COLMAP bundle adjustment.

**Closed fallbacks.**
- **Metashape Pro** (US$3,499): spherical cameras, rigs, laser-scan alignment, and native COLMAP export since version 2.2.
- **RealityScan 2.2**: free only for organisations under US$1 M revenue, so Hexagon needs a paid seat (US$1,250 per year). It imports LAS/E57 and SLAM trajectories.

**Why not simply use LiDAR poses as fixed camera poses?** 1° of orientation error is about 17 px in a 1920 px, 90° view. Sync and extrinsic errors at handheld rotation rates would blur the splat. Keep this as a fallback for SfM failure (likely in dense tropical forest), not the default.

### 1.5 Splat trainers (open source, Windows, 10 GB RTX 3080)

| Trainer | Licence | State (Oct 2026) | Windows | Masks | LiDAR init / depth | Exposure comp. | Splat cap | Verdict |
|---|---|---|---|---|---|---|---|---|
| **gsplat** | Apache-2.0 | PyPI 1.5.3 (Jul 2025); main v1.6.0-dev, active | Prebuilt wheel only for 1.5.3 + torch 2.4; main = source build | Yes via custom loader (main masks L1+SSIM) | Custom loader (stock depth uses SfM tracks only) | Bilateral grid; **PPISP** (main) | MCMC `cap_max` | **Primary** |
| Brush | Apache-2.0 | v0.3.0 (Sep 2025); main active (`units_per_meter`, Oct 2026) | Prebuilt zip (WebGPU) | Yes | Initialisation via `ply_file_path`; no depth loss | None | `max_splats` | No-code baseline / backup |
| NVIDIA 3DGRUT | Apache-2.0 | v1.1.0 (Jun 2026) | Install script | `*_mask.png` | `point_cloud.ply` initialisation; no depth loss | PPISP | MCMC | Backup; fisheye / rolling-shutter research |
| LichtFeld Studio | GPL-3.0 | v0.5.3 (Jun 2026), daily commits | Free **source build** (VS2022 exactly, CUDA 12.8, **path without spaces**); prebuilt only via a paid donation portal | Yes | Initialisation from a splat PLY only | PPISP, bilateral grid | `--max-cap` | GUI backup (standalone use is fine under GPL) |
| Spirula Studio | GPL-3.0 | New; daily releases | Prebuilt | Yes | Experimental LiDAR | n/a | n/a | One side-by-side test |
| **Faster-GS** (NeRFICG, CVPR 2026) | Apache-2.0 | 2026 | Windows supported | n/a | n/a | n/a | MCMC | **Speed option.** Measured on an RTX 4090: 4m31s vs Inria 18m44s; MCMC 6m17s vs the original 27m22s |
| VkSplat | Apache-2.0 | May 2026 | Vulkan (any GPU), Windows | n/a | n/a | n/a | MCMC | Watch item. On an RTX 3090, MCMC 1 M took 285 s vs gsplat's 995 s |
| OpenSplat | AGPL-3.0 | v1.2.2 (Sep 2026) | Source build or paid exe | Yes | n/a | n/a | `--max-gaussians` | Not needed |
| nerfstudio splatfacto(-w) | Apache-2.0 | Stale (Nov 2024; pins gsplat 1.4) | | | | | | No |
| Inria 3DGS and derivatives (3DGS-MCMC, Mip-Splatting, 2DGS, RaDe-GS, Taming base, WildGaussians, RobustSplat, Horizon-GS, CLM, Hierarchical 3DGS) | **Inria non-commercial** (research/evaluation) | Inria repo last commit Oct 2024 | Inria: yes (source build); others mostly Linux | Varies | Inria has a depth-regularisation hook | Inria per-image exposure; WildGaussians appearance | Taming: deterministic budget | **Allowed for this personal project.** Use for comparison or specific problems: WildGaussians (wind/appearance), Hierarchical 3DGS / CLM (large tropical scenes), LightGaussian / PUP-3DGS (pruning for web). Swap out if the project ever becomes commercial |
| PGSR (ZJU licence), CityGS (CC BY-NC-SA) | Non-commercial | | | | | | | Allowed for personal use; low priority |
| Postshot Free, Polycam Free, KIRI, Teleport | Closed | Postshot Free: no PLY export, watermark. Polycam Free: glTF only, watermarked video. KIRI and Teleport process in the cloud | | | | | | Excluded |

**Training facts that shape the pipeline.**
- gsplat's default `normalize_world_space=True` exports the PLY **in a normalised, rotated frame**. Apply the registration transform to the COLMAP model first and train with normalisation off. A bounding-box regression check catches mistakes.
- With MCMC, the final count is max(initial count, `cap_max`). Keep the LiDAR initialisation **below** the cap.
- **VRAM and time.** Measured on an A100 (Mip-NeRF360, about 1.0–1.6 MP images, close to our 1600 px): MCMC 1 M = 2.0 GB / 15 min, 2 M = 3.4 GB / 22 min, 3 M = 5.0 GB / 28 min. On an RTX 3090, gsplat MCMC 1 M took 16.6 min at 1.4 GB.
  - **Your GPU is a desktop RTX 3080 with 10 GB.** About 0.9 GB is already taken by the display, leaving **≈ 9 GB usable**.
  - **Estimate** (unmeasured; scaled from the RTX 3090 figures): about 20–25 min at 1 M, 30–40 min at 2 M, 40–50 min at 3 M.
  - Our square views (1600² ≈ 2.6 MP) are larger than the benchmark images, so expect roughly **4–5 GB at 2 M and 6–7 GB at 3 M**.
  - **2 M fits without `packed`. Use `packed=True` (27–50% less memory, ~6–9% slower) for 3 M.** If it still runs out of memory, drop the views to 1440 px or the cap to 1.5 M. 4 M+ is not realistic.
  - Faster-GS / LichtFeld would be about 3× faster.
  - Optional trick: the 7800X3D has an integrated Radeon GPU. Plugging the monitor into the motherboard output frees the ≈ 0.9 GB of display memory on the 3080, and the iGPU doubles as a low-end device for the web benchmark.
  - Known blow-up: LichtFeld with 3840 px 360-camera frames went from 4.4 GB to 31 GB of VRAM. **Cap training images at 1600 px wide.**
  - Log `max_memory_allocated` and wall-clock on the first forest run.
- Use `packed=True`: it saves 27–50% memory for about 6–9% speed. Stream images from disk (no `--cache_images`).
- **Exposure:** PPISP beats bilateral grids on novel views (24.62 vs 19.78 dB). The virtual views from one 360 frame must *share* one set of exposure parameters per lens, which needs a custom frame-index mapping. Freeze vignetting for reprojected views. In short tests, shorten the controller activation steps. Always keep an uncompensated baseline.
- **Anti-aliased (Mip-filter) training** changes what opacity means, so the viewer must match. For web delivery, train without it or verify in Spark.
- **LiDAR depth supervision:** custom loader; z-buffer occlusion filtering; ground and stems only; L1/Huber with confidence weights; weight decayed later in training; never on sky or foliage.

### 1.6 Registration: SfM/splat ↔ LiDAR, and the device offset

**What the splat actually needs** is only one similarity transform **S** (SfM frame → LiDAR metric frame). The camera↔BLK2GO extrinsic **X** and the time offset **dt** are *by-products* used to check consistency, and they are what your measured-vs-estimated report is about. So splat quality does not depend on sync or mount flex.

**Which approach is most robust?** Both, in stages.

| Stage | Method | Gives |
|---|---|---|
| 0 | Coarse time window from file clocks; fine sync from angular-rate correlation (§1.8) | dt(t) = a + b·t |
| 1 | Robust Sim(3) from SfM camera centres to the BLK2GO trajectory (`pycolmap.align_reconstruction_to_locations` with RANSAC, or Umeyama with truncated least squares). The lever arm must be included: a **position-only fit ignoring the lever arm is biased**. Expect a vertical shift equal to the mount offset, and a scale bias of lateral offset ÷ loop radius (5 cm / 5 m = 1%) | S₀ |
| 2 | Scaled ICP, then robust point-to-plane ICP (Tukey/Cauchy kernel, shrinking distances 0.5 → 0.2 → 0.05 m) between **filtered SfM points** (track length ≥ 4, reprojection error < 1 px) and **LiDAR ground + trunks only**. Foliage moves and gives mixed edge returns, so it is excluded | S_geo (all 7 degrees of freedom, vertical included, sync-independent) |
| 3 | Per-frame X_i = T_LiDAR(t_i + dt)⁻¹ · S · T_cam(t_i); robust mean; refine dt by minimising the scatter of X_i | X, dt |
| 4 | Joint robust least squares (`scipy.optimize.least_squares`) over S, X, dt and drift, with pose-consistency and point-to-plane residuals. Uncertainty from the Jacobian, plus a block bootstrap over 5–10 s segments | Final estimate ± σ |
| 5 | **LiDAR-anchored refinement.** Re-run bundle adjustment (`pose_prior_mapper`) with per-frame position priors from the BLK2GO trajectory × X (motion-inflated σ, §1.8), then a final ICP check. These become the **training poses**. The independent check in stages 1–4 stays untouched | Final camera poses for the splat |

**Hand-eye theory caveat.** Trajectory-only extrinsic estimation (AX = XB) cannot observe the offset along the vertical axis when you only walk and turn (yaw only). Because stage 2 fixes S from geometry, the per-frame X is observable in all six degrees of freedom anyway. A gentle pitch/roll sequence at start and end is cheap insurance (vertical σ ≈ 4 cm → ≈ 0.4 cm by estimate).

**Comparing with your tape measurement.** Compare in a gravity-aligned rig frame (z up from the LiDAR, x = BLK2GO forward). Proposed thresholds, which are engineering proposals rather than literature values:

| Component | First (taped) test | Rigid mount |
|---|---|---|
| Lever arm, each horizontal component | PASS ≤ max(3 cm, 3σ); WARN ≤ 6 cm; FAIL > 6 cm or > 5σ | PASS ≤ 2 cm |
| Lever arm, vertical | Judge against its own σ only | ≤ 2 cm |
| Pitch/roll (inclinometer) | PASS ≤ 2°, WARN ≤ 5° | ≤ 1–2° |
| Yaw (hand-measured) | PASS ≤ 5° | ≤ 2° |
| Scale, trajectory vs geometry | ≤ 0.3% | ≤ 0.3% |
| Sync σ | ≤ 5 ms (≤ 10 ms acceptable) | same |

The report also carries an explicit **reference-point uncertainty**, because Leica does not document where on the BLK2GO the trajectory refers to (§1.7).

**What a disagreement means.** The estimator diagnoses this automatically:

| Pattern | Likely cause |
|---|---|
| Residual along the direction of travel, growing with speed | Time offset |
| Error grows with distance from the centroid, or scale differs per side of the square | Scale error or SfM drift |
| X changes over time or during turns | Mount flex (tape) |
| Errors near 90° or 180°, or a flipped axis | Convention mistake: COLMAP stores camera-from-world, COLMAP cameras are y-down/z-forward, LAS is Z-up, three.js is Y-up, quaternions may be wxyz or xyzw |
| Constant body-frame offset while rotation agrees | Lever arm measured to the wrong reference point |

**Closed loop.**
- The BLK2GO SLAM should correct drift when you return to the start. Leica's documentation does not describe this, so verify it with per-side checks.
- On the SfM side, loop detection plus global bundle adjustment removes most scale drift. A 360 camera recognises a revisited place from any heading.
- Monocular SfM has no absolute scale, but S fixes it.
- **Drift test:** fit a Sim(3) per side of the square. A scale spread above 0.5% means drift, handled with pose priors.

**Validation is independent of the estimator:**
- 4–6 spheres plus AprilTag boards (detected with OpenCV aruco, Apache-2.0);
- one 1.000 m scale bar;
- trunk diameter at 1.3 m fitted in both clouds;
- cloud-to-cloud / M3C2 distances per region (ground, trunks, canopy) and per quadrant;
- the signed vertical bias on the ground.

Targets: median ≤ 2 cm and P90 ≤ 5 cm on hard surfaces, target RMS ≤ 2 cm, ground bias ≤ 1 cm. The BLK2GO accuracy floor is about 1 cm (±10 mm indoor spec), and outdoor studies report 10–60 mm.

**Run 2 / camera-only passes:** `pycolmap.align_reconstructions_via_*` needs *shared images*, so two independently reconstructed videos **cannot** be aligned that way. Reconstruct all passes in **one COLMAP database**, or register the extra frames into the main model.

### 1.7 BLK2GO and Cyclone data (no Leica SDK)

**Hardware (original BLK2GO).**
- LiDAR: 420 k pts/s, 0.5–25 m range, 360°×270° field of view, ±3 mm range noise, ±10 mm indoor accuracy. The older 2019 datasheet says 6–15 mm relative.
- Cameras: three global-shutter panoramic cameras capturing about 1 image per second, plus a 12 MP detail camera.
- Operating temperature 0 to +40 °C on the 2021 datasheet (+5 °C on the 2019 one).
- 775 g with battery, 45–50 min per battery.
- **The BLK2GO PULSE is indoor-only (ToF, 10 m range). Do not take it into the forest.**

**Exports.**
- **Cyclone REGISTER 360 PLUS** (2026.1.1) exports E57, PTS, PTX, RCP, LGS/LGSx and LAS. LAS may need PUBLISHER Pro. **LAZ is not an export option**, so convert in Python with laspy.
- **E57 with WayPoints and rectified, posed images** needs the **WORKFLOW** licence. It is in the GUI since Sep 2026, or available as the CLI `Register360.exe -b2g2trajectory`. Use version ≥ 2026.0.0, which fixed missing WayPoints and a 100-WayPoint cap. Pinhole images use a fixed 6 µm pixel size.
- **Trajectory CSV** comes from **BLK Live** (≥ 2.1.0) or **Cyclone FIELD 360** (≥ 5.0), *not* from BLK Data Manager.

**Getting BLK2GO poses over time.**
- **Primary (verified 2026-10-07 on your file): read the `.b2g` directly.** It is an SQLite 3 database. Opening it read-only with Python's `sqlite3` gives:
  - **`bodytrajectories`**: 200 Hz poses as 40-byte records. Layout: `u64` tick · position x, y, z (m) · quaternion **(w, x, y, z), body → world**. The world frame is **gravity-aligned, Z up, origin at the start pose**.
  - **`imudata`**: 200 Hz raw accelerometer (m/s²) + gyro (rad/s). The IMU frame is ≈ the body frame (within ~3°).
  - **`panoimagedata`**: 1,593 timestamped 1456 × 1088 pano frames; **`userimagedata`**: detail photos; button-press events; static-initialisation events; calibration protobufs.

  Checks passed on `hq-office.b2g`:
  - quaternion norm exactly 1;
  - constant world gravity +9.82 m/s² (only under the (w, x, y, z) body → world reading);
  - \|gyro\| vs trajectory \|ω\| correlation 0.997 (trajectory lags the IMU by ≈ 10 ms);
  - the loop closes to 3.7 cm;
  - UTC mapping matches the scan start and end times.

  **Caveats:** the format is undocumented, so the reader asserts the chunk-format versions in `config` and fails loudly on a firmware change. The on-device trajectory is a SLAM *draft*: use it for sync, and for registration use the trajectory matching the exported cloud. Full details: [research/b2g-findings.md](research/b2g-findings.md).

**Other routes** (gap research, 2026-10-07; now cross-checks and fallbacks):
- **Primary: a Cyclone 3DR script.** REGISTER 360 PLUS publishes the walk as **LGSx**. Cyclone 3DR (≥ 2024.1) imports it, and its documented script class `STrajectory` gives `GetNumberOfPoses()`, `GetPoseInfo(i)` (a 4×4 pose + timestamp), `EstimatePose(t)` (interpolated), `GetTimestampRange()`, `LinkToCloud()` and `Save()` (CSV). This route needs **no WORKFLOW option**. Unknown until the first run: the timestamp units, whether the 4×4 is body→world, and the pose rate.
- **Fallback 1: REGISTER 360 *Publish → Pano images*.** It writes a pose TXT at each WayPoint: x, y, z (m) + quaternion w, x, y, z. WayPoints can be densified anywhere with the Track Editor (≥ 1 m spacing at import).
- **Fallback 2:** `-b2g2trajectory` E57 (WORKFLOW only; not in the BLK edition). Don't use the E57 image `acquisitionDateTime`: Leica's writer stamps the *export* time.
- **BLK Live / FIELD 360 CSV:** columns and time base are still undocumented; inspect the first export.

**Per-point time.** The 8 ns tick hypothesis from your sample is **consistent with the BLK2GO manual**: mirror 100 Hz → 1.25 M ticks; base rotation 2.5 Hz → 50 M ticks; pulse rate 1.64 MHz ≈ 125 MHz / 76; 410–420 k pts/s ≈ 296–305 ticks. **Confirmed:** the `.b2g` config states `ClockFrequency = 125000000`, and its UTC anchor (`system-epoch-ns` + `main-fpga-ticks`) converts ticks to wall-clock time to within a second. Remaining Phase-0 check: one walk exported from Cyclone 3DR, to prove the LAS `gps_time` uses this same counter.
- If trajectory and point times prove to share a clock (compare 3DR `GetTimestampRange()`), we can interpolate the **sensor position for every point**. That enables ray-based free-space and ground logic, and filtering of moving objects.
- The trajectory reference point and body axes are still undocumented. The extrinsic is therefore estimated from data, with the static-height test of §3.4.

**Intensity exists in the raw scan.** REGISTER 360 extracts B&W targets from BLK2GO data, which needs intensity. It was lost in the 3DR LAS export (older 3DR versions stored intensity as an overwritable scalar). **Re-export as PTS or E57 from REGISTER 360** to get it back (verify day 0).

**Built-in targets and SLAM tools.**
- Since 2022.1, REGISTER 360 has **Auto B&W target extraction for BLK2GO walks**: expected target error ±8 mm with Leica's printable 6-inch B&W targets; walk 1–2 m from each target with a 1–2 s stop.
- *Apply Control* with ≥ 3 targets is a rigid fit. GCP-constrained SLAM correction is not documented.
- *Re-Run SLAM* and *Re-observation* at import reduce drift and double walls, at +20–25% import time.

**Forest drift evidence.** No published BLK2GO forest numbers with checkpoints exist.
- Outdoor tests: 10–60 mm (vs about 5 mm indoors).
- One study saw orientation drift outdoors without man-made features (about ±10 cm after correction to TLS). It recommends walking the path **again in reverse**.
- Practitioners keep sessions under about 10 min under dense canopy.
- Hexagon's R-evolution team used a BLK2GO in Costa Rican rainforest (La Gamba) without publishing accuracy. They are a possible contact for the tropical phase.

**Practical notes.**
- Keep BLK Live 3.0's "**Image security**" setting OFF. It can disable image creation, which would mean no panoramas, no colour and no WayPoints.
- Read E57 files per scan with pye57. PDAL merges the trajectory cloud into the scene.
- Keep the `.b2g` file as the master copy.
- Cyclone 3DR can display trajectories and timestamps (LGSx), which is a quick way to inspect what exists.
- Recentre coordinates before anything reaches float32. At Swedish northings (~6.5e6 m) the float32 step is 0.5 m.

**Two sample files, two export paths, two different field sets** ([findings](research/sample-data-findings.md)):

| | Sample 1 (Brazil `.laz`, Cyclone 3DR) | Sample 2 (`mac-1.las`, exporter unknown) |
|---|---|---|
| Per-point time | ✅ (apparent 8 ns ticks) | ❌ (point format 2 has no time field) |
| Intensity | ❌ all zero | ✅ informative (ground ≈ 10.7 k, understory ≈ 6.6 k, canopy ≈ 2.4 k) |
| RGB | ✅ | ✅ |
| Scene | 20 × 20 m crop, 46 M points | 48 × 69 m corridor walk, 56 M points; **steep (~21 m relief), dense understory** (half the points at 1–5 m), canopy up to ~16 m |

**Neither export has both time and intensity.** Phase 0 tries every export path of one walk (REGISTER 360 LAS / E57 / PTS, Cyclone 3DR LAS 1.4) to find one that keeps time, intensity and RGB. Fallback: merge two exports of the same walk point by point.

Sample 1 details:
- **Per-point timestamps are present** in `gps_time`, but they are **not GPS time**. They look like a **125 MHz (8 ns) device tick counter**: the smallest step between points is 296 ticks = 2.37 µs = 420 k pts/s, matching the spec, and sweeps recur every 1.25 M ticks = 10 ms. The span is ≈ 545 s, i.e. a ≈ 9-minute walk.
- **Intensity is 0 everywhere**, so targets must be *geometric* (spheres, 3D shapes) unless another export path carries intensity.
- RGB is present for 99.86% of points; there is no classification; all points are single-return; the frame is local with no CRS.
- Still unknown: whether the trajectory CSV uses the same clock. Checking that is one Phase-0 comparison.

**Hexagon landscape.** No Hexagon/Leica product was found that shows BLK2GO LiDAR and splats together in a browser. Reality Cloud Studio became **Hexagon GeoCloud** (Apr 2026), which shares point clouds only.

### 1.8 Time synchronisation

**No hardware sync exists.** The BLK2GO has only Wi-Fi/USB. Insta360 timecode input works only from an external generator. File timestamps are good to about ±1 s, which only narrows the search window.

| Method | Accuracy | Needs | Role |
|---|---|---|---|
| **Gyro \|ω\| cross-correlation**: Insta360 1 kHz gyro vs the **BLK2GO's own 200 Hz gyro** from the `.b2g` (or its 200 Hz trajectory) | ~1–3 ms expected (both are raw gyros; 200 Hz with good excitation) | The `.b2g` file: **available**, verified on `hq-office.b2g` (§1.7) | **Primary** |
| SfM camera rotations vs BLK2GO rotations | ~5–10 ms | Full-rate frames in the sync segments | Independent check |
| Position-based spatio-temporal fit (dt plus lever arm from positions; 1 cm ≈ 10 ms at 1 m/s) | ~10–20 ms | Timestamped positions only | Backup if no orientation |
| Time-free geometric registration | n/a | Nothing | Last resort: S still works, but the extrinsic check is weaker |
| Clap / tap | n/a for the BLK2GO | Insta360 audio | Marks the Insta360 timeline and checks the camera's own audio-to-IMU alignment |
| Filming the BLK2GO start button or light | ~±1 frame | Visible event | Coarse cross-check of what trajectory t = 0 means |

**Error budget.** At 1 m/s and 90°/s turning, a 10 ms error ≈ 1 cm and 0.9°. **Target ≤ 5 ms** (≤ 10 ms acceptable); one frame (33 ms) is not acceptable.

**Clock drift.** Budget 10–50 ppm between the two devices, which is 9–45 ms over 15 minutes. Always estimate **offset and rate** from start and end events, robustly fitted with Theil–Sen.

**Gesture design.** Use *aperiodic* twists of different amplitudes at irregular intervals (e.g. 0.4 / 1.1 / 0.7 s apart). Identical periodic twists create correlation side-lobes. Keep them at a moderate 60–100°/s: Leica wants smooth motion, and whether GrandSLAM tolerates sharp twists is untested. Do them after SLAM has initialised and you have walked a few metres.

**Processing.**
1. Apply the identical zero-phase low-pass filter to both signals.
2. Resample to 100–200 Hz.
3. FFT correlation inside the gesture windows.
4. Parabolic sub-sample peak.
5. Bounded continuous refinement.
6. Theil–Sen drift fit.
7. Mount rotation via `Rotation.align_vectors`.

**Use LiDAR poses as soft priors only, with motion-inflated sigmas:** σ_pos² = s₀² + (|v|·σ_t)². COLMAP supports only position and gravity priors; rotation priors would need custom bundle adjustment.

### 1.9 Verdict on your capture plan (details in §3)

Your Run 1 + Run 2 plan is a reasonable start but has five gaps:
1. A camera-only Run 2 loses metric pose information for half the images and the second LiDAR pass.
2. A perimeter-only path leaves the plot **interior**, where viewers will fly, seen only from its edges.
3. "Different angle" does little for a 360 camera. **Height and lateral offset** are what matter.
4. Walking a loop gives only yaw rotation, so the vertical offset is unobservable from trajectories alone (geometry fixes this; gentle pitch/roll adds insurance).
5. Tape flexes.

**Recommended:** one continuous BLK2GO scan containing 3–5 passes:
- A: perimeter at about 1.2 m;
- B: perimeter in the opposite direction at about 2.0–2.2 m, offset 1.5–2 m outside the edge;
- C: interior figure-8 or "#" grid at about 1.5 m;
- D (optional): low pass at 0.7–0.9 m;
- E (optional): camera-only pass on a 3–5 m pole.

Walk at 0.4–0.5 m/s, on a rigid mount, under overcast and calm conditions.

### 1.10 Ground detection and navigation boundaries

**Ground filtering.** Use PDAL from conda-forge on Windows. Do not use the pip packages: the PyPI `python-pdal` name is a squatter package.

Pipeline: recentre, then outlier/ELM noise removal, then `filters.csf`, cross-checked with `filters.smrf`.
- PDAL's defaults are airborne-LiDAR scale (1 m cells, 0.5 m threshold). Scale them down, for example CSF resolution 0.15–0.5 m, rigidness 2–3, threshold 0.08–0.15 m.
- Treat these values as a **sweep**, judged by cross-sections and a CSF-vs-SMRF diff. There is no published under-canopy handheld DTM accuracy for this.
- RANSAC plane fitting is not enough on a forest floor.
- Deep-learning segmenters are not ready for this use. ForAINet (BSD-3) was trained on drone LiDAR, ForestFormer3D is non-commercial, and SegmentAnyTreeV2 has no released weights yet. Treat them as R&D for tropical sites only.

**Navigation geometry** (Python side, all permissive licences):
- **DTM** at 5 cm, built by TIN rasterisation (`filters.delaunay` + `filters.faceraster`, with a max edge length so it does not bridge occluded gaps), with interior-only hole fill and a **support mask**. Never let viewers walk on extrapolated terrain at the 25 m-range fringe.
- **Stems as cylinders**: height-above-ground slices → DBSCAN → circle fit → leaning cylinders in `stems.json`. Validate with 3DFin (GPL, used as a standalone tool).
- **Bounds** = DTM support ∩ a 2–4 m buffer around the capture path, plus a z range.
- **User-drawn boundaries** (polylines extruded to walls), stored as JSON in the project frame.
- Optional voxel occupancy / distance field for "solid surfaces" in general.
- In a forest, *foliage and shrubs are passable*. Only stems, rocks, logs and drawn walls block.

**Viewer side.** Constraints run *after* the camera controls update:
1. Bounds polygon and z clamp.
2. Walk mode: eye height ≈ 1.6 m above the smoothed DTM, with step and slope limits.
3. 2D circle push-out against stems through a spatial hash.
4. Fly mode: minimum clearance above the DTM plus the registration error margin.
5. Capsule shapecast against walls and meshes using **three-mesh-bvh**.

Never raycast the splat per frame; Spark's documentation explicitly warns against it.

**Independent cross-check.** splat-transform can carve a voxel collision mesh *from the splat*. Diffing that against the LiDAR DTM measures the vertical splat/LiDAR misregistration. The SuperSplat viewer's walk mode, which takes a `.glb` collision mesh, is a no-code baseline.

### 1.11 Web delivery: formats, renderers, limits

**Splat formats.**

| Format | Bytes per splat | SH | LoD / streaming | Notes | Use |
|---|---|---|---|---|---|
| 3DGS `.ply` | 68 (SH0) … **248 (SH3)**, so 1 M splats ≈ 248 MB | ≤3 | No | Training output | **Master copy** |
| `.splat` (antimatter15) | 32 | None | No | Obsolete | **Don't** |
| Compressed `.ply` (PlayCanvas) | ≈16 + chunk header | Optional | No | | OK |
| `.ksplat` | | | | GaussianSplats3D is no longer developed | No |
| **SPZ** (Niantic) | ~10× smaller than PLY | ≤3 | No | The library defaults to **format v4 (ZSTD)**, which **Spark 2.3.1 and Luciad cannot read**. Always write gzip **format v3** (`--spz-version 3`) | Interop |
| **SOG** (PlayCanvas) | ~15–20× smaller (≈12–17 MB per 1 M SH3 splats) | ≤3 | Streamed SOG variant | Read by Spark, PlayCanvas, Babylon | **Fallback** |
| **Spark `.rad`** | LoD tree adds +30–40% | ≤3 | **Yes**: 64 K-splat chunks over HTTP Range, or chunked `.radc` files | Young (Apr 2026), single vendor | **Primary web** |
| glTF `KHR_gaussian_splatting` (+ `_compression_spz_2`) in 3D Tiles | | ≤3 | Via 3D Tiles | Base extension **ratified**; the spz_2 compression extension is **still a draft**, with competing proposals | Luciad / Cesium export |
| XGRIDS LCC | 32–96 | | Yes | Restrictive licence | No |

Forest content is mostly diffuse, so **deliver SH1–SH2**. The SH3 rest coefficients are 180 of the 248 bytes per splat.

**Renderers.**
- **Spark 2.3.1** (MIT, three.js ≥ r180, WebGL2) is the primary choice:
  - LoD with device budgets (desktop 2.5 M, iOS 1.5 M, Android 1 M) and paged streaming;
  - CPU bucket sort in a WASM worker;
  - splats depth-test against opaque three.js meshes and points without writing depth, so a LiDAR layer composites correctly;
  - `SparkControls` can drive a camera rig;
  - evaluates SH in object space, so a registration transform can be a node transform. Scale must be uniform.
- **PlayCanvas engine / SuperSplat viewer** (MIT): fastest (WebGPU GPU sort), and has walk mode with collision. It has no Potree/LiDAR streaming and is not three.js. It is the alternative if splat counts ever exceed 5–10 M.
- **Babylon.js 9** (Apache-2.0) and **CesiumJS 1.146** (globe/GIS) are possible. **Gaussian-Splat-Lite** (WebGPU) is used by the three.js 3D Tiles splat plugin and **cannot co-sort with Spark**: one splat renderer per scene.

**LiDAR in the browser.** PotreeConverter 2.1 produces the Potree 2.0 format. Two loaders to prototype side by side against three r180+ and Spark:
- the **3DTilesRendererJS 0.5.3 PotreePlugin** (Apache-2.0, eye-dome lighting, Sep 2026; use no Brotli encoding with it);
- **potree-core 2.0.15** (MIT, but only ever tested against three r154).

Fallback: a decimated LiDAR cloud loaded as a Spark splat mesh. COPC via copc.js would need our own renderer.

**Realistic limits.**

| Device | Splats at ≥ 30 fps |
|---|---|
| Android phone | 1–2 M (Spark guidance) |
| iPhone | 1–3 M |
| Typical laptop / desktop | 1–5 M |

The table above is vendor guidance. **Measured data is thin; no published Spark 2.x fps exists for any phone or integrated GPU.** What was measured:

| Measurement | Result |
|---|---|
| PlayCanvas WebGL2 / WebGPU, iPhone 13 Pro Max at 642×1126 (≈ 1.5 DPR) | 1 M: 38 / 78 fps · 2 M: 36 / 73 · 3 M: 26 / 53 · 4 M: 20 / 42 |
| Research WebGPU viewer, 1.06 M splats | Snapdragon 8 Gen 3 ≈ 30 fps · iPhone 15 Pro Max ≈ 26 fps · Snapdragon 865 ≈ 9.5 fps |
| Spark CPU sort, 1 M splats, desktop | 4–6 ms. Spark 2.2 sorts about 20% faster, and 2.3 adds on-demand rendering |

**Phone memory.** Spark uses 16 / 24 / 40 / 56 bytes of GPU memory per splat at SH0 / SH1 / SH2 / SH3. The full iOS paging pool is therefore about 101 MB at SH0 and 352 MB at SH3. One unverified report says iOS Safari allows about 380 MB of GPU memory per tab, and low-RAM iPhones crash far earlier. **Serve SH0–SH1 to phones.**

**Download size per million splats.**

| Format | SH0 | SH3 |
|---|---|---|
| `.rad` | ≈ 16 MB | ≈ 36 MB |
| SOG | ≈ 8–11 MB (estimate) | ≈ 10.5–14 MB (higher SH bands are almost free) |
| SPZ v3 | ≈ 10–15 MB (estimate) | ≈ 20–26 MB |

Plan **0.5–1 M on phones with device pixel ratio capped at 1–1.5**, and enable Spark's on-demand rendering. Download budget: about 10–20 MB for the first view on mobile, about 50–150 MB in total, streamed. Build a small **benchmark page** (fixed camera path; median and 1%-low frame times at 0.5–3 M × SH0/SH1/SH3 × DPR 1/native) and run it on the coworkers' real devices. If Spark (WebGL2-only) is too slow on phones, PlayCanvas WebGPU is a measured ~2× faster fallback.

**What this changes for training.**
- One gsplat MCMC master at **`cap_max` 2 M (3 M with `packed` if VRAM allows on the 10 GB card), SH3**, with LiDAR initialisation below the cap.
- The web build is a `.rad` LoD built with `--max-sh 0` or `1` for phones and the default, plus an optional SH3 `.rad` for desktop, with a phone budget of about 0.75–1 M.
- Going from 2 M to 3 M gained only +0.12 dB PSNR for about 27% more training time. Train **2 M as baseline and 3 M as the "high" variant.**
- In Phase 2, A/B test against a dedicated 1 M training run and keep it only if it is clearly better on phones.
- Measured basis: gsplat Mip-NeRF360 PSNR is 29.18 at 1 M, 29.53 at 2 M and 29.65 at 3 M.

**Hosting.** Static hosting with same-origin data, so no CORS is needed.
- Cloudflare Pages caps files at 25 MiB, so use chunked `.radc`. R2 has free egress.
- GitHub Pages: 100 MiB per file, 1 GB per site.
- Range-read files must not be recompressed by the host.

### 1.12 Luciad, now Octave Alto

**Ownership.** Octave, Hexagon's software spin-off, separated on **28 May 2026**. LuciadRIA became **Alto Browser**, LuciadFusion **Alto Server** and LuciadCPillar **Alto Universal**. The dev portal still uses the Luciad names. **You have confirmed access to any version and contact with the Luciad team.** Use that contact for what the public docs leave open: whether SH is rendered, which SPZ versions are accepted, splat performance figures, and deployment terms for anonymous external viewers.

**Splats.**
- Supported **from LuciadRIA 2026.1** (also CPillar). Not in 2026.0 or 2025.x.
- Input is OGC 3D Tiles whose glTF payloads use `KHR_gaussian_splatting` (uncompressed) or `KHR_gaussian_splatting_compression_spz_2`. A single PLY or SPZ file can be wrapped in a one-tile tileset.
- LoD comes from the tileset's `geometricError`. Global budgets: `maxSplatCount` profiles 1 M (phones) … 6 M (gaming GPUs), and `maxMemoryUsage`.
- SH rendering is **undocumented, so test it**.
- Luciad bundles Niantic spz *library* 2.0.0, which reads gzip formats 1–3. Write SPZ **format v3 (or v2), LUF axes, never v4**.
- Tile constraints: no multi-node glTF, no multiple contents per tile, no CMPT containing PNTS. LuciadFusion cannot tile splats.

**Point clouds.** Formats: 3D Tiles PNTS, glTF points and HSPC. HSPC is proprietary, so avoid it as the shared format. Since 2026.1 LuciadFusion can tile *non-georeferenced* LAS/LAZ, which suits a BLK2GO scan without GNSS. Budget profiles run 5–25 M points.

**Layering.** Splats and LiDAR load as two `TileSet3DLayer`s with independent visibility. `enableDepth` composites them correctly. `isInside(orientedBox)` can clip both.

**Navigation.** Built-in constraints are too weak. The "above terrain" constraint works only on geocentric maps and is bypassed by direct camera control, and the first-person controller is sample code. Walk limits need custom code, so ship them as viewer-independent data (§1.10).

**Georeferencing.** A tileset with a box bounding volume and no root transform is placed as `LUCIAD:XYZ` (metres, X east, Y north, Z up) via `TileSet3DLayer.transformation`. A root ENU→ECEF transform makes it geocentric. **Pitfall:** Luciad's `Affine3DTransformation` is row-major, while the 3D Tiles `transform` is column-major.

**Delivery constraints.** Since 2026.0 LuciadRIA is **WebGPU-only**: iOS/macOS 26, Android 12+ with Chrome 121+, Firefox 141+. It needs HTTPS and has no fallback. Production use needs a deployment licence whose terms are not public, so ask Octave about public anonymous viewers and which tier includes splats.

**Recommendation.** Keep one canonical SH3 PLY in the local metric frame and derive per-viewer files from it. "Same data" means the same frame and source, not the same bytes. For Luciad and Cesium, write two tilesets:
- **splats**: single-node GLBs with SPZ v3, LUF axes;
- **LiDAR**: PNTS via py3dtiles.

Each has a thin local `tileset.json` (box, no root transform) and an optional georeferenced variant (root ENU→ECEF). Keep the encoder stage replaceable, because spz_2 is not final. Validate with an asymmetric L-shaped marker in all viewers: neither 3d-tiles-validator nor glTF-Validator understands the splat extensions.

### 1.13 Drone imagery: is it worth it?

**Evidence.**
- **Merging aerial and ground images into one splat does not improve ground-level views.** Horizon-GS (CVPR 2025), the best unified method, reaches street-level parity: 23.80 vs 23.84 dB for Scaffold-GS. It needed bridging views, external poses and an A100 80 GB, and its code is Inria non-commercial.
- Naive fusion degrades quality: in MatrixCity, Mip-NeRF360 aerial PSNR fell from 28.4 to 17.1 dB.
- **Aerial↔ground SfM fails:**
  - SIFT degrades beyond about 30–50° of viewpoint change, and nadir vs horizontal is about 90°;
  - plain COLMAP registered about 50% of a drone + ground set (DRAGON);
  - DUSt3R placed fewer than 5% of aerial–ground pairs within 5° before fine-tuning on urban data.
- This evidence is mostly urban or synthetic, and **forests are harder**. The drone sees crown *tops*; the ground camera sees trunks and crown *undersides*. They share almost no surfaces.

**What a drone sees in a forest.**
- UAV photogrammetry reconstructs the top-of-canopy surface and ground only in large enough gaps.
- Swedish stands vary by species. Measured canopy transmittance is 0.12–0.89 in Scots pine and 0.04–0.40 in spruce (UK data used as a proxy).
- In thinned pine, oblique drone images recover some stems (TreeDGS). In spruce and in tropical rainforest the drone gives **canopy, terrain and context only**. Rainforest gaps are "rare or absent", and SfM cannot map the ground there.
- The drone does fill a real hole: handheld scanners underestimate tree height (one study: −2.34 m bias) and never see a 30–50 m tropical canopy top.

**Options compared.**

| Option | Cost | Complexity | Expected quality gain | Verdict |
|---|---|---|---|---|
| **(a) LiDAR + Insta360 only** | Nothing new beyond targets | Lowest | Baseline. Complete eye-level coverage. Canopy seen only from below | **Phase 1 and permanent default** |
| (a+) (a) + free **Lantmäteriet open data** (airborne LiDAR at 1–2 pts/m², 1 m DTM, 0.16 m orthophoto) and/or the Insta360 on a 3–8 m **mast** | ~€0 data; a few hundred to a few thousand SEK for a mast. **No permit**: the law covers only material captured from aircraft | Low–moderate (needs a coarse LiDAR→SWEREF 99 placement) | Context terrain and orthophoto around the plot (Sweden only); mid-canopy views from the mast | **Try before buying a drone** |
| (b) Drone merged into **one splat** | Drone + bridging capture. Non-commercial reference code, or a reimplementation. The whole model becomes drone-derived and permit-bound | Highest: joint SfM across about 90° of viewpoint change, learned matchers, custom staged training, cm-consistent poses | Expected ≈ 0 dB at ground level, with real risk of degradation. Only benefit: a seamless fly-up. Tropics: effectively infeasible | **Rejected** as product path. Optional research experiment at a forest edge after (c) works |
| **(c) Drone as a separate aerial layer**, registered to the LiDAR frame | C0 drone ≈ €800–1,200 (price unverified) + targets; operator registration, A1/A3 card, insurance; **Lantmäteriet permit (~65 working days)** before any sharing | Moderate: drone module, own reconstruction group, target-based registration, multi-layer viewer with height cross-fade. ~1–2 weeks of engineering once Phase 1 works (estimate) | Sweden 10×10 m: none at walking height (by design); adds crown tops, gaps, edges and surroundings for an overview mode. Tropics: high, as the only source of canopy-top content | **Recommended way to support drones**, as a later optional phase |

**Alignment of drone data.** Use **physical targets** in a clearing, track or forest edge that the drone sees *and* the BLK2GO scans in the same walk.
- Measure the target centres in the LiDAR cloud, then fit a robust Sim(3) (SE(3) with a scale check if the drone has RTK).
- COLMAP has no GCP term in bundle adjustment, so run the drone SfM with EXIF GNSS pose priors and fit the transform to triangulated target centres.
- Expected accuracy: 2–5 cm near targets (medium–low confidence until measured); decimetres away from targets or without markers (0.2–0.6 m).
- RTK (centimetre-level, e.g. Matrice 4E) optionally georeferences the whole project. It does **not** replace targets, because the BLK2GO frame has no GNSS.
- Without RTK, consumer GPS is about 2.5 m horizontal and barometric altitude 5–50 m off. **Never let drone GNSS rescale the LiDAR.**
- Datum traps: SWEREF 99/ETRS89 vs WGS84 differ by about 0.9 m; ellipsoidal vs RH 2000 heights differ by tens of metres.

Effect on the ground alignment: none. The drone adds one new edge, drone → LiDAR, plus an optional LiDAR → world edge.

**Drone class: what to look for**, in order:
1. Automated missions: DJI MSDK support (Dronelink/Litchi), or DJI Fly waypoints/KMZ.
2. About a 1-inch sensor with fast readout, or a mechanical shutter.
3. **C0/C1 class label with Remote ID.**
4. RAW and manual exposure.
5. RTK only for georeferenced or tropical multi-hectare work.

Candidates for a **private buyer** (gap research, 2026-10-07):
- **Recommended: DJI Mini 5 Pro.** C0 with the standard battery, 249.9 g, 1-inch 50 MP sensor, rolling shutter. About **8,700–9,500 SEK** with the RC-N3, or 10,400–13,400 SEK as the Fly More Combo.
  - Fly it with DJI Fly's built-in **waypoints**: per waypoint photo, hover, gimbal pitch and heading; up to 200 waypoints per mission (verify whether the limit is 200 or 101).
  - Missions are loaded as KMZ. Sources: Pixpro (≈ €5/month), Litchi Hub, Dronelink KMZ export, or **our own Python WPML/KMZ generator** (nadir grid, 4 × 45° obliques, orbits, all hover-and-shoot).
  - Shoot in 12 MP binned mode (2 s minimum interval; 50 MP needs 5 s). Hover-and-shoot also removes most rolling-shutter distortion.
  - DJI's Mobile SDK does not support it yet (maybe around 2027).
- Fallback: **Mini 4 Pro + RC-N2** (the only consumer DJI model with SDK support, e.g. Litchi/Dronelink), but it appears end-of-life in Swedish shops.
- **Matrice 4E** (C2, ≈ 52–57 k SEK; mechanical shutter, RTK): overkill for a hobby plot. **DJI Lito X1** (≈ €419) is a budget option.
- **DJI Avata 360** (C1, 455 g, 8K 360 video, ≈ 8 k SEK) is the one drone worth an experiment, because it reuses the 360 pipeline. It has no waypoints.
- Not recommended: Air 3S (C1, so the test is mandatory; no SDK), Autel EVO II RTK V3 (uncertain vendor outlook), Parrot ANAFI Ai, Antigravity A1.
- The US FCC Covered List (Dec 2025) has no legal effect in the EU. The indirect risk is slower third-party app support for new DJI models.

**Load.** About 300–550 stills of 4–8 MB each at 12 MP, so roughly 2–4 GB per plot as JPEG. Train aerial layers at ≤ 1600 px with images streamed from disk and an MCMC cap of ≤ 1.5 M (10 GB GPU). TreeDGS used 32 GB of VRAM for 365 images, so downscale or tile.

**Regulations (Sweden, Oct 2026).**
- **EU:** Regulations 2019/947 and 2019/945. Open category means visual line of sight and ≤ 120 m above the nearest terrain. C0 in A1 can fly over uninvolved people but never over assemblies. C2 in A3 must stay ≥ 150 m from residential, commercial, industrial or *recreational* areas, which are undefined in public forests. Direct Remote ID is mandatory for C1/C2. EASA Opinion 06/2026 (not yet adopted) would lower thresholds to 100 g around 2028.
- **Transportstyrelsen, private hobby use:**
  - Operator registration (190 SEK + 250 SEK per year) for any camera drone, age 18+.
  - A **C0** drone needs no competency test; the A1/A3 online test (600 SEK) is still recommended. C1 and drones of 250 g or more require the A1/A3 card; flying without it has been an offence since 1 Jan 2026. The A2 card is needed only for a C2 near people.
  - Liability insurance is **not required for leisure use under 20 kg**, but home insurance often excludes drones. Check yours, or buy a private drone policy (e.g. Svedea).
  - The earlier "mandatory insurance" note applied to work flights; this is a personal project.
- **Airspace:** check the LFV drone map and NOTAMs, the 5 km rule around runways, the control-zone 50 m / 10 m limits and heliports within 1,000 m. Also nature-reserve and national-park take-off bans, bird-season access bans, and written landowner consent.
- **Lantmäteriet dissemination permit** (*spridningstillstånd*, lag 2016:319 §9; mechanics verified with Lantmäteriet quotes in the gap research). **Any drone-derived product** (images, orthophoto, DSM, 3D model or splat) needs a permit before *any* sharing.
  - **What counts as dissemination:** email, websites, social media, cloud storage, and *servers you do not fully control*. That includes a **private hosted git repo**, personal cloud drives, cloud GPU training, sending files to the Luciad team, and **embedding drone outputs in a shared web page like this one**. A home NAS that only you control is not dissemination.
  - **Submit the source JPGs right after each flight** (highest-resolution JPG; not RAW-only). Apply as "*Privatperson*" via the file-transfer service (≤ 5 GB per file, ≤ 250 GB or 5,000 files per upload). Free, about **65 working days**. You cannot apply in advance; each flight is a new application.
  - **Follow-on products are covered:** "Följdprodukter som exempelvis ortofoton, 3D-modeller och ytmodeller ska genereras i efterhand från det godkända materialet … behöver i så fall inte skickas in". So any number of splat or mesh versions trained *only from approved or returned images* can be published. If the decision is *bifall med villkor* (approved with conditions), retrain from the retouched images Lantmäteriet returns, and delete the originals.
  - **Do not submit a finished splat.** Models cannot be retouched, and each retrained version would need a new application.
  - **The forest exemption** (LMFS 2017:2) covers only *photos or film*, only if the landowner ordered or took them, and only if no vehicles, people or non-forestry activity are visible. Survey targets, a visible surveyor, a power line or views of the surroundings void it. It probably never covers a splat.
  - **Ground-only capture (a) is outside this law.** Keep it that way: take scale and frame from the BLK2GO and transform the drone layer *into* the LiDAR frame, never the reverse.
  - Pre-capture questions: **spridningstillstand@lm.se** (phone 0771-63 63 63). GDPR blurring and the skyddsobjekt rules apply to every source.
- **Tropics:** country-specific and often closed to foreigners (examples: Indonesia, Brazil RBAC 100, Malaysia CAAM + JUPEM, Costa Rica DGAC + SINAC). EU certificates are generally not recognised. Budget months and a local licensed operator.

**Target tie and software** (gap research):
- Use dual-use targets detectable **geometrically** (intensity may be missing):
  - Leica's printable **6-inch B&W targets**, auto-extracted by REGISTER 360 (±8 mm);
  - **200 mm spheres**;
  - a proposed (untested) **50 cm black/white square pyramid**: it reads as a checker GCP from above, and its apex is the intersection of the four faces fitted in the LiDAR.
- Place **≥ 5 targets where the sky is visible** (gaps, an edge or a nearby clearing) and hold 1–2 out as checkpoints. Expect about 2–4 cm horizontal and 3–6 cm vertical RMS at 2 cm GSD (estimate).
- GCP adjustment in a local frame: **RealityScan** (free for individuals), Metashape Pro, ODM with a fake projection, or COLMAP + pycolmap + **pyceres** with a custom GCP residual (Apache-2.0, Windows wheels).

**Lantmäteriet open data** (checked 2026). All need a Geotorget account plus STAC API authorisation (OAuth2).
- **Laserdata skog**, 1–2 pts/m²: CC0 (confirm under the new GDPR terms of use). Since 2026-06-01 it comes only as COPC tiles via STAC.
- **Markhöjdmodell** 1 m: CC BY 4.0.
- **Ortofoto** 0.16 m: free under CC BY 4.0 since 2025-02-03.
- Laserdata NH is *not* open.
- For a 10×10 m plot this gives only ≈ 100–200 LiDAR points, 100 terrain cells and ≈ 3,900 orthophoto pixels. It is fine as **context around** the plot and for coarse SWEREF 99 placement (decimetres to a metre). It is useless as crown detail.

**Recommendation.**
- **The drone is optional, worth it only if the viewer should offer above-canopy views.** No published paper reports ground-level metrics with vs without aerial images in a real forest, so if you fly one, run our own with/without ablation.
- Phase 1 stays ground-only.
- In Phase 1, still place the 4–6 targets (they are checkpoints anyway) and **stub the drone module**: capability declarations, a DJI EXIF/XMP probe, and clearance and lineage fields.
- Try (a+) for Swedish context first.
- Run a Swedish (c) pilot only when Phase 1's checkpoint RMSE and target detection are proven, the viewer supports multiple layers, and the legal checklist is done.
- Bring it forward only if a tropical campaign date is fixed and close.

### 1.14 Licensing summary

**Update 2026-10-07: this is a personal, non-commercial project.** The ⛔ rows below were written for a possible Hexagon deliverable. For your own non-commercial use, and free public sharing of the results, research licences (Inria, CC BY-NC, FAIR non-commercial) are acceptable. Under those licences you may use the code and share renders and models; you may not sell them or build a commercial service on them. The default stack stays permissive (gsplat, COLMAP, Spark) because it is also the best-maintained and most scriptable. That keeps the door open if the project ever turns commercial.

Two caveats:
1. **Leica EPP / demo / eval licence terms:** you confirmed it covers this personal project.
2. **Model weights carry their own licences:** VGGT-1B, MASt3R, SAM 3 and others.

| Category | Tools |
|---|---|
| ✅ **Use freely** (permissive) | COLMAP/pycolmap, gsplat, PPISP, 3DGRUT, Brush, Spark, splat-transform, SuperSplat, Open3D, small_gicp, SciPy, laspy/lazrs, pye57, PDAL, GDAL, three.js, three-mesh-bvh, 3DTilesRendererJS, potree-core, PotreeConverter, py3dtiles, FastAPI, SAM 2.1, LightGlue/ALIKED/LoMa, MapAnything-apache, Niantic spz |
| ⚠️ **Use as standalone tools only, not linked into distributed code** (GPL/AGPL) | LichtFeld Studio, Spirula Studio, 3DFin, CloudCompare, evo, OpenSplat, ODM/WebODM, gsbox, Ultralytics YOLO |
| ⚠️ **Custom licences: check with Hexagon legal** | SAM 3 (commercial OK; military/ITAR banned), VGGT-1B-Commercial (no military use), Insta360 SDKs (by application) |
| ⛔ **Never in commercial deliverables**; ✅ OK for this personal non-commercial project | Inria 3DGS and derivatives (incl. LightGaussian, PUP-3DGS, Octree-GS, WildGaussians, RobustSplat, Horizon-GS, CLM, Hierarchical 3DGS), PGSR, CityGS, ForestFormer3D, SuperPoint/SuperGlue, MASt3R, VGGSfM, Pi3, VGGT-1B, VGGT-Ω, InstantSfM, DA3 Giant/Large |
| ⛔ **Closed / cloud** (excluded by your requirements) | Postshot Free (no PLY export, watermark), Polycam Free (glTF only, watermark), KIRI and Teleport (cloud), Insta360 Spatial Capture |

Add a licence-audit step to CI later: `pip-licenses` plus a check of CUDA rasteriser submodules. `diff-gaussian-rasterization` is Inria non-commercial.

---

## 2. Architecture and pipeline

### 2.1 Principles

1. **One metric project frame.** When LiDAR is present, the project frame is the recentred BLK2GO frame. Everything is registered *into* it before splat training, so the splat is metric from the start.
2. **Capture sources are optional modules with one interface.** They declare *capabilities* (scale, georeference, imagery, geometry, time base). The pipeline and the viewer enable only the steps and toggles those capabilities allow.
3. **Stages are separate processes with cached, content-hashed outputs.** This gives reruns, cancellation, VRAM release and crash isolation on Windows.
4. **One viewer codebase, driven by a `scene.json` manifest.** The same code serves local preview and the public static web build. Luciad and Cesium get an *export*, not a second app.
5. **Everything the user must trust is reported.** Alignment, scale, georeference status, sync quality and dissemination clearance appear per layer.
6. **Phase 1 is CLI-only.** It uses the same module and stage structure, so nothing is rewritten when the UI arrives in Phase 3.

### 2.2 Component overview

```
┌──────────────────────── Local machine (Windows 11, Ryzen 7 7800X3D, 32 GB, RTX 3080 10 GB) ───────────┐
│                                                                                                        │
│  UI (Vite/TS, browser tab on localhost; optional pywebview window later)                               │
│   ├─ Source selection → Import/probe → Alignment setup → Process (status/logs/QA) → View & Export      │
│   └─ embeds ──► Viewer package (three.js + Spark + Potree loader; reads scene.json)                    │
│                     ▲                                                                                  │
│  Backend: FastAPI on 127.0.0.1 (REST commands + server-sent events + static/Range file serving)        │
│   ├─ core: source registry · capability model · DAG planner · content-hash cache · frame graph         │
│   ├─ runner: 1 GPU queue + CPU pool; each stage = subprocess in a Windows Job Object                   │
│   └─ project/ (project.json, frames.json, state/*.json, cache/<stage>/<key>/, export/)                 │
│                                                                                                        │
│  Stage processes (python -m app.stages.<name>)                                                         │
│   ├─ env "pipe" (pixi, Python 3.12, conda-forge): PDAL, laspy, pye57, Open3D, pycolmap(CPU), SciPy,    │
│   │                                               OpenCV-contrib, own .insv parser                     │
│   ├─ env "gs" (uv, torch 2.8.0 + CUDA 12.8): patched gsplat fork, PPISP                              │
│   └─ external tools (pinned + version-probed): colmap.exe (CUDA), ffmpeg, PotreeConverter,             │
│                                                splat-transform (Node), Spark build-lod                 │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
            │ export/ (static bundle: viewer dist + scene.json + .rad/.sog + Potree + nav data)
            ▼
   Static web hosting (Cloudflare Pages + R2 / GitHub Pages / Hexagon-internal)   ──►  laptops & phones
            │ optional
            ▼
   3D Tiles bundle (splat GLB+SPZ v3, LiDAR PNTS, local + ENU→ECEF tilesets)       ──►  LuciadRIA ≥2026.1 / CesiumJS
```

### 2.3 Capture-source modules

Every source implements the same interface. It is shown here in outline, since the design is to be reviewed before any code.

| Member | Purpose |
|---|---|
| `kind`, `version` | e.g. `lidar_las`, `insta360_video`, `drone_images` |
| `capabilities` | `metric_scale`: exact / approx / none · `georef`: none / gnss / rtk / gcp (+σ) · `gravity_aligned` · `imagery_for_splat` · `geometry` · `time_base` · `dissemination` (cleared / pending / approved / denied + case number) |
| `probe(inputs)` | Fast validation, giving a metadata report and refined capabilities. Examples: LAS dimensions, point format and gps_time present? CSV columns and rate? `.insv` model, firmware, fps, IMU rate, rolling-shutter time? DJI `RtkFlag`? |
| `stages(cfg)` | The source's own stages, with typed input/output ports, a parameter model and resource needs (GPU, estimated VRAM) |
| `layers(artefacts)` | What the source contributes to the viewer |

| Source | Metric scale | Georef | Imagery for splat | Geometry | Time base | Clearance |
|---|---|---|---|---|---|---|
| **BLK2GO (LAS/E57 + trajectory)** | Exact | None (local SLAM frame) | No (panoramas are 1 Hz and low resolution; used only as optional anchors) | Yes | Trajectory clock (format TBD, day 0) | Cleared (ground capture) |
| **Insta360 video** | None | None (GPS tag, coarse) | Yes | No | Camera capture clock (µs) | Cleared after GDPR blur |
| **Drone images** (Phase 5; stub in Phase 1) | Approx (GNSS) or near-exact (RTK) | GNSS / RTK | Yes (own group) | DSM/ortho | EXIF time | **Pending** until Lantmäteriet approves |

**Project-level stages that combine sources** are not owned by modules: *Reconstruction group* (SfM per group of imagery), *Register*, *Train splat* (per group), *Build navigation* and *Export*.

The **reconstruction group** turns the drone decision into configuration rather than a code fork:
- Insta360 and drone in one group = option (b).
- Separate groups = option (c), the default.

**Lineage.** Every artefact records which sources' pixels and which sources' poses or scale it depends on. A model trained on drone pixels inherits the drone's clearance. Pose-only dependence is marked "pending" until Lantmäteriet clarifies it.

### 2.4 Shared coordinate frame

**Anchor policy**, chosen automatically and overridable in the UI:
1. **LiDAR present:** the BLK2GO frame, recentred to a local origin (e.g. the staked start point). The double-precision offset is stored.
2. Else **drone with GNSS/RTK:** local ENU at a stored lat/lon/height origin.
3. Else: the first imagery group's SfM frame, gravity-aligned, with **scale marked "arbitrary"** until the user enters a known distance (scale bar or targets). Measurements and walk mode stay disabled until then.

**Frame graph** (`frames.json`). Each edge is a Sim(3) stored as a float64 4×4 matrix plus s, R, t. Each edge carries:
- status: prior / estimated / manual / verified;
- method and parameters;
- RMSE, inlier ratio, correspondence count and an optional 7×7 covariance;
- input hashes, tool versions and a user-accepted flag.

Your tape-measured offset is a `prior` edge, and the estimator's result is an `estimated` edge. The report compares them. When two paths exist between frames (e.g. Insta360→LiDAR directly vs via drone), the discrepancy is reported.

An optional, separate **project → world** transform (ECEF plus EPSG metadata, e.g. SWEREF 99 TM EPSG:3006 + RH 2000 EPSG:5613, with epoch) is filled only when a connected source is georeferenced. Drone GNSS never rescales the LiDAR; any scale ≠ 1 is reported as a QA flag.

**Conventions fixed once** and checked with an asymmetric L-shaped marker test in Phase 0/1:
- project frame Z-up in metres;
- three.js is Y-up, handled by one root group rotating −90° about X;
- COLMAP stores camera-from-world, with cameras y-down/z-forward;
- quaternion order stated explicitly;
- glTF Y-up vs 3D Tiles Z-up;
- Luciad matrices row-major vs 3D Tiles column-major.

**No real-world coordinates in float32, ever.**

### 2.5 Pipeline, step by step (main case: LiDAR + Insta360)

| # | Stage | Input → output | Tools | Key details |
|---|---|---|---|---|
| S0a | Ingest LiDAR | REGISTER 360 PTS/E57 (with intensity) or 3DR LAS → recentred LAZ + metadata. **Pose + IMU extraction: read the `.b2g` directly** (SQLite): 200 Hz trajectory + 200 Hz IMU + pano image timestamps → `trajectory.parquet`, `imu.parquet`. Cross-check: LGSx → 3DR `STrajectory` | pye57, laspy+lazrs, Python `sqlite3` (B2G reader with format-version asserts), Cyclone 3DR script (cross-check) | Choose the origin; store the offset; enforce metres. **Timestamp sanity check:** step histogram, 10 ms / 0.4 s periods, span. Then convert ticks → s as a *new* field, never overwriting the original. Check trajectory vs point clock |
| S0b | Ingest Insta360 | `.insv` → two fisheye tracks (stream copy, keep PTS), IMU table, exposure records, calibration, audio | ffmpeg, own trailer parser (cross-checked with telemetry-parser master) | Frame times = exposure-record time (mid-row) ± shutter/2 + gyro offset (tags 28/29); fps from tag 78/PTS (30 vs 29.97). Log readout (tag 25), lens/guard state (68/104), rotation (130) and firmware. **Fail loudly if the gyro record is missing** |
| S1 | LiDAR prep | LAZ → cleaned cloud, ground class, DTM, stems, support mask | PDAL (CSF + SMRF), GDAL, NumPy/scikit-image | Parameter sweep; QA hillshade; stems from height-above-ground slices |
| S2 | Time sync (Run 1) | IMU + trajectory → dt(t) = a + b·t, σ, NCC peak, mount rotation | SciPy | Method A/B/C chosen from the S0a probe; start/end consistency check |
| S3 | Frame selection + reprojection | Tracks + dt → selected frames → **5 pinhole views per lens** (10 per frame) + masks + rig config (lens-to-lens translation ≈ 30 mm) | NVDEC/ffmpeg, OpenCV `omnidir` / NumPy remap, SAM 2.1 | Sharpest per 0.3–0.4 m; drop sync/calibration segments and stationary parts; static rig mask + operator masks + sky mask. Fallback: Studio equirect → 12-view rig |
| S4 | SfM | Images + masks + rig → sparse model, **prior-free** | colmap.exe 4.2.1 | SIFT → (ALIKED/LoMa if needed); sequential + loop detection + vocab tree; global mapper with rig and intrinsics fixed; QA: % registered, components, reprojection error, track length |
| S5 | Register | Sparse model + LiDAR (ground + stems) + trajectory + dt → S, X, dt, report → **LiDAR-anchored bundle adjustment** → training poses | Open3D, small_gicp, SciPy, pycolmap, colmap.exe `pose_prior_mapper` | Staged estimator (§1.6, stages 1–5); PASS/WARN/FAIL vs tape; per-quadrant and per-side residuals; target checkpoints (Leica B&W / spheres / pyramids fitted geometrically) |
| S6 | Prepare training data | Model × S → model in the project frame; LiDAR init points; LiDAR sparse depth per view | pycolmap (`Reconstruction.transform`), NumPy | Voxel-downsample the LiDAR to below `cap_max` and colour it from the images; z-buffer occlusion filtering; ground + stems only for depth |
| S7 | Train splat | Images + masks + model + init + depth → PLY (SH3) in the project frame | gsplat fork (MCMC, packed, PPISP, depth loss) | `normalize_world_space=False`; cap 2 M (3 M with `packed`; 10 GB GPU); checkpoints for resume; QA: held-out PSNR/LPIPS, bbox check, splat-depth vs LiDAR |
| S8 | Clean + export splat | PLY → cleaned PLY → `.rad` (LoD, SH1–2), `.sog`, `.spz` (v3), optional 3D Tiles | splat-transform, Spark build-lod | Floater removal (LiDAR free-space test + `-F`/opacity filters), crop to bounds; SH reduction for the web |
| S9 | LiDAR web export | Cleaned LAZ → Potree 2.0 (+ optional PNTS 3D Tiles) | PotreeConverter, py3dtiles | Subsample to 5–10 mm; RGB/intensity |
| S10 | Navigation export | DTM/stems/bounds → `dtm` tiles, `stems.json`, `bounds.json`, `boundaries.json`, `collision.glb` | GDAL, Python, trimesh-style export | All in the project frame; collision mesh = DTM TIN + stems + walls |
| S11 | Scene + bundle | All exports → `scene.json` + static bundle | backend | Layers, presets, transforms, budgets, start pose; clearance gate omits uncleared layers |

**Phase-1 shortcuts** (still the same stages):
- S2 may use method B or C if the trajectory export lacks orientation.
- S6 and S7 may start without depth loss and PPISP, which are added as A/B tests.
- S8 exports a single SOG or `.rad`.
- S10 starts with the DTM clamp plus bounds.

### 2.6 What runs for each source combination

| Selected sources | Anchor frame / scale | Stages that run | Viewer presets |
|---|---|---|---|
| LiDAR only | LiDAR, exact | S0a, S1, S9, S10, S11 | LiDAR |
| Splat only (Insta360) | SfM frame, **arbitrary scale** until a scale bar/targets are entered | S0b, S3 (no sync), S4, S6 (no LiDAR), S7, S8, S10 (splat-derived collision via splat-transform, flagged), S11 | Splat |
| **LiDAR + Insta360** (main) | LiDAR, exact | All of S0–S11 | LiDAR / Splat / Combined |
| Drone only | ENU from GNSS/RTK (approx/exact) | Drone ingest, S4 (drone group, GPS priors), S7, S8, S11 | Aerial |
| Drone + Insta360 | Drone ENU; ground group tied by **shared targets** (joint SfM opt-in) | Both groups + target registration | Splat / Aerial |
| Drone + LiDAR | LiDAR; drone tied by targets | LiDAR stages + drone group + target registration | LiDAR / Aerial |
| All three | LiDAR; ground via S5, drone via targets | Everything | LiDAR / Splat / Combined / Aerial |

A preset appears only when all its layers exist. Uncleared drone layers are excluded from the public build automatically.

### 2.7 Project files and caching

- `project.json`: user intent (sources, parameters, reconstruction groups, anchor policy).
- `frames.json`: the frame graph.
- `state/<stage>.json`: status, PID, heartbeat, cache key, outputs.
- `export/scene.json`: generated.

All are Pydantic v2 models with `schema_version`. Writes are atomic (temp file + `os.replace`). TypeScript types are generated from the JSON Schema.

**Cache key** = BLAKE3(stage id + implementation version + canonical parameters + input artefact IDs + external tool versions). Outputs go to `cache/<stage>/<key16>/`. Changing an export parameter does not redo SfM.

**Raw inputs** (multi-GB LAS and video) stay where they are, fingerprinted by size + mtime + BLAKE3. If a file moves, the project offers to relink it.

**Commands:** "rerun from stage" and "force", in the style of OpenDroneMap. A hand-rolled DAG of a few hundred lines is proportionate. doit is the off-the-shelf fallback. Dagster, Prefect, Snakemake and Hamilton are overkill or a poor fit on Windows.

### 2.8 Backend, runner and UI flow (Phase 3; Phase 1 uses the same stage CLIs)

**Backend.**
- FastAPI ≥ 0.135 on 127.0.0.1, with REST commands and native server-sent events for progress.
- Pin **Starlette ≥ 1.7**: range-request security fixes, and the server streams `.rad`/Potree with byte ranges.
- Never run with `--reload` or more than one worker. On Windows that switches the event loop and breaks subprocess spawning.

**Runner.**
- `subprocess.Popen` from worker threads.
- Each child goes into a Windows **Job Object** (kill-on-close) with `CREATE_NEW_PROCESS_GROUP`. Cancel = Ctrl-Break, then terminate the job.
- **One GPU job at a time**, plus a CPU pool.
- Progress comes from each stage's own `events.jsonl` (step, loss, number of Gaussians, VRAM). Parsing stdout (COLMAP "Processed file [i/n]", tqdm) is the fallback.
- On startup, stale RUNNING records become INTERRUPTED, with resume offered from checkpoints.

**UI flow:**
1. **Home**: new or open project.
2. **Sources**: checkboxes for LiDAR / 360 video / drone images. A live "you will get" panel shows the layers, anchor frame, scale and georeference status, and the permit flag derived from capabilities.
3. **Import**: path pickers through a backend file browser (native dialog later via pywebview), probe reports and warnings. Example: "trajectory has no orientation → sync method B".
4. **Alignment setup**: shown only when two or more sources are selected. The proposed anchor (overridable), the device-offset prior entry form (with photos and reference-point choice), time-offset priors, targets, and imagery grouping (separate / joint).
5. **Process**: stage graph with status chips, progress and ETA, live logs, GPU memory, cancel and rerun-from. QA panels: SfM stats, registration residual heat map, PASS/WARN/FAIL card for measured vs estimated offset, sync plot.
6. **View & Export**: embedded viewer with preset toggles, then export the web bundle or 3D Tiles. The clearance gate is enforced here.

A developer-only **viser** view (Apache-2.0) is useful in Phases 0–1 for checking registration with transform gizmos.

### 2.9 Viewer

**`scene.json` contains:**
- `project_frame`: up axis +Z, units m, origin note.
- An optional `world` block: ECEF-from-project float64 matrix, EPSG codes, and a "pseudo" flag.
- `layers[]`: id, kind (pointcloud / splat / mesh / ortho / dsm / ground / navmesh), source, group (lidar / ground_splat / aerial), format and URI, transform, bounds, LoD budget, default visibility, clearance.
- `presets[]`: LiDAR / Splat / Combined / Aerial.
- `navigation`: DTM tiles, stems, bounds, boundaries, collision mesh, start pose, allowed modes.

**Rendering.**
- WebGLRenderer with antialias off and device pixel ratio capped (1.5–2 desktop, 1–1.5 phones). Spark on-demand rendering on.
- Splat layers are `SplatMesh` objects, all inside **one Spark renderer**: a global sort and a joint LoD budget across layers, with layer opacity used for fades.
- The LiDAR is Potree, rendered **opaque with depth write** so splats composite against it. Optional eye-dome lighting, and a colour mode (RGB / intensity / height) to avoid confusing speckle where points lie on splat surfaces.
- Toggles set `.visible`. "Combined" shows both, with optional LiDAR point size and opacity sliders.

**Navigation.**
- Fly and walk modes using `SparkControls`, with a phone joystick (nipplejs).
- A constraint solver runs after every controls update, with sub-steps to avoid tunnelling: bounds → DTM clamp → stem push-out → wall/mesh capsule tests (three-mesh-bvh).
- Fly clearance ≥ DTM + 0.3 m + registration RMSE.
- Optional later: click-to-walk with a Recast navmesh.

**Measurement tools** (distance, height) are enabled only when scale is exact.

### 2.10 Environment and machine setup

- **Machine (checked 2026-10-07 on your PC):**
  - AMD Ryzen 7 7800X3D (8 cores / 16 threads), 32 GB DDR5;
  - **NVIDIA GeForce RTX 3080, 10 GB** (compute 8.6), **driver 596.36 (R595 branch, CUDA 13.2 capable) ✅**;
  - Windows 11 Home 26200; C: 506 GB free;
  - **Visual Studio 2022 Community 17.14 with MSVC 14.44 ✅** (the exact toolset recommended below);
  - **no CUDA toolkit installed yet.**
- **Driver.** Already fine. Keep R595 or newer and avoid 595.59 (a fan bug on RTX 30).
- **One CUDA toolkit: 12.8.1** (plus cuDNN 9 for CUDA 12) and **VS 2022 Build Tools 17.14 (MSVC 14.44)**. If VS 2026 is installed, add the v14.44 toolset and use `vcvarsall x64 -vcvars_ver=14.44`. Don't install a CUDA 13 toolkit.
- **COLMAP.** The official 4.2.1 `colmap-x64-windows-cuda.zip`. It carries its own CUDA 13 runtime and needs only the driver. For ALIKED/LightGlue/LoMa, start it from **`colmap_gpu.bat`**, which puts CUDA 12.8 `bin` and cuDNN 9 first on PATH. Smoke test: ALIKED on 10 frames with no ONNX Runtime error and visible GPU load. Run LoMa in FP32. Alternative: `lyehe/build_gpu_colmap` 4.2.0 (CUDA 12.8 bundled, Caspar bundle adjustment, GPU pycolmap; one version behind).
- **Environments** (each venv has an activation script setting `CUDA_HOME`/`CUDA_PATH` = 12.8, PATH, `TORCH_CUDA_ARCH_LIST=8.6`, `DISTUTILS_USE_SDK=1`, `MAX_JOBS=4`):
  - **pipe** (pixi, conda-forge): Python 3.12, PDAL/GDAL/PROJ, laspy+lazrs, pye57, Open3D, pycolmap (CPU), SciPy, OpenCV-contrib, Pydantic, FastAPI. telemetry-parser is built from master (Rust/MSVC + maturin), for cross-checks only.
  - **gs** (uv): Python 3.11, **torch 2.8.0 + torchvision 0.23.0 (cu128)**. **gsplat main pinned (e.g. `512d366`) with the MSVC fixes from PR #1055** (`__builtin_clzll`, C3495, LNK2001, cub radix sort), kept as a patch file in the repo. Also PPISP v1.2.1, fused-ssim and fused-bilagrid, all with `--no-build-isolation`. Pin torch in gsplat's `examples/requirements.txt` to 2.8.0: torch 2.9–2.11 fail to build fused-ssim on Windows. Smoke test: 50 iterations of simple_trainer + `import ppisp`.
  - **3dgrut** (optional; its `install_env_uv.ps1`, CUDA 12.8 default) and **inria** (optional baseline; Python 3.10/3.11, torch 2.8.0+cu128, `#include <float.h>` patch in simple-knn).
  - Documented fallback if cu128 hits a wall: CUDA 13.0 + torch 2.9.1+cu130 + the full PR #1055 branch + the compiled_autograd.h patch (pytorch PR #188952).
- **Node ≥ 22** for splat-transform. **Rust** stable (MSVC) for Spark `build-lod` (`cargo run --release`; if wgpu picks the integrated GPU, use `--no-default-features`). PotreeConverter **2.1.5** Windows binary. ffmpeg.
- **Paths.** **The project stays where it is** (`Desktop\Code\Gsplat+Lidar`; you decided this, and OneDrive is and will stay off). The space in `C:\Users\Leonard Lind\` and the `+` only matter to some *compilers and build tools*: the LichtFeld source build refuses such paths, and CUDA-extension builds have failed on them before. So keep only the **tool side** in a short space-free folder:
  - `C:\dev\envs` (Python venvs);
  - `C:\dev\build` (gsplat / PPISP / fused-ssim builds, `TORCH_EXTENSIONS_DIR`);
  - `C:\dev\cache` (pip/uv/torch/HF caches);
  - `C:\dev\src` (cloned third-party repos).

  Code, data, results and docs stay in the project folder. Scripts always quote paths. TEMP already resolves to the 8.3 short path. Consider a Defender exclusion for the data folder.
- **Hardware consequences.**
  - **VRAM (10 GB)** sets the splat cap (§1.5): 2 M baseline; 3 M only with `packed`; aerial or merged models ≤ 1.5 M; tropical tiles smaller (10–15 m) with ≤ 2 M per tile.
  - Feed-forward SfM fallbacks (VGGT-class) only manage about 30–60 frames per chunk.
  - **RAM (32 GB):** never cache all training images (3–6 k images × 1600² × 3 B ≈ 23–46 GB); stream them from the NVMe disk. Process LiDAR in chunks (46 M points is fine). OpenDroneMap, if ever used, tops out around 300–400 images.
  - **Disk:** about 1.35 GB per minute of 8K30 video, so a 10-minute capture is about 14 GB, plus caches and checkpoints. 506 GB free is enough for now.
  - A desktop has no thermal throttling concerns. Close GPU-heavy apps while training.

### 2.10a Which computer: home or office

| | **Home PC** | **Office PC** | Better for this project |
|---|---|---|---|
| GPU | **RTX 3080, 10 GB** GDDR6X, 8,704 CUDA cores, 760 GB/s, ~29.8 TFLOPS FP32 (Ampere, sm_86) | **RTX 5060, 8 GB** GDDR7, 3,840 CUDA cores, 448 GB/s, ~19 TFLOPS FP32 (Blackwell, sm_120) | **Home** |
| Usable VRAM (minus display) | ≈ 9 GB | ≈ 7 GB | **Home** |
| Splat cap (MCMC, ~1600 px views) | 2 M baseline; 3 M with `packed` | ≈ 1.5 M; 2 M only tight with `packed` and 1440 px views | **Home** |
| Splat training speed (estimate) | 1.0× (≈ 30–40 min at 2 M) | ≈ 0.6× (≈ 50–65 min at 2 M) | Home (but time is not a priority) |
| GPU SfM (SIFT extraction/matching, LightGlue) | Faster | Slower | **Home** |
| Software maturity | Ampere is supported by everything | Blackwell needs CUDA ≥ 12.8 and torch ≥ 2.7 (our stack qualifies). Older research code built with CUDA 11.x/12.1 (Inria repos, tiny-cuda-nn/3DGRUT, nerfstudio) often needs rebuilds or fails | **Home** |
| CPU | Ryzen 7 7800X3D, 8 cores / 16 threads | Core Ultra 9 285, 24 cores (8P + 16E) / 24 threads | **Office** (≈ 1.5–2× multi-thread: COLMAP mapping and bundle adjustment, PDAL, decoding) |
| RAM | 32 GB | 64 GB | **Office** (large point clouds, image caching, OpenDroneMap) |
| Disk | 1.86 TB, 506 GB free | 2 TB | Similar |
| Admin and installs | Your own machine: CUDA, drivers, VS, Python envs freely | Company-managed: installs may need IT; a personal project on company hardware may be against policy | **Home** |
| Leica Cyclone (EPP licence) | Installed ✅ | Installed ✅ | Either, so home |

**Current assumption (provisional; final decision at checkpoint D1, §0.1): use the home PC as the main machine for everything** (SfM, registration, splat training, web export, viewer development). Because quality matters more than time, the speed rows above matter least. The deciding rows are VRAM capacity and software maturity, and the home PC wins both.
- Splat training is limited by GPU memory and bandwidth. The home RTX 3080 has more of both, and it is the architecture every tool supports.
- The office PC's advantages (more cores, 64 GB RAM) only help CPU-bound steps that are not the bottleneck at 10×10 m scale.

**Cyclone REGISTER 360 PLUS and Cyclone 3DR are installed on both PCs** (confirmed 2026-10-07). So the Cyclone steps also run on the home PC:
- REGISTER 360 import with Re-Run SLAM / Re-observation;
- publishing LGSx, PTS and E57;
- the Cyclone 3DR `STrajectory` pose script.

The whole pipeline stays on one machine; the office PC is not needed.

**If the home PC runs short later:**
- **RAM** (e.g. large tropical scans in PDAL, or OpenDroneMap): upgrade to 64 GB. That is cheap, so do it rather than moving work to the office PC.
- **VRAM** (scenes needing more than about 3 M splats per tile): the one upgrade that matters is a GPU with ≥ 16–24 GB (e.g. a used RTX 3090 with 24 GB). Not needed for the 10×10 m test.

### 2.11 Proposed repository layout (for Phase 1)

```
Desktop\Code\Gsplat+Lidar\  (repo root; stays where it is; tool builds/venvs in C:\dev\)
├─ pixi.toml / pixi.lock
├─ tools.toml                (pinned external binaries + checksums + version probes)
├─ app/
│  ├─ core/                  (models, capabilities, frame graph, DAG, cache, runner)
│  ├─ sources/               (lidar_blk2go/, insta360/, drone/ [stub])
│  ├─ stages/                (ingest_*, lidar_prep, sync, frames, sfm, register, prepare_train,
│  │                          train_splat, export_splat, export_lidar, export_nav, scene)
│  ├─ trainers/gsplat_fork/  (thin fork of simple_trainer + custom dataset)
│  └─ server/                (FastAPI, Phase 3)
├─ web/                      (pnpm workspace: packages/viewer, packages/app-ui, packages/schema)
├─ tests/                    (synthetic registration, frame-convention marker, bbox regression)
├─ research/                 (this research: raw + digest)
└─ docs/                     (PLAN.md, capture SOP, alignment report spec, known-good toolchain matrix)
```

---

## 3. Capture protocol for the 10×10 m test

### 3.1 Session overview

| When | What | Time |
|---|---|---|
| 2–3 days before | Check forecast (overcast, calm, ≥ 5 °C, dry); update firmware at home; charge everything; finish and measure the rig | — |
| Phase 0 (earlier) | **Calibration capture** in a controlled, textured scene (§3.9a) and the backyard rehearsal | ~1 h |
| On site | Mark the plot, place and photograph the targets, tape-measure sides and diagonals, walk the path once without recording | 30–45 min |
| On site | Camera test clip (exposure, blur), BLK2GO initialisation, start ritual, passes A–C (+D/E), end ritual | 15–20 min of recording |
| On site | Checks: BLK Live preview and loop closure, camera spot-check, re-measure the rig, copy data to two drives | 20 min |

### 3.2 Equipment

- **Capture:** BLK2GO (original, not PULSE) with 2 batteries; Insta360 (X5/X6) with 2 batteries; microSD (V30, ≥ 256 GB); phone with BLK Live or FIELD 360.
- **Rig:** a **rigid mount** in place of tape: REALiT OmniGO handle clamp (US$695, with 5/8″ and ARCA mounts, accessory points for 360 cameras, and a flat base that doubles as the start stand), or a machined / 3D-printed collar with a 1/4″-20 screw and an anti-twist pin. Optional telescopic pole for pass E.
- **Targets:** 5 stakes; 5 matte spheres of 200 mm; 7–8 rigid matte AprilTag boards (A2, black square 30–40 cm, unique IDs, tag36h11 or tagStandard41h12); **Leica printable 6-inch B&W targets** (REGISTER 360 auto-extracts them from BLK2GO walks, ±8 mm); 1–2 scale bars of exactly 1.000 m with tags at both ends. Optionally a 50 cm B/W pyramid (geometric apex). The 3DR LAS export had **zero intensity**, so every target must also be detectable **geometrically**.
- **Measurement:** steel rule, callipers, tape measure, phone inclinometer app, grey card.
- **Field kit:** lens cloth and blower, sealed bag for acclimatisation, mallet, flagging tape, gaffer tape and zip ties as backup only, field log sheet, hi-vis (moose season: northern Sweden opened early September; southern Sweden opens 8 October).

### 3.3 Rig and mount

- **Placement:** mount the Insta360 **coaxially below** the BLK2GO (inverted is fine), inside the LiDAR's downward blind cone. The FoV is 360°×270°, so the cone is roughly a 45° half-angle below the device. Keep clear of the dome, the three panoramic camera windows, the battery door and the buttons. Leica says to keep the phone "below or behind".
- **Lens orientation:** lenses facing left and right of the walking direction, so the seam points fore and aft. Sideways views carry the most parallax, and the operator falls in the rear seam, which is masked anyway. This is a judgement call against Insta360's own tip, and it matters less on the raw-fisheye path.
- **Rigidity:** tighten, then **witness-mark**. Photograph from front, side and top with a ruler in view, and re-measure after the session. If tape *must* be used for the first test, the estimator reports extrinsic stability over time instead of trusting a single offset.

### 3.4 Measuring the device offset (your prior)

1. **Define reference points.** Write them down; the software stores them with the prior.
   - BLK2GO: **R_B** = the centre of the bottom face of the base, on the device's long axis. Define "forward" as a visible physical feature (e.g. the button side) and note which.
   - Insta360: **R_C** = the midpoint between the two lens front vertices, on the lens axis.
2. **Translation**, in BLK2GO body axes (up along the long axis, forward, left). Use a steel rule or callipers (±1–2 mm). For a coaxial mount, lateral and fore-aft should be about 0.
3. **Orientation:**
   - **yaw** of the Insta360 lens axis relative to BLK2GO forward, using a protractor template or a top-down photo with a ruler (±2–3°);
   - **tilt**, using a phone inclinometer held on a flat face of each device (±1–2°).
4. **Enter the values with uncertainties** (e.g. `z = −0.142 ± 0.003 m, yaw = 90 ± 3°`) plus the photos.
5. **One-time BLK2GO reference-point calibration.** Leica does not document where the trajectory refers to on the device.
   - Stand the BLK2GO on its stand on a flat floor with R_B at a measured height. Do a short static start/stop scan.
   - Compare the trajectory's start height above the LiDAR floor with your measured height. That gives the vertical offset from R_B to the trajectory origin.
   - Repeat with the device rotated 90° (static) to confirm the axes.
   - (This is a hypothesis to test in Phase 0. If the trajectory proves to sit somewhere else, the prior is re-expressed accordingly.)
6. The estimator then reports **measured vs estimated, per component, with σ and PASS/WARN/FAIL** (§1.6).

### 3.5 Device settings

| Insta360 (X5 / X6) | Setting |
|---|---|
| Mode | **360 Video** (not PureVideo, Timelapse, InstaFrame or Active HDR) |
| Resolution / fps | **8K 30** (or 25). Alternative **5.7K60**: about 2.6× less rolling-shutter skew (≈ 8 ms vs ≈ 21 ms readout) and twice the frames |
| Codec / bitrate | H.265, **High** bitrate. Keep the raw `.insv` |
| Exposure | **Manual**: shutter **1/500 s** (1/250 floor under dark canopy, 1/1000 if bright); **fixed ISO**, the lowest that exposes trunks and ground (expect 400–1600 under an overcast canopy); expose for shaded mid-tones and let sky gaps clip |
| White balance | **Fixed Kelvin** (~5500 K overcast); shoot the grey card at the start |
| Colour | X5: Standard (or Flat). X6: Standard or 10-bit I-Log, converted with one fixed HLG→SDR transform |
| Off | AdaptiveTone (it exposes the lenses independently), HDR, PureVideo, Balanced Exposure, **Jitter Blur Reduction**, filters, Timelapse/TimeShift/Me/InstaFrame modes. Record the firmware version and lens-guard state |
| Physical | Lens guards **removed**, lenses cleaned, same lens set every session, IMU calibrated on a level surface |
| Post | Never export with FlowState / Direction Lock / Horizon correction for SfM. Pipeline reads the raw `.insv` |

| BLK2GO | Setting |
|---|---|
| Control | Record via **BLK Live (≥ 2.1)** or **FIELD 360 (≥ 5.0)**, the documented trajectory-CSV sources |
| Images / density | **Store Images ON**; BLK Live "**Image security**" **OFF**; **full density** (lower densities filter points on the device and change timestamp statistics); uncompressed images if storage allows |
| Targets | Walk **1–2 m past each Leica B&W target with a 1–2 s stop** (needed for REGISTER 360's auto-extraction) |
| Import (REGISTER 360) | Enable **Re-Run SLAM** and **Re-observation**; set the WayPoint interval to 1 m. Publish **LGSx** (for 3DR poses) and **PTS/E57** (with intensity) |
| Start | **Static initialisation** on the stand (OmniGO base or table stand) for 10–15 s until the LED is green, then +10 s |
| Handling | Slow constant pace, smooth turns, ≥ 1 m from objects (minimum range 0.5 m H / 0.7 m V). Hold it over the shoulder or head, or out to the side, **not in front of the chest**, which blocks the view behind you. Nobody walks directly in front of or behind the scanner |

### 3.6 Plot layout, targets and passes

```
            B (≈2.1 m, clockwise, 1.5–2 m outside the edge)
      ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐
        T1 ●──────────────────────────● T2
      │    │  A (≈1.2 m, counter-clockwise,  │  │
           │     on the edge)                │
      │    │        ╭───╮     ╭───╮          │  │
           │        │ C (≈1.5 m figure-8)    │
      │    │        ╰───╳─────╳───╯          │  │
           │            T5 ● (centre: sphere + board,
      │    │                 + flat board on ground)  │
           │                                 │
      │    │                                 │  │
        T4 ●──────────────────────────● T3
      │  S ◆ start/end (staked; static init here)  │
      └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘
   T1–T4: stations ≈0.5 m outside the path: stake + 200 mm sphere at 1.2–1.5 m + A2 AprilTag board facing centre
   Extra: 1–2 boards at other heights (e.g. ≈2 m on a trunk), 1–2 scale bars (1.000 m), tape all sides + diagonals
   Split targets: ≥3 control + ≥2 held-out check
```

**Passes**, all inside **one continuous BLK2GO scan of ≤ 10 min** (practitioners keep sessions under about 10 min under canopy; split into two scans that share targets if needed), starting and ending at S. Passes A and B run in **opposite directions**, the reverse walk that the BLK2GO accuracy studies recommend:

| Pass | Height (camera) | Path | Notes |
|---|---|---|---|
| A | ≈ 1.2 m | Perimeter, counter-clockwise, on the edge | Rig held out to the side at arm's length |
| B | ≈ 2.0–2.2 m | Perimeter, clockwise, 1.5–2 m outside the edge | Rig overhead or on a short pole. Edge trees are seen from both sides |
| C | ≈ 1.5 m | Interior figure-8 through the centre (or a "#" grid at 3.3 / 6.7 m) | ≥ 1 m from trunks; turn outside the plot |
| D (optional) | 0.7–0.9 m | Low perimeter loop | Ground and understory detail |
| E (optional, camera only) | 3–5 m | Pole loop, separate recording | Reconstructed in the **same** COLMAP database; permit-free elevated views |

- Walk at **0.4–0.5 m/s**; turn at **≤ 30°/s**.
- Pause **5–10 s** at corners and between passes.
- Overlap the start and end of each loop by about 2 m.
- Keep the camera level. Change *height and offset*, not tilt.
- Total path about 150–200 m.

### 3.7 Sync and calibration ritual (identical at start and end)

1. Start **Insta360 recording first**.
2. BLK2GO static initialisation on the stand at S (LED green, then +10 s).
3. **Clap twice** near the camera, then **one firm tap** on the rig. This marks the Insta360 timeline and checks the camera's audio-to-IMU alignment.
4. Hold still for 5 s. Walk about 3–5 m so SLAM is settled.
5. **Aperiodic yaw twists**: 4–5 twists of different amplitudes (±20–40°) at irregular spacing (e.g. 0.4 / 1.1 / 0.7 / 1.5 s), at a moderate 60–100°/s.
6. A **gentle pitch/roll sequence**: ±20–30°, 3 cycles each, about 2 s per cycle.
7. Hold still for 5 s, then start the passes.
8. **At the end:** steps 3–7 again at S, then put the rig static on the stand, **stop the BLK2GO**, then stop the Insta360.
9. Optionally film the BLK2GO start-button press and light change with the Insta360 (a coarse check of what trajectory t = 0 means).

These segments are used for sync and calibration only, and are excluded from SfM and training. Note them in the field log with approximate times.

### 3.8 Conditions, safety and legal

- **Light:** stable, uniform **overcast**, around **10:00–14:00**. October noon sun at 59–63° N is only 22–27° high, so sunny days mean long, harsh sunflecks, and passing clouds are worse than steady sun.
- **Wind:** foliage visibly still. As a guide (not from a source), forecast ≤ 2–3 m/s. Wind is the main foliage-quality risk.
- **Weather:** dry; droplets on the lens ruin segments. Do all passes within about 1 hour.
- **Temperature:** ≥ 5 °C (BLK2GO spec 0/+5 to +40 °C). Acclimatise the gear 15–30 min in a closed bag to avoid condensation.
- **Safety:** hi-vis in the hunting season; inform the landowner and the hunting team.
- **Legal (ground capture):** no Lantmäteriet permit is needed. Do check that the site is not a **skyddsobjekt** (skyddslag §7 can ban depicting or measuring, and covers ground scans too). Get **written landowner consent** (good practice). Blur faces and number plates before publishing (GDPR).
- **People:** a second person helps (log, claps, keeps others out, stands still ≥ 5 m outside the plot). Solo capture works if needed. The operator wears dark, plain clothing.

### 3.9 Field checklist

**Before (at home):**
- [ ] Forecast OK: overcast, calm, dry, ≥ 5 °C.
- [ ] Firmware updated: BLK2GO and Insta360. Note the versions.
- [ ] Batteries charged (BLK2GO ×2, Insta360 ×2, phone); microSD and BLK2GO storage empty.
- [ ] Rig tight and witness-marked; offset measured and photographed (§3.4).
- [ ] Insta360 preset saved (§3.5); BLK Live settings checked (Store Images ON, Image security OFF).
- [ ] Targets, stakes, scale bars, tape, callipers, inclinometer app, grey card, lens kit, stand, field log.

**On-site setup:**
- [ ] Mark S, the corners and the centre; place stations T1–T5 and the extra boards; photograph each.
- [ ] Tape-measure the 4 sides and 2 diagonals; note the target heights.
- [ ] Walk the route once without recording (trip hazards, branches at head height).
- [ ] 30 s camera test clip: check exposure on trunks, sky clipping and blur on screen.

**During:**
- [ ] Insta360 REC → BLK2GO static init (green + 10 s) → start ritual (§3.7).
- [ ] Passes A → B → C (→ D) at 0.4–0.5 m/s, with pauses at corners. Watch the BLK2GO LED: yellow = slow down, orange = stop.
- [ ] Helper logs pass start/end times, heights, gusts, people and incidents.
- [ ] End ritual at S → static → stop BLK2GO → stop Insta360.
- [ ] Optional pass E (pole, camera only, its own clip, with clap and tap).

**After (before leaving):**
- [ ] BLK Live / FIELD 360 preview: loop closed, no obvious doubling.
- [ ] Spot-check the camera footage (blur, exposure, drops on the lenses).
- [ ] Each target visible at close range in both devices' data (check the preview).
- [ ] Re-measure and photograph the rig offset; note any change.
- [ ] Log temperature, cloud, wind and times.
- [ ] **Copy both datasets to two drives.** Keep the `.b2g` and the `.insv` files.

### 3.9a Calibration capture (recommended, Phase 0)

Estimate the extrinsic **X** once per mount in a **controlled, textured scene**: courtyard or office walls with AprilTag boards and spheres.
- Record 3–5 minutes with rich rotations about all axes, plus slow walking. Use the same ritual.
- X is then known with high accuracy. The forest capture *verifies* it rather than having to estimate it from scratch under foliage.
- Repeat after any mount change.

### 3.10 Drone capture protocol (later, Phase 5; summary)

- **Order:** ground walk and drone flight in the **same overcast window**, under 30 minutes apart (60 at most); canopy wind ≤ 3–4 m/s; the ground operator out of aerial frames.
- **Flights**, all heights relative to the **canopy top** and never above 120 m above ground:
  - **Mapping block:** nadir + **45° oblique crosshatch** at canopy + 40–60 m, **90/80 overlap**.
  - **Orbits:** 2–3 rings around the plot at canopy + 15–45 m (gimbal −30° to −50°) where emergent trees leave safe clearance.
  - **GCP pass:** a dedicated low pass over the target clearing (about 1 cm ground resolution).
  - **Optional bridge sequence** (vertical "elevator" in a gap or at the edge), only for a later merge experiment.
- **Images:** 12 MP 4:3 **JPEG stills** (DNG only if colour-matching), hover-and-shoot or slow flight. Manual exposure (ISO 100–400, ≥ 1/1000 s when moving), fixed white balance, **distortion correction OFF**. Never mix 12 MP and 48/50 MP images in one camera group.
- **Targets:** 6–8 dual-use targets (≥ 5 control + ≥ 2 check), each ≥ 20× the ground resolution on the diagonal (≥ 60 cm), each in ≥ 5 drone images and passed by the BLK2GO within the same walk.
- **No under-canopy flights.** Obstacle sensing does not reliably see thin branches, and you must keep visual line of sight.
- **Data stays local** (not OneDrive, not cloud) until the Lantmäteriet permit is granted. Submit the images right after capture.

---

## 4. Risks and unknowns, with cheap tests

Likelihood refers to the **Swedish 10×10 m test**. "Day 0" means Phase 0.

| # | Risk | Likelihood | Impact | Mitigation | Cheap test |
|---|---|---|---|---|---|
| R1 | BLK2GO pose/IMU stream unusable: firmware changes the undocumented `.b2g` layout, or the draft trajectory differs from Cyclone's re-run SLAM | **Low** (decoded and verified on your file) | Medium | B2G reader with format-version asserts; Cyclone 3DR `STrajectory` and *Pano images* poses as fallbacks; sync method A (gyro) → B (positions) → C (time-free). S stays geometric, so the splat is unaffected | Day 0: run the B2G reader on every new capture; compare the draft vs re-run-SLAM trajectory once; compare the 3DR LAS point clock with the B2G clock |
| R2 | Wrong Insta360 frame timing (index/fps, 29.97 vs 30, per-file gyro offset up to ~11 ms, clock drift) or a Studio export with hidden rotation or trim | Medium (body-fixedness of the raw tracks is now confirmed) | High (extrinsic, masks, sync) | **Raw `.insv` lens tracks** as primary; frame times from exposure records; per-recording offset estimate; ffprobe and tag 78 | Day 0: indoor clip with known rotation. Compare frame count and PTS vs exposure records; check that the BLK2GO body pixels stay fixed; measure the gyro-vs-video residual |
| R3 | Operator and BLK2GO in every frame | Certain | High if unmasked | Static rig mask + SAM 2.1 operator masks; drop zenith/nadir views; walk passes in both directions | Day 0: 1-minute rig clip; measure the masked-pixel fraction per view direction; fix the layout |
| R4 | **SfM fragmentation** or false loop closures under canopy | Medium | High (blocks the pipeline) | Rig constraints, loop detection plus spatial priors; ALIKED / LoMa; global vs incremental; fallback to pose-prior mapper with LiDAR priors | 60 s subset: SIFT vs ALIKED vs LoMa × global vs incremental; report % registered, components, track length (under 1 h) |
| R5 | Passes at different heights don't co-register | Medium | Medium | One continuous scan, one COLMAP database; vocab-tree / MegaLoc cross-pass pairs | Backyard: two passes at 1.2 m and 2.1 m, 10 minutes apart; check that a single component results |
| R6 | Blurry foliage, floaters, missing thin branches | High | Medium | MCMC cap; LiDAR initialisation; ground+stem depth loss; LiDAR free-space floater cull; splat-transform filters | Backyard shrub: 7k-step variants (default / MCMC / delayed densification / LiDAR init); held-out PSNR/LPIPS + visual check |
| R7 | Sky through the canopy fitted as near-field haze | High | Medium | Sky masks; no depth loss on sky; drop zenith views; random background colour during training | Same data with and without sky masks; count floaters looking up |
| R8 | **Wind-moving foliage** | Medium | Medium–high (canopy) | Calm day; short capture; passes back-to-back; delayed densification; robust residual mask (Splatfacto-W idea, ported to gsplat) | Calm vs breezy 1-minute capture of one tree; optionally a synthetic Blender wind-tree render |
| R9 | Exposure / white-balance variation, dappled light | High | Medium | Locked exposure and WB; overcast; PPISP shared per 360 frame | Locked vs auto exposure × {none, bilateral grid, PPISP} on a tree line in partial sun |
| R10 | Motion blur and rolling shutter in low light | Medium | Medium–high | 0.4–0.5 m/s; ≤ 30°/s turns; 1/500 s; sharpest-frame selection; 3DGUT rolling-shutter later | 3 walks at 0.5 / 1.0 / 1.5 m/s at dusk; sharpness distribution + SfM registration rate → pick speed and threshold |
| R11 | Stitch-seam parallax (stitched path) | High on stitched path | Medium | Seam fore/aft; masks near the seam; raw-fisheye A/B | Checkerboard 1–2 m away on the seam: stitched vs raw-fisheye rig reprojection error |
| R12 | LiDAR foliage noise biasing ICP and depth | High | Medium (cm bias) | Register and supervise on **ground + stems only**; robust kernels; occlusion filter | Synthetic: apply a known Sim(3) (scale 0.37, 20°, 3 m) + foliage noise to the LiDAR; recover it with all points vs ground+stems |
| R13 | BLK2GO SLAM drift (no GNSS) | Low at 10×10 m | High for 100 m+ walks | Close loops explicitly; per-side Sim(3) drift test; targets | Double lap: compare stem positions between laps; a 100 m open-loop walk to measure drift per 100 m |
| R14 | **Lever arm poorly observable**, tape flex, unknown trajectory reference point | Medium | Medium (false disagreement) | Rigid mount; geometry-based S; pitch/roll sequence; windowed X estimate; reference-point calibration (§3.4) | Backyard: 2 minutes with pitch/roll vs 2 minutes walking only; compare vertical σ; static height test |
| R15 | **VRAM out-of-memory on the 10 GB RTX 3080** (≈ 9 GB usable) | Medium–high | Medium | MCMC cap 2 M (3 M with `packed`); views ≤ 1600 px (1440 px fallback); stream images from disk; log VRAM; one GPU job at a time; optionally drive the display from the iGPU | First dataset: sweep cap {1, 2, 3 M} × view size {1024, 1440, 1600} for 3k steps each, with and without `packed`; log peak VRAM and time |
| R16 | **Windows toolchain friction**: gsplat main does not build with MSVC without PR #1055's fixes; torch 2.9–2.11 break fused-ssim; COLMAP's ONNX provider needs CUDA 12 + cuDNN; PPISP untested on Windows | High | Medium (days lost) | The matrix in §2.10 (CUDA 12.8.1 + torch 2.8.0 + patched gsplat), separate venvs, Brush and Faster-GS as low-friction fallbacks, a documented cu130 fallback | Day 0: toolchain smoke test (nvidia-smi, nvcc, cl, torch arch list, 50-iteration gsplat run, `import ppisp`, COLMAP ALIKED on 10 frames) |
| R17 | Splat frame mistakes (gsplat normalisation, SH rotation, axis conventions, float32) | Medium | High (silent misalignment) | Train in the project frame; bbox regression test; asymmetric marker test across viewers; recentre | Unit test with a synthetic scene; L-marker visible in LiDAR, splat, Spark and Luciad |
| R18 | Phone viewer cannot hold the splat count | Medium | Medium | LoD budget 0.5–1 M; DPR cap; SH1; on-demand rendering | Export 0.5 / 1 / 2 / 4 M; measure fps on a mid-range Android and an iPhone |
| R19 | **Format churn** (SPZ v4, spz_2 draft, young `.rad`, potree-core vs three r180+) | Medium | Medium | Canonical PLY master; replaceable encoders; SOG fallback; prototype two Potree loaders | Phase 2: load the same scene via `.rad`, SOG, SPZ v3 and both Potree loaders |
| R20 | Ground contamination (shrubs as ground) or DTM holes → wrong navigation | Medium (`mac-1.las`: ~21 m slope relief and half the points in the 1–5 m understory) | Medium | CSF (with slope smoothing) + SMRF diff; intensity as an extra ground cue where available; support mask; interior-only hole fill; fly clearance margin | **Can start now:** run the CSF/SMRF sweep on `mac-1.las` and the Brazil sample. Check hillshade bumps, hole fraction and cross-sections; later diff against the splat-carved collision |
| R21 | Licence contamination from research code | High if chasing state of the art | High | Whitelist (§1.14); `pip-licenses` audit | Audit script in CI |
| R22 | Luciad access or WebGPU-only reach | Medium | Low (optional) | Three.js viewer primary; Luciad as an export | One-tile smoke test in LuciadRIA 2026.1 when access is confirmed |
| R23 | Cold, condensation, lens fogging; hunting season | Medium (October) | Medium | Midday window, acclimatisation, hi-vis | n/a |
| R24 | GDPR (people, plates), skyddsobjekt, landowner | Low | High if violated | Blur step; site check; written consent | Site check before choosing the plot |

**Drone-specific risks** (Phase 5):

| # | Risk | Mitigation |
|---|---|---|
| D1 | Lantmäteriet permit delay or refusal (~65 working days, whole-model decision); syncing to OneDrive or a git remote already counts as dissemination | Separate layer (c); clearance gate in the build; non-synced local data root; submit images right after capture |
| D2 | **Lineage contamination**: a model trained on drone pixels inherits the drone clearance; pose-only dependence is a grey zone | Lineage tracking per artefact; ground group separate by default |
| D3 | No shared surfaces under canopy, so registration falls to decimetres | Targets in a clearing, track or edge within the BLK2GO loop (constrains plot choice); height-fade / canopy-height partition in the viewer to tolerate ≥ 0.3 m error |
| D4 | Targets not visible in LiDAR intensity | Dual-use targets (pattern + retro-reflective / raised geometry); validated in Phase 1 |
| D5 | Datum and height errors (SWEREF 99 vs WGS84 about 0.9 m; ellipsoid vs RH 2000 heights; non-RTK altitude 5–50 m off) | Float64 frame graph with CRS and epoch; never rescale the LiDAR from GNSS |
| D6 | Aviation compliance and private insurance (not legally required for leisure < 20 kg, but home insurance often excludes drones); no DJI SDK for the Mini 5 Pro | Checklist (§1.13); our own KMZ mission generator instead of the SDK |
| D7 | Double canopy or ghosting where layers overlap; shared mobile splat budget | Canopy-height-model partition + height cross-fade in one Spark sort; budget split (e.g. 350 K ground / 150 K aerial on phones) |
| D8 | Tropical legal and safety (foreign operators, VLOS over 30–50 m canopy) | Local licensed operator; fly from clearings or rivers; legal review months ahead |

**Design-in now for tropical scale-up** (cheap to plan for, expensive to retrofit):
- LiDAR-trajectory pose priors as an optional SfM mode.
- **Spatial tiling on gsplat**: 10–15 m tiles (sized for the 10 GB GPU, ≤ 2 M splats each) with 3–5 m overlap, then merge and build LoD. The permissive chunked trainers don't exist; CityGS, Hierarchical 3DGS and CLM are non-commercial.
- LiDAR initialisation + confidence-masked depth loss.
- PPISP grouped per 360 frame.
- LoD export.
- A capture SOP for humidity and heat (the X5/X6 are rated to 40 °C).
- Long walks with multiple loop closures.

A **cheap tiling test** in Phase 3: split the 10×10 m scene into 4 tiles and compare seams, PSNR and splat count against the single model.

---

## 5. Phased plan

Effort figures assume **one developer, part-time research tooling around a day job**. **Compute time is not a constraint (quality first)**: long or multi-day GPU runs are expected and are not counted as effort. They are rough estimates, to be revisited after Phase 0. Each phase ends with a **gate**: what must be true before moving on.

### Phase 0: Set-up and day-0 audits (≈ 1–2 weeks)

**Goal:** settle the unknowns that change the design, with your own hardware, before any forest trip.

| Step | Deliverable |
|---|---|
| 0.1 **Toolchain** | `docs/toolchain.md`, the known-good matrix from §2.10: driver R595+; CUDA 12.8.1 + cuDNN 9; VS 2022 Build Tools 17.14; COLMAP 4.2.1 zip + `colmap_gpu.bat`; venvs `pipe` / `gs` (torch 2.8.0+cu128, patched gsplat main, PPISP); Brush prebuilt; Node / splat-transform; Rust / build-lod; PotreeConverter 2.1.5; a minimal Spark page that loads a sample splat. Project stays in place; venvs, CUDA-extension builds and caches go in `C:\dev\` (space-free). Gate: the toolchain smoke test passes |
| 0.2 **BLK2GO export audit** | First, the **sample-data checks** on your Brazil LAZ: step histogram, 10 ms and 0.4 s periods, span vs walk duration. Then a 2–3 minute walk *with the sync ritual and a few Leica B&W targets*. Exports:<br>• REGISTER 360 → **LGSx**, then the **3DR `STrajectory` script** → poses CSV (check units, rate, body→world)<br>• **PTS/E57 with intensity**<br>• *Pano images* pose TXT<br>• the BLK Live / FIELD 360 CSV<br>• try `-b2g2trajectory`, which shows whether WORKFLOW is in your EPP licence; or check Leica CLM<br>Also compare trajectory vs per-point clock and check the auto-extraction of the B&W targets. **Export-path table:** which export keeps time, intensity and RGB (the two samples show 3DR LAS = time without intensity, `mac-1.las` = intensity without time). → **Decides sync method A / B / C and the LiDAR export path** |
| 0.2b **Ground and navigation on the samples** (no capture needed) | CSF/SMRF parameter sweep, support mask, DTM and stem extraction on `mac-1.las` (steep, dense understory) and the Brazil sample. Also the first Potree conversion as a web stress test (46–56 M points) |
| 0.3 **Insta360 audit** (X5) | 10–30 s test clips at 8K30 and 5.7K60, with still periods, clap/tap and a known rotation. Report:<br>• ffprobe: tracks, fps 30 vs 29.97, stts<br>• trailer parse: IMU rate and ranges (tag 65), exposure records, readout (tag 25), gyro offset (tags 28/29), calibration tokens, lens guard (68/104), firmware<br>• BLK2GO body pixels fixed in the raw tracks<br>• gyro-vs-video residual; capture-clock vs track drift<br>• telemetry-parser master vs own parser |
| 0.4 **Rig** | Rigid mount built; offset measured and photographed (§3.4); BLK2GO reference-point static test |
| 0.5 **Backyard rehearsal** (both devices, ~5 minutes, targets placed) | Does BLK2GO SLAM tolerate the gestures? Start vs end sync consistency. Mask fraction per view. 60 s SfM test (SIFT vs ALIKED/LoMa, global vs incremental). Cross-pass matchability at two heights. Target detectability in LiDAR intensity and in images. A quick 7k-step splat + VRAM sweep (10 GB) |
| 0.6 **Calibration capture** (§3.9a) | X estimated in a textured scene; this is the reference for the forest test |
| 0.7 **Synthetic tests** (first code) | Registration estimator recovers a known Sim(3) + extrinsic + dt from simulated data; frame-convention L-marker test; gsplat bbox regression |
| 0.8 **Decision checkpoint D1** | Run the benchmark and A/B tests for P1–P7 (§0.1) on the rehearsal data, including the **same benchmark on the home and office PCs**. Write `docs/decisions.md` with the final choices and their measurements |

**Gate 0:**
- the sync method is chosen;
- the toolchain is reproducible;
- the trailer parser is validated against telemetry-parser (X5) or GyroView (X6);
- the backyard test gives one SfM component and a plausible S;
- you have reviewed and accepted the capture SOP;
- **checkpoint D1 is done**: final decisions P1–P7 recorded in `docs/decisions.md`.

### Phase 1: Minimal end-to-end alignment proof (≈ 3–5 weeks) **← smallest test that proves alignment**

**Goal:** a Swedish 10×10 m forest capture processed end to end, with an **alignment report** and a **local viewer showing LiDAR, splat and both, correctly aligned at metric scale**.

**Scope:**
- Sources: LiDAR + Insta360 only.
- Stages S0–S9 as CLIs on the module/stage structure (§2.5).
- One reconstruction group; raw per-lens fisheye → pinhole rig (stitched 12-view path only as fallback).
- gsplat MCMC 2 M (3 M if VRAM allows, with `packed`) trained in the project frame. Masks yes; LiDAR initialisation yes; depth loss and PPISP as A/B tests if time allows.
- Viewer: the minimal Spark + Potree page with three toggles and a simple DTM clamp.
- Drone module **stub** (capabilities + DJI XMP probe on public sample data).

**Milestone M1 deliverables:**
1. `alignment_report.html/json`: S, X and dt with σ; PASS/WARN/FAIL vs your tape values; residual diagnostics; per-quadrant cloud-to-cloud distances; target checkpoint residuals; sync plot.
2. A splat PLY in the LiDAR frame.
3. A local viewer page.
4. A short "lessons" note that updates the SOP.

**Acceptance criteria** (first, taped or semi-rigid test; tightened for the rigid mount):

| Check | Target |
|---|---|
| SfM | ≥ 95% of selected frames registered in **one** component; mean reprojection error < 1 px |
| Sync (method A) | σ ≤ 5 ms; start vs end offsets consistent after the drift model (≤ 3 ms) |
| Registration S | Independent target RMS ≤ 2–3 cm; median cloud-to-cloud ≤ 2 cm on ground + trunks, P90 ≤ 5 cm; ground bias ≤ 1 cm; trajectory-vs-geometry scale agreement ≤ 0.3% |
| Extrinsic vs tape | PASS or explained WARN per §1.6 thresholds |
| Splat | Visually aligned with the LiDAR at trunks and ground; no gross floaters in the walkable volume; held-out PSNR recorded as baseline |
| Viewer | Toggling LiDAR / splat / combined works; scales and positions match; camera cannot go below the DTM |

**Gate 1:** alignment proven, or the failure is understood and a fix planned. The checkpoint RMSE is measured, which is a prerequisite for the drone phase.

### Phase 2: Web delivery, a minimal browser demo of the test scene (≈ 2–3 weeks)

**Goal:** other people open a URL on a laptop or phone, fly or walk through the test scene, toggle LiDAR / splat / both, and cannot go below ground or through trunks.

**Work:**
- Viewer package driven by `scene.json`.
- Splat as **Spark `.rad`** (LoD, SH1–2) with an **SOG** fallback.
- LiDAR as Potree 2.0. Prototype the 3DTilesRendererJS PotreePlugin and potree-core; keep the one that works with three r180+ and Spark.
- Navigation: DTM tiles + stems + bounds + optional drawn walls; walk and fly modes; phone joystick.
- Mobile budgets: LoD 0.5–1 M, device pixel ratio cap, on-demand rendering.
- **Quality presets Low / Medium / High / Ultra** (LoD splat budget, SH level, pixel ratio, LiDAR point budget). They are auto-selected per device, user-switchable, and never alter the master data.
- Device benchmark page: fps at 0.5 / 1 / 2 / 4 M on your phone(s) and a typical laptop.
- A/B: one master with LoD vs a dedicated 1 M training run.
- Static hosting (Cloudflare Pages + R2, GitHub Pages, or Hexagon-internal), with chunked files, same origin and no recompression of range-read files.
- GDPR blur step.

**Optional track:** Luciad / Cesium smoke test.
- 3D Tiles export: a one-tile splat tileset with SPZ v3 in LUF, LiDAR as PNTS.
- Load in CesiumJS, and in LuciadRIA ≥ 2026.1 if access is confirmed.
- L-marker conformance check.

**Milestone M2:** a public or shareable URL. Targets: ≥ 30 fps on a mid-range phone and a typical laptop; first view in under about 20 MB on mobile; toggles and collision work. The **training budget is now fixed from measurements**.

### Phase 3: Application with modular sources and UI (≈ 4–6 weeks)

**Goal:** a non-developer can create a project, choose sources, import, process with live status, review QA, view and export.

**Work:**
- `core`: source registry, capabilities, frame graph, content-hashed DAG cache, runner with Job Objects and a single GPU queue.
- FastAPI backend with server-sent events.
- UI flow (§2.8): Sources → Import → Alignment setup → Process → View & Export.
- All non-drone combinations: **LiDAR-only, splat-only (arbitrary scale + manual scale entry), LiDAR + splat**.
- Lineage and clearance fields.
- Export bundle generator; optional pywebview window.

**Milestone M3:** all three non-drone modes run from the UI on fresh data, and reruns reuse the cache.

### Phase 4: Quality, robustness and stress tests (≈ 3–6 weeks; can interleave with Phase 3)

**Work:**
- PPISP with per-360-frame grouping.
- LiDAR depth loss (ground + stems, occlusion-filtered).
- Sky masks and background model; LiDAR free-space floater cull.
- Delayed densification and robust mask for wind.
- **Raw-fisheye A/B** (seams at trunks under 2 m).
- 16-view layout; rolling-shutter handling; learned features.
- Camera-only pole pass (E) integration.
- Repeat captures in harder conditions: some wind, sun, a denser stand, a longer 100 m walk.
- **Tiling test** (4 tiles).
- LiDAR pose-prior SfM mode.

**Milestone M4:** a quality report against the Phase 1 baseline (PSNR/LPIPS, floater counts, registration residuals) and a documented "known limits" list.

### Phase 5: Drone as a separate aerial layer (optional; ≈ 3–5 weeks plus ~13 weeks permit wait before publishing)

**Prerequisites (gate):**
- Phase 1 checkpoint RMSE measured and target detection proven.
- Multi-layer viewer (joint Spark sort, canopy-height partition, height cross-fade).
- The viewer actually needs above-canopy views (otherwise skip this phase).
- Operator registration (190 SEK + 250 SEK/yr), A1/A3 test (recommended) and a private drone liability policy checked.
- A pre-capture question sent to spridningstillstand@lm.se; a `drone_quarantine` folder set up outside every synced or git-tracked path.
- Site legal check done.
- A plot touching a clearing, track or edge.
- **First:** evaluate the free Lantmäteriet open-data context layer (a+). If it meets the overview need for Swedish sites, the Swedish drone pilot becomes optional.

**Work:**
- Drone source module (EXIF/XMP probe, RtkFlag, capabilities).
- Its own reconstruction group (COLMAP spatial matcher + GPS pose priors).
- Aerial gsplat model (antialiased; cap ≤ 1.5 M; ≤ 1600 px; 10 GB GPU).
- Target-based drone→LiDAR Sim(3) with ICP as a gated refinement only.
- Aerial layer in the viewer.
- Clearance gate; permit submission.
- Optional bridge-image capture to keep a later (b) research experiment possible.

**Milestone M5:** aerial layer aligned within the measured tolerance near the targets; the ground layer still publishable independently.

### Phase 6: Scale-up and tropical preparation (later)

**Work:**
- Spatial tiling on gsplat as the default for large plots.
- LiDAR pose priors as the default SfM mode under dense canopy.
- Multiple-closure walk designs.
- LoD / paged streaming for large scenes.
- Humidity and heat capture SOP.
- Country-specific legal review and a local partner (drone).
- Stress tests on the first tropical data.

### Timeline sketch

```
Week:   1   2   3   4   5   6   7   8   9  10  11  12  13  14  15  16  17  18  19  20+
P0     ████████
P1             ██████████████████
P2                               ████████████
P3                                           ████████████████████████
P4                                                   ███████████████████████  (interleaved)
P5     (legal/procurement groundwork can start in P2) ······················ ████████████ + permit wait
P6                                                                                    ▶
```

---

## 6. Clarifying questions

**Answered on 2026-10-07:**
- personal non-commercial project;
- camera is not the X6;
- Luciad is available (any version, good contact with the team);
- OneDrive is disabled;
- Cyclone REGISTER 360 PLUS + 3DR are available via the "TLS Software Demo / Eval. / EPP" licence;
- two LiDAR samples were delivered and analysed: the Brazil `.laz` (3DR export, timestamps, no intensity) and `mac-1.las` (intensity, no timestamps; a steep, dense forest). Remaining: **which tool exported `mac-1.las`**, and where was it captured?

Still open, ordered by how much they block:

| # | Question | Blocks |
|---|---|---|
| 1 | **Exact camera: X5, X4 or X4 Air?** Firmware version? Bare lenses or guards? (The `.insv` trailer reports the model, e.g. via ExifTool.) | Phase 0 parser and timing work (X4 has no verified open tooling) |
| 2 | ~~A short BLK2GO test walk~~. **Done:** `hq-office.b2g` decoded (trajectory + IMU at 200 Hz, 125 MHz clock). Optional: the same walk exported from Cyclone 3DR as LAS (with timestamps) to confirm the point clock, and whether `-b2g2trajectory` runs (WORKFLOW). | Clock cross-check only |
| 3 | ~~EPP licence terms~~. **Answered: yes, it covers this personal project.** | — |
| 4 | ~~The laptop~~ **Answered:** desktop PC (Ryzen 7 7800X3D, 32 GB, RTX 3080 10 GB, driver 596.36, VS 2022 17.14 / MSVC 14.44). Cyclone is installed on both the home and office PCs. The project folder stays where it is (only tool builds go to `C:\dev\`). | — |
| 5 | **Web audience:** which phones and laptops will coworkers use (models)? Public static hosting OK (Cloudflare / GitHub Pages)? Acceptable mobile download size? Is PlayCanvas (WebGPU) acceptable as a fallback viewer if Spark is too slow on phones? | Phase 2 budgets, hosting, benchmark matrix |
| 6 | **Mount and helpers:** a rigid mount (OmniGO or a printed collar) before the forest test? A second person on site? How is the camera mounted (upright or inverted, lens 0 forward or sideways)? | Capture quality; extrinsic check |
| 7 | **Site and date:** plot location (municipality / coordinates), landowner, date (≥ 5 °C, hunting season), and stand type (pine / spruce / birch, canopy openness) | Legal and site checks; drone feasibility |
| 8 | **Georeferencing:** is a local metric frame enough, or do you want coarse SWEREF 99 TM placement (e.g. via the Lantmäteriet 1 m DTM, or a borrowed RTK rover on the targets) for Luciad globe views? | Export variants |
| 9 | **Navigation semantics:** should walk mode treat shrubs and low branches as passable and block only on trunks, rocks, logs and drawn walls? May fly mode pass through canopy foliage? Click-to-walk / pathfinding wanted? | Phase 2 navigation design |
| 10 | **App style:** is a browser tab on localhost fine for the processing UI? Should raw captures be copied into the project or referenced in place? | Phase 3 |
| 11 | **Drone (later):** do you want above-canopy views at all? If yes, the Mini 5 Pro is the default; is publishing drone layers wanted (≈ 3 months of permit lead time)? | Phase 5 |
| 12 | **Contacts:** would you ask the BLK team (via Hexagon) to confirm the per-point time unit and zero point, whether trajectory and points share a clock, and the trajectory reference point and axes? And would you contact Hexagon R-evolution (BLK2GO rainforest work at La Gamba) for tropical experience? | Removes the remaining BLK2GO unknowns; tropical phase |

---

## 7. Key sources

The full list, with every claim and correction, is in [research/digest/](research/digest/), one file per topic with a `FACT-CHECK` section each. The most load-bearing sources:

**Insta360 and 360 processing**
- X6 / X5 manuals (specs, modes, FlowState): https://onlinemanual.insta360.com/x6/en-us/specs/shooting-specs · https://onlinemanual.insta360.com/x5/en-us/specs/shooting-specs · https://onlinemanual.insta360.com/x6/zh-cn/operating-tutorials/capture-preview/parameters/flowstate
- X6 announcement: https://www.dpreview.com/news/insta360-x6-360-camera-announcement/
- `.insv` format (trailer, IMU, exposure records, calibration, timing): https://github.com/bubo-squared/GyroView (docs/FORMAT.md, ADRs)
- telemetry-parser: https://github.com/AdrianEddy/telemetry-parser (PyPI 0.3.0 is from 2024: https://pypi.org/project/telemetry-parser/#history)
- insv-stitch (seam parallax, rolling-shutter model): https://github.com/BenjaminHenriksson/insv-stitch
- COLMAP panorama pipeline: https://github.com/colmap/colmap/blob/main/python/pycolmap/panorama.py · https://colmap.github.io/rigs.html
- OpenCV omnidir (Mei model): https://github.com/opencv/opencv_contrib/blob/4.x/modules/ccalib/include/opencv2/ccalib/omnidir.hpp

**SfM**
- COLMAP changelog and releases (4.0–4.2.1, global mapper, spherical model, LoMa): https://colmap.github.io/changelog.html · https://github.com/colmap/colmap/releases
- Windows build details (CUDA 13.2, ONNX CUDA 12): https://raw.githubusercontent.com/colmap/colmap/4.2.1/.github/workflows/build-windows.yml · https://raw.githubusercontent.com/colmap/colmap/4.2.1/cmake/FindDependencies.cmake
- Unofficial Windows CUDA pycolmap / Caspar: https://github.com/lyehe/build_gpu_colmap
- GLOMAP archived: https://github.com/colmap/glomap

**Splat training**
- gsplat (repo, benchmarks, Windows wheels): https://github.com/nerfstudio-project/gsplat · https://docs.gsplat.studio/main/tests/eval.html · https://docs.gsplat.studio/whl/gsplat/
- PPISP: https://github.com/nv-tlabs/ppisp · https://arxiv.org/abs/2601.18336
- 3DGRUT: https://github.com/nv-tlabs/3dgrut · Brush: https://github.com/ArthurBrussee/brush · LichtFeld: https://github.com/MrNeRF/LichtFeld-Studio
- Inria licence: https://github.com/graphdeco-inria/gaussian-splatting/blob/main/LICENSE.md

**Registration, sync, BLK2GO**
- pycolmap alignment API: https://colmap.github.io/pycolmap/pycolmap.html · Open3D: https://www.open3d.org/docs/latest/
- Hand-eye minimum-motion condition: https://github.com/opencv/opencv/blob/4.x/modules/calib3d/include/opencv2/calib3d.hpp
- Angular-velocity time alignment reference: https://github.com/ethz-asl/hand_eye_calibration (time_alignment.py)
- Clock drift (RecSync): https://arxiv.org/abs/2107.00987
- BLK2GO datasheets: https://leica-geosystems.com/-/media/files/leicageosystems/products/datasheets/leica-blk2go-ds-0521.pdf · https://shop.leica-geosystems.com/sites/default/files/2025-09/BLK2GO_SpecSheet.pdf
- Cyclone BLK kinematic export to E57 (WayPoints, images, CLI): https://rcdocs.leica-geosystems.com/cyclone-register-360/latest/b2g-to-e57 · https://rcdocs.leica-geosystems.com/docs/cyclone-register-360-export-blk-kinematic-data-to-e57-with-waypoints-and-images.md
- BLK Live versions (CSV trajectory, Image security): https://apps.apple.com/us/app/blk-live/id1608854881
- BLK2GO handling guidance: https://www.praxi.fr/Files/101641/22335001123097.pdf · https://knowledgebase.globalsurvey.co.nz/blk2go-best-practice-tips

**Ground and navigation**
- PDAL ground filters: https://pdal.io/en/stable/stages/filters.csf.html · https://pdal.io/en/stable/stages/filters.smrf.html · https://pdal.io/en/stable/stages/filters.faceraster.html
- 3DFin: https://github.com/3DFin/3DFin · three-mesh-bvh: https://github.com/gkjohnson/three-mesh-bvh
- splat-transform collision: https://developer.playcanvas.com/user-manual/splat-transform/collision/

**Web delivery**
- Spark (LoD, budgets, performance, controls): https://sparkjs.dev/docs/lod-getting-started/ · https://sparkjs.dev/docs/performance/ · https://github.com/sparkjsdev/spark
- SOG format: https://developer.playcanvas.com/user-manual/gaussian-splatting/formats/sog/ · splat-transform: https://github.com/playcanvas/splat-transform
- SPZ: https://github.com/nianticlabs/spz
- KHR_gaussian_splatting: https://github.com/KhronosGroup/glTF/tree/main/extensions/2.0/Khronos/KHR_gaussian_splatting · spz_2 draft PR: https://github.com/KhronosGroup/glTF/pull/2531
- PlayCanvas WebGPU benchmarks: https://blog.playcanvas.com/new-in-supersplat-webgpu-and-streaming-bring-huge-performance-wins/
- Potree: https://github.com/potree/PotreeConverter · 3DTilesRendererJS (PotreePlugin): https://github.com/NASA-AMMOS/3DTilesRendererJS
- Hosting limits: https://developers.cloudflare.com/pages/platform/limits/ · https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits

**Luciad / Octave Alto**
- Release notes (splats in 2026.1): https://dev.luciad.com/portal/productDocumentation/LuciadRIA/docs/releasenotes.html
- Gaussian splats tutorial and budgets: https://dev.luciad.com/portal/productDocumentation/LuciadRIA/docs/articles/tutorial/tileset3dpainting/visualize_gaussiansplats.html
- WebGPU-only (2026 changes): https://dev.luciad.com/portal/productDocumentation/LuciadRIA/docs/articles/guide/2026_major_changes.html
- Octave spin-off / Alto: https://investors.hexagon.com/share-information/octave-separation · https://www.octave.com/products/geospatial-intelligence/alto/alto-browser

**Forest GS and risks**
- TreeDGS: https://arxiv.org/html/2601.12823v3 · SpotLessSplats: https://github.com/lilygoli/SpotLessSplats · forest GS commentary: https://www.maxapress.com/article/id/697fff2efa6c5871c5fdb968

**Drone**
- Horizon-GS (aerial + street): https://arxiv.org/html/2412.01745 · MatrixCity: https://arxiv.org/html/2309.16553
- EASA Open category: https://www.easa.europa.eu/en/the-agency/faqs/drones-uas · Transportstyrelsen: https://www.transportstyrelsen.se/dronare
- Lag 2016:319: https://lagen.nu/2016:319 · Lantmäteriet dissemination permit FAQ and exemptions: https://www.lantmateriet.se/sv/spridningstillstand/vanliga-fragor/ · https://www.lantmateriet.se/sv/spridningstillstand/undantag/
- EASA Opinion 06/2026: https://www.easa.europa.eu/en/document-library/opinions/opinion-no-062026

**Gap research (2026-10-07)**
- BLK2GO User Manual v0.9 (mirror 100 Hz, base 2.5 Hz, PRF 1.64 MHz): https://3dscannertech.com/files/Leica-BLK2GO-User-Quide.pdf
- Cyclone 3DR `STrajectory` script class: https://cyclone3dr.leica-geosystems.com/help/2025.0/Script/class_s_trajectory.html
- REGISTER 360 pano-image pose export: https://rcdocs.leica-geosystems.com/docs/cyclone-register-360-option-to-publish-pano-images.md
- X5 rolling-shutter and timing ADR (GyroView): https://raw.githubusercontent.com/bubo-squared/GyroView/main/docs/adr/0034-a-frame-is-timed-half-way-through-its-shutter.md · insta360-rs format notes: https://github.com/OpenSpeleo/insta360-rs
- Insta360 FlowState in 360 mode (not supported in-camera): https://onlinemanual.insta360.com/x4/en-us/operating_tutorials/capture-preview/shooting-parameters/flowstate
- gsplat Windows/MSVC PR #1055: https://github.com/nerfstudio-project/gsplat/pull/1055 · Faster-GS: https://github.com/nerficg-project/faster-gaussian-splatting · VkSplat: https://github.com/harry7557558/vksplat
- Spark packed-splat memory: https://sparkjs.dev/docs/packed-splats/ · `.rad` sizes (PR #433): https://github.com/sparkjsdev/spark/pull/433 · WebSplatter mobile timings: https://arxiv.org/html/2602.03207
- Lantmäteriet large image sets / följdprodukter: https://www.lantmateriet.se/sv/spridningstillstand/ · contact: spridningstillstand@lm.se
- Forest analogues: Sapling-NeRF https://arxiv.org/abs/2602.22731 · RedwoodNeRF https://arxiv.org/abs/2410.07418 · He et al. 360 forest DBH https://arxiv.org/abs/2505.03093
- DJI Mini 5 Pro waypoints: https://www.dji.com/mini-5-pro · Transportstyrelsen drones: https://www.transportstyrelsen.se/dronare
- RTX 5060 specs: https://videocardz.com/newz/nvidia-geforce-rtx-5060-to-feature-3840-cuda-cores-150w-tgp-and-8gb-gddr7-memory · https://en.wikipedia.org/wiki/GeForce_RTX_50_series · Blackwell sm_120 in PyTorch: https://github.com/pytorch/pytorch/issues/164342 · nerfstudio on RTX 5070: https://github.com/nerfstudio-project/nerfstudio/issues/3732
