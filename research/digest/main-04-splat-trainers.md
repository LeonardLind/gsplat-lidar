# splat-trainers

## Summary

State of open-source Gaussian splat trainers as of 2026-10-06, for Windows 11 on a 16 GB RTX 3080 Ti Laptop GPU (Ampere, sm_86).

Note on method: the shared WebSearch budget ran out partway through. All claims marked high/medium confidence come from fetched primary pages (GitHub READMEs, configs, LICENSE files, release and commit pages). Laptop-GPU timings, viewer anti-aliasing compatibility and the status of Luma/Teleport come from my background knowledge and are marked low confidence.

**gsplat (nerfstudio-project), Apache-2.0**
- Status: the most capable and scriptable option. The latest PyPI release is still v1.5.3 (2025-07-04). On main, v1.6.0 was version-bumped on 2026-08-14 but is not on PyPI. Commits continue (2026-09-19, including an optional `--cache_images`). Main added PPISP (Jan 2026), LiDAR-sensor rasterization (Mar 2026), native CUDA MCMC perturb, AccuTile, sparse rasterization, faster 3DGUT, and FTheta cameras with FOV over 180° (Aug 2026).
- Windows: prebuilt wheels exist only up to 1.5.3, and only for pt24cu124 / cp310. Main must be built locally with MSVC and the CUDA toolkit. The examples pin torch 2.9.1, and v1.6.0 requires PyTorch 2.7 or newer.
- `simple_trainer.py` main options:
  - MCMC with `--strategy.cap-max` (default 1M).
  - `packed`, `sparse_grad`, `visible_adam`, `antialiased`, `data_factor`.
  - `post_processing` = `bilateral_grid` | `ppisp`; also `app_opt`, `pose_opt`.
  - 3DGUT (`with_ut` / `with_eval3d`) for fisheye and other distorted cameras.
  - A viser live viewer on port 8080.
  - Export via `export_splats`: ply / splat / ply_compressed (no SPZ or SOG).
- Benchmark (A100, MipNeRF360, 30k steps): MCMC capped at 1M uses 1.98 GB and 15.4 min for PSNR 29.18. That beats default densification (3.24M Gaussians, 5.62 GB, 19.4 min, PSNR 29.00). MCMC at 3M gives 4.99 GB, 27.6 min, PSNR 29.65.
- Limitations for this project:
  - The COLMAP parser loads only per-camera fisheye validity masks, not user mask files.
  - `depth_loss` supervises with COLMAP sparse points through per-image track indices.
  - `init_type='lidar'` exists only for NVIDIA NCore datasets.
  - `normalize_world_space=True` (the default) rotates, translates and scales the scene, and the exported PLY stays in that normalized frame. You must either train in a pre-transformed metric frame with normalization off, or invert the similarity transform including an SH rotation.

**nerfstudio splatfacto**
- Last release v1.1.5 (2024-11-11); last commit 2025-07-29. It pins gsplat==1.4.0, so it has no 3DGUT and no PPISP.
- splatfacto-w was last committed 2024-11-07. Treat both as stale; they are useful only for their `transforms.json` conventions (`ply_file_path`, `mask_path`, `depth_file_path`).

**Inria graphdeco 3DGS**
- Last commit 2024-10-30. It has depth regularization (`-d`, monocular inverse-depth maps plus `depth_params.json`), exposure compensation, EWA anti-aliasing, sparse_adam, and needs 24 GB to reach paper quality.
- Its Gaussian-Splatting License is non-commercial (research and evaluation only). Derivatives under the same license: 3DGS-MCMC (last update Dec 2024), Mip-Splatting, 2DGS, RaDe-GS, and the base code of Taming 3DGS (only Taming's own modifications are MIT; last commit 2025-06-16).
- PGSR uses a custom ZJU license that forbids commercial use. All of these should be avoided for a Hexagon project.

**Free, permissive or copyleft alternatives**
- **LichtFeld Studio** (GPLv3; v0.5.3 released 2026-07-01; commits daily through 2026-10-06):
  - Training: MCMC, MRNF and IGS+ strategies with `--max-cap`; `--bilateral-grid`; `--ppisp` with a novel-view controller; `--enable-mip`; `--gut` for nine distorted COLMAP models.
  - Cameras: EQUIRECTANGULAR (SPHERICAL) camera model in the COLMAP loader.
  - Data and memory: masks (`--mask-mode`); `--init` from a splat file; `--tile-mode`; quantized Adam state; ADMM sparsity pruning.
  - "Adaptive depth loss", a Python plugin API with `--python-script` callbacks, MCP, and `--headless`.
  - Export to PLY, SOG, SPZ, HTML, USD and RAD.
  - Requires compute capability 7.5+, driver 570+, CUDA 12.8 and at least 8 GB VRAM. The prebuilt Windows binary needs a donation of at least $30 on the portal; building from source (VS2022, CUDA 12.8, CMake 3.30+, vcpkg) is free.
- **Brush** (Apache-2.0; last tag v0.3.0 on 2025-09-14 with a Windows x64 zip; main very active, 2026-10-03 added `units_per_meter` so it can train in metres):
  - Cross-vendor WebGPU. Reads COLMAP and nerfstudio data, including `ply_file_path` for initialization.
  - Masks and native distorted cameras (RadialTangential8, KannalaBrandt4 fisheye, ThinPrism); no equirect.
  - `max_splats` (default 10M) is a cap only. It can produce LOD levels, has a live viewer, and exports PLY.
- **OpenSplat** (AGPLv3; v1.2.2 on 2026-09-16):
  - Input: COLMAP, nerfstudio, OpenSfM, ODM or OpenMVG data, plus masks.
  - Splat count: `--max-gaussians`, default 5M.
  - Export to ply, splat, spz and rad.
  - Memory: about 2 GB per million Gaussians.
  - Windows requires a source build.
- **NVIDIA 3DGRUT** (Apache-2.0; v1.1.0 on 2026-06-10; Windows since 2025-07 via `install_env_uv.ps1`):
  - Rendering: 3DGUT/3DGRT handle fisheye and rolling shutter.
  - Training: MCMC with `max_n_gaussians` (1M); PPISP.
  - Data: masks via `_mask.png` files; lidar / point_cloud initialization configs.
  - Export to PLY and USD/USDZ; Hydra configs.
- **Spirula Studio** (GPLv3; new; near-daily releases, the latest v2026.10.6 today):
  - Self-contained Vulkan or CUDA binary with built-in SfM, frame extraction and AI masking.
  - Native 360/equirect support, plus a dual-fisheye rig constraint (v2026.9.13).
  - Claims 10M SH3 Gaussians in 8 GB.
  - Experimental LiDAR support for metric scale and depth/normal maps; warm-start from PLY.
  - Export to PLY, SPZ, SOG and SPLAT; has a CLI.
- **Faster-GS** (CVPR 2026, Apache-2.0, NeRFICG): research code with 2-5x faster training, MCMC and Mip filter; Linux preferred.

**Closed tools (only relevant to watermark and export limits)**
- Postshot's Free plan cannot export PLY or SPZ, watermarks renders and is non-commercial.
- Polycam Free exports only glTF and watermarks video.
- KIRI 3DGS is a Pro feature.
- Polycam, KIRI and Teleport process in the cloud, which conflicts with the everything-local requirement.

**Implication for this project**
- Primary: gsplat `simple_trainer` in a thin custom Python fork. Use MCMC with an explicit `cap_max` (with MCMC the final splat count is effectively the cap).
- Pinhole crops from the Insta360 frames, and per-image masks for the operator and the BLK2GO.
- LiDAR-initialized points (LiDAR written into `points3D`).
- LiDAR sparse-depth supervision, using the same data-dict format gsplat already uses for its depth loss.
- Bilateral grid (1.5.3 wheel) or PPISP (main build) for forest exposure swings.
- Train directly in the LiDAR metric frame with `normalize_world_space=False`.
- Backup: LichtFeld Studio, which needs no code for equirect, masks, PPISP, the cap, and SOG/SPZ export. Brush is a fully permissive second backup. Spirula is worth one side-by-side test for 360 handling.

## Recommendations

- **Primary trainer: gsplat `examples/simple_trainer.py`, vendored into a thin project fork (custom Dataset/Parser and loss hooks). Start with the Windows wheel gsplat 1.5.3+pt24cu124 (Python 3.10) for a fast first test. Then move to a pinned commit of gsplat main (v1.6.0, PPISP, FTheta >180°, faster kernels) built locally with VS2022 Build Tools, CUDA 12.8 and torch 2.9.1.** — Apache-2.0 with no watermark or export limits, and pure Python, so LiDAR initialization, LiDAR depth loss, per-image masks, metric-frame export and splat-count control are all ordinary Python changes in-process. MCMC cap_max gives a deterministic final count. Its MCMC at 1M beats default densification at 3.24M on MipNeRF360. It is also the most actively developed (NVIDIA contributors, commits through 2026-09). _Alternatives:_ 3DGRUT (also Apache-2.0 Python with Hydra configs, Windows-supported, better for raw fisheye via 3DGUT, but heavier and without a sparse-depth hook). nerfstudio splatfacto is not recommended: stale and pinned to gsplat 1.4.0.
- **Backup trainer: LichtFeld Studio (GPLv3). Build from source for free, or pay the $30+ portal donation for the binary. Use `--strategy mcmc --max-cap N --ppisp --ppisp-controller (or --bilateral-grid) --mask-mode ignore --headless`, export SOG/SPZ, and point --init at a LiDAR-derived splat PLY. Secondary backup: Brush (Apache-2.0, prebuilt Windows zip; masks; KB4 fisheye; nerfstudio ply_file_path initialization from LiDAR; LOD levels).** — LichtFeld covers most needs without code: equirect, masks, PPISP, the cap, sparsity pruning and web formats. Its Python `--python-script` callbacks allow some customization. It runs as a standalone tool, so GPL does not affect the output splats. Brush is fully permissive but lacks depth and appearance compensation. _Alternatives:_ Spirula Studio (GPLv3) for one side-by-side test: native 360, dual-fisheye rig SfM, experimental LiDAR. Too new to depend on.
- **Avoid all Inria-licensed code (Inria 3DGS, 3DGS-MCMC original, Mip-Splatting, 2DGS repo, RaDe-GS, the Taming base) and PGSR, even for experiments that may become product work at Hexagon.** — The Gaussian-Splatting License and the ZJU license forbid commercial use or exploitation without consent. gsplat re-implements the equivalent features (MCMC, antialiased/Mip filter, 2DGS, absgrad) under Apache-2.0. _Alternatives:_ Use the Apache-2.0 equivalents: gsplat MCMC, gsplat 2DGS, 3DGRUT, Faster-GS native, DN-Splatter as reference code.
- **Train in the LiDAR metric frame. First solve the Sim3 from SfM to LiDAR, apply it to the COLMAP model (e.g., colmap model_transformer or pycolmap), and set `--normalize_world_space False`. Then the exported PLY is already metric and aligned with the LAS.** — gsplat's default normalization rotates, translates and scales the scene, and exports in that normalized frame. Undoing it afterwards requires rotating the SH coefficients as well as the means, scales and quaternions. A 10x10 m scene in metres is well-conditioned, because scene_scale is still derived from the camera spread. _Alternatives:_ Keep normalization and apply parser.transform^-1 to the exported splats with an SH rotation (e.g., splat-transform rotate, which should handle SH but is unverified), then re-verify against the LAS.
- **LiDAR initialization: voxel-downsample the registered BLK2GO cloud (2-3 cm voxels, aiming for about 0.3-1.5M points for the 10x10 m loop). Color the points from the LAS RGB if present, otherwise use the median color sampled from visible images. Write them as COLMAP points3D (empty tracks are fine for initialization; medium confidence). Optionally merge them with the SfM points to cover canopy areas the LiDAR missed.** — points3D is the universal initialization path for gsplat (init_type='sfm'), Brush, LichtFeld, 3DGRUT and OpenSplat. LiDAR initialization gives metric, dense geometry in low-texture foliage. With MCMC, set cap_max at or above the initialization count; growth is 5% per 100 steps, so 0.5M to 1.5M takes about 2.3k steps. _Alternatives:_ nerfstudio transforms.json with ply_file_path (Brush, splatfacto). LichtFeld --init with a splat PLY. 3DGRUT initialization=point_cloud.
- **LiDAR depth supervision in gsplat: subclass Dataset so that data['points'] (pixel coordinates) and data['depths'] come from LiDAR points projected into each virtual camera. Remove occluded points first: z-buffer the points at 1/4 resolution with a splat radius of a few pixels, or render a Cyclone mesh, and keep only points within about 2-3% of the buffer depth. Reuse the existing disparity L1 loss (depth_lambda 1e-2 to 1e-1). Consider an edge-aware log-L1 loss (DN-Splatter style) and decay the weight after about 15k steps. Mask sky and moving foliage.** — The trainer already consumes this sparse-depth format, so only the data source changes. Sparse LiDAR depth reduces floaters and fixes scale. Occlusion filtering is essential in forests, otherwise background trunk and ground points bleed through foreground leaves. Run 2 (camera-only) frames can be supervised the same way once registered. _Alternatives:_ Dense LiDAR depth maps via render_mode='RGB+ED' with a per-pixel L1 on valid pixels. Normal priors (LiDAR PCA normals compared with rendered normals of flattened Gaussians, or the gsplat 2DGS normal loss). These are lower priority for noisy vegetation and give no MCMC cap in 2DGS.
- **Masks and cameras: train on pinhole perspective crops from the 360 video, with a per-image (or per-virtual-camera) mask that removes the operator, the BLK2GO and the tape mount. In gsplat, add mask loading to the Parser and zero both the ground-truth and rendered pixels where the mask is off.** — Every trainer supports pinhole crops. gsplat has no equirect model, and its COLMAP mask_dict is per camera only. With a rigid rig, a static mask per virtual camera may be enough because the operator stays fixed in each crop direction. _Alternatives:_ LichtFeld EQUIRECTANGULAR + --gut, or Spirula native 360, to train on equirect frames directly; raw dual-fisheye through 3DGUT / OPENCV_FISHEYE / FTheta beyond 180° in gsplat main.
- **Exposure handling: use post_processing='bilateral_grid' on the 1.5.3 wheel, or 'ppisp' (with its controller) on gsplat main. Avoid app_opt for deliverables.** — Forest light and shade drive Insta360 auto exposure and white balance. These modules absorb the variation during training and are not exported, so web viewers see clean base radiance. app_opt appearance embeddings cannot be reproduced in standard viewers. _Alternatives:_ Lock exposure and white balance on the Insta360 if possible, which reduces the need for compensation.
- **Splat budget: train separate MCMC runs per target, for example 3-4M for desktop and 0.75-1.5M for phones (budgets are background knowledge; confirm with the viewer agent). Strip SH bands for the phone build (splat-transform -H 1 or 0) and package as SOG with LOD. Use post-hoc `splat-transform --decimate N` only for quick variants.** — With MCMC the final count is effectively the cap, and retraining at a cap preserves quality better than decimation (MCMC 1M beat default 3.24M in the gsplat benchmark). SOG and LOD streaming are the PlayCanvas-recommended web formats. _Alternatives:_ LichtFeld --max-cap plus --enable-sparsity --prune-ratio; Brush lod_levels; OpenSplat --max-gaussians; 3DGRUT max_n_gaussians.
- **Leave antialiased off (or test in the target viewer) for web-delivered splats. Set the starting VRAM controls for the 16 GB laptop: packed=True, data_factor 1-2 on 1600 px crops, visible_adam, images loaded on the fly (do not use --cache_images when there are 2000 images), sh_degree 3 reducible to 1.** — Antialiased / Mip-filter training changes opacity semantics, and viewers without matching compensation may render it differently (low confidence; unverified). The memory settings keep about 4-6M Gaussians within 16 GB, extrapolated from the gsplat benchmarks. _Alternatives:_ LichtFeld --tile-mode 2/4, --max-width, --no-cpu-cache; Brush max_resolution 1920.

## Load-bearing findings (claim + sources)

- [high] gsplat is Apache-2.0. The latest PyPI release is 1.5.3 (2025-07-04). v1.6.0 exists only on main (bumped 2026-08-14) with commits through 2026-09-19. — https://github.com/nerfstudio-project/gsplat https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/README.md https://pypi.org/project/gsplat/
- [high] gsplat Windows prebuilt wheels go only up to 1.5.3 and only for pt24cu124 / cp310. Newer main requires a local MSVC and CUDA build; the examples pin torch==2.9.1. — https://docs.gsplat.studio/whl/gsplat/ https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/docs/INSTALL_WIN.md https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/examples/requirements.txt
- [high] gsplat MCMC `cap_max` directly controls the final splat count. MCMC at 1M Gaussians beat default densification at 3.24M on MipNeRF360. — https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/gsplat/strategy/mcmc.py https://docs.gsplat.studio/main/tests/eval.html https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/examples/benchmarks/mcmc.sh
- [high] gsplat simple_trainer exports splats in the normalized training frame (rotated, translated and scaled), not the input COLMAP frame. — https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/examples/simple_trainer.py https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/examples/datasets/normalize.py
- [high] gsplat COLMAP data path: SfM points3D initialization, sparse-point depth loss, and only per-camera fisheye validity masks. There is no user-mask loading, no external LiDAR file initialization and no rig model. — https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/examples/datasets/colmap.py https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/examples/simple_trainer.py
- [high] PPISP (NVIDIA, Apache-2.0, Jan 2026) handles exposure, white balance, vignetting and camera-response variation better than a bilateral grid, and it is integrated in gsplat main, 3DGRUT and LichtFeld. — https://research.nvidia.com/labs/sil/projects/ppisp/ https://arxiv.org/abs/2601.18336 https://github.com/nv-tlabs/ppisp
- [high] The Inria 3DGS family is non-commercial: Inria 3DGS, 3DGS-MCMC (ubc-vision), Mip-Splatting, 2DGS and RaDe-GS use the 'Gaussian-Splatting License'. Taming 3DGS has MIT modifications on Inria base code. PGSR uses a ZJU license that forbids commercial use. — https://raw.githubusercontent.com/graphdeco-inria/gaussian-splatting/main/LICENSE.md https://raw.githubusercontent.com/graphdeco-inria/gaussian-splatting/main/README.md https://github.com/graphdeco-inria/gaussian-splatting/commits/main
- [high] LichtFeld Studio (GPLv3) is the most feature-complete free GUI and headless trainer on Windows: MCMC cap, PPISP, bilateral grid, masks, equirect, 3DGUT, Python callbacks, and SOG/SPZ export. Prebuilt Windows binaries are behind a donation of at least $30; source builds are free. — https://github.com/MrNeRF/LichtFeld-Studio https://raw.githubusercontent.com/MrNeRF/LichtFeld-Studio/master/LICENSE https://github.com/MrNeRF/LichtFeld-Studio/wiki/Command-Line-Options
- [medium] LiDAR depth and normal priors are an established, effective technique, and permissive reference code exists (DN-Splatter, Apache-2.0). — https://github.com/maturk/dn-splatter https://arxiv.org/abs/2404.09748 https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/examples/simple_trainer_2dgs.py

## Key numbers

- gsplat latest PyPI release: 1.5.3, 2025-07-04 (main is v1.6.0 bumped 2026-08-14, unreleased; last commit 2026-09-19) (https://pypi.org/project/gsplat/ ; https://github.com/nerfstudio-project/gsplat/commits/main)
- gsplat Windows wheel for latest version: gsplat-1.5.3+pt24cu124-cp310-win_amd64 only (https://docs.gsplat.studio/whl/gsplat/)
- gsplat MCMC cap_max default / growth: 1,000,000; +5% per refine every 100 steps, from step 500 to 25,000 (https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/gsplat/strategy/mcmc.py)
- gsplat A100 MipNeRF360 MCMC 1M: 1.00M Gaussians, 1.98 GB, 15.42 min, PSNR 29.18 (https://docs.gsplat.studio/main/tests/eval.html)
- gsplat A100 MipNeRF360 MCMC 3M: 3.00M Gaussians, 4.99 GB, 27.63 min, PSNR 29.65 (https://docs.gsplat.studio/main/tests/eval.html)
- gsplat A100 MipNeRF360 default densification: 3.24M Gaussians, 5.62 GB, 19.39 min, PSNR 29.00 (https://docs.gsplat.studio/main/tests/eval.html)
- gsplat depth_lambda default: 1e-2 (disparity L1 on sparse points) (https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/examples/simple_trainer.py)
- gsplat examples torch pin: torch==2.9.1, torchvision==0.24.1; v1.6.0 requires PyTorch 2.7+ (https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/examples/requirements.txt)
- nerfstudio latest release: 1.1.5, 2024-11-11; pins gsplat==1.4.0; last commit 2025-07-29 (https://pypi.org/project/nerfstudio/)
- splatfacto / splatfacto-big VRAM: ~6 GB / ~12 GB (https://docs.nerf.studio/nerfology/methods/splat.html)
- Inria 3DGS VRAM for paper quality: 24 GB; last commit 2024-10-30 (https://raw.githubusercontent.com/graphdeco-inria/gaussian-splatting/main/README.md)
- LichtFeld Studio latest: v0.5.3, 2026-07-01; daily commits through 2026-10-06; binary needs a donation of at least $30 (https://lichtfeld.io/blog/release-lichtfeld-studio-v0-5-3/ ; https://lichtfeld.io/)
- LichtFeld requirements: compute capability 7.5+, driver 570+, CUDA 12.8, at least 8 GB VRAM (https://lichtfeld.io/ ; https://github.com/MrNeRF/LichtFeld-Studio)
- Brush latest tag / max_splats default: v0.3.0, 2025-09-14 / 10,000,000 (cap only); main active 2026-10-03 (https://github.com/ArthurBrussee/brush/tags ; https://raw.githubusercontent.com/ArthurBrussee/brush/main/crates/brush-train/src/config.rs)
- Brush max_resolution default: 1920 px; frame cache 6 GiB native (https://raw.githubusercontent.com/ArthurBrussee/brush/main/crates/brush-dataset/src/config.rs)
- OpenSplat latest / memory: v1.2.2, 2026-09-16; ~2 GB GPU per 1M Gaussians; --max-gaussians default 5M (https://github.com/WebODM/OpenSplat/tags ; https://raw.githubusercontent.com/WebODM/OpenSplat/main/opensplat.cpp)
- 3DGRUT latest: v1.1.0, 2026-06-10; MCMC max_n_gaussians 1,000,000; CUDA 12.8 default (https://github.com/nv-tlabs/3dgrut/releases ; https://raw.githubusercontent.com/nv-tlabs/3dgrut/main/configs/strategy/mcmc.yaml)
- Spirula Studio latest / VRAM claim: v2026.10.6 (2026-10-06); 10M SH3 Gaussians in 8 GB (https://github.com/harry7557558/spirula-studio/releases ; https://github.com/harry7557558/spirula-studio)
- Faster-GS speedup: up to 5x faster training (CVPR 2026, Apache-2.0) (https://arxiv.org/abs/2602.09999 ; https://github.com/nerficg-project/faster-gaussian-splatting)
- SPZ compression: ~10x smaller than PLY (https://github.com/nianticlabs/spz)
- fused-bilagrid speedup: 3.5x less total training time than the nerfstudio bilateral grid (~800 high-res images) (https://github.com/harry7557558/fused-bilagrid)

## Tools & licenses

- gsplat (nerfstudio-project) | PyPI 1.5.3 (2025-07-04); main v1.6.0 (Aug 2026, unreleased), last commit 2026-09-19 | Apache-2.0 | win: pip wheel 1.5.3 pt24cu124 cp310; main needs a local MSVC + CUDA build (torch 2.7+, examples pin 2.9.1) | Python library plus simple_trainer: MCMC cap_max, packed, antialiased, 3DGUT fisheye/FTheta, bilateral grid, PPISP (main), sparse-point depth loss, viser viewer :8080, export ply/splat/ply_compressed. Exports in the normalized frame by default.
- nerfstudio splatfacto / splatfacto-big / splatfacto-mcmc | 1.1.5 (2024-11-11); last commit 2025-07-29 | Apache-2.0 | win: pip; Windows fixes in 1.1.2 | Stale; pins gsplat==1.4.0; bilateral grid, masks, ply_file_path initialization; no depth loss.
- splatfacto-w | last commit 2024-11-07 | Apache-2.0 | win: via nerfstudio | Appearance embeddings and transient masks; the background model is not exportable; stale.
- Inria graphdeco 3DGS | last commit 2024-10-30 | Gaussian-Splatting License (NON-COMMERCIAL, research/evaluation only) | win: yes (source build; prebuilt SIBR viewers) | Depth regularization (-d), exposure compensation, --antialiasing, sparse_adam; 24 GB for paper quality.
- Taming 3DGS | last commit 2025-06-16 | MIT modifications on Inria base (effectively NON-COMMERCIAL) | win: not documented | --budget with --mode final_count gives a deterministic count.
- 3DGS-MCMC (ubc-vision) | last update Dec 2024 | Gaussian-Splatting License (NON-COMMERCIAL) | win: tested on Ubuntu only | cap_max; superseded by gsplat MCMCStrategy (Apache).
- Mip-Splatting |  | Gaussian-Splatting License (NON-COMMERCIAL) | win: not documented | The 3D/2D filter is reimplemented in gsplat antialiased, Brush and LichtFeld --enable-mip.
- 2DGS |  | Gaussian-Splatting License (NON-COMMERCIAL) | win: prebuilt SIBR viewer only | Use gsplat simple_trainer_2dgs.py (Apache) instead.
- PGSR | last update 2024-07-18 | Custom ZJU license, commercial use prohibited | win: not documented | Planar surface reconstruction.
- RaDe-GS |  | Gaussian-Splatting License (NON-COMMERCIAL) | win: not documented | Depth/normal rendering and mesh extraction.
- LichtFeld Studio | v0.5.3 (2026-07-01); daily commits to 2026-10-06 | GPL-3.0 | win: prebuilt via portal (at least $30 donation) or free source build (VS2022, CUDA 12.8, CMake 3.30+, vcpkg) | MCMC/MRNF/IGS+ with --max-cap, PPISP, bilateral grid, masks, EQUIRECTANGULAR, --gut, Python plugins, headless, export PLY/SOG/SPZ/HTML/USD.
- Brush | v0.3.0 (2025-09-14); main active 2026-10-03 | Apache-2.0 | win: prebuilt Windows x64 zip; Rust/WebGPU | COLMAP and nerfstudio input (ply_file_path initialization), masks, KB4 fisheye, max_splats cap, LOD, live viewer; no depth or appearance modules.
- OpenSplat | v1.2.2 (2026-09-16) | AGPL-3.0 | win: source build (VS2022, CUDA 11.8, LibTorch 2.1.2, OpenCV 4.9) | --max-gaussians, masks, ply/splat/spz/rad; about 2 GB per 1M Gaussians.
- NVIDIA 3DGRUT (3DGRT/3DGUT) | v1.1.0 (2026-06-10); commits to 2026-09-22 | Apache-2.0 | win: yes since 2025-07 via install_env_uv.ps1 | Fisheye/rolling shutter, MCMC max_n_gaussians, PPISP, *_mask.png masks, lidar/point_cloud initialization configs, PLY/USD export, Viser GUI.
- PPISP | v1.0.0 (Jan 2026) | Apache-2.0 | win: CUDA extension build (pip --no-build-isolation) | Physically plausible exposure, white balance, vignetting and camera-response correction with a novel-view controller.
- Spirula Studio | v2026.10.6 (2026-10-06) | GPL-3.0 | win: prebuilt binaries (Vulkan/CUDA) | All-in-one: SfM, native 360, dual-fisheye rig, experimental LiDAR, quantized training, PLY/SPZ/SOG/SPLAT export, CLI.
- Faster-GS (NeRFICG) | CVPR 2026 (arXiv 2602.09999, 2026-02-10) | Apache-2.0 | win: Linux preferred, Windows possible | 2-5x faster research baseline; PLY export.
- DN-Splatter | 2024-11-29 | Apache-2.0 | win: not documented | Reference implementation for sensor depth and normal losses.
- PlayCanvas splat-transform |  | MIT | win: npm (Node) | PLY to SOG/LOD, --decimate, -H SH stripping.
- Niantic spz |  | MIT | win: Python bindings via nanobind | About 10x smaller than PLY.
- Jawset Postshot (closed) |  | Proprietary | win: yes | Free plan: no PLY/SPZ export, watermarked renders, non-commercial.
- Polycam / KIRI / Teleport (closed, cloud) |  | Proprietary | win:  | Polycam Free: glTF-only export and watermarked video. KIRI: 3DGS is Pro. Teleport: cloud processing. None meets the local, unrestricted requirement.

## risks

- gsplat main (v1.6.0) is unreleased and requires a local Windows CUDA/MSVC build against torch 2.7+ (examples pin 2.9.1). The build may break, so pin a commit. The 1.5.3 Windows wheel is limited to torch 2.4, CUDA 12.4 and Python 3.10, and lacks PPISP and FTheta beyond 180°.
- gsplat exports splats in its normalized frame by default. Forgetting this, or transforming a trained splat without rotating its SH coefficients, will misalign the splat against the LAS or produce wrong view-dependent colors.
- LiDAR depth supervision in dense forest is vulnerable to see-through. Sparse projected points from occluded trunks and ground land on foreground leaves unless they are z-buffer filtered. Wind-driven foliage motion between Run 1 and Run 2 also makes depth and photometric terms inconsistent.
- Masks are mandatory: the operator, the BLK2GO and the tape mount appear in the 360 frames. gsplat needs custom per-image mask loading, and its trainer zeroes only the rendered pixels.
- Laptop 3080 Ti thermal throttling and the 16 GB limit: long runs (1-2 h or more at 2-3M Gaussians and 50k+ steps) are an unmeasured estimate.
- License contamination: Inria-derived repos (3DGS, 3DGS-MCMC, Mip-Splatting, 2DGS, RaDe-GS, the Taming base) and PGSR are non-commercial. GPL/AGPL tools (LichtFeld, Spirula, OpenSplat) are fine as standalone tools, but modifying and redistributing them imposes copyleft.
- LichtFeld's prebuilt Windows binary is paid (a donation of at least $30). The free route is a source build with VS2022, CUDA 12.8, CMake 3.30+ and vcpkg.
- Splats trained with antialiased / Mip-filter may look different in web viewers that do not apply the same compensation (unverified).
- Spirula Studio and LichtFeld change daily, so behaviour may shift between versions. Spirula's LiDAR support is explicitly experimental.
- The shared web-search budget ran out partway through. Luma's status, mobile splat budgets, viewer AA support and laptop training times are background knowledge, not verified.

## open_questions

- Does LichtFeld `--init` accept a plain xyz+rgb point cloud PLY (for example voxelized LiDAR), or only a full 3DGS splat PLY? Does its 'adaptive depth loss' accept external depth maps, and in what format?
- Which input formats does Spirula Studio's LiDAR mode take (LAS/LAZ/E57/PLY)? Does it use LiDAR for depth supervision during training or only for scale? Can it import an existing COLMAP model and poses?
- Does gsplat's pycolmap-based Parser accept points3D entries with empty tracks? Expected yes, but it needs verifying before relying on it for LiDAR initialization.
- Measured gsplat MCMC throughput on an RTX 3080 Ti Laptop GPU at about 1600x1600 crops with 1-3M Gaussians.
- Which target web viewer (Spark, PlayCanvas/SuperSplat, LuciadRIA) correctly renders splats trained with antialiased/Mip-filter, and what splat counts does each sustain on mid-range phones?
- Does the LAS exported from Cyclone carry per-point RGB from the BLK2GO cameras, or only intensity? This affects how the LiDAR initialization points are colored.
- Is PPISP's controller useful for web delivery, given that it cannot be applied in standard viewers? It still yields cleaner base radiance; quantify the difference against the bilateral grid on forest data.

## questions_for_user

- Will this pipeline or its outputs be used commercially at Hexagon, or only for internal research and evaluation? This decides whether GPL tools are acceptable as standalone tools and confirms that all Inria-licensed code must be excluded.
- Are you willing to build gsplat main from source on Windows (VS2022 Build Tools, CUDA 12.8, PyTorch 2.9.1) to get PPISP and the newest kernels, or should v1 stay on the gsplat 1.5.3 Windows wheel (Python 3.10, torch 2.4, CUDA 12.4)?
- Do you want to keep the Insta360 raw dual-fisheye (.insv) footage for direct fisheye training (3DGUT, LichtFeld --gut, Spirula rig mode), or standardize on pinhole crops for every trainer?
- What are the target splat budgets: a single deliverable, or separate desktop and phone builds (for example about 3M and about 1M)?
- Would you pay the $30+ LichtFeld portal donation for the prebuilt binary, or should the backup path use a free source build or Brush?

## FACT-CHECK: non-confirmed verdicts

- **CORRECTED**: gsplat COLMAP path loads only per-camera fisheye validity masks, has a sparse-point depth loss from COLMAP tracks, uses init_type 'lidar' only for NCore, and the trainer only zeroes the rendered pixels where ~mask, so ground-truth pixels must also be zeroed. → Per-camera masks only, track-based depth and NCore-only LiDAR initialization are confirmed. Stock Dataset.__getitem__ sets data['mask'] only from the undistortion validity mask. The masking-loss part is stale for main:
- main zeroes the render, computes L1 only on valid pixels (`l1_loss(colors[masks], pixels[masks])`), and multiplies both colors and pixels by the mask before SSIM.
- On main you only need to add per-image mask loading; the loss already handles GT.
- The report's description fits only v1.5.3, which zeroes only the render and computes L1 and fused_ssim on full images.
Also: point_indices comes from COLMAP track elements. LiDAR points written to points3D with empty tracks give images no entry, so the stock depth path would fail with a KeyError if depth_loss is on; a custom Dataset is required. (https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/examples/simple_trainer.py https://raw.githubusercontent.com/nerfstudio-project/gsplat/v1.5.3/examples/simple_trainer.py)
- **CORRECTED**: gsplat camera models are pinhole/ortho/fisheye/ftheta/lidar, and 3DGUT (with_ut / with_eval3d) in simple_trainer handles fisheye and distorted cameras. → rasterization() documents only 'pinhole', 'ortho', 'fisheye' and 'ftheta'. LiDAR lives in the separate sensors and LiDAR rasterization path (`pip install "gsplat[lidar]"`).
- In simple_trainer, the COLMAP Parser always undistorts; there is no undistort flag, and the signature is (data_dir, factor, normalize, test_every, load_exposure).
- Distortion coefficients reach rasterize_splats only from `self.ncore_camera_data` (NCore datasets).
- So COLMAP OPENCV_FISHEYE input is remapped to pinhole even with --with_ut, and the ~200° Insta360 lens FOV cannot be kept.
- Raw-fisheye or FTheta training in gsplat needs a custom dataset that passes camera_model and coefficients. (https://docs.gsplat.studio/main/apis/rasterization.html https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/examples/datasets/colmap.py)
- **CORRECTED**: PPISP (NVIDIA, Apache-2.0, Jan 2026) is integrated in gsplat main, 3DGRUT and LichtFeld. On the 1.5.3 wheel use post_processing='bilateral_grid'. → PPISP itself is confirmed: arXiv 2601.18336 (submitted 2026-01-26, revised 2026-04-07), Apache-2.0, v1.0.0, installed with `pip install . --no-build-isolation`, and Windows support is not documented. It models exposure, vignetting, chromaticity white balance and CRF, plus a novel-view controller. It is integrated in gsplat main (Jan 2026, both strategies since 2026-07-20; ValueError unless batch_size=1), 3DGRUT (2026/01 news) and LichtFeld (--ppisp, --ppisp-controller).
The correction: v1.5.3 simple_trainer has no post_processing field. On the 1.5.3 wheel the flag is `--use_bilateral_grid` (grid 16x16x8). The `post_processing` Literal ['bilateral_grid','ppisp'] exists only on main. (https://arxiv.org/abs/2601.18336 https://github.com/nv-tlabs/ppisp)
- **CORRECTED**: LichtFeld Studio (GPLv3): v0.5.3 released 2026-07-01 with MCMC --max-cap, PPISP, bilateral grid, masks, EQUIRECTANGULAR, --gut, Python callbacks and PLY/SOG/SPZ/HTML/USD export. The prebuilt Windows binary needs a donation of at least $30; source builds are free (VS2022, CUDA 12.8, CMake 3.30+, vcpkg). → Mostly confirmed (GPLv3 LICENSE; CLI flags exist as listed; export .ply/.sog/.spz/.usd*/.html; CC 7.5+, driver 570+, CUDA 12.8, 8 GB). Corrections:
1) The GitHub v0.5.3 release was published 2026-06-24; 2026-07-01 is the blog date. v0.5.0 was 2026-03-18.
2) `--init` accepts only splat files (.ply/.sog/.spz/.usd*/.resume), not a plain xyz+rgb LiDAR cloud. LiDAR initialization must go through COLMAP points3D, or by converting LiDAR points into a 3DGS-format PLY.
3) The 'adaptive depth loss' input is undocumented, and depth-map output is still marked '[TODO] not yet implemented'.
4) The Windows build requires VS2022 specifically (not 2019 or 2026), Perl 5.42+, Ninja, an x64 Native Tools prompt, and a repository path with NO spaces. The user's working directory 'C:\Users\Leonard Lind\...' contains a space.
5) Price is inconsistent: lichtfeld.io says a minimum contribution of $30, while the README says 'a donation of your choosing' and includes daily builds. (https://api.github.com/repos/MrNeRF/LichtFeld-Studio/releases?per_page=8 https://lichtfeld.io/blog/release-lichtfeld-studio-v0-5-3/)
- **CORRECTED**: OpenSplat (AGPLv3, v1.2.2 on 2026-09-16) has --max-gaussians (default 5M), masks, ply/splat/spz/rad export and ~2 GB per 1M Gaussians, and needs a Windows source build. → Version, license, flags and memory are confirmed. v1.2.2 was published 2026-09-16T17:41Z (v1.2.0 on 2026-08-20). Masks are read from a masks/mask/segmentation/dynamic_masks folder. The Windows stack is VS2022, CMake 3.28.3, CUDA 11.8, libtorch 2.1.2 and OpenCV 4.9.0.
Correction: the README says Windows users can buy a pre-built executable, so source build is not the only option. GitHub releases have no assets. (https://api.github.com/repos/WebODM/OpenSplat/releases?per_page=3 https://raw.githubusercontent.com/WebODM/OpenSplat/main/README.md)
- **CORRECTED**: Closed tools: Postshot Free has no PLY/SPZ export, a watermark and is non-commercial; Polycam Free exports glTF only with watermarked video; KIRI 3DGS is Pro-only; Teleport is cloud. → Postshot is confirmed: PLY/SPZ export, watermark-free renders and commercial use start at Indie, and the CLI is Studio only. Polycam is confirmed: Free is .gltf only, watermarked video and 150 images per capture. Teleport's 'elastic GPU clusters' confirm cloud processing.
KIRI is wrong: its pricing page advertises 'Unlimited Free Exports' with no watermarks, and only 'Mesh-Inclusive 3DGS Scan' is Pro. It is still cloud-processed, so the conclusion stands. (https://www.jawset.com/shop/pricing https://poly.cam/pricing)
- **UNVERIFIABLE**: Training time on a 3080 Ti Laptop: ~35-50 min for MCMC 1M at 30k steps, ~60-120 min for 2-3M Gaussians or 50-60k steps; 16 GB fits ~4-6M Gaussians at 1600 px with packed. → No primary benchmark for a laptop 3080 Ti was found, and the web-search budget was exhausted. The only anchor is A100 data: 1.98 GB at 1M, 3.43 GB at 2M, 4.99 GB at 3M on MipNeRF360 with data_factor 4. Memory scales with resolution, and gsplat's default data_factor is 4, so 1600 px crops at factor 1 will use much more than the benchmark. Treat this as a hypothesis to measure in the first test. (https://docs.gsplat.studio/main/tests/eval.html https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/examples/simple_trainer.py)

_13 of 20 checked claims confirmed._


## FACT-CHECK: missed developments

- gsplat main ships examples/av_trainer.py, a multi-camera trainer with LiDAR rendering supervision (lidar_distance_loss), built on the Mar-2026 LiDAR rasterization.: AV_TRAINER.md: trains on surround-view driving scenes, PandaSet (pinhole) and NCore v4 (FTheta + 3DGUT), 'with optional LiDAR rendering for geometric supervision'. It documents no generic or custom dataset input. It needs per-scan sensor poses and spinning-LiDAR models, which a merged Cyclone LAS lacks, so it is not directly usable for the BLK2GO. It is useful as reference code for a LiDAR distance loss if raw scans plus trajectory ever become available. (https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/examples/AV_TRAINER.md https://github.com/nerfstudio-project/gsplat/tree/main/examples)
- The gsplat main COLMAP Parser gained load_exposure (EXIF exposure for PPISP) and --cache_images (2026-09-17).: load_exposure reads EXIF from the original images. Frames extracted from Insta360 video with FFmpeg or Blender carry no per-frame EXIF exposure, so this does not help unless metadata is injected. Rely on PPISP or the bilateral grid instead. --cache_images decodes and undistorts every image once into host RAM; avoid it with about 2000 frames at 1600 px on a laptop. (https://github.com/nerfstudio-project/gsplat/blob/main/examples/datasets/colmap.py https://github.com/nerfstudio-project/gsplat/commits/main)
- 3DGRUT initialization=point_cloud loads <dataset>/point_cloud.ply directly, the simplest LiDAR initialization among the Python trainers.: trainer.py: `ply_path = os.path.join(conf.path, 'point_cloud.ply')`. fused_point_cloud uses conf.initialization.fused_point_cloud_path. 'lidar' initialization pulls point clouds from dataset frames (NCore-type), num_points 1M. No points3D editing is needed. (https://raw.githubusercontent.com/nv-tlabs/3dgrut/main/threedgrut/trainer.py https://raw.githubusercontent.com/nv-tlabs/3dgrut/main/configs/initialization/point_cloud.yaml)
- LichtFeld Studio is shipping ML model-weight releases (MoGe-2 normal ONNX 2026-07-05, SAM 2.1 2026-08-28, LPIPS 2026-09-03, RoMa v1 dense matcher 2026-09-16, MoGe-3 2026-09-23).: This suggests built-in auto-masking (SAM 2.1), monocular normal or depth priors (MoGe), and dense matching (RoMa) in daily or portal builds. The features themselves were not documented in the pages fetched (medium-low confidence). Check whether the MoGe normal priors can be swapped for LiDAR normals. (https://api.github.com/repos/MrNeRF/LichtFeld-Studio/releases?per_page=8)
- COLMAP has no equirectangular or spherical camera model, which limits the 'train equirect directly' alternatives.: COLMAP's camera list covers pinhole, radial, OpenCV, division, fisheye, thin-prism and EUCM models, with no SPHERICAL. LichtFeld's SPHERICAL/EQUIRECTANGULAR loader therefore needs an SfM tool that exports spherical cameras, such as Spirula's built-in SfM or a commercial tool. Pinhole crops plus COLMAP/GLOMAP (with rig support) remain the most portable route. (https://colmap.github.io/cameras.html https://lichtfeld.io/blog/release-lichtfeld-studio-v0-5-3/)
- Gaussian-LIC2 (LiDAR-inertial-camera Gaussian SLAM, GPL-3, code Feb 2026, IJRR Jul 2026) exists but does not fit this pipeline.: It needs raw synchronized LiDAR/IMU/camera streams under ROS on Ubuntu 20.04 (tested on RTX 3090/4090). The BLK2GO-through-Cyclone LAS export and Windows-only processing rule it out. It is noted so the planner does not chase it. (https://github.com/APRIL-ZJU/Gaussian-LIC)
- The SPZ format carries an antialiasing flag for Mip-trained data, and Brush bakes its Mip 3D filter into exported splats.: This supports the report's caution about antialiased training. Splats trained with gsplat `--antialiased` export raw opacities and need viewer-side compensation; SPZ can signal it with a flag. Brush folds min_scale_factor into scales and opacity at export, so its PLYs render correctly in standard viewers. (https://github.com/nianticlabs/spz https://raw.githubusercontent.com/ArthurBrussee/brush/main/crates/brush-train/src/config.rs)

## FACT-CHECK: recommendation assessment

The core recommendations survive; several implementation details need correcting. The web-search budget ran out partway through, so everything after that came from direct fetches of primary pages (GitHub API/raw files, PyPI, vendor pages). No new search for unknown 2026 trainers was possible beyond the awesome list and known repos.

Primary trainer (gsplat simple_trainer in a thin fork): KEEP. Apache-2.0, latest PyPI 1.5.3, main at v1.6.0 unreleased, and it is the most scriptable option. Changes:
1) Go straight to a pinned gsplat main commit (torch 2.9.1, CUDA 12.8, VS2022 Build Tools) instead of starting on the 1.5.3 wheel.
   - The pieces this project needs (correct masked L1/SSIM, the post_processing / PPISP switch, --cache_images, PPISP+MCMC) are main-only, and the 1.5.3 examples differ, e.g. `--use_bilateral_grid` rather than `post_processing`.
   - If a quick test is needed, `pip install gsplat` with JIT compile also works with newer torch.
2) Masks: on main you only need a Dataset that returns data['mask'] per image; the loss already excludes masked pixels from L1 and zeroes both sides for SSIM. Drop the 'also zero GT' step unless you stay on 1.5.3.
3) The stock COLMAP parser always undistorts, and distortion coefficients reach the rasterizer only from NCore data. So '3DGUT for fisheye' and 'FTheta >180°' are not usable through the COLMAP path. Pinhole crops stay the right default for gsplat; raw dual-fisheye means writing a custom dataset.
4) MCMC count control: the final count is max(init_count, cap_max). Voxel-downsample the LiDAR initialization strictly below cap_max (e.g. 0.3-0.8M for a 1M cap), otherwise the web budget is silently exceeded.
5) LiDAR depth: a custom Dataset is mandatory, not optional. The stock depth path indexes COLMAP tracks and would fail with a KeyError on empty-track LiDAR points. The occlusion-filtered projected-LiDAR plan in the report is sound.
6) Training in the LiDAR metric frame with normalize_world_space=False is confirmed workable: scene_scale is still derived from the camera spread, and the Parser uses an identity transform.

Backups:
- Consider promoting NVIDIA 3DGRUT to co-backup for the Python path:
  - Apache-2.0, official Windows install script (install_env_uv.ps1), v1.1.0 (2026-06-10).
  - Zero-code LiDAR initialization: drop the cloud as <dataset>/point_cloud.ply and set initialization=point_cloud.
  - Per-image `_mask.png` masks, MCMC max_n_gaussians, PPISP.
  - Its gap is no depth loss.
- LichtFeld remains a good no-code backup, with caveats:
  - The Windows source build needs VS2022 exactly, CUDA 12.8, CMake 3.30+, Perl 5.42+ and a repository path with no spaces. The user's working directory 'C:\Users\Leonard Lind\...' contains one, so clone to e.g. C:\src\lfs.
  - --init accepts only splat files, so LiDAR initialization goes through COLMAP points3D or a 3DGS-format PLY.
  - Its depth loss input is undocumented.
  - Its equirect path needs an SfM tool that writes SPHERICAL cameras, because COLMAP has no equirect model.
  - Binary price: lichtfeld.io says $30 minimum, the README says 'donation of your choosing'.
- Brush is confirmed as the fully permissive prebuilt fallback (Apache-2.0; v0.3.0 Windows zip; units_per_meter since 2026-10-03) with no depth or appearance modules.
- Spirula is confirmed real and fast-moving (GPLv3; LiDAR scans support added 2026-10-06); keep it as a side-by-side test only.
- OpenSplat also sells a prebuilt Windows exe.

License recommendations: confirmed in full. Every Inria-derived repo checked (3DGS, 3DGS-MCMC, Mip-Splatting, 2DGS, RaDe-GS, the Taming base) is non-commercial, and PGSR forbids commercial use.

Closed-tool notes are fine except KIRI: only Mesh-Inclusive 3DGS is Pro, and exports are free and unwatermarked. It is still cloud-processed, so it remains excluded.

The training-time and VRAM numbers are unverified extrapolations from an A100 at data_factor 4. Budget a measured pilot run (e.g. 1M MCMC at 1600 px, 30k steps) before fixing splat budgets.
