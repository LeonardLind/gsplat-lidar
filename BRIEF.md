# Project brief (condensed from the user's messages, 2026-10-06)

Rule: research and produce a plan first; do NOT code until the user has reviewed it. User preferences are starting points — recommend better options with reasons.

## Goal
Pipeline + viewer to: (1) fly freely through a captured environment; (2) toggle LiDAR point cloud vs Gaussian splat; (3) show both at once, correctly aligned, real-world metric scale; (4) navigation boundaries (not below ground / through defined surfaces), probably via LiDAR ground detection.

## Capture
- Leica BLK2GO + recent Insta360 360 camera (model TBD — research newest models' video, gyro/IMU metadata, export formats). Captured simultaneously, held together; first test Insta360 taped just below the BLK2GO, later a rigid mount.
- Test: walk a ~10x10 m square in a Swedish forest (later: dense tropical forest, stress tests).
- Run 1: LiDAR + Insta360. Run 2: back at start, LiDAR stopped, same loop with Insta360 only, held higher at a different angle. Research whether this is good and advise better (passes, heights, angles, overlap, walking speed, lighting, exposure).
- Insta360 is video. Idea: reproject 360 video into 6+ virtual perspective cameras (Blender + FFmpeg). Research best way (FFmpeg v360, py360convert, cubemap/pinhole, tools with native equirect/fisheye input), frame rate / frame count / overlap, and masking of the operator and BLK2GO.

## Alignment (key requirement)
- SfM splat has arbitrary scale/frame; must register to LiDAR.
- Human measures the physical BLK2GO<->Insta360 offset (distance + orientation) as a prior; software independently estimates the transform (trajectory alignment, ICP of SfM sparse points vs LiDAR, etc.) and reports agreement; flag disagreement.
- Research most robust approach: trajectories, geometry, or both; how the closed loop helps drift/scale.
- Time sync: clap only in Insta360 audio; BLK2GO has no audio. Research alternatives (sharp motion in Insta360 IMU + BLK2GO trajectory/IMU, trajectory matching). Recommend simplest reliable method.

## Tech constraints
- Windows, everything local. (Brief said "RTX 3080 Ti 16 GB"; **corrected 2026-10-07: a desktop PC with Ryzen 7 7800X3D, 32 GB RAM, NVIDIA RTX 3080 10 GB VRAM**, driver 596.36, VS 2022 Community 17.14 / MSVC 14.44.)
- Python pipeline. Viewer open; user knows TypeScript/Vite; web (Three.js-based) welcome.
- LiDAR input: LAS exported from Leica Cyclone after cleanup (consider LAZ, E57). No proprietary Leica SDKs.
- Splat trainer: free, open-source, no watermark, no export limit. Compare nerfstudio/splatfacto, gsplat, original 3DGS, Brush, OpenSplat, and newer ones; SfM front end (COLMAP, GLOMAP...); 360-derived images; 16 GB; licenses; verify with current sources.
- Splat output: probably .splat — compare .ply and newer compressed formats; pick best for viewer.

## Deliverables (before code)
1. Research summary with sources; recommended stack, alternatives, trade-offs.
2. Architecture + step-by-step pipeline: capture -> frame extraction -> SfM -> splat training -> registration to LiDAR -> viewer.
3. Capture protocol/checklist for the 10x10 m test (sync method, how to measure device offset).
4. Risks/unknowns (foliage, moving branches, GPS-less drift, lighting, VRAM) and cheap tests for each.
5. Phased plan with milestones; phase 1 = smallest end-to-end test proving alignment. Clarifying questions at the end.

## Web delivery (final target)
- Result viewable in a web browser by other people. Luciad (Hexagon, e.g. LuciadRIA) is an option, not a hard dependency: research its support for splat formats, point clouds (LAS/LAZ, 3D Tiles), size limits, georeferencing, showing/toggling LiDAR + splat together.
- Plan from the start: best web splat formats/compression (.splat, .ply, newer compressed/streamable), size/quality trade-offs; realistic splat-count/file-size limits on laptops and phones and techniques (pruning, quantization, LoD, tiling/streaming); best web renderers (Luciad, Three.js-based, standalone), LiDAR + splat together, toggles, navigation boundaries in browser; how this changes training (target splat count).
- Include a "web delivery" phase with a minimal browser demo of the test scene.

## Addendum: input modes and drone capture
1. Selectable capture sources at program start, any combination: splat only (Insta360), LiDAR only (BLK2GO LAS), LiDAR + splat (main case, aligned), drone imagery (third source) alone or combined. Each source = separate optional module with a common interface; pipeline and viewer only enable relevant steps/toggles. Shared coordinate frame + metric scale (LiDAR when present, else georeferenced or arbitrary). Viewer layer toggles follow the selected sources. Suggest a clean UI flow for source selection, import, processing status (UI tech open).
2. Drone (research whether worth it): does aerial imagery meaningfully improve the splat vs Insta360-only (current results combining aerial + ground; problems: viewpoint/scale differences, appearance/lighting, SfM matching aerial<->ground)? Forest: how much ground/understory is visible through canopy (Swedish vs dense tropical)? Mostly canopy/terrain/surroundings? Better as a separate layer? Alignment (shared SfM, GPS/RTK metadata, registration to LiDAR, GCPs) and effect on the proposed alignment approach. Capture protocol (grid/orbit/oblique, altitude, overlap, stills vs video, settings, timing vs ground capture for matching light). Practical: drone class to look for, file sizes, GPU load on 16 GB, EU/Swedish regulations and permits for test flights. Compare and recommend: (a) LiDAR + Insta360 only, (b) + drone merged into one splat, (c) drone as separate aerial model alongside — cost, complexity, expected quality gain.
3. Plan updates: first test stays minimal LiDAR + Insta360; drone as later optional phase unless research says otherwise; list new risks/unknowns.
