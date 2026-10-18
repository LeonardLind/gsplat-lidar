# web-delivery

## Summary

STATE OF THE ART (Oct 2026), browser delivery of a Gaussian splat plus a LiDAR point cloud.

Formats. The original 3DGS .ply stores 17-62 float32 per splat: 68 B at SH0, 104 B at SH1, 164 B at SH2 and 248 B at SH3, so 1M SH3 splats is about 248 MB. It is the archival and training master, not a delivery format. antimatter15 .splat uses 32 B per splat (float32 position and scale, uint8 RGBA and quaternion). It has no SH, no LoD and no spatial ordering, and it is now obsolete. The user's assumption that .splat is the right viewer format is WRONG for 2026.
- PlayCanvas compressed .ply: 16 B per splat plus 48 B per 256-splat chunk, with optional uint8 SH.
- PlayCanvas SOG v2: lossless-WebP textures, a meta.json and k-means SH palettes, about 15-20x smaller than PLY (roughly 12-17 MB per 1M SH3 splats), SH up to 3 bands. Streamed SOG (lod-meta.json plus SOG chunks) adds LoD and streaming.
- Niantic SPZ: about 10x smaller than PLY. Library v3.0.0 (May 2026) writes format v4 (ZSTD, SH up to degree 4); older readers expect gzip v2/v3.
- Spark .RAD (Apr 2026): 64K-splat gzip column chunks, LoD tree, streamed over HTTP Range or as chunked .radc files. It is the native streaming format of the Spark renderer.
- Khronos KHR_gaussian_splatting: now 'Complete, Ratified' (RC Feb 3 2026; registry update Sep 3 2026). The SPZ compression extension KHR_gaussian_splatting_compression_spz_2 is still a draft PR (#2531), even though CesiumJS (since 1.139, Mar 2026) and LuciadRIA 2026.1 already consume 3D Tiles with glTF tiles that use both extensions.
- XGRIDS LCC: LoD format under a restrictive custom license.
- Octree-GS: a neural anchor representation that cannot be rendered directly in the browser, under the Inria non-commercial license.

Renderers.
- Spark 2.3.1 (MIT, World Labs, Oct 1 2026; three.js >=0.180, WebGL2). The best fit for a three.js/Vite user. It reads PLY, compressed PLY, SPZ, SPLAT, KSPLAT, SOG and RAD, with SH up to 3. Since 2.0 it has a continuous LoD with device budgets (desktop 2.5M, iOS 1.5M, Android 1M, per docs) and virtual paging with a fixed GPU pool (16.7M desktop, 6.3M iOS, 8.4M other mobile). Sorting is CPU bucket sort in a Wasm worker on GPU-computed distances. Splats are drawn as one transparent mesh that depth-tests but does not write depth, so opaque three.js meshes and point clouds composite correctly. SparkControls (FpsMovement plus PointerControls) can drive any Object3D rig, so collision constraints are easy to add after the update.
- PlayCanvas engine 2.23.0 / SuperSplat 3 / supersplat-viewer 1.37.0 (all MIT). The most performant stack: a WebGPU compute renderer with GPU radix sort (35M splats at 76 fps vs 13 fps WebGL2 on M4 Max; iPhone 13 Pro Max 1M splats at 77.6 fps WebGPU vs 38.1 WebGL2), streamed LoD and walk mode with voxel/GLB collision. There is no Potree/COPC point cloud streaming and it is not three.js.
- mkkellogg GaussianSplats3D: officially no longer developed; the author points to Spark.
- Babylon.js 9.x (Apache-2.0, 9.0 released Mar 26 2026): PLY, SPLAT, SPZ and SOG, budget-driven streaming LoD added in about 9.23.
- CesiumJS 1.146 (Apache-2.0): 3D Tiles splats with hierarchical LoD and Wasm sorting. It fits globe or GIS use, not this local fly-through.
- three.js with 3D Tiles splats: 3DTilesRendererJS has no native support; a young third-party Apache-2.0 plugin exists.

Point clouds.
- PotreeConverter 2.1.x (BSD-2) writes the Potree 2.0 format (metadata.json, hierarchy.bin, octree.bin, optional Brotli).
- potree-core 2.0.15 (MIT, commits through Sep 2026) loads it into a plain three.js scene with a point budget. EDL is not supported.
- @pnext/three-loader never added Potree 2.0.
- COPC via copc.js (MIT) is a parser only: you write your own renderer, and it streams by HTTP range.
- 3D Tiles point clouds (py3dtiles, Apache-2.0) are mainly useful for the Luciad and Cesium path.
- Spark 2.1+ can also load plain xyz/rgb PLY point clouds as splats. That is an alternative for small clouds and gives perfect mutual sorting.

Limits.
Spark's own guidance:
- phones: 1-3M splats (Android 1-2M)
- computers: 1-5M (integrated GPUs nearer the low end)
- Quest: 1M or less

Spark packed splats use 16 B per splat on the GPU (float16 centres), and extSplats use 32 B with float32 centres. Fill-rate, overdraw and sort cost limit performance more than memory does. Pruning and size reduction:
- MIT tools: SuperSplat manual cleanup; splat-transform filter-value/box/sphere/cluster, --filter-harmonics, --decimate/--decimate-adaptive.
- Research methods LightGaussian (15x, NeurIPS'24) and PUP-3DGS (90% pruning, 3.56x faster, CVPR'25) are under the Inria non-commercial license, so avoid them for Hexagon production.
- Training: gsplat MCMC cap_max (default 1M) gives a hard cap. On Mip-NeRF360, PSNR is 29.18 at 1M, 29.53 at 2M and 29.65 at 3M, vs 29.00 for default densification at 3.24M.

Hosting.
- Static hosting works. Range-based formats (.rad single file, Potree octree.bin, COPC) need HTTP Range, and same-origin hosting avoids CORS.
- Cloudflare Pages caps each file at 25 MiB (20k files on the free plan). Use Spark --rad-chunked, or R2 for large files (10 GB free, egress free).
- GitHub Pages: 1 GB site, 100 GB/month soft bandwidth, 100 MiB per-file git limit.
- Do not let the host recompress already-compressed binaries, especially those read with Range.

WHAT IT MEANS FOR THE PROJECT. Use one three.js app with Spark (splats) and potree-core (LiDAR) in a shared local metric frame: the LiDAR frame recentred at the loop centre, Z-up converted to three.js Y-up once at a root group. The registered similarity transform (scale, R, t) is applied to the SplatMesh, or baked with splat-transform. Deliver the splat as a Spark .rad LoD file built from the trained PLY (build-lod --quality --rad-chunked, --max-sh 1-2 for the forest). Keep the PLY SH3 master and offer an SOG or SPZ fallback. Train the 10x10 m forest with MCMC cap_max around 2-3M; LoD covers mobile, or produce an explicit 0.5-1M SH0/SH1 mobile variant. Build navigation from LiDAR: a PDAL SMRF ground DTM heightfield, a walkable boundary polygon, and an obstacle collision mesh queried with three-mesh-bvh, all enforced after the controls update the camera rig. For optional Luciad, export the same splat as 3D Tiles with glTF KHR_gaussian_splatting (+spz_2) and the LiDAR as 3D Tiles. LuciadRIA 2026.1 renders those, and Luciad stays a side path. Caveats: release dates for some 2026 releases were reported inconsistently by fetched pages (year shown as 2024), and the shared web-search budget ran out mid-task. The 'Gaussian Splat Lite' renderer, iOS tab memory limits and integrated-GPU fps could not be verified.

## Recommendations

- **Viewer stack for the minimal demo: TypeScript + Vite + three.js (>=0.180) + Spark 2.3.x (@sparkjsdev/spark) for splats + potree-core 2.0.x for the LiDAR, all in one scene graph. Use WebGLRenderer with antialias:false and the pixel ratio capped at about 1.5-2.** — Spark is MIT, is actively developed (2.3.1 on Oct 1 2026) and runs on WebGL2 on laptops and phones. It has built-in LoD, paging and streaming. Its splats depth-test against opaque three.js content, so Potree points composite correctly. potree-core is the maintained Potree 2.0 loader for plain three.js. Both fit the user's existing three.js and Vite skills. _Alternatives:_ Option 1: PlayCanvas engine or supersplat-viewer (MIT). Faster with WebGPU GPU sort and already has walk mode and collision, but there is no Potree/COPC streaming and it is not three.js; use it if splat counts grow above about 5-10M. Option 2: Babylon.js 9 (Apache-2.0). Option 3: CesiumJS 3D Tiles, only for a globe or GIS context.
- **Splat delivery formats: keep the trained PLY (SH3) as master. Publish (1) a Spark .rad built with 'npm run build-lod -- scene.ply --quality --rad-chunked --max-sh 1' (or SH2 for desktop) as the primary web asset, and (2) a single SOG (splat-transform scene.ply scene.sog) as a fallback and for SuperSplat sharing. Optionally publish (3) SPZ for interop. Do NOT use .splat.** — .rad gives coarse-to-fine streaming and device-adaptive LoD, and chunked .radc files avoid Range and per-file size problems on static hosts. SOG is about 15-20x smaller than PLY with SH and is read by Spark, PlayCanvas and Babylon. .splat has no SH and no LoD and is larger than SOG. Forest foliage is mostly diffuse, so SH1-SH2 is usually enough, and cutting SH saves most of the bytes (the SH3 rest coefficients are 180 of the 248 B in PLY). _Alternatives:_ If .rad proves immature, ship SOG or SPZ and use Spark's runtime lod:true (Tiny-LoD in a worker), or use PlayCanvas Streamed SOG (lod-meta.json).
- **Training targets for the 10x10 m forest: gsplat MCMC with cap_max 2,000,000-3,000,000 for the master (sh_degree 3). Create a mobile variant by running splat-transform --filter-harmonics 0 or 1 plus --decimate to about 0.5-1M, or rely on Spark LoD budgets (iOS 1.5M, Android 1M by default; set lodSplatCount around 0.75-1M for phones). Prune flyers with SuperSplat or splat-transform (-V opacity,gt,0.05; -B box crop to the LiDAR bounding box; -C cluster).** — Mip-NeRF360 quality rises only slowly beyond 1-2M (PSNR 29.18 at 1M vs 29.65 at 3M), and 3M uses about 5 GB of VRAM, which fits the 16 GB 3080 Ti laptop. Phones sustain about 1M splats at 30+ fps. _Alternatives:_ LightGaussian or PUP-3DGS give stronger pruning but carry the Inria non-commercial license. Use them only for research evaluation, not for a Hexagon deliverable.
- **Coordinate frames: make the LiDAR frame the master metric frame and define a local origin at the loop centre. PotreeConverter keeps the offset in metadata.json; record the same offset for the splat. Put one root THREE.Group that rotates Z-up to Y-up (-90° about X) above both layers. Apply the estimated Sim(3) (s, R, t from SfM to LiDAR) as the SplatMesh matrix at runtime, or bake it offline with splat-transform -s/-r/-t, which must rotate SH correctly; verify this. Enable extSplats or pagedExtSplats if the scene extends beyond about 30 m from the origin.** — Spark packed splats store float16 centres, and both layers run in float32 on the GPU. Projected CRS coordinates (around 6.5e6 m) would destroy precision. A single shared root transform guarantees the two layers stay aligned and the toggles stay consistent. _Alternatives:_ Bake everything into one georeferenced frame and use 3D Tiles with an ECEF root transform. Only needed for the Luciad and Cesium path.
- **Navigation constraints from LiDAR. In the Python pipeline: run PDAL filters.smrf, rasterize ground to a DTM grid (e.g. 10 cm, Float32 or 16-bit PNG, a few hundred KB), derive a walkable boundary polygon (e.g. the buffered LiDAR trajectory or hull), and build an obstacle mesh (trunks, rocks) or a voxel occupancy grid from non-ground points. In the viewer: drive a camera rig with Spark FpsMovement and PointerControls (or custom touch joysticks), then after each update clamp eye height to at least DTM + 1.6 m (or allow free fly with a ground clearance of 0.3 m or more), keep the rig inside the polygon, and resolve capsule collisions against the obstacle mesh with three-mesh-bvh shapecast.** — Spark has no collision. LiDAR geometry is metric, accurate and unaffected by splat floaters. The DTM lookup costs almost nothing, even on phones. _Alternatives:_ Use splat-transform --voxel-carve / --collision-mesh to get a .collision.glb from the splat itself (noisier in forests), or use supersplat-viewer walk mode if you switch to PlayCanvas.
- **Point cloud preparation: export LAS/LAZ from Cyclone (PotreeConverter reads LAS/LAZ, not E57). Subsample to about 5-10 mm spacing, then run PotreeConverter 2.1.x (Windows binary, Brotli encoding if potree-core decodes it in testing). Set the point budget to about 2-3M on desktop and 0.5-1M on mobile. Render points opaque with depthWrite (adaptive size, colour or intensity) so splats composite correctly. Toggle LiDAR, splat or both by setting .visible on the Potree object and the SplatMesh.** — Potree's LoD and budget keep phones responsive for tens of millions of points, and opaque points composite correctly with Spark's depth-tested, non-depth-writing splats. _Alternatives:_ (1) COPC via PDAL writers.copc plus copc.js, which needs a custom renderer. (2) Load a heavily decimated point cloud as a Spark SplatMesh (plain PLY), which gives correct mutual sorting but uses the splat budget. (3) 3D Tiles pnts via py3dtiles for Luciad.
- **Optional Luciad path, never on the critical path. Export the registered splat to 3D Tiles with glTF KHR_gaussian_splatting + KHR_gaussian_splatting_compression_spz_2 using 3DGS-PLY-3DTiles-Converter (Apache-2.0, local). Export the LiDAR to 3D Tiles (py3dtiles, or Luciad's own tooling). Load both in LuciadRIA 2026.1 with TileSet3DLayer, OGC3DTilesModel and gaussianSplatsStyle.** — LuciadRIA 2026.1 explicitly supports these extensions, and the same tiles also work in CesiumJS. The KHR base extension is ratified, which reduces lock-in. _Alternatives:_ A single GLB from splat-transform (uncompressed KHR_gaussian_splatting) wrapped in a hand-written one-tile tileset.json.
- **Hosting: build the viewer as a static Vite site and serve the data from the same origin, so no CORS is needed. Options are Cloudflare Pages for the app plus R2 on a custom domain for large binaries (configure CORS GET/HEAD and the Range header if cross-origin; expose Content-Range, Content-Length, Accept-Ranges and ETag), or GitHub Pages if every file is under 100 MiB and the site under 1 GB. Use --rad-chunked to keep files small. Disable on-the-fly compression for binary and range-read files and brotli only HTML/JS/JSON. Aim for an initial mobile download of about 10-20 MB and a total scene of roughly 50-150 MB streamed on demand.** — Pages' 25 MiB per-file cap and GitHub's 100 MiB hard limit rule out monolithic files. R2 has free egress. Range requests and transparent compression conflict. _Alternatives:_ Netlify, S3 + CloudFront, or Hexagon-internal hosting (see questions).

## Load-bearing findings (claim + sources)

- [high] Antimatter15 .splat (the user's assumed format) is not the right delivery format in 2026 — https://github.com/antimatter15/splat https://developer.playcanvas.com/user-manual/gaussian-splatting/formats/sog/ https://sparkjs.dev/docs/splat-mesh/
- [high] 3D Tiles splats: tiles are glTF with KHR_gaussian_splatting + KHR_gaussian_splatting_compression_spz_2; supported by CesiumJS (>=1.139, Mar 2026; now 1.146) and LuciadRIA 2026.1 — https://cesium.com/blog/2026/04/27/3d-gaussian-splats-lod/ https://raw.githubusercontent.com/CesiumGS/cesium/main/CHANGES.md https://dev.luciad.com/portal/productDocumentation/LuciadRIA/docs/releasenotes.html?component=LuciadRIA.LuciadRIA
- [high] Spark 2.3.1 (MIT, Oct 1 2026, three.js >=0.180, WebGL2) is the most suitable three.js splat renderer; it has LoD, streaming and paging and composites with ordinary three.js geometry — https://github.com/sparkjsdev/spark https://github.com/sparkjsdev/spark/releases https://unpkg.com/@sparkjsdev/spark/package.json
- [high] Spark LoD/streaming: default per-frame splat budgets Desktop 2.5M / iOS 1.5M / Android 1M / AVP 750K / Quest 500K; fixed GPU page pool (desktop 16,777,216; iOS 6,291,456; other mobile 8,388,608 splats); .RAD built offline with build-lod — https://sparkjs.dev/docs/lod-getting-started/ https://sparkjs.dev/docs/spark-2.0-quick-start/ https://sparkjs.dev/docs/new-features-2.0/
- [medium] Spark packed splats store centres as float16: keep the scene near the origin or enable extSplats/pagedExtSplats for larger scenes — https://sparkjs.dev/docs/new-spark-renderer/ https://sparkjs.dev/docs/new-features-2.0/ https://sparkjs.dev/docs/spark-2.0-quick-start/
- [medium] Point clouds in three.js: PotreeConverter 2.1.x -> Potree 2.0 format -> potree-core 2.0.15 (MIT) is the practical, maintained path; @pnext/three-loader lacks Potree 2.0 — https://github.com/potree/PotreeConverter https://github.com/potree/PotreeConverter/releases https://unpkg.com/potree-core/package.json
- [medium] Realistic budgets: phones about 1M splats (1-3M on iPhone), integrated-GPU laptops about 1-3M, desktops 5M+, at about 30+ fps — https://sparkjs.dev/docs/performance/ https://sparkjs.dev/docs/lod-getting-started/ https://sparkjs.dev/docs/spark-renderer/
- [high] MIT-licensed reduction tooling exists (splat-transform, SuperSplat); the best-known research pruners (LightGaussian, PUP-3DGS) and Octree-GS are under the Inria non-commercial license — https://github.com/playcanvas/splat-transform https://raw.githubusercontent.com/playcanvas/splat-transform/main/README.md https://unpkg.com/@playcanvas/splat-transform/package.json
- [high] Training feedback: cap splat count with gsplat MCMC (cap_max), since quality grows only slowly beyond 1-2M on 360 scenes — https://docs.gsplat.studio/main/tests/eval.html https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/gsplat/strategy/mcmc.py https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/examples/simple_trainer.py
- [high] Navigation constraints are not built into Spark; the camera rig must be constrained after each controls update. PlayCanvas's voxel and collision tooling shows how, but LiDAR is the better source here — https://sparkjs.dev/docs/controls/ https://github.com/gkjohnson/three-mesh-bvh https://developer.playcanvas.com/user-manual/splat-transform/collision/

## Key numbers

- 3DGS PLY bytes/splat at SH0/SH1/SH2/SH3: 68 / 104 / 164 / 248 B (1M SH3 splats ≈ 248 MB) (https://raw.githubusercontent.com/graphdeco-inria/gaussian-splatting/main/scene/gaussian_model.py (derived))
- .splat bytes/splat: 32 B, no SH (https://github.com/antimatter15/splat)
- PlayCanvas compressed PLY: 16 B/splat + 48 B per 256-splat chunk; guitar 132.8 MB -> 8.7 MB (https://blog.playcanvas.com/compressing-gaussian-splats/)
- SOG v2 compression vs PLY: ~15-20x smaller; SH palette up to 65,536 entries; up to 3 SH bands (https://developer.playcanvas.com/user-manual/gaussian-splatting/formats/sog/)
- SPZ compression vs PLY: ~10x smaller; format v4 = ZSTD; library v3.0.0 (https://github.com/nianticlabs/spz)
- Spark latest version: 2.3.1 (Oct 1 2026); 2.0.0 Apr 14 2026; three.js >=0.180 (https://github.com/sparkjsdev/spark/releases)
- Spark default LoD splat budgets: Desktop 2.5M, iOS 1.5M, Android 1M, Vision Pro 750K, Quest 500K (https://sparkjs.dev/docs/lod-getting-started/)
- Spark paged GPU splat pool (maxPagedSplats): Desktop 16,777,216; iOS 6,291,456; other mobile 8,388,608 (https://sparkjs.dev/docs/spark-renderer/)
- Spark .RAD chunk size / LoD overhead: 64K splats per chunk; LoD tree ~30-40% larger than input (https://www.worldlabs.ai/blog/spark-2.0)
- Spark splat encoding in GPU memory: 16 B/splat packed (float16 centres); 32 B/splat extSplats (float32 centres) (https://sparkjs.dev/docs/new-features-2.0/)
- Spark recommended splat counts: Android 1-2M, iPhone 1-3M, computer 1-5M (10-20M+ some desktops), Quest <=1M (https://sparkjs.dev/docs/performance/)
- PlayCanvas iPhone 13 Pro Max fps (WebGL2 / WebGPU): 1M: 38.1 / 77.6; 2M: 35.5 / 73.2; 4M: 20.4 / 42.4 (https://blog.playcanvas.com/new-in-supersplat-webgpu-and-streaming-bring-huge-performance-wins/)
- PlayCanvas M4 Max fps (WebGL2 / WebGPU): 10M: 48.1 / 124.1; 35M: 13.3 / 75.8 (https://blog.playcanvas.com/new-in-supersplat-webgpu-and-streaming-bring-huge-performance-wins/)
- PlayCanvas default gsplat splatBudget: 1,000,000 (https://api.playcanvas.com/engine/classes/GSplatParams.html)
- WebGPU availability (PlayCanvas estimate): ~85% of end users (https://radiancefields.com/supersplat-ships-compute-based-webgpu-rendering-and-automatic-streamed-lod)
- gsplat MCMC cap_max default: 1,000,000 (https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/gsplat/strategy/mcmc.py)
- gsplat Mip-NeRF360 PSNR / VRAM by splat count: Default 3.24M: 29.00 / 5.62 GB; MCMC 1M: 29.18 / 1.98 GB; 2M: 29.53 / 3.43 GB; 3M: 29.65 / 4.99 GB (https://docs.gsplat.studio/main/tests/eval.html)
- PUP-3DGS pruning: 90% Gaussians removed, 3.56x faster rendering (Inria NC license) (https://github.com/j-alex-hanson/gaussian-splatting-pup)
- LightGaussian compression: ~15x (Inria NC license) (https://github.com/VITA-Group/LightGaussian)
- GaussianSplats3D max splats: ~16M SH0 / ~11M SH1 / ~8M SH2 (https://github.com/mkkellogg/GaussianSplats3D)
- splat-transform version: 3.10.0 (MIT, Node >=22) (https://unpkg.com/@playcanvas/splat-transform/package.json)
- splat-transform voxel/collision defaults: voxel 0.05, opacity 0.1, carve capsule 1.6 x 0.2; LoD chunk 512K Gaussians / 16 units extent (https://developer.playcanvas.com/user-manual/splat-transform/collision/)
- potree-core version: 2.0.15 (MIT), last commit Sep 14 2026 (https://unpkg.com/potree-core/package.json)
- KHR_gaussian_splatting status: Ratified/Complete; RC Feb 3 2026; registry update Sep 3 2026 (https://github.com/KhronosGroup/glTF/commits/main/extensions/2.0/Khronos/KHR_gaussian_splatting)
- CesiumJS version with KHR splats: 1.139 (Mar 2026); latest 1.146 (2026-10-01) (https://raw.githubusercontent.com/CesiumGS/cesium/main/CHANGES.md)
- Cloudflare Pages per-file limit: 25 MiB; 20,000 files (free) (https://developers.cloudflare.com/pages/platform/limits/)
- GitHub Pages limits: 1 GB site, 100 GB/month soft bandwidth, 100 MiB per-file git block (https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)
- Cloudflare R2 free tier: 10 GB-month storage, 1M Class A, 10M Class B ops, free egress (https://developers.cloudflare.com/r2/pricing/)
- LCC bytes/splat: 32 B (SH0) / 96 B (SH3) (https://github.com/xgrids/LCCWhitepaper)

## Tools & licenses

- Spark (@sparkjsdev/spark) | 2.3.1, 2026-10-01 | MIT | win: Browser library; build-lod is Rust/cargo (cross-platform) | three.js >=0.180, WebGL2; LoD, .rad streaming, paging, SH3
- PlayCanvas engine | 2.23.0 (early Oct 2026) | MIT | win: Browser | WebGPU compute GPU sort + WebGL2 fallback; streamed SOG LoD
- SuperSplat editor / supersplat-viewer | SuperSplat 3 (2026-09-18); viewer 1.37.0 | MIT | win: Browser; editor needs WebGPU | Manual cleanup; viewer has walk mode + collision; static self-hosting
- splat-transform (@playcanvas/splat-transform) | 3.10.0 | MIT | win: Node >=22, WebGPU via 'webgpu' npm | Conversion/filter/decimate/LoD/GLB/voxel collision
- SPZ (nianticlabs/spz; npm @adobe/spz mirror) | library v3.0.0 (May 2026), format v4 | MIT | win: Yes (CMake, Python bindings) | ZSTD v4; older readers gzip v2/v3
- gsbox | v4.8.4 (2026; release page dates garbled) | GPL-3.0 | win: Windows binaries | ply/splat/spx/spz/sog/glb(KHR)/lod-meta conversion; GPL, so use as an external CLI only
- 3dgsconverter | no tagged release seen | MIT | win: Yes (pip from git) | SOR flyer removal, opacity/bbox filters, many formats
- GaussianSplats3D (mkkellogg) | no longer actively developed | MIT | win: Browser | Superseded by Spark per its author
- Babylon.js | 9.29.x (9.0 on 2026-03-26) | Apache-2.0 | win: Browser | PLY/SPLAT/SPZ/SOG, streaming LoD since ~9.23
- CesiumJS | 1.146 (2026-10-01) | Apache-2.0 | win: Browser | 3D Tiles splats with KHR_gaussian_splatting + spz_2, LoD
- LuciadRIA | 2026.1 | Commercial (Hexagon) | win: Browser | OGC 3D Tiles splats (KHR_gaussian_splatting / spz_2); optional target
- 3DGS-PLY-3DTiles-Converter | 2026 (npm) | Apache-2.0 | win: Node >=18 | PLY -> 3D Tiles with LoD + SPZ-compressed GLB
- 3D-Tiles-RendererJS-3DGS-Plugin | 0.3.0 (three >=0.186) | Apache-2.0 | win: Browser | Young; KHR + spz_2 tiles into three.js via 'Gaussian Splat Lite' (renderer not verified)
- 3DTilesRendererJS | current npm 3d-tiles-renderer | Apache-2.0 | win: Browser | No native KHR_gaussian_splatting (issue #863)
- PotreeConverter | 2.1.x (2.1.5 latest seen) | BSD-2-Clause | win: Windows binaries | LAS/LAZ -> Potree 2.0 (3 files), Brotli option
- potree-core | 2.0.15; commits to 2026-09-14 | MIT | win: Browser | Potree 2.0 in plain three.js; no EDL
- @pnext/three-loader | n/a | MIT (per repo LICENSE, background) | win: Browser | No Potree 2.0 support
- copc.js | npm 'copc' | MIT | win: Browser/Node | COPC parser + laz-perf; no renderer
- py3dtiles | 16 releases (latest not verified) | Apache-2.0 | win: Python | Point cloud -> 3D Tiles for the Luciad/Cesium path
- three-mesh-bvh | current npm | MIT | win: Browser | Capsule/shapecast collision, PointsBVH
- PDAL (filters.smrf) | 2.10.x | BSD (background) | win: Yes (conda) | Ground classification for DTM/navigation
- gsplat | 1.5.3 (2025-07-04) | Apache-2.0 | win: Yes (CUDA) | MCMC cap_max; exporter ply/splat/compressed ply
- LightGaussian / PUP-3DGS / Octree-GS | NeurIPS'24 / CVPR'25 / TPAMI'25 | Inria Gaussian-Splatting License (non-commercial) | win: CUDA research code | Research/evaluation only; avoid in a Hexagon deliverable
- XGRIDS LCC | whitepaper | Custom XGRIDS license (restrictive) | win: n/a | LoD + collision; not recommended

## risks

- Spark .RAD is a young (Apr 2026), single-vendor format. Keep the PLY master and an SOG/SPZ fallback, and pin the Spark version.
- Spark's sort is asynchronous on the CPU (at least one frame of lag). On phones, fast rotation can show sorting pops; PlayCanvas's WebGPU GPU sort is faster at high splat counts.
- potree-core (peer three >0.125, checks WebGL1-era extensions) has not been confirmed against three >=0.180 required by Spark. Prototype early. The fallback is points loaded as a Spark SplatMesh or a custom COPC/Potree loader.
- Spark packed splats use float16 centres. Large tropical scenes or un-recentred CRS coordinates will show artefacts unless extSplats/pagedExtSplats is used and the data is recentred.
- SPZ v4 (ZSTD) may not be readable by all viewers. The KHR_gaussian_splatting_compression_spz_2 spec is still a draft, so tiles produced now may need regenerating.
- Rotating splats requires rotating SH. Baking the Sim(3) into the file must handle SH (verify in splat-transform); a runtime Object3D transform avoids the problem.
- Antialiased (Mip-Splatting) training without matching renderer settings (Spark blurAmount/preBlurAmount, PlayCanvas antiAlias) makes splats look too thick or too sparse.
- When both layers are shown, LiDAR points lying on splat surfaces will speckle (z-fighting-like). Consider point colour coding, smaller points or a slight depth bias.
- iOS Safari kills tabs under memory pressure (exact limits not verified). Use LoD budgets and chunked streaming, and test on older iPhones.
- Static host limits: Cloudflare Pages 25 MiB per file, GitHub 100 MiB per file. Transparent compression can break Range reads. Cross-origin hosting needs CORS with Range allowed.
- Licensing: LightGaussian, PUP-3DGS, Octree-GS and graphdeco code are non-commercial. gsbox is GPL-3.0, so use it as an external tool only. The LCC format is restricted.
- Data provenance: release dates fetched for PlayCanvas engine, splat-transform, Babylon, PotreeConverter, gsbox and PDAL showed year inconsistencies (2024 for versions that must be 2026). Versions are reliable; exact dates have medium confidence.
- Web search budget ran out mid-research. Not verified: the 'Gaussian Splat Lite' renderer, Spark's support for SPZ v4, Potree 2.0 Range usage, integrated-GPU fps numbers, and iOS memory limits (marked low or medium confidence).

## open_questions

- Does Spark 2.3 read SPZ format v4 (ZSTD), or only v2/v3? It decides which SPZ writer settings to use.
- Is potree-core 2.0.15 fully compatible with three.js r180+ (shader chunks, WebGL2 only) alongside Spark?
- Does splat-transform -r rotate SH coefficients correctly when baking the registration transform?
- Actual .rad file size per million splats at SH0/SH1/SH2 for a forest scene (needs a test build).
- Real fps of Spark at 1-2M splats on Intel/AMD integrated GPUs and mid-range Android (e.g. Adreno 6xx/7xx) at the native pixel ratio.
- Will KHR_gaussian_splatting_compression_spz_2 change before ratification, and which SPZ version will it pin?
- Does LuciadRIA 2026.1 accept uncompressed KHR_gaussian_splatting GLB tiles produced by splat-transform, plus a hand-written tileset.json?

## questions_for_user

- Which devices must the demo hit 30 fps on (e.g. oldest iPhone/Android model, typical laptop GPU)? This sets the splat and point budgets.
- Can demo data be hosted publicly (Cloudflare Pages/R2, GitHub Pages), or must it stay on Hexagon-internal hosting or behind authentication?
- Is the BLK2GO data georeferenced (a CRS such as SWEREF 99 TM) or in a local SLAM frame? This matters for 3D Tiles and Luciad placement.
- Should viewers be able to fly freely with ground and obstacle clamping, or walk at fixed eye height on the ground?
- Is the Luciad deliverable needed in phase 1, or can it wait until the three.js demo works?
- What download size is acceptable for phone users on mobile data (e.g. under 20 MB first view, under 100 MB total)?

## FACT-CHECK: non-confirmed verdicts

- **CORRECTED**: Spark reads SPZ (implicitly any version); SPZ is a usable fallback/interop format for the Spark viewer → Spark's getSplatFileType only recognises SPZ when the file starts with a gzip header (0x088b1f) that wraps the NGSP magic, i.e. SPZ v1-v3. SPZ v4 (NGSP header + ZSTD, written by default by nianticlabs/spz v3.0.0 and @adobe/spz) is not detected. Spark's Rust Cargo.lock contains no zstd crate (only flate2/miniz_oxide). splat-transform writes SPZ v4 by default ('--spz-version <3|4>, Default: 4'), so a default-converted .spz will not load in Spark 2.3.1. Write with --spz-version 3. This answers the report's open question. (https://raw.githubusercontent.com/sparkjsdev/spark/main/src/SplatLoader.ts https://raw.githubusercontent.com/sparkjsdev/spark/main/rust/Cargo.lock)
- **CORRECTED**: CesiumJS consumes KHR_gaussian_splatting + spz_2 'since 1.139, Mar 2026'; 1.140 fixed >16M splat crash; latest 1.146 → CesiumJS 1.135 (2025-11-03) already 'Removed support for the KHR_spz_gaussian_splats_compression extension in favor of the latest 3D Gaussian splatting extensions for glTF', after deprecating it in 1.133. KHR + spz_2 support therefore dates from late 2025, not 1.139. 1.139 (Mar 2026) only fixed sort race conditions and flashing. The 1.140 fix ('WebGL crash ... more than ~16 million splats') and 1.146 = 2026-10-01 are confirmed. Hierarchical-LoD splats across Cesium were announced on 2026-04-27 (110M-splat Redmond example, Wasm sorting). The precise first-support version is medium confidence, because the CHANGES.md summaries were inconsistent. (https://raw.githubusercontent.com/CesiumGS/cesium/main/CHANGES.md https://cesium.com/blog/2026/04/27/3d-gaussian-splats-lod/)
- **CORRECTED**: potree-core 2.0.15 (MIT, peer three >0.125, commits to Sep 14 2026) is the practical maintained Potree 2.0 loader for plain three.js; no EDL → Version, license, last commit (2026-09-14) and lack of EDL are confirmed. However, devDependencies pin three ^0.154.0, so it has only been built and tested against r154, not the r180+ that Spark needs. The README still lists WebGL1-era extensions (EXT_frag_depth etc.). Open issues include 'README quick-start passes a callback to loadPointCloud (TypeError since 2.0.11)' (Sep 8 2026) and a long-standing 'Pointcloud doesn't play nice with transparent meshes'. It is no longer the only maintained option: 3DTilesRendererJS 0.5.3 (2026-09-18) added a PotreePlugin (see missed developments). (https://unpkg.com/potree-core/package.json https://raw.githubusercontent.com/tentone/potree-core/master/package.json)
- **CORRECTED**: 3DTilesRendererJS has no native KHR_gaussian_splatting; young third-party Apache-2.0 plugin v0.3 uses an unverified 'Gaussian Splat Lite' renderer → Issue #863 is still open, and the README lists only the community 3D-Tiles-RendererJS-3DGS-Plugin (0.3.0, Apache-2.0, three >=0.186, 3d-tiles-renderer ^0.5). The plugin handles only spz_2-compressed tiles, not raw KHR primitives. 'Gaussian Splat Lite' exists: npm gaussian-splat-lite 1.2.1, Apache-2.0, three >=0.186, built on three's WebGPURenderer with WebGL2 fallback, GPU radix sort on WebGPU, reads PLY/SPZ/SOG/RAD, with RAD and SOG streaming-LoD schedulers and ECEF precision support. One maintainer, about 160 stars. (https://github.com/NASA-AMMOS/3DTilesRendererJS/issues/863 https://github.com/NASA-AMMOS/3DTilesRendererJS/blob/master/src/three/plugins/README.md)
- **UNVERIFIABLE**: @pnext/three-loader never added Potree 2.0 (issue #79 closed without implementation) → Issue #79 (opened 2020-09-28, milestone 0.3.0) is closed, but neither the issue page nor the README shows whether support was implemented. The README never mentions Potree 2.0. Either way it is irrelevant now that better options exist. (https://github.com/pnext/three-loader/issues/79 https://github.com/pnext/three-loader)
- **UNVERIFIABLE**: iOS Safari kills tabs at roughly 1-2 GB per-tab memory → No primary source found. The web-search budget was exhausted, so only WebFetch on known URLs was possible. Keep as low confidence. ()

_21 of 27 checked claims confirmed._


## FACT-CHECK: missed developments

- 3DTilesRendererJS 0.5.3 (2026-09-18, Apache-2.0, three >=0.167) added PotreePlugin (Potree v1.x and v2.0) plus PointCloudEffectsPlugin (eye-dome lighting, point shape, minimum point size): This is a maintained three.js loader from NASA-AMMOS, and unlike potree-core it supports EDL. PotreeLoader reads metadata.json, hierarchy.bin and octree.bin with HTTP Range requests and does no Brotli decoding of its own, so run PotreeConverter without --encoding BROTLI. The example registers new PotreePlugin({url, pointScale, pointShape, edlStrength, edlRadius}) on a TilesRenderer. The same library also loads 3D Tiles point clouds (pnts/glTF), which matches the optional Luciad/Cesium path, and it is the host for the community 3DGS plugin. It is only about three weeks old, so prototype it next to potree-core and keep whichever works with three r180-r186 and Spark. (https://raw.githubusercontent.com/NASA-AMMOS/3DTilesRendererJS/master/CHANGELOG.md https://raw.githubusercontent.com/NASA-AMMOS/3DTilesRendererJS/master/example/three/potree.js)
- SPZ version trap: splat-transform (and @adobe/spz / nianticlabs spz 3.0.0) write SPZ v4 by default, but Spark 2.3.1 reads only gzip-wrapped SPZ v1-v3: splat-transform: '--spz-version <3|4> ... Default: 4'. Spark's getSplatFileType returns SPZ only after a gzip magic check, and its Rust crates contain no zstd. Any SPZ fallback meant for Spark must therefore be written with --spz-version 3. The KHR spz_2 draft is also anchored to SPZ v2, and reviewers raised the v4 mismatch in Aug-Sep 2026. (https://raw.githubusercontent.com/playcanvas/splat-transform/main/README.md https://raw.githubusercontent.com/sparkjsdev/spark/main/src/SplatLoader.ts)
- Gaussian-Splat-Lite 1.2.1 (Apache-2.0): a three.js WebGPU/WebGL2 splat renderer with GPU sorting that reads PLY/SPZ/SOG/RAD and streams LoD: It needs three >=0.186 and three's WebGPURenderer (WebGL2 fallback via forceWebGL), and it has RadStreamScheduler and SogStreamScheduler. It is a possible WebGPU upgrade path that reuses Spark's .rad files, which lowers the single-vendor risk of .RAD. Inference, not verified: it probably cannot share a renderer with Spark or potree-core, because those rely on WebGLRenderer GLSL/RawShaderMaterial, which WebGPURenderer does not run. Pairing it with LiDAR would need a node-material point renderer. Single maintainer, about 160 stars. (https://unpkg.com/gaussian-splat-lite/package.json https://raw.githubusercontent.com/WilliamLiu-1997/Gaussian-Splat-Lite/main/README.md)
- splat-transform rotates SH when transforming and has a voxel-based floater filter (-F/--filter-floaters): transform.ts applies RotateSH from the rotation quaternion, so offline Sim(3) baking is SH-correct. -F removes Gaussians that contribute to no solid voxel, which is directly useful for forest flyers alongside -V opacity, -B box and -C cluster. (https://raw.githubusercontent.com/playcanvas/splat-transform/main/src/lib/data-table/transform.ts https://raw.githubusercontent.com/playcanvas/splat-transform/main/README.md)
- Spark versions before 2.1 break on Chrome 149+: The v2.1.0 notes rename 'packed' to 'packedData' because 'Chrome 149 onwards considers it a reserved keyword'. Any tutorial code pinned to Spark 0.1.x or 2.0.x will fail in current Chrome. Pin @sparkjsdev/spark >=2.1, preferably 2.3.1. Spark 2.3's on-demand rendering (render only when the camera or scene changes) helps phone battery and heat in a static viewer. (https://github.com/sparkjsdev/spark/releases/tag/v2.1.0 https://github.com/sparkjsdev/spark/releases)
- PlayCanvas's iPhone benchmark ran at a reduced resolution (642x1126): So the 38 fps (WebGL2) / 78 fps (WebGPU) at 1M splats are not native-DPR numbers. Mobile budgets in the plan should assume DPR capping to about 1-1.5 and 0.5-1M splats for 30 fps on mid-range phones. (https://blog.playcanvas.com/new-in-supersplat-webgpu-and-streaming-bring-huge-performance-wins/)
- CesiumJS has used the KHR_gaussian_splatting + spz_2 extensions since late 2025, not Mar 2026: 1.135 (2025-11-03) removed the old KHR_spz_gaussian_splats_compression 'in favor of the latest 3D Gaussian splatting extensions for glTF'. 1.133 (2025-09) added SH support for SPZ splats. Hierarchical-LoD splats across Cesium followed on 2026-04-27. Tiles from the converter should work on any recent CesiumJS (>=1.140 recommended for the >16M-splat crash fix and the leak fix). (https://raw.githubusercontent.com/CesiumGS/cesium/main/CHANGES.md https://cesium.com/blog/2026/04/27/3d-gaussian-splats-lod/)
- Khronos named a second proposed compression extension for KHR_gaussian_splatting: Qualcomm L-GSC: The Feb 3 2026 press release lists SPZ and Qualcomm L-GSC compression extensions as proposed. Compression is not settled, which supports keeping 3D Tiles output as a regenerable side path. (https://www.khronos.org/news/press/gltf-gaussian-splatting-press-release)
- The 3DGS-PLY-3DTiles-Converter GitHub repository URL now returns 404: npm 0.6.5 (Apache-2.0) is still published and lists github.com/WilliamLiu-1997/3DGS-PLY-3DTiles-Converter, but that URL 404s, and only a '-Website' variant appears in the author's repo list. Vendor or pin the npm tarball, and consider Cesium ion, Luciad tooling or a hand-written single-tile tileset.json as fallbacks. (https://unpkg.com/3dgs-ply-3dtiles-converter/package.json https://github.com/WilliamLiu-1997/3DGS-PLY-3DTiles-Converter)

## FACT-CHECK: recommendation assessment

Most recommendations hold: TypeScript, Vite and three.js with Spark 2.3.x for the splats, .rad as the primary asset with an SOG fallback, no .splat, gsplat MCMC capped at 2-3M, navigation from the LiDAR (PDAL SMRF DTM plus three-mesh-bvh), and Luciad kept as a side path. Spark's version, license, LoD budgets, paging, depth compositing, controls and the PlayCanvas numbers all check out against primary sources. Six changes are needed.

(1) Point cloud loader. Do not commit to potree-core alone. Its devDependency pins three ^0.154 (never tested on r180+), its README quick-start has been broken since 2.0.11, and a 2019 issue about transparent meshes is still open. Prototype 3DTilesRendererJS 0.5.3's PotreePlugin and PointCloudEffectsPlugin at the same time: Apache-2.0, three >=0.167, released 2026-09-18, Potree 2.0 over HTTP Range, eye-dome lighting included. If PotreePlugin is used, run PotreeConverter without Brotli. Keep the Spark plain-PLY point cloud as a third fallback.

(2) SPZ fallback. Write it with splat-transform --spz-version 3. The default v4 (ZSTD) will not load in Spark 2.3.1. SOG is the safer fallback for Spark anyway.

(3) Registration transform. Baking the Sim(3) offline with splat-transform is confirmed to rotate SH correctly, but -r takes Euler angles in degrees. Applying the transform to the SplatMesh at runtime is still the simplest option.

(4) Mobile budget. Lower the default phone budget to about 0.5-1M (lodSplatCount) with DPR capped at 1-1.5, and enable Spark 2.3 on-demand rendering. PlayCanvas's iPhone figures were measured at a reduced 642x1126 resolution.

(5) Version pin. Pin Spark >=2.1 (preferably 2.3.1), because older versions break on Chrome 149+.

(6) Luciad path. LuciadRIA 2026.1 accepts plain KHR_gaussian_splatting as well as spz_2, so splat-transform's GLB in a one-tile tileset is a credible, maintained alternative. The npm converter's GitHub repo now returns 404 and has a single maintainer, so pin or vendor it. The spz_2 extension is still a draft and may be revised toward SPZ v4, and a Qualcomm L-GSC compression extension is also proposed, so treat any tiles as regenerable.

Two smaller corrections. CesiumJS has supported the KHR splat extensions since about 1.135 (Nov 2025), not 1.139. Gaussian-Splat-Lite is real and worth tracking as a WebGPU and .rad-compatible upgrade path, but it needs WebGPURenderer and so is not drop-in alongside Spark or potree-core.

The web-search budget was exhausted from the start, so every check used WebFetch on primary URLs. The iOS memory limit, integrated-GPU frame rates and @pnext/three-loader's Potree 2.0 status remain unverified.
