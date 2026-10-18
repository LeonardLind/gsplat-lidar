# main critic

```json
{
 "gaps": [
  {
   "title": "BLK2GO trajectory export: content, time base, rate, orientation and reference point",
   "why_it_matters": "Most of the plan depends on this. Gyro cross-correlation sync, the joint Sim3 + lever arm + dt solve, hand-eye, the measured-vs-estimated offset report, motion-inflated pose priors and walk bounds all need a BLK2GO trajectory with timestamps, ideally with orientation at 10 Hz or more. Every topic (time-sync, registration, blk2go-cyclone, capture-strategy, sfm, forest-risks) marked it unverified. If the trajectory has only positions, or no usable time base, the primary sync method has to change to a position-based or time-free fallback. The reference point and body axes, which define what the tape-measured offset means, are also undocumented. The only BLK2GO pose source documented so far is the E57 WayPoint pose list, spaced by distance (at least 1 m), which cannot support gyro correlation.",
   "research_prompt": "Context: a pipeline that fuses Leica BLK2GO (original model, not the PULSE) handheld SLAM LiDAR with a 360 camera needs the BLK2GO SLAM trajectory for time sync (cross-correlating angular rate with a camera gyro) and for hand-eye calibration. Find, from primary or first-hand sources, the exact content of BLK2GO trajectory exports from: (a) the BLK Live app (v2.1.0 or later; 3.0.2 current) 'trajectory to .csv' export; (b) Cyclone FIELD 360 (5.0 or later; 7.1 current) CSV trajectory export; (c) Cyclone REGISTER 360 PLUS 2026.x E57 export with WayPoints (the 'Register360.exe -b2g2trajectory' CLI or the GUI 'Export BLK kinematic data to E57 with WayPoints and images'), where the trajectory is stored as a separate point cloud; (d) Cyclone 3DR trajectory objects imported from LGSx. For each, report: column or field names, units, time base (seconds since scan start, device clock, GPS/UTC epoch), sample rate in Hz, whether orientation is included (quaternion/Euler, component order, body-to-world or world-to-body), whether the data is raw SLAM output or smoothed/decimated, and the physical reference point and body axes the poses refer to (LiDAR centre, IMU, panoramic camera rig, handle). Also find out whether BLK2GO point exports carry non-zero per-point timestamps (E57 timeStamp, LAS gps_time) and on what clock relative to the trajectory. Search Leica RCDOCS (rcdocs.leica-geosystems.com and its llms.txt), the Leica/Hexagon community forums, Reddit (r/Surveying, r/LiDAR, r/photogrammetry), GitHub code that parses BLK2GO CSV or E57 trajectories (queries: 'BLK2GO trajectory csv', 'b2g2trajectory', 'BLK2GO timestamp quaternion', 'blk2go e57 trajectory'), the Immersal BLK2GO pipeline docs, and academic papers that used the BLK2GO trajectory as ground truth or for camera fusion. Quote sample header lines or field lists where found, with URLs and dates, and say plainly what is still unknown."
  },
  {
   "title": "Insta360 X5 vs X6 measured metadata and export behaviour (rolling shutter, IMU, HDR default, Studio stabilisation)",
   "why_it_matters": "These facts decide which camera to use and how frames are timed. The topics disagree on X5 rolling-shutter readout: about 21 ms (an insv-stitch model parameter, not a measurement) versus about 10.6 ms at 8K30 (GyroView PR #13). Neither the X6 IMU rate nor its readout has been read from a real file. The X6 manual says normal Video mode is 'HDR by default' and that Standard mode is 10-bit, so it is unclear whether the in-camera HDR can be turned off and whether it is temporally consistent, which matters for multi-view consistency. It is also contradictory whether 360 .insv streams or Studio equirect exports carry any baked-in rotation: one source says in-camera stabilisation 'cannot be disabled', another says 360 FlowState is 'not supported' in-camera, and horizon correction is on by default. Every equirect-path and extrinsic estimate assumes the frames stay body-fixed.",
   "research_prompt": "Context: an Insta360 X5 or X6 recording 8K 360 video is used for SfM/Gaussian splatting and must be rigidly calibrated against a handheld LiDAR, so frames must stay body-fixed and be timed to sub-frame accuracy. Using primary sources (the GyroView repo docs, ADRs, FORMAT.md and PRs at github.com/bubo-squared/GyroView; telemetry-parser master commits and issues at github.com/AdrianEddy/telemetry-parser; insv-stitch; the Insta360 online manuals at onlinemanual.insta360.com/x5 and /x6, including the zh-cn pages; ExifTool QuickTimeStream.pl; Gyroflow issues; r/Insta360 and r/GaussianSplatting threads), find: (1) the rolling-shutter readout time actually stored in or measured from .insv files for X5 and X6 at 8K30, 8K50 (X6) and 5.7K60, and the value of the info-protobuf rolling-shutter field; (2) the X6 IMU sample rate, timestamp units and gyro offset; (3) whether X6 'Video (HDR by default)' uses multi-frame or temporally varying tone mapping, whether it can be turned off, and which colour modes yield HLG/BT.2020 versus SDR tracks; (4) whether raw 360 .insv video tracks are ever rotated in-camera (horizon correction, FlowState), and whether Insta360 Studio's equirect export with FlowState, Direction Lock and horizon correction all OFF is exactly body-fixed and frame-for-frame identical to the .insv timeline (frame count, start time, 30 vs 29.97 fps); (5) whether Timelapse-mode .insv files keep audio, IMU and per-frame exposure records; (6) which open parsers currently decode X6 trailers (gyro, exposure records, offset_v6 calibration) and on which platforms. Give a per-model table with source URLs and dates, and flag anything still unverified."
  },
  {
   "title": "Measured browser splat performance and laptop training throughput (sets the training target)",
   "why_it_matters": "The user asked how web limits change the training target. Every budget in the digest is a vendor default or an extrapolation: Spark LoD defaults of 1M splats on Android, 1.5M on iOS and 2.5M on desktop; a PlayCanvas iPhone benchmark run at reduced resolution; gsplat VRAM figures from an A100 at data_factor 4. There are no measured fps numbers for Spark 2.x on mid-range Android, iPhones or integrated laptop GPUs at native or capped DPR, and no measured gsplat MCMC VRAM or time on a 16 GB laptop GPU at about 1600 px. These numbers decide the cap_max, the SH degree and whether to train a separate mobile model, and the topics disagree on all three.",
   "research_prompt": "Find measured (not vendor-default) performance data for browser Gaussian-splat rendering and consumer-GPU training, 2025–2026. (A) Browser rendering: frame rates for Spark 2.x (github.com/sparkjsdev/spark, three.js WebGL2, with LoD/paging on and off) and PlayCanvas/SuperSplat (WebGL2 vs WebGPU) at about 0.5M, 1M, 2M and 3M splats, SH0 vs SH1–SH3, on mid-range Android (Adreno 6xx/7xx, Mali-G7x), iPhones (A14–A18), and Intel Iris Xe / AMD Radeon integrated laptop GPUs, at native device pixel ratio and at DPR capped to 1–1.5. Include iOS Safari per-tab memory limits that affect splat scenes, and download sizes per million splats for SOG, SPZ v3 and Spark .rad at SH0/SH1/SH2. Search the Spark docs performance page, Spark GitHub issues and discussions, the PlayCanvas blog, the Babylon.js forum, r/GaussianSplatting and community benchmark repos. (B) Training: measured gsplat (1.5.x or main) MCMC peak VRAM and wall-clock time for 1–4M Gaussians and 30k steps at about 1600×1600 training images on 12–16 GB consumer or laptop GPUs (RTX 3080 Ti Laptop, 3090, 4080, 4070 Ti), with packed=True. Search gsplat GitHub issues and discussions and LichtFeld/Brush benchmarks. Present results as tables with device, settings, fps or VRAM, and source URL and date."
  },
  {
   "title": "Empirical evidence for handheld 360-camera SfM/3DGS under forest canopy, fused with handheld LiDAR",
   "why_it_matters": "The forest risk register is calibrated mostly on aerial forest-GS papers (TreeDGS is a UAV study) and on background knowledge. There are no under-canopy results for handheld 360 capture, no published registration accuracy between a camera reconstruction and handheld SLAM LiDAR in forest, and no BLK2GO forest drift figures (the 3.2–4.7 cm figure was refuted as a BLK2GO number). Real precedents would set realistic pass/fail thresholds for phase 1, show which SfM front-end and frame density work under canopy, and might offer a tested recipe for the later dense tropical work.",
   "research_prompt": "Find 2023–2026 papers, datasets, theses and practitioner reports on reconstructing forests or dense vegetation from handheld or pole-mounted 360 cameras (Insta360 X3/X4/X5/X6, DJI Osmo 360, Ricoh Theta, Kandao, Labpano), with SfM and/or Gaussian splatting / NeRF, ideally combined with handheld or backpack SLAM LiDAR (Leica BLK2GO, GeoSLAM ZEB Horizon/Revo, Emesent Hovermap, XGRIDS Lixel / PortalCam, FARO Orbis, Hesai/Livox rigs). For each, extract: camera model and capture settings, walking pattern, number of frames or views, SfM tool (COLMAP/GLOMAP/Metashape/RealityScan/OpenMVG) and its registration rate under canopy, how the camera reconstruction was registered to the LiDAR, the accuracy achieved (cloud-to-cloud, target residuals, DBH errors), splat quality metrics, and reported failure modes (wind, sky, low light, seam parallax, operator occlusion). Also find measured handheld SLAM LiDAR drift or loop-closure residuals in boreal and tropical forests, especially for the BLK2GO. Search arXiv, MDPI Forests/Remote Sensing, ISPRS archives, IEEE RA-L/ICRA, Google Scholar, the LichtFeld Studio and lichtfeld-360-plugin docs and examples, Spirula Studio, and the XGRIDS case studies, plus r/GaussianSplatting threads about forest captures. Summarise in a table and highlight any reusable open-source pipeline."
  },
  {
   "title": "Known-good Windows 11 toolchain matrix for the RTX 3080 Ti Laptop (COLMAP CUDA, ONNX EP, gsplat main, PPISP)",
   "why_it_matters": "Phase 1 needs every stage running locally on Windows, and the digest shows several version requirements that may clash. The official COLMAP 4.2.1 zip is built with CUDA 13.2 and needs driver 580 or newer. Its ONNX learned features need a separate CUDA 12 runtime and cuDNN 9, and otherwise fall back silently to the CPU. gsplat main (needed for PPISP, the correct masked loss and the 2026 kernels) has no Windows wheels and must be built with MSVC, CUDA 12.8 and torch 2.9.1. PPISP's Windows build is undocumented. LichtFeld needs VS2022 exactly and a repository path with no spaces, and the user's path contains one. Nobody verified whether the laptop's OEM driver branch supports R580/R595, or that these pieces can coexist.",
   "research_prompt": "Target: Windows 11, NVIDIA RTX 3080 Ti Laptop GPU (Ampere sm_86, 16 GB), October 2026. Find evidence for a working version matrix, citing GitHub issues, release notes and forum posts. (1) Do NVIDIA Studio or Game Ready driver branches R580 and R595 (required by CUDA 13.x, used by the official COLMAP 4.2.1 colmap-x64-windows-cuda.zip) support RTX 30-series laptop GPUs, and are there OEM laptop driver restrictions? (2) Does COLMAP 4.2.x's bundled onnxruntime-win-x64-gpu_cuda12 run ALIKED/LightGlue/LoMa on the GPU once a CUDA 12.x runtime and cuDNN 9 are on PATH next to the CUDA 13 build? Check issues such as colmap/colmap #4787. (3) Reports of building nerfstudio-project/gsplat main (v1.6.0 dev, 2026) from source on Windows: MSVC version, CUDA toolkit 12.8 vs 13.x, torch 2.9.x wheel, Python version, and known errors. (4) Building nv-tlabs/ppisp on Windows. (5) Status and compatibility of the lyehe/build_gpu_colmap Windows CUDA pycolmap wheels. (6) NVIDIA 3DGRUT install_env_uv.ps1 on laptop GPUs. (7) Any conflicts from running several CUDA toolkits side by side on one machine. Output a recommended known-good matrix (driver, CUDA toolkits, Python, torch, gsplat commit, COLMAP build) and list the unresolved risks, with sources."
  }
 ],
 "conflicts": [
  {
   "description": "Camera model choice. insta360 recommends the X6 if buying and the X5 if one is on hand. video-to-images and time-sync recommend the X5 because its tooling is the most verified. registration called the X6 'unverifiable' and said to plan around the X5. capture-strategy and video-to-images (citing DPReview and the X6 manual) confirm the X6 shipped on 2026-08-12.",
   "topics": [
    "insta360",
    "video-to-images",
    "time-sync",
    "registration",
    "capture-strategy",
    "forest-risks"
   ],
   "suggested_resolution": "The X6 exists, so drop registration's doubt. For the Swedish phase-1 pilot use an X5 if one is available: telemetry-parser master, GyroView (3 clips), insv-stitch and MediaSDK all support it. Treat the X6 as the upgrade for low light under canopy, once a Python trailer parser built from GyroView FORMAT.md (offset_v6, all 27 tokens) and a deterministic HLG-to-SDR conversion have been checked on a real X6 clip."
  },
  {
   "description": "Primary image path. insta360 and forest-risks R8 want the raw dual-fisheye tracks demuxed from the .insv, used as a 2-lens rig or as pinhole crops built from the factory Mei calibration. video-to-images and sfm want a Studio-stitched equirect export (FlowState, Direction Lock and Horizon OFF) fed to pycolmap.panorama-style 12/16-view virtual rigs with zero translation. splat-trainers says gsplat's stock loader undistorts fisheye to pinhole anyway.",
   "topics": [
    "insta360",
    "video-to-images",
    "sfm",
    "forest-risks",
    "splat-trainers"
   ],
   "suggested_resolution": "Phase 1, lowest engineering: stitched equirect with all stabilisation and horizon correction OFF, then pycolmap.panorama's render_perspective_images (forked to add user masks), then colmap.exe as a zero-translation rig. Phase 1b A/B test: raw fisheye tracks remapped to pinhole crops per lens with cv::omnidir and the factory calibration, declared as a 2-lens rig with the ~30 mm lens-to-lens translation. Compare reprojection error and LiDAR cloud-to-cloud on trunks under 3 m, where stitch parallax (~18 px) matters. Both paths give pinhole images, so every trainer works."
  },
  {
   "description": "Virtual views per frame and frame density. video-to-images recommends 16 views at 0.2–0.3 m spacing (3–6k images), but its own assessment says start with 12 views, ~0.4 m and ~100 panos per loop. sfm uses COLMAP's default 12 views at 1–2 fps or 0.25–0.5 m. insta360 cites 6–24 views. capture-strategy estimates 550–800 equirect frames, giving 1.5–4k crops.",
   "topics": [
    "video-to-images",
    "sfm",
    "insta360",
    "capture-strategy"
   ],
   "suggested_resolution": "Phase 1: COLMAP's 12-view layout (4 yaws × pitch -35/0/+35, 90°, 1920 px from 8K), the sharpest frame per 0.3–0.4 m of path, and segments where the operator stands still removed. That is roughly 100–200 panos per pass. Go to 16 views or 0.25 m only if registration gaps or splat holes appear. Keep the full frame rate only for the sync and calibration segments."
  },
  {
   "description": "X5 rolling-shutter readout: about 21 ms (insta360 and video-to-images, from insv-stitch; later corrected to an assumed model parameter) versus about 10.6 ms at 8K30 (time-sync, from GyroView PR #13).",
   "topics": [
    "insta360",
    "video-to-images",
    "time-sync"
   ],
   "suggested_resolution": "Read the rolling-shutter field from the info protobuf of the user's own clips and use that value. Until then, prefer GyroView's 10.6 ms (8K30) over the insv-stitch assumption, and size the rolling-shutter correction step from the measured value."
  },
  {
   "description": "Whether the camera's own output is body-fixed. The insta360 topic cites the X6 manual table saying in-camera 360 FlowState is 'not supported', so the raw .insv is never stabilised. video-to-images, citing the manual, says in-camera stabilisation 'cannot be manually disabled'. Horizon correction is on by default in 360 mode and in Studio exports.",
   "topics": [
    "insta360",
    "video-to-images",
    "registration",
    "sfm"
   ],
   "suggested_resolution": "Treat this as a day-0 test. Record a clip with deliberate tilts and compare the gyro-integrated rotation with the rotation of SfM frames, for both the raw .insv tracks and a Studio export with FlowState, Direction Lock, Horizon and tilt restoration all OFF. If any rotation is baked in, use the raw-fisheye path."
  },
  {
   "description": "Sync gesture design. time-sync wants sharp ±20–30° twists at 100–200°/s. capture-strategy wants ±45° at ~90°/s plus a 30 s pitch/roll dance, but its assessment says to drop sharp twists because Leica asks for smooth motion. The time-sync assessment says identical twists ~0.5 s apart create correlation side-lobes and calls for an aperiodic pattern. Separately, registration and capture-strategy say the pitch/roll dance is needed for the vertical lever arm, while capture-strategy's correction says geometry-based registration makes it observable anyway.",
   "topics": [
    "time-sync",
    "capture-strategy",
    "registration",
    "forest-risks"
   ],
   "suggested_resolution": "Use moderate (~60–100°/s), aperiodic twists with varied amplitudes and spacing, done after SLAM has initialised and the operator has walked a few metres, at both start and end. Add a gentle pitch/roll sequence as insurance for the trajectory-only extrinsic. Exclude these segments from SfM and training. In a backyard test, check that BLK2GO SLAM tolerates the gestures and that the start and end offsets agree."
  },
  {
   "description": "Role of LiDAR pose priors in SfM. forest-risks (tropical design-in) puts LiDAR-trajectory priors in from the start, with SfM only refining. sfm and registration want prior-free SfM followed by Sim3/ICP, so the extrinsic estimate stays independent, with priors as a fallback only (pose_prior_mapper, incremental only; the global mapper ignores priors).",
   "topics": [
    "forest-risks",
    "sfm",
    "registration"
   ],
   "suggested_resolution": "Phase 1: prior-free SfM (global mapper with refine_sensor_from_rig and intrinsics refinement explicitly OFF), then a geometry-based S as the reference for the independent offset check. Run a prior-based variant as a comparison and a fallback. For tropical scale-up, priors may become the default, but the independent check must then come from targets and geometry, not from the trajectory."
  },
  {
   "description": "Run 2 design. The user's plan is a camera-only Run 2, held higher. capture-strategy recommends keeping the BLK2GO scanning through every pass in one continuous 8–12 min scan. registration first proposed aligning separate models with pycolmap align_reconstructions_via_points, then refuted it (it needs shared images). sfm says joint SfM.",
   "topics": [
    "capture-strategy",
    "registration",
    "sfm",
    "forest-risks"
   ],
   "suggested_resolution": "If practical, keep the BLK2GO scanning during the higher pass as well (one scan, same start and end point). In every case, reconstruct Run 1 and Run 2 in ONE COLMAP database with cross-run vocab-tree or retrieval matching, or register Run 2 images into the Run 1 model. Test cross-run matchability on the first capture. Never rely on aligning two independent reconstructions."
  },
  {
   "description": "Whether BLK2GO posed images are available. capture-strategy says they are reachable only through proprietary .b2g files and the Immersal cloud, with no open export. blk2go-cyclone documents E57 export with WayPoint panoramas and rectified pinhole images with poses: the REGISTER 360 PLUS CLI b2g2trajectory, or the GUI since 2026-09, needing a WORKFLOW licence, 6 µm pixel size and version 2026.0.0 or later.",
   "topics": [
    "capture-strategy",
    "blk2go-cyclone",
    "time-sync"
   ],
   "suggested_resolution": "blk2go-cyclone is right per RCDOCS. The images are a usable time-free registration anchor if the user's Cyclone licence includes WORKFLOW. Enable Store Images, and check that the BLK Live 3.0 'Image security' setting is not disabling image creation. Read E57 per scan with pye57, not PDAL, which merges clouds. These images are sparse in time, so they are not a sync source."
  },
  {
   "description": "BLK2GO operating temperature and accuracy specs: +5 to +40 °C and 6–15 mm relative accuracy (capture-strategy and registration, from the 2019 sheet) versus 0 to +40 °C and ±10 mm indoor (blk2go-cyclone, from the May 2021 datasheet).",
   "topics": [
    "capture-strategy",
    "registration",
    "blk2go-cyclone"
   ],
   "suggested_resolution": "Cite the 2021 datasheet (0 °C minimum) but plan field sessions at 5 °C or warmer for battery and condensation margin. Measure the actual accuracy floor with the planned spheres, tags and per-side Sim3 test rather than relying on either sheet."
  },
  {
   "description": "Whether COLMAP has an equirect camera model. splat-trainers (missed developments) says it has none, citing colmap.github.io/cameras.html. insta360, video-to-images, sfm and capture-strategy cite the 4.1.0 release notes, which add an EQUIRECTANGULAR/spherical model.",
   "topics": [
    "splat-trainers",
    "sfm",
    "video-to-images",
    "insta360",
    "capture-strategy"
   ],
   "suggested_resolution": "COLMAP 4.1+ has the model; the cameras.html page is stale. This means LichtFeld's equirect loader could take COLMAP output, but check that the model names and IDs match. Keep the perspective-rig route as primary, since COLMAP itself says spherical is faster but less accurate."
  },
  {
   "description": "Training on fisheye/3DGUT vs pinhole. insta360 and forest-risks favour native fisheye with 3DGUT and rolling-shutter handling (gsplat, 3DGRUT, LichtFeld). splat-trainers and forest-risks' correction show that gsplat's stock COLMAP path undistorts to pinhole. video-to-images reports that many viewers render 3DGUT-trained splats incorrectly.",
   "topics": [
    "insta360",
    "forest-risks",
    "splat-trainers",
    "video-to-images",
    "web-delivery"
   ],
   "suggested_resolution": "Train the delivery splat with standard rasterisation on pinhole views. Treat 3DGUT/fisheye training (custom loader, or the NCore v4 or 3DGRUT paths) as a research branch, and check output from that branch in Spark before using it for delivery."
  },
  {
   "description": "Splat budget and how to build the mobile version. splat-trainers says train separate MCMC runs: 3–4M for desktop and 0.75–1.5M for phones. web-delivery says one 2–3M master with Spark LoD and phone lodSplatCount 0.5–1M at DPR 1–1.5. forest-risks R16 says 1–1.5M for phones and 3–5M for desktop.",
   "topics": [
    "splat-trainers",
    "web-delivery",
    "forest-risks"
   ],
   "suggested_resolution": "Train one MCMC master at 2–3M with SH3 and the LiDAR init count kept below cap_max. Deliver it as a Spark .rad with LoD at SH1–SH2, phone lodSplatCount ~0.75–1M, and DPR capped. In the web phase, A/B test against a dedicated 1M MCMC run and keep the dedicated run only if it looks clearly better on phones."
  },
  {
   "description": "Canonical delivery format and which bytes go to which viewer. web-delivery: Spark .rad primary with SOG fallback. splat-trainers: SOG plus LoD via splat-transform. luciad: 3D Tiles with KHR_gaussian_splatting + spz_2 as 'the same data for every viewer', with three.js reading it via the 3DTilesRendererJS plugin, which now uses gaussian-splat-lite rather than Spark. The SPZ version is also inconsistent: splat-transform and spz 3.0 default to v4 (ZSTD), which neither Spark 2.3.1 nor Luciad's bundled spz 2.0.0 reads.",
   "topics": [
    "web-delivery",
    "splat-trainers",
    "luciad",
    "blk2go-cyclone",
    "forest-risks"
   ],
   "suggested_resolution": "Keep one canonical SH3 PLY in the local metric ENU frame (LiDAR frame, recentred). Derive (a) a chunked Spark .rad for the main three.js viewer, (b) an SOG fallback, (c) any SPZ written as gzip v3 (--spz-version 3), and (d) for Luciad/Cesium only, 3D Tiles with single-node GLBs using spz_2 (gzip v3, LUF). 'Same data' means the same frame and source, not the same bytes. Keep the encoder stage replaceable, since spz_2 is still a draft."
  },
  {
   "description": "LiDAR web format: Potree 2.0 via potree-core or the 3DTilesRendererJS PotreePlugin (web-delivery) versus 3D Tiles PNTS as the shared format (luciad). Export routes also differ: web-delivery says export LAS/LAZ from Cyclone, while blk2go-cyclone and ground-navigation note that LAZ is not a REGISTER 360 export and LAS publishing may need PUBLISHER Pro.",
   "topics": [
    "web-delivery",
    "luciad",
    "blk2go-cyclone",
    "ground-navigation"
   ],
   "suggested_resolution": "Export E57 (per scan, pye57), convert to recentred LAZ in Python with laspy and lazrs, then build Potree 2.0 (no Brotli if PotreePlugin is used) for three.js and PNTS via py3dtiles for Luciad. Prototype potree-core and the 3DTilesRendererJS PotreePlugin side by side against three r180+ and Spark."
  },
  {
   "description": "Python and toolchain pinning. registration says pin Python 3.12 (CSF and telemetry-parser wheels stop at cp312). ground-navigation says csf-3dfin supports up to 3.13 and PDAL filters.csf avoids the issue. SciPy 1.18 requires 3.12 or newer. The gsplat 1.5.3 prebuilt Windows wheels are cp310 / pt24cu124 only. telemetry-parser must be built from master anyway, which removes its wheel limit. splat-trainers first proposed starting on the 1.5.3 wheel, then in its assessment said to go straight to gsplat main.",
   "topics": [
    "registration",
    "ground-navigation",
    "splat-trainers",
    "forest-risks",
    "time-sync"
   ],
   "suggested_resolution": "Use separate environments. (1) A conda-forge Python 3.12 pipeline env: PDAL, pycolmap CPU, Open3D, laspy, SciPy, a telemetry-parser maturin build, and gtsam 4.2.2 if needed. (2) A training env with a pinned gsplat main commit built from source (torch 2.9.1, CUDA 12.8). (3) COLMAP through the colmap.exe CUDA binaries, plus CUDA 12 and cuDNN 9 for ONNX. Clone any source builds to a path with no spaces."
  },
  {
   "description": "Capture parameters differ across topics. Shutter: insta360 1/500–1/1000, video-to-images 1/250–1/500, capture-strategy 1/500 with a 1/250 floor. Walking speed: video-to-images 0.5–0.7 m/s, capture-strategy 0.3–0.5 m/s, blk2go ≤1 m/s, forest-risks ~0.5 m/s, with the ≤1 m/s figure unsourced. Lens orientation: insta360 and capture-strategy say lenses left/right with the seam fore/aft, which contradicts Insta360's own tip to keep a lens facing the operator.",
   "topics": [
    "insta360",
    "video-to-images",
    "capture-strategy",
    "blk2go-cyclone",
    "forest-risks"
   ],
   "suggested_resolution": "Default to 1/500 s, fixed ISO and WB, and 0.4–0.5 m/s, then confirm with the cheap blur and speed test (forest-risks R7). Seam orientation matters only on the stitched path: if the raw-fisheye path is chosen, keep lenses left/right; otherwise either orientation works, since the operator is masked."
  }
 ],
 "overall_notes": "Coverage is broad and mostly consistent once each topic's own corrections are applied. Several topics corrected themselves in the fact-check pass: telemetry-parser PyPI dates from 2024, align_reconstructions needs shared images, Luciad is now Octave Alto (WebGPU-only), there is no SPZ v4 in Spark or Luciad, and BLK Data Manager does not export a CSV trajectory. The planner should use the corrected versions, not the original summaries.\n\nThe biggest structural risk is that the shared WebSearch budget ran out early in almost every topic. Verification was done by fetching known primary URLs, so discovery-type questions are the weakest areas: undocumented vendor formats, measured performance, and field evidence from forests. Those are the five gaps.\n\nSeveral load-bearing items are better settled by day-0 audits on the user's own data than by more web research. The phased plan should put these first:\n(1) Export a short BLK2GO walk through BLK Live/FIELD 360 CSV, REGISTER 360 PLUS E57 (b2g2trajectory) and LAS. Dump the headers and fields and check them with laspy and pye57.\n(2) Run ffprobe and a trailer parse on a short .insv to get frame rate (30 vs 29.97), rolling-shutter field, IMU rate, exposure records, colour transfer (HLG on X6), and whether any rotation is baked into raw or Studio exports.\n(3) Build the Windows toolchain (COLMAP CUDA plus ONNX EP check, gsplat main) and record peak VRAM in a 3k-step sweep.\n(4) A minimal Spark page benchmark on the user's phone and laptop.\n\nQuestions that only the user or their organisation can answer:\n- Which Cyclone licences they hold: WORKFLOW (E57 with WayPoints and images) and PUBLISHER Pro (LAS).\n- Whether Luciad/Octave Alto licence access survived the Hexagon spin-off, and which tier includes splats and public deployment.\n- Hexagon legal's position on research-only licences (Inria NC allows industrial research and evaluation; CC BY-NC-SA unclear) and on the SAM 3 licence. SAM 2.1 under Apache-2.0 is the clean default.\n- Which Insta360 model they own or will buy.\n- The laptop's NVIDIA driver branch.\n\nMinor items with no conflict:\n- No maintained open tool yet writes LoD-tiled 3D Tiles splats with spz_2 v3. The converter repo returns 404. splat-transform's GLB in a one-tile tileset is the fallback for Luciad. This only affects the optional Luciad path.\n- The user's working directory path contains a space, which breaks the LichtFeld source build.\n- Matrix-order conventions (Luciad row-major vs 3D Tiles column-major), COLMAP cam_from_world, LAS Z-up vs three.js Y-up, and float32 recentring should be covered by one frame-convention test with an asymmetric marker, run early."
}
```
