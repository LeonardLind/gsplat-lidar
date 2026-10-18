# modular-architecture

## Summary

Proposed architecture for a single-developer local app on Windows 11 with an RTX 3080 Ti (16 GB): a Python backend that plans and runs the processing pipeline, a Vite/TypeScript web UI, and one Three.js viewer package. The same viewer serves both the local preview and the public static export.

1) SOURCE MODULES. Each capture source is a plugin with a small interface:
- probe() runs a fast validation and returns a metadata report plus refined capabilities.
- stages() declares the source's part of the pipeline graph, with typed inputs and outputs, a parameter model, resource needs (GPU yes/no, estimated VRAM) and whether the stage can resume.
- layers() lists what the source contributes to the viewer.

Capabilities are explicit fields:
- metric_scale: exact / approx / none
- georef: none / gnss / rtk / gcp, with its accuracy
- gravity_aligned
- imagery_for_splat
- geometry
- time_base

For the current sources:
- BLK2GO LAS: exact metric scale, gravity-aligned, no georeference.
- Insta360 video: imagery only. No scale, no georeference.
- Drone images: approximate scale and georeference from GNSS. Accuracy depends on RTK status read from the DJI XMP tags. Barometric altitude is unreliable.

This mirrors established tools:
- nerfstudio DataParsers turn any dataset into one common output (image filenames, cameras, dataparser_transform, dataparser_scale) and are registered through Python entry points.
- ODM runs a fixed list of named stages (dataset ... odm_postprocess) and supports rerun / rerun-from.
- Meshroom gives every node a hash of its output-affecting attributes and caches results in MeshroomCache/<NodeType>/<uid>.

Work that combines sources lives in project-level stages, not inside the modules:
- reconstruction groups: one SfM run per group of imagery sources
- registration
- splat training per group
- export

The reconstruction group is what makes drone options (b) and (c) a configuration choice rather than a code fork:
- (b) = Insta360 and drone in one SfM/splat group.
- (c) = separate groups that produce separate layers.
So the drone decision can be postponed and tested empirically.

2) FRAMES. A frame graph with Sim(3) edges (s, R, t as 4x4 doubles), each carrying:
- an optional 7x7 tangent-space covariance and scalar quality metrics (RMSE, inlier fraction, correspondence count)
- provenance: method, parameters, input hashes, tool versions, time, and a user-accepted flag
- a status: prior / estimated / manual / verified

Rules for picking the project (anchor) frame automatically:
- LiDAR present: use the LiDAR frame, re-centred to a local origin with the offset stored.
- Otherwise, a drone with GNSS: use a local ENU tangent frame at a chosen latitude/longitude/height origin. This is the OpenSfM reference_lla pattern.
- Otherwise: the SfM frame of the first imagery group, with gravity from COLMAP orientation alignment. Scale is marked arbitrary until the user enters a known distance.

A separate double-precision project-to-world transform (ECEF plus EPSG metadata, e.g. SWEREF 99 TM EPSG:3006 + RH 2000 EPSG:5613) exists only when a connected source provides a georeference. The LiDAR scale is never changed by the drone GNSS. A drone-to-LiDAR scale that differs from 1 is reported as a QA signal.

Never store or render real-world coordinates in float32. At Swedish northings around 6.5e6 m the float32 step is 0.5 m. 3D Tiles solves the same problem with relative-to-centre storage and root transforms.

Consistency check: where two paths exist between frames (e.g. Insta360→LiDAR directly versus Insta360→drone→LiDAR), report the discrepancy.

Implementation:
- Hand-rolled frame graph of about 100 lines; pytransform3d's TransformManager is an optional reference.
- pycolmap Sim3d, align_reconstructions_via_points and Reconstruction.transform for the SfM-side operations.
- COLMAP model_aligner (ENU/ECEF, needs at least 3 images with known positions) for GNSS georeferencing.

3) CRITICAL SPLAT-FRAME FINDING. gsplat's simple_trainer defaults to normalize_world_space=True. Its parser applies a similarity transform plus a principal-axes rotation (and possibly a 180° flip), stores it as parser.transform, and exports the PLY in that normalized frame without inverting it. Undoing this afterwards means rotating the SH coefficients as well. Recommendation:
- Register the sparse SfM to the LiDAR first. This is cheap and can be repeated.
- Apply the Sim(3) to the COLMAP model.
- Train in the project frame with normalization off, or invert the transform with proper SH rotation.
- Apply only small later corrections as viewer node transforms.

Spark's SplatMesh supports position/quaternion transforms but only uniform scale. Whether SH is evaluated correctly under object rotation is not documented and must be tested.

4) PROJECT FILES AND CACHING. Pydantic v2 models, saved as JSON:
- project.json: user intent, i.e. sources, parameters, groups, anchor policy.
- frames.json: the transform graph.
- state/<stage>.json: status, PID, input fingerprint, output hashes.
- export/scene.json: the viewer manifest, generated from the rest.

The JSON Schema is exported to TypeScript types for the UI and viewer. Writes are atomic (temp file + os.replace).

Stage cache key = hash of:
- stage id and implementation version
- canonical parameters
- input artefact content IDs
- external tool versions

Outputs live in cache/<stage>/<key>/ (Meshroom style). The stage record works like DVC's dvc.lock. Large raw inputs (multi-GB LAS or video) stay where they are and are fingerprinted with size, mtime and BLAKE3.

Proportionate tooling is a hand-rolled DAG of a few hundred lines. The alternatives fit worse:
- doit is the closest off-the-shelf fit (file_dep, config_changed, works on Windows).
- Snakemake runs on Windows only through WSL.
- Dagster and Prefect bring a server/UI and are overkill.
- Hamilton caches in-process Python objects (pickle), not subprocess GPU jobs producing gigabytes of files.
- Luigi checks whether target files exist, with no content hashing.

5) BACKEND AND UI. Option (a): FastAPI + uvicorn on localhost, serving the built Vite app and the project files. Range requests work from Starlette 0.39. Native SSE exists from FastAPI 0.135, with Last-Event-ID resume and a 15 s keep-alive. Commands go over REST.

Each stage runs as its own Python or native subprocess:
- Started with subprocess.Popen in a worker thread, not asyncio subprocesses. uvicorn --reload or workers>1 on Windows switches to the Selector event loop, which raises NotImplementedError for subprocesses.
- Placed in a Windows Job Object with KILL_ON_JOB_CLOSE plus CREATE_NEW_PROCESS_GROUP, so cancelling kills the whole process tree.
- Writes events.jsonl for progress and metrics, plus a log. stdout is parsed only as a fallback (COLMAP "Processed file [i/n]", "Matching block", gsplat tqdm).
- A process per stage also frees VRAM reliably. PyTorch's caching allocator keeps memory, and empty_cache() cannot free memory held by live tensors.
- One GPU job at a time.
- On startup, records still marked RUNNING whose PID is dead become INTERRUPTED, with resume offered for stages that checkpoint. Meshroom has the same stale-RUNNING problem.

Option (b): pywebview (WebView2) can wrap the same UI later to get native file dialogs. Browsers cannot hand over absolute paths, and uploading gigabytes to localhost is wasteful. Tauri/Electron add a Rust/Node layer and sidecar packaging with no benefit here.

Option (c) loses on reuse:
- Gradio, Streamlit and NiceGUI cannot reuse the TypeScript viewer. NiceGUI also has the Windows asyncio subprocess issue.
- PySide6 cannot reuse it either.
- viser (Apache-2.0) is still worth using as a developer tool for checking registration, thanks to its transform gizmos.

Packaging:
- A pixi workspace with a lockfile: conda-forge for PDAL/GDAL/PROJ (PDAL's PyPI bindings need a separate libpdal), PyTorch CUDA from conda-forge or the PyTorch index.
- External binaries pinned with version probes: COLMAP CUDA build (pycolmap Windows wheels are CPU-only), ODM native if used.
- No PyInstaller.
- Avoid spaces in paths. The user profile "C:\Users\Leonard Lind" has one, and both ODM and torch cpp_extension JIT builds have failed on spaces. Set TORCH_EXTENSIONS_DIR and use a short project root.

6) VIEWER. scene.json lists layers:
- id, kind (pointcloud, splat, mesh, ortho/dsm, ground/navmesh), source, format and URI
- a 4x4 transform to the project frame, bounds, LoD information
- toggle group and default visibility

It also holds presets (LiDAR / Splat / Combined / Aerial), each shown only when all the layers it needs exist, the project-to-world block, and navigation (ground, start pose).

The static export is the viewer dist folder plus export/ copied as-is. For 3D Tiles:
- Each layer becomes its own tileset.
- A root tileset references them, with root.transform = project→ECEF.
- Point clouds via py3dtiles; splats as glTF with KHR_gaussian_splatting (ratified Sept 2026) plus spz_2 compression.
- LuciadRIA 2026.1 reads these. In Three.js they load through 3DTilesRendererJS plus a 3DGS plugin.
- A project with no georeference has to be placed at a pseudo-georeference, flagged as such.

## Recommendations

- **Architecture: (1) a Python backend package 'core' (Pydantic models, source registry, DAG planner, stage runner, frame graph, cache); (2) 'stages/' as standalone CLI entry points (python -m app.stages.<name> --record <state.json>), each writing events.jsonl and a log; (3) FastAPI ≥0.135 on 127.0.0.1 serving REST commands, an SSE event stream, the built UI and project files with Range support; (4) a Vite/TS monorepo with packages/viewer (Three.js + Spark 2 + point-cloud loader, driven only by scene.json), packages/app-ui (wizard, status, logs, embeds the viewer) and packages/schema (TS types generated from the Pydantic JSON Schema); (5) export = viewer dist + export/ folder, plus an optional 3D Tiles bundle.** — One viewer codebase serves the local preview, the public web and the Luciad/Cesium paths. Running stages as subprocesses gives cancellation, VRAM release and crash isolation on Windows. Everything fits a single developer's TypeScript and Python skills. _Alternatives:_ Tauri/Electron shell: extra layer, no gain. PySide6/NiceGUI/Gradio/Streamlit: cannot reuse the web viewer. Add pywebview later only for native dialogs and an app window.
- **Source module interface (Python Protocol): kind, version, capabilities {metric_scale: exact|approx|none, georef: none|gnss|rtk|gcp with sigma_m, gravity_aligned, imagery_for_splat, geometry, time_base}; probe(inputs) -> ProbeReport (metadata, warnings, refined capabilities); stages(cfg) -> list[StageSpec{id, inputs: typed artefact ports, outputs, params model, resources{gpu, vram_gb_est}, resumable}]; layers(artefacts) -> list[LayerSpec]. Artefact types: PointCloud, GroundModel, ImageSet (frames, masks, intrinsics prior, timestamps), SfMModel (COLMAP), Splat, Mesh, Ortho/DSM, TransformEdge. Project-level stages (not owned by modules): ReconstructionGroup SfM, Register, TrainSplat (per group), BuildNav, Export.** — Mirrors nerfstudio DataParser normalization and ODM's stage list. Reconstruction groups turn drone options (b) merged and (c) separate into a config switch, so the drone decision can be made from data later. The UI enables only the steps and toggles the declared capabilities allow. _Alternatives:_ Per-combination hard-coded pipelines: simpler for the first test, but the number of combinations explodes once the drone source arrives.
- **Anchor-frame policy and frame graph: project frame = re-centred LiDAR frame if LiDAR present; else ENU at the drone GNSS origin (lat/lon/h stored as in OpenSfM reference_lla) if drone present; else the SfM frame with gravity-up and scale 'arbitrary' until the user enters a known distance. Store every source→project edge as Sim(3) (4x4 float64 + s,R,t) with {method, status: prior|estimated|manual|verified, rmse, inlier_ratio, n_corr, optional 7x7 covariance, input hashes, tool versions, accepted_by_user}. Keep project→world (ECEF 4x4 float64 + EPSG:3006/5613 metadata) separate, and fill it only when a connected source is georeferenced. Never let drone GNSS rescale LiDAR; report the drone↔LiDAR scale deviation as QA. Check cycle consistency when several paths exist.** — Keeps all GPU buffers in small local coordinates (float32 step ≈0.5 m at Swedish northings otherwise). Makes georeferencing optional and auditable. The user-measured device offset becomes a 'prior' edge that the software estimate checks. _Alternatives:_ pytransform3d TransformManager for graph path-finding (BSD-3; Sim(3) support unverified); ROS tf2-style tree (no uncertainty).
- **Splat-frame handling: register the COLMAP sparse model to LiDAR before training (pycolmap align/Sim3d + ICP refine), apply the Sim(3) to the COLMAP model, then train with gsplat normalize_world_space=False, or invert parser.transform including SH rotation. Apply only small post-training corrections as viewer node transforms. Add an automated check that compares the exported splat-means bbox with the sparse-points bbox in the project frame.** — gsplat exports in a normalized, rotated frame by default, and undoing a rotation requires rotating SH. Spark supports only uniform scale and does not document SH correctness under rotation. For a 10x10 m test, re-training after a registration change is acceptable. _Alternatives:_ Train in the SfM frame and bake the transform at export with an SH-rotation utility (implement Wigner-D rotation, or verify that splat-transform rotates SH).
- **Project files and cache: project.json (intent), frames.json (transform graph), state/<stage>.json (status, PID, heartbeat, cache_key, outputs), export/scene.json (generated), all Pydantic v2 with schema_version and atomic writes (temp + os.replace). Stage cache key = BLAKE3(stage id + impl version + canonical params JSON + input artefact IDs + external tool version strings). Outputs go to cache/<stage>/<key16>/. Raw inputs are referenced in place and fingerprinted by size + mtime_ns + BLAKE3 (fast partial hash at import, full hash in the background). Provide 'rerun from stage' and 'force' like ODM.** — Content-addressed and proportionate. Changing registration or export parameters does not redo SfM, and the cache records double as provenance. Avoids the heavy orchestration frameworks. _Alternatives:_ doit (file_dep + config_changed) as the engine under the same records; DVC only if the user wants git-tracked data lineage.
- **Runner on Windows: one GPU queue (one GPU job at a time on 16 GB) plus a CPU pool. Start subprocess.Popen in threads with CREATE_NEW_PROCESS_GROUP and attach each child to a Job Object with KILL_ON_JOB_CLOSE. Cancel = CTRL_BREAK, then job terminate. Never run uvicorn with --reload or workers>1 for the job host. Progress comes from stage-emitted JSONL (step, total, loss, n_gaussians, vram); stdout regex parsing (COLMAP 'Processed file [i/n]', 'Matching block [a/b, c/d]', mapper registration lines, tqdm) is the fallback. Poll GPU memory via NVML. On restart, mark stale RUNNING records INTERRUPTED and offer resume from checkpoints.** — Avoids the SelectorEventLoop NotImplementedError, process-tree leaks and VRAM held by PyTorch's caching allocator. Avoids the stale-RUNNING lockups Meshroom users hit. _Alternatives:_ Wrap ODM through NodeODM's REST semantics for the drone-only aerial model.
- **UI flow: Home (new/open) → Sources (checkboxes for LiDAR / 360 video / drone images, with a live 'you will get' panel derived from capabilities: layers, anchor frame, scale and georef status) → Import (per-source path pickers through a backend file browser or a native dialog; probe reports with warnings) → Alignment setup (shown only with ≥2 sources: proposed anchor with override, device offset and time-offset priors, optional GCPs, imagery grouping joint vs separate) → Process (graph view of stages, status chips, progress/ETA, live logs over SSE, GPU memory, cancel/rerun-from, QA panels: SfM stats, registration residual heatmap) → View & Export (embedded viewer with toggles from scene.json; export web bundle / 3D Tiles).** — Each step appears only when the selected sources need it. Suits single-user desktop use and matches the user's request for a clean selection → import → status flow. _Alternatives:_ A single-page dashboard without a wizard, once the user is familiar with the tool.
- **Viewer manifest scene.json: {schema_version, project_frame{up:'+Z', units:'m', origin_note}, world?{ecef_from_project 4x4 f64, epsg_h:3006, epsg_v:5613, pseudo:boolean}, layers[{id, kind: pointcloud|splat|mesh|ortho|dsm|ground|navmesh, source, group: 'lidar'|'ground_splat'|'aerial', format: copc|potree2|3dtiles|spz|sog|rad|glb, uri, transform 4x4 (project_from_layer, column-major), bounds, lod, default_visible}], presets[{id:'lidar'|'splat'|'combined'|'aerial', layers:[...]}] (shown only if all their layers exist), navigation{ground_uri, walkable_polygon?, start_pose, mode: walk|orbit}}. For 3D Tiles, write one tileset per layer plus a root tileset.json whose root.transform = ecef_from_project. Splats as glTF with KHR_gaussian_splatting + spz_2; point clouds via py3dtiles.** — Toggles follow the selected sources automatically. The same manifest drives the local preview and the public export, and converts directly to the 3D Tiles that LuciadRIA 2026.1 and Cesium accept. _Alternatives:_ Use a glTF scene graph as the manifest. Less readable, and point-cloud LoD formats do not fit inside glTF.
- **Environment: a pixi workspace with a lockfile (conda-forge pdal/python-pdal, gdal, pyproj, laspy; PyTorch CUDA 12.8; gsplat prebuilt wheel), plus tools.toml pinning external binaries (COLMAP CUDA Windows build, optional ODM) with a version probe and checksum. Data and project root without spaces (e.g. C:\gsl\projects). For subprocesses set TORCH_EXTENSIONS_DIR and TEMP/TMP to paths without spaces; consider a Windows Defender exclusion for the project root.** — pycolmap's Windows wheels are CPU-only. PDAL's PyPI bindings need libpdal. The user's profile path contains a space, which has broken ODM and torch JIT builds. CUDA 13.2+ breaks Windows JIT extensions. _Alternatives:_ uv with the PyTorch cu128 index plus laspy instead of PDAL; implement ground detection with CSF/SMRF from another library.
- **Scope for the first test (LiDAR + Insta360): build only the LiDAR-LAS and Insta360-video modules, one reconstruction group, registration with a device-offset prior plus ICP check, gsplat training in the project frame, scene.json with the LiDAR/splat/combined presets, and static export. Keep the drone module as a stub with capability declarations and a probe() for DJI EXIF/XMP so the anchor and frame logic is exercised early. Defer ODM, 3D Tiles and the pywebview wrapper.** — Proves the riskiest parts first: frames, registration and splat-frame correctness. The interface stays ready for drone options (b) and (c) without building them now. _Alternatives:_ Build drone support earlier only if the drone research finds aerial imagery essential for the forest splat.

## Load-bearing findings (claim + sources)

- [high] Model the pipeline on ODM's named stages with rerun-from, but key each stage's cache on content (Meshroom/DVC style) rather than on whether output files exist. — https://docs.opendronemap.org/arguments/rerun-from/ https://raw.githubusercontent.com/OpenDroneMap/ODM/master/opendm/types.py https://meshroom-manual.readthedocs.io/en/latest/feature-documentation/core/nodes.html
- [high] gsplat's simple_trainer exports splats in a normalized frame, not the input COLMAP frame. The registration/export pipeline must account for this. — https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/examples/simple_trainer.py https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/examples/datasets/colmap.py
- [medium] Viewer-time transforms for splats are limited: Spark SplatMesh supports position/quaternion but only uniform scale, and does not document whether SH is evaluated correctly in a rotated object space. — https://sparkjs.dev/docs/splat-mesh/ https://github.com/playcanvas/splat-transform
- [high] Real-world coordinates must never reach float32 buffers. The project frame has to be local, with a double-precision offset or ECEF transform kept separately. — https://github.com/CesiumGS/3d-tiles/tree/main/specification/TileFormats/Batched3DModel https://reearth.engineering/posts/high-precision-rendering-en/ https://opensfm.readthedocs.io/en/latest/geometry.html
- [high] COLMAP and pycolmap already provide the georeferencing and Sim(3) primitives the registration and anchor logic needs. — https://colmap.github.io/faq.html https://colmap.github.io/pycolmap/pycolmap.html https://colmap.github.io/database.html
- [medium] pycolmap's Windows wheels are CPU-only. GPU SIFT on Windows needs the COLMAP CUDA executable run as a subprocess; pycolmap stays useful for model I/O and alignment. — https://colmap.github.io/pycolmap/index.html https://github.com/colmap/colmap/releases
- [high] On Windows, run GPU stages as separate subprocesses started with Popen in worker threads, not asyncio subprocesses inside uvicorn. — https://github.com/Kludex/uvicorn/discussions/2346 https://github.com/zauberzeug/nicegui/issues/486 https://learn.microsoft.com/nl-nl/windows/win32/procthread/job-objects
- [high] FastAPI now has native SSE and Starlette serves HTTP Range requests, so a plain FastAPI app can stream status events and serve streaming 3D formats to the same viewer used in the public export. — https://fastapi.tiangolo.com/tutorial/server-sent-events/ https://fastapi.tiangolo.com/reference/sse/ https://raw.githubusercontent.com/encode/starlette/master/docs/release-notes.md
- [high] The user's Windows profile path contains a space ('C:\Users\Leonard Lind'), and the current project path contains a space and a '+'. Both are known to break parts of this toolchain. — https://github.com/pytorch/pytorch/issues/38781 https://github.com/pytorch/pytorch/issues/122476 https://github.com/pytorch/pytorch/issues/197574
- [medium] The drone module's georeference capability must carry an accuracy class taken from metadata. Its altitude is not trustworthy without RTK or GCPs. — https://exiftool.org/TagNames/DJI.html https://photogrammetrycommunity.github.io/metashape-expert-manual/workflow/project-setup/dji-drone-metadata/

## Key numbers

- float32 spacing at a SWEREF 99 TM northing of ~6.5e6 m (and ECEF ~3–6e6 m): 0.5 m (0.25–0.5 m); own computation (computed (2^22 ≤ 6.5e6 < 2^23 → ulp 2^-1))
- FastAPI version with native SSE (fastapi.sse): 0.135.0; automatic keep-alive every 15 s (https://fastapi.tiangolo.com/tutorial/server-sent-events/)
- Starlette version adding HTTP Range to FileResponse: 0.39.0 (2024-09-23) (https://raw.githubusercontent.com/encode/starlette/master/docs/release-notes.md)
- Minimum images with known positions for COLMAP model_aligner: 3 (https://colmap.github.io/faq.html)
- NodeODM task status codes: 10 QUEUED, 20 RUNNING, 30 FAILED, 40 COMPLETED, 50 CANCELED; progress 0–100 (https://github.com/OpenDroneMap/NodeODM/blob/master/docs/index.adoc)
- Spark 2.0 LoD splat budget per frame / RAD chunk size: 500K–2.5M default (platform); 64K splats per chunk; released 2026-04-15 (https://www.worldlabs.ai/blog/spark-2.0)
- KHR_gaussian_splatting status: Ratified (README); 2026-09-03 per third-party issue; RC Feb 2026 (https://github.com/KhronosGroup/glTF/blob/main/extensions/2.0/Khronos/KHR_gaussian_splatting/README.md)
- LuciadRIA version with Gaussian splats: 2026.1 (3D Tiles + KHR_gaussian_splatting / _compression_spz_2) (https://dev.luciad.com/portal/productDocumentation/LuciadRIA/docs/releasenotes.html?component=LuciadRIA.LuciadRIA)
- py3dtiles latest: v12.1.1 (2026-03-20), Apache-2.0 (https://py3dtiles.org/main/index.html)
- COLMAP current release / dev: 4.2.1 (Sep 29, year inferred 2026); docs built from 4.3.0.dev0 on 2026-10-01 (https://github.com/colmap/colmap/releases)
- LichtFeld Studio requirements: compute capability ≥7.5, driver ≥570 (CUDA 12.8+); latest v0.5.3 (https://github.com/MrNeRF/LichtFeld-Studio)
- gsplat PyTorch requirement: PyTorch 2.7+ (https://github.com/nerfstudio-project/gsplat)
- Brush web build browser requirement: Chrome 134+ (Windows/macOS) (https://github.com/ArthurBrussee/brush)
- SWEN17_RH2000 geoid standard uncertainty: 8–10 mm (https://www.lantmateriet.se/sv/geodata/gps-geodesi-och-swepos/Referenssystem/Geoiden/Svenska-geoidmodeller/)
- DJI non-RTK barometric altitude error without GCPs: 5–50 m systematic; RTK per-image sigma typically 0.01–0.05 m horizontal (https://photogrammetrycommunity.github.io/metashape-expert-manual/workflow/project-setup/dji-drone-metadata/)
- ODM GCP recommendation: ≥5 GCPs × 3 images each (≥15 rows) (https://docs.opendronemap.org/gcp/)

## Tools & licenses

- FastAPI (+ uvicorn, Starlette) | FastAPI ≥0.135 (native SSE); Starlette ≥0.39 (Range) | MIT | win: yes; avoid --reload/workers>1 for subprocess spawning | Recommended backend
- COLMAP (CUDA binary) / pycolmap | 4.2.1 (2026, inferred); pycolmap 4.3.0.dev | BSD-3-Clause | win: COLMAP CUDA builds on Windows; pycolmap Windows wheels CPU-only | Sim3d, align_reconstructions_*, model_aligner, spherical camera model (4.1)
- gsplat | requires PyTorch 2.7+ | Apache-2.0 | win: prebuilt wheels for some torch/CUDA combos; JIT needs MSVC, breaks on paths with spaces | normalize_world_space=True by default; PLY exported in normalized frame
- Brush | 2026 | Apache-2.0 | win: yes (native, no CUDA); web Chrome 134+ | COLMAP/nerfstudio input
- LichtFeld Studio | v0.5.3 (2026, inferred) | GPL-3.0 | win: yes; binary distribution unclear (README says Portal, GitHub lists assets) | Python plugins; PLY/SOG/SPZ/HTML export
- Spark (sparkjs) | 2.0 (2026-04-15) | MIT (background knowledge) | win: browser | Three.js splat renderer, LoD/.RAD, uniform scale only
- viser | 2026 | Apache-2.0 | win: yes | Developer/QA registration tool; transform gizmos; splats
- pywebview | 6.x | BSD-3-Clause (background knowledge) | win: EdgeChromium/WebView2 | Optional desktop wrapper for native dialogs
- Tauri v2 | v2 | MIT/Apache-2.0 | win: yes (WebView2) | Not recommended; sidecar packaging of Python+CUDA is awkward
- pixi | 2026 | BSD-3-Clause (background knowledge) | win: yes | conda-forge + PyPI with lockfile; recommended env manager
- uv | 2026 | MIT/Apache-2.0 | win: yes; CUDA torch via explicit index | Alternative if PDAL is not needed
- PDAL + python-pdal | python-pdal 3.5.5 (conda-forge) | BSD | win: via conda-forge; PyPI wheels need libpdal | Declarative JSON pipelines; ground filters
- OpenDroneMap ODM / NodeODM / pyodm | docs 3.6.0 | AGPL-3.0 | win: native installer; breaks on paths with spaces | Optional engine for the drone aerial model (ortho/DSM/mesh/3D Tiles)
- Meshroom/AliceVision | n/a | MPL-2.0 | win: yes | Design reference only (UID-hashed node cache)
- doit | n/a | MIT | win: yes | Best off-the-shelf DAG fallback
- Snakemake | 9.27.0 docs | MIT | win: WSL only per docs | Not recommended
- Dagster | Python ≥3.10 | Apache-2.0 | win: yes | Overkill (webserver/UI)
- Prefect 3 | 3.x | Apache-2.0 | win: yes | Input/source-hash caching; heavy for this use
- Apache Hamilton | 2026 | Apache-2.0 (incubating) | win: yes | In-process dataflow; not suited to GPU subprocess stages
- blake3-py | n/a | CC0/Apache-2.0 (background knowledge) | win: PyPI wheels | Multithreaded, update_mmap for large-file fingerprints
- py3dtiles | 12.1.1 (2026-03-20) | Apache-2.0 | win: not stated | LAS/XYZ → 3D Tiles pnts
- PlayCanvas splat-transform | 2026 | MIT | win: Node CLI | Format conversion, GLB KHR_gaussian_splatting, LOD chunks; SH rotation unverified
- 3D-Tiles-RendererJS-3DGS-Plugin | 2026 | Apache-2.0 | win: browser | Splat 3D Tiles in Three.js; spz_2 only
- LuciadRIA | 2026.1 | Commercial (Hexagon) | win: browser | Consumes splat 3D Tiles with KHR_gaussian_splatting(+spz_2)

## risks

- gsplat exports in a normalized and rotated frame by default. If this is missed, the splat and the LiDAR will be misaligned by an arbitrary similarity transform. Undoing it afterwards also requires SH rotation.
- Whether SH is evaluated correctly under viewer-side rotation (Spark) and whether splat-transform rotates SH are both unverified. Late-bound transforms may give wrong view-dependent colour for SH degree >0.
- Brush and LichtFeld output frames (normalized or input frame) were not checked. Add a bbox regression test for every trainer.
- The spaces in 'C:\Users\Leonard Lind' and the project path ('Desktop\Code\Gsplat+Lidar') can break ODM, torch JIT and some scripts. Windows MAX_PATH (260) limits may also hit deep cache paths.
- CUDA 13.2+ breaks Windows JIT CUDA extensions (pytorch #197574). Mixing toolkits between COLMAP, gsplat and torch can cause DLL conflicts.
- uvicorn --reload or workers>1 on Windows silently breaks asyncio subprocesses (empty NotImplementedError).
- Process-tree leaks on cancel or crash (COLMAP, trainer) without Job Objects can hold VRAM on a 16 GB laptop GPU that also drives the display.
- A stale RUNNING state after a crash blocks reruns unless PID/heartbeat checks are implemented.
- If raw multi-GB inputs are referenced in place, moving the files breaks the project. Fingerprints must detect this and offer relinking.
- Without LiDAR or a georeferenced source, a 'splat only' project has arbitrary scale. Navigation and measurements must be disabled or flagged until a manual scale is set.
- Drone GNSS without RTK has metre-level horizontal error and 5–50 m barometric vertical error. Letting it influence the LiDAR frame would corrupt metric accuracy.
- 3D Tiles export of non-georeferenced projects needs a pseudo-georeference, which can mislead if it is not clearly flagged.
- LichtFeld's Windows binary distribution model (Portal vs GitHub releases) is unclear. The GPLv3 licence matters if it is embedded rather than called as a separate tool.
- ODM is AGPL-3.0. Keep it as an optional external process.

## open_questions

- Web search budget ran out (200-call limit shared across agents) before these could be checked: whether Spark evaluates SH in object-local space under rotation, whether splat-transform rotates SH, and the output frames of Brush and LichtFeld. Verify each empirically or in a follow-up search.
- Exact years for the COLMAP 4.x and LichtFeld v0.5.x releases are inferred (2026); the release pages showed only month and day.
- Does pytransform3d's TransformManager accept Sim(3) (scaled) matrices with checks disabled, and is its uncertainty module usable for 7-DoF covariance? Otherwise hand-roll it.
- Does Starlette StaticFiles handle the range-request patterns that COPC and RAD streaming loaders use (multiple ranges, If-Range)? Test locally.
- Does gsplat training with normalize_world_space=False in a metric LiDAR frame (scene extent ~10–30 m) keep quality? Learning-rate scaling uses the scene scale; confirm on the first test.
- Should the drone aerial model (option c) be a splat, an ODM textured mesh, or DSM + orthophoto? That decides the layer kinds and export formats; it depends on the drone research outcome.
- DJI RtkFlag value meanings (e.g. 16 vs 50) for automatic accuracy classification were not confirmed.

## questions_for_user

- Can the project and data root be on a path without spaces (e.g. C:\gsl or D:\gsl)? Your profile path 'C:\Users\Leonard Lind' has a space, which breaks some tools.
- Is a browser tab on localhost acceptable for the processing UI in phase 1, with a native window (pywebview) later? Or do you want a desktop app window from the start?
- Should raw captures (multi-GB LAS, Insta360 video, drone images) be copied into the project folder, or referenced where they already are?
- For georeferenced output, should SWEREF 99 TM (EPSG:3006) + RH 2000 be the default export CRS, or WGS84/ECEF only?
- Will the public web export always be static hosting, or might it be served through a Hexagon/Luciad server? This affects whether 3D Tiles is the primary or a secondary export.

## FACT-CHECK: non-confirmed verdicts

- **CORRECTED**: Spark SplatMesh supports position/quaternion but only uniform scale. Whether SH is evaluated correctly under object rotation is undocumented, and so is depth/occlusion with other Three.js objects. → Uniform scale only is confirmed ('scale only allows uniform scaling and averages the x/y/z scales'). The SH question is answered by the source: SplatMesh.ts updates context.viewToObject from the view-to-object matrix and passes viewOrigin: viewToObject.translate to fetchSplat, with the comment 'Only trigger update if we have view-dependent spherical harmonics'. So SH is evaluated in object-local space, and rotating or translating a SplatMesh gives correct view-dependent colour. This is read from code, not from docs, so verify with one test. The Spark README states it 'Integrates with THREE.js rendering pipeline to fuse splat and mesh-based objects'. The current npm version is 2.3.1 (MIT), not 2.0. The Spark 2.0 blog is dated 2026-04-14 (the report says 04-15). The 64K-splat RAD chunks and the 500K–2.5M budget are confirmed. (https://sparkjs.dev/docs/splat-mesh/ https://raw.githubusercontent.com/sparkjsdev/spark/main/src/SplatMesh.ts)
- **CORRECTED**: Whether PlayCanvas splat-transform rotates SH is unverified, so baking a transform at export needs a custom Wigner-D implementation. → splat-transform's data-table transform code builds `new RotateSH(mat3)` from the rotation and calls `rotateSH.apply(shCoeffs)` on the f_rest_* channels. SH rotation is therefore implemented, and a custom Wigner-D utility is not needed. The CLI offers -t translate, -r Euler degrees and -s uniform scale. License MIT. Outputs: PLY, compressed PLY, SOG, streamed SOG, SPZ, GLB (KHR_gaussian_splatting), HTML, LOD. The GLB is plain KHR_gaussian_splatting, so it is NOT the spz_2-compressed payload that the 3DTilesRendererJS 3DGS plugin requires. (https://raw.githubusercontent.com/playcanvas/splat-transform/main/src/lib/data-table/transform.ts https://github.com/playcanvas/splat-transform)
- **REFUTED**: Prefer gsplat's prebuilt Windows wheels and pin CUDA 12.8. gsplat needs PyTorch 2.7+ and ships prebuilt Linux and Windows wheels for some torch/CUDA combinations. → The two requirements conflict. The prebuilt wheel index (docs.gsplat.studio/whl/gsplat/, 110 files) only goes up to gsplat 1.5.3, with tags pt20–pt24 × cu118/cu121/cu124. The newest Windows wheel is 1.5.3+pt24cu124 (cp310), and no pt27+/cu126+/cu128 wheels exist. The latest PyPI release is 1.5.3 (2025-07-04), a py3-none-any wheel that JIT-compiles CUDA on first import. GitHub main (v1.6.0, Jul 2026) says 'PyTorch 2.7+ is now required' with 'improved CUDA 12.8 and 13.2 build compatibility', but it has no tagged release and no prebuilt wheels. The real choice on Windows: (a) gsplat 1.5.3 prebuilt on torch 2.4/cu124 (fine for an RTX 3080 Ti, sm_86), or (b) gsplat main/1.6 compiled from source or JIT with VS Build Tools (MSVC 143/142), cl.exe on PATH via vcvars64.bat and a CUDA toolkit. Option (b) is where the CUDA 13.2+ /Zc:preprocessor issue and any path problems apply. (https://docs.gsplat.studio/whl/gsplat/ https://pypi.org/project/gsplat/)
- **CORRECTED**: pycolmap provides the Sim(3) and alignment primitives the SfM→LiDAR registration needs (Sim3d, align_reconstructions_via_points/_via_reprojections/_via_proj_centers, Reconstruction.transform); the recommended registration is 'pycolmap align/Sim3d + ICP refine'. → The functions exist: Sim3d(scale, rotation, translation), Reconstruction.transform(new_from_old_world: Sim3d), align_reconstructions_via_points(src_reconstruction, tgt_reconstruction, min_common_observations=3, max_error=0.005, min_inlier_ratio=0.9) -> Sim3d|None, and the reprojection and proj-centre variants. The via_* functions align one COLMAP Reconstruction to another through shared images and observations, so they cannot register SfM to a LiDAR point cloud. They fit cross-group alignment, such as an Insta360 group against a drone group that shares images. The pycolmap call that fits the LiDAR case is align_reconstruction_to_locations(src, tgt_image_names, tgt_locations, min_common_images, ransac_options) -> Sim3d|None. It takes camera centres expressed in the LiDAR frame, for example from the BLK2GO trajectory plus the measured device offset and time sync. ICP refinement needs an external library (Open3D or similar); pycolmap has none. Also confirmed: model_aligner needs ≥3 images with known positions, --ref_is_gps, --alignment_type ecef etc., and --alignment_max_error. pose_prior_mapper has --overwrite_priors_covariance with prior_position_std defaults of 1.0 m. The COLMAP database has rigs and frames tables. (https://colmap.github.io/pycolmap/pycolmap.html https://colmap.github.io/faq.html)
- **CORRECTED**: FastAPI 0.135.0 added native SSE (fastapi.sse EventSourceResponse/ServerSentEvent) with Last-Event-ID resume, a 15 s keep-alive and the Cache-Control/X-Accel-Buffering headers. Starlette 0.39.0 (2024-09-23) added Range support to FileResponse/StaticFiles, so COPC/RAD/3D Tiles range loading works from localhost. → The SSE details are confirmed verbatim, and Starlette 0.39.0 (2024-09-23) did add Range support. The report misses that Starlette's Range handling has since had a security advisory and several correctness fixes: GHSA-7f5h-v6xp-fcq8 (0.49.1, 2025-10-28, range-parsing DoS); 1.0.0rc1 (2026-02-23) with sort-based range merge, multipart byterange CRLF and Content-Type fixes; 1.5.1 (2026-08-08), which rejects inverted ranges and caps ranges at 100; and 1.7.0 (2026-09-23), which ignores Range on non-200 FileResponse. The latest FastAPI, 0.142.2, only requires starlette>=0.46.0, so a resolver could install a vulnerable or buggy Starlette. Pin starlette>=1.7 (or at least >=0.49.1) and bind to 127.0.0.1. Multi-range and If-Range behaviour for COPC/RAD loaders still has to be tested. (https://fastapi.tiangolo.com/tutorial/server-sent-events/ https://raw.githubusercontent.com/encode/starlette/master/docs/release-notes.md)
- **CORRECTED**: Splats can be exported to 3D Tiles as glTF with KHR_gaussian_splatting (ratified Sept 2026) plus spz_2 compression, which LuciadRIA 2026.1 reads and which load in Three.js through 3DTilesRendererJS plus a 3DGS plugin. This keeps one viewer codebase for local preview, the public web and the Luciad/Cesium paths. → KHR_gaussian_splatting is confirmed as 'Complete, Ratified by the Khronos Group'. Its PR #2490 merged 2026-01-27, and a third-party issue gives 2026-09-03 for the status change. KHR_gaussian_splatting_compression_spz_2 is NOT ratified: it is still an open glTF PR (#2531, opened 2025-09-29) and is not in the Khronos or Vendor extension folders on main. LuciadRIA 2026.1 does consume 3D Tiles with glTF payloads using KHR_gaussian_splatting or KHR_gaussian_splatting_compression_spz_2 (TileSet3DLayer + OGC3DTilesModel; release notes, no date). The release notes give no sign that standalone .ply/.spz files load. The Three.js plugin (Apache-2.0, v0.3.0) accepts ONLY spz_2-compressed payloads, needs three>=0.186 and 3d-tiles-renderer ^0.5.0, and renders through 'Gaussian Splat Lite', not Spark. The 3D Tiles path in Three.js is therefore a second splat renderer that cannot depth-sort together with Spark SplatMeshes, so it is not 'the same viewer code'. Core 3DTilesRendererJS has no splat support but does have a Potree plugin. The nianticlabs SPZ library is now at file version 4; check that spz_2 encoders and decoders agree. (https://github.com/KhronosGroup/glTF/blob/main/extensions/2.0/Khronos/KHR_gaussian_splatting/README.md https://github.com/KhronosGroup/glTF/pulls?q=gaussian+spz)
- **CORRECTED**: Spaces in 'C:\Users\Leonard Lind' and in the project path are known to break torch cpp_extension JIT builds (pytorch #38781, #122476) and ODM/OpenSfM (#1006). CUDA 13.2+ breaks Windows JIT extensions (pytorch #197574). → #197574 is confirmed: 'Windows JIT CUDA extensions fail on CUDA 13.2+ (CCCL requires /Zc:preprocessor)', opened 2026-09-18 and still open, with proposed fix PR #188761. The space-in-path evidence is old and closed. #38781 dates from 2020 (Windows 10, ninja 'multiple outputs' error) and is closed. #122476 dates from 2024, was on macOS/Clang ('cpp_extension doesn't support include paths with spaces') and is closed. ODM #1006 dates from 2019, was in Docker and is closed. No current, open evidence was found that these still break, so the claim is overstated. A space-free root (C:\gsl) remains a cheap precaution, especially for source-building gsplat and for MAX_PATH, but present it as a precaution, not as a known current bug. (https://github.com/pytorch/pytorch/issues/197574 https://github.com/pytorch/pytorch/issues/38781)
- **CORRECTED**: The LichtFeld Studio README says Windows binaries come through the 'LichtFeld Portal', yet the GitHub releases page lists Windows assets for v0.4.2–v0.5.3; this conflict is unresolved. GPLv3, CC≥7.5, driver ≥570. → Resolved. v0.4.2 shipped LichtFeld-Studio-Windows-v0_4_2_.zip on GitHub. v0.5.3 (2026-06-24) has only 'Source code (zip)' and 'Source code (tar.gz)', which GitHub generates automatically. The README states: 'Prebuilt Windows binaries are distributed through the LichtFeld Portal. Access is paid: you register and make a donation of your choosing... Binaries are not published on GitHub Releases.' Since v0.5.x a free Windows option means building from source (C++23, CUDA 12.8+). GPLv3, compute capability ≥7.5 and driver ≥570 (CUDA 12.8+) are confirmed. (https://github.com/MrNeRF/LichtFeld-Studio https://github.com/MrNeRF/LichtFeld-Studio/releases/expanded_assets/v0.5.3)
- **CORRECTED**: ODM is AGPL-3.0, has a native Windows installer, offers GPU via Docker, has --3d-tiles (docs 3.6.0), and its GCP file recommends ≥5 GCPs × 3 images. → AGPL-3.0, the native Windows setup from releases, GPU only through the opendronemap/odm:gpu Docker image, and --3d-tiles ('Generate OGC 3D Tiles outputs. Default: False', docs 3.6.0) are all confirmed. On GCPs the docs say 'a minimum of 5 GCP works for most of the jobs, and for larger projects 8–10 are sufficient', and that each GCP should be 'found in at least 5 images'. The 15-line minimum (5 points × 3 images) is the absolute floor, not the recommendation. (https://github.com/OpenDroneMap/ODM https://docs.opendronemap.org/arguments/3d-tiles/)

_10 of 19 checked claims confirmed._


## FACT-CHECK: missed developments

- Spark evaluates view-dependent SH in object-local space (viewToObject), so viewer-side Sim(3) rotation and translation of a splat layer do not corrupt SH colour.: This changes the risk balance in the report. The default can be 'train in the SfM frame, then apply the registration Sim(3) as a viewer node transform', with uniform scale only. Re-training after every registration change is no longer forced. A one-scene visual test is still advised because the evidence is source code, not docs. Spark is now at 2.3.1 (MIT), and its README advertises fusing splats with meshes in the Three.js pipeline. (https://raw.githubusercontent.com/sparkjsdev/spark/main/src/SplatMesh.ts https://raw.githubusercontent.com/sparkjsdev/spark/main/README.md)
- PlayCanvas splat-transform (MIT) already rotates SH (RotateSH) when it bakes transforms, so it can bake the project-frame Sim(3) into exported splats.: Use it in the Export stage to bake source→project transforms into PLY/SOG/SPZ/GLB without writing a Wigner-D implementation. The CLI takes Euler degrees and a uniform scale, so convert R to Euler or use the library API. Its GLB output is KHR_gaussian_splatting without spz_2, and the Three.js 3D Tiles plugin rejects that. (https://raw.githubusercontent.com/playcanvas/splat-transform/main/src/lib/data-table/transform.ts https://github.com/playcanvas/splat-transform)
- There are no prebuilt Windows gsplat wheels for PyTorch ≥2.5. The prebuilt index stops at 1.5.3+pt24cu124, while gsplat main (v1.6.0, Jul 2026) requires PyTorch 2.7+ and has no release or wheels.: Phase-1 environment decision: pin gsplat 1.5.3 + torch 2.4 cu124 prebuilt (simplest, sm_86 is fine), or install VS Build Tools + CUDA 12.8 toolkit and build main from source. The second route is exposed to pytorch #197574 if CUDA ≥13.2 and to the usual MSVC/vcvars setup. Brush (Apache-2.0, no CUDA, native Windows) is the low-friction fallback trainer. (https://docs.gsplat.studio/whl/gsplat/ https://pypi.org/project/gsplat/)
- Starlette has had a security advisory and a series of fixes in its Range handling since 0.39 (GHSA-7f5h-v6xp-fcq8 in 0.49.1; fixes in 1.0.0rc1, 1.5.1 and 1.7.0). FastAPI 0.142.2 only requires starlette>=0.46.0.: Pin starlette>=1.7.0 in the lockfile, because the local server streams COPC/RAD/3D Tiles with byte ranges. Bind the server to 127.0.0.1 only. (https://raw.githubusercontent.com/encode/starlette/master/docs/release-notes.md https://pypi.org/pypi/fastapi/json)
- KHR_gaussian_splatting_compression_spz_2 is still an open glTF PR (#2531), not ratified, although LuciadRIA 2026.1 and the Three.js 3DGS plugin already consume it. The SPZ reference library has moved to file version 4.: Treat spz_2 as a moving target. Pin the encoder version, and validate each 3D Tiles export against LuciadRIA and the Three.js plugin before promising it as a deliverable. (https://github.com/KhronosGroup/glTF/pulls?q=gaussian+spz https://github.com/KhronosGroup/glTF/tree/main/extensions/2.0/Khronos)
- The Three.js 3D Tiles splat plugin renders through 'Gaussian Splat Lite', not Spark, and accepts only spz_2 payloads.: The scene.json-driven viewer should use either a Spark path (PLY/SPZ/SOG/RAD with LoD) or a 3D Tiles path per splat layer, never both in one scene, because two splat sorters do not composite with each other. Keep Spark plus RAD/SOG as the primary web path and 3D Tiles as the Luciad/Cesium interchange export. Core 3DTilesRendererJS also has a Potree plugin, which is an option for the LiDAR layer. (https://github.com/WilliamLiu-1997/3D-Tiles-RendererJS-3DGS-Plugin https://github.com/NASA-AMMOS/3DTilesRendererJS)
- pycolmap.align_reconstruction_to_locations (and COLMAP pose_prior_mapper) can turn the BLK2GO trajectory plus the measured device offset directly into a metric Sim(3), or into priors, in the LiDAR frame.: This is the natural implementation of the 'device-offset prior' edge in the frame graph. Interpolate the BLK2GO trajectory at the Insta360 frame timestamps, apply the lever arm, and call align_reconstruction_to_locations, then refine with ICP against the LiDAR (external library). Alternatively, feed the positions as pose priors to pose_prior_mapper (default prior std 1.0 m, overridable) so the SfM is metric and LiDAR-framed from the start. align_reconstructions_via_points only applies between two COLMAP reconstructions, for example ground and drone groups. (https://colmap.github.io/pycolmap/pycolmap.html https://colmap.github.io/faq.html)
- Since v0.5.0, LichtFeld Studio Windows binaries come only through a paid, donation-based Portal; GitHub releases carry source archives only.: For a zero-cost, no-watermark Windows workflow, LichtFeld means building from source (C++23, CUDA 12.8+). Keep gsplat or Brush as the default trainer modules. (https://github.com/MrNeRF/LichtFeld-Studio https://github.com/MrNeRF/LichtFeld-Studio/releases/expanded_assets/v0.5.3)
- COLMAP 4.1's native spherical camera model is described as 'generally faster but less accurate than rendering perspective views'.: For the Insta360 source module, keep cubemap or perspective rendering with a rig as the quality path and treat the spherical model as a quick-look option. The COLMAP Windows CUDA binary (colmap-x64-windows-cuda.zip) is available in 4.2.1. (https://github.com/colmap/colmap/releases/tag/4.1.0 https://github.com/colmap/colmap/releases/expanded_assets/4.2.1)

## FACT-CHECK: recommendation assessment

The core architecture holds up and is proportionate. It has five parts: a FastAPI backend on localhost; each stage run as a CLI subprocess in a Windows Job Object; a hand-rolled, content-hashed DAG with JSON records; a frame graph with Sim(3) edges and the anchor policy (LiDAR, else drone ENU, else arbitrary); and a single Vite/Three.js viewer driven by scene.json with capability-gated toggles. Its main evidence also checked out against primary sources: the gsplat normalization default, the Selector event loop under reload, FastAPI SSE, CPU-only pycolmap on Windows, and the poor fit of Snakemake, Prefect and Hamilton.

Seven changes are needed:
1. **gsplat packaging.** The packaging plan is internally inconsistent. No prebuilt Windows gsplat wheel exists for torch ≥2.5 or cu128. Choose explicitly between gsplat 1.5.3+pt24cu124 (prebuilt) and a source build of main/1.6 with VS Build Tools and CUDA 12.8 (not 13.2+). Keep Brush as a no-CUDA fallback. Pixi's 'don't mix PyPI torch with conda torch-dependents' rule affects how PDAL and torch share one environment; consider two environments, each stage running as its own subprocess.
2. **Registration call.** Replace 'pycolmap align_reconstructions_via_points + ICP' for SfM→LiDAR with align_reconstruction_to_locations, or pose_prior_mapper priors, using BLK2GO trajectory positions plus the device offset, then refine with ICP from an external library. align_reconstructions_via_* is only for aligning one imagery group to another.
3. **Splat frame.** Training in the project frame with normalize_world_space=False is still the cleanest choice; scene_scale adapts. But the claim that viewer-side transforms are unsafe was too strong. Spark evaluates SH in object space, and splat-transform rotates SH when baking. So keep training frames flexible: apply the registration as a viewer node transform during iteration, and bake it with splat-transform at export. Keep the bbox regression test.
4. **3D Tiles.** Keep it as a secondary interchange export, not as part of 'the same viewer'. The spz_2 extension is unratified (open PR #2531), and the Three.js 3DGS plugin requires spz_2 and uses a different renderer (Gaussian Splat Lite). Validate in LuciadRIA 2026.1 directly.
5. **Starlette pin.** Pin starlette ≥1.7.0 because of the Range-parsing security fixes, and never use `fastapi dev`/--reload for the job host.
6. **Paths with spaces.** Downgrade this from 'known breakage' to a precaution: the cited issues are 2019–2020 and closed. Keep the space-free root because it costs nothing.
7. **LichtFeld.** Since v0.5 its Windows binaries are paid-portal only, which matters if it was planned as a trainer module.

The phase-1 scope (only the LiDAR + Insta360 modules, plus a drone stub with capability declarations and a DJI XMP probe) should stay as is. The reconstruction-group mechanism, which makes drone options (b) and (c) a configuration switch, is well founded.
