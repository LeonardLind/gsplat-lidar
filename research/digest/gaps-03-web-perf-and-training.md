# gap: web-perf-and-training

## Summary

BOTTOM LINE FOR THE TRAINING TARGET: Train with MCMC capped at about 2-3M Gaussians (SH3 in training), with image width capped at about 1600 px. Ship a Spark .rad LoD file built with --max-sh 0 or 1 for phones, and an optional SH3 variant for desktop. On the 16 GB RTX 3080 Ti Laptop this should fit comfortably without packed mode. Expected peak VRAM is about 2-6 GB, plus any cached images. Expected wall-clock (my estimate, not measured on this GPU) is about 25-30 min for gsplat at 1M and about 45-55 min at 3M. LichtFeld or Faster-GS should be about 3-4x faster. Spark's own runtime budgets cap what is drawn: Android 1M, iOS 1.5M, desktop 2.5M LoD splats. Training beyond about 3M therefore only helps close-up desktop views.

(A) BROWSER - MEASURED DATA IS THIN. I found no published measurements of Spark 2.x fps on any phone or integrated laptop GPU, of SH0 vs SH3 render cost, or of Mali-G7x or Iris Xe with Spark or PlayCanvas. The web-search budget ran out before the Babylon.js forum, r/GaussianSplatting and Iris Xe searches; those were not run.

Measured results that do exist:
- PlayCanvas Engine 2.19 / SuperSplat (blog, 3 Jun 2026), iPhone 13 Pro Max (A15), 642x1126 canvas (I infer device pixel ratio about 1.5, not native 3). WebGL2 / WebGPU fps: 1M 38.1/77.6; 2M 35.5/73.2; 3M 25.5/52.7; 4M 20.4/42.4.
- Same blog, M4 Max at 1298x962: 1M 137/139; 2M 140/154; 3M 125/136; 10M 48/124.
- WebSplatter paper (arXiv 2602.03207, Feb 2026), research viewers, resolution and SH not stated, bicycle-c scene with 1.06M splats:
  - Snapdragon 8 Gen 3 (Adreno 750): WebGPU WebSplatter 33.6 ms (about 30 fps); WebGL antimatter15 55.3 ms; GaussianSplats3D 76.4 ms. Truck scene (2.54M): 52.7 ms.
  - Snapdragon 865 (Adreno 650): 105 ms (about 9.5 fps); GaussianSplats3D 183 ms.
  - iPhone 15 Pro Max: 38.5 ms; GaussianSplats3D repeatedly crashed Safari.
  - MX350 laptop: Train scene (1.03M) 77 ms.
  - Intel UHD iGPU: Garden scene (5.8M) 151 ms.
- Spark issue #117 (Jul 2025): CPU sort of 1M splats takes 4-6 ms on desktop.
- Spark issue #202 (Oct 2025, pre-LoD 0.1.x): about 10 fps on an M4 MacBook Air.
- Spark changelog: 2.2.0 (11 Sep 2026) up to 14% fps gain and about 20% faster sorting. 2.3.0 (30 Sep 2026) adds on-demand rendering. Latest is 2.3.1.

Spark vendor guidance (not measurements):
- Performance page: Quest 3 at most 1M; Android 1-2M; iPhone 1-3M; computer 1-5M.
- Default lodSplatCount: Oculus 500K, Vision Pro 750K, Android 1M, iOS 1.5M, desktop 2.5M.
- maxPagedSplats (GPU pool): desktop 16,777,216; iOS 6,291,456; other mobile 8,388,608.
- GPU memory per splat: SH0 16 B, SH1 24 B, SH2 40 B, SH3 56 B.
- Spark is WebGL2 only. PlayCanvas falls back from WebGPU to WebGL2 and says WebGPU reaches about 85% of users. Its recommended budget is 1M on mobile and 3M+ on desktop.

iOS memory: Safari has no fixed per-tab limit. Reports put the tab reload at about 3 GB on iPhone 15 Pro and 1.5-3 GB on iPhone 12 Pro. A JS-heap test crashed at about 100 MB on a 3rd-gen iPhone SE and about 200 MB on an 8th-gen iPad (lapcat, Jan 2026). A Spark reviewer said about 380 MB of GPU memory per tab is allowed on iOS. That is unverified, but it matters: the iOS paged pool at SH3 is 6.29M x 56 B = 352 MB, versus 101 MB at SH0 and 151 MB at SH1.

Download size per million splats:
- SOG, SH3, measured: 10.5 MB (4M scene to 42 MB) and 13.75 MB (4M church to 55 MB). SOG SH0 has not been measured; my estimate is about 8-11 MB. Because SOG stores SH as a palette, SH1-SH3 add only about 2-3 MB per million.
- SPZ v3, SH3: 20-25 MB (Spark blog: 10M splats to 200-250 MB) and 25.8 MB (one third-party reference). The raw layout is 20 B per splat at SH0 and 65 B at SH3, before gzip. Measured SH0 is not available; my estimate is about 10-15 MB. SPZ v4 (May 2026) is about 2.5% smaller.
- Spark .rad (gzip), measured in PR #433 on an 18.3M-splat SH3 scene: 16.0 B per splat for the non-SH data plus 19.6 B for SH3. That is about 16 MB per million at SH0 and about 35.6 MB at SH3. An unmerged zstd option brings SH3 to about 25.8 MB. The LoD tree adds 30-40% more splats, but .rad streams 64K-splat chunks, so viewers download only what they need.

(B) TRAINING:
- gsplat docs (A100, Mip-NeRF360, data factor 4/2, about 1.0-1.6 MP images):
  - MCMC 1M: 1.98 GB, 15.4 min
  - MCMC 2M: 3.43 GB, 21.8 min
  - MCMC 3M: 4.99 GB, 27.6 min
  - Default densification (3.24M Gaussians): 5.6 GB, 19.4 min
- VkSplat paper (RTX 3090, May 2026):
  - gsplat MCMC 1M: 1.37 GiB, 995 s
  - gsplat default: 4.56 GiB, 1384 s
  - VkSplat MCMC 1M: 0.93 GiB, 285 s. VkSplat is Apache-2.0, runs on Windows over Vulkan, and fits 9M SH3 Gaussians in 8 GB.
- LichtFeld MCMC 1M (RTX A4500, 30k steps): 5m00s-7m59s per scene, 6m55s on average.
- Faster-GS (CVPR 2026, Apache-2.0, RTX 4090, Mip-NeRF360):
  - Faster-GS: 4m31s, 6.1 GiB
  - Inria 3DGS: 18m44s, 8.8 GiB
  - Taming 3DGS: 10m49s, 8.9 GiB
  - On RTX 3090: Inria 23m46s vs Faster-GS 6m03s
  - Original 3DGS-MCMC: 27m22s, 8.9 GiB; Faster-GS MCMC: 6m17s, 7.2 GiB
- Inria repo: accelerated rasterizer is 1.6x faster; with sparse_adam, 2.7x.
- Taming 3DGS budget mode: 0.63M Gaussians in 11 min on an A4500, and the paper says it runs under 10 GB on an RTX 3080.

Warnings:
- One user reported about 13 GB for gsplat MCMC at 2M (scene unknown), versus 4 GB with default densification.
- LichtFeld with 3840 px 360-camera frames grew from 4.4 GB to 31 GB of VRAM on an RTX 5090 and ran out of memory. The fix was max width 1920.
- gsplat's PyPI release is still 1.5.3 (Jul 2025). Version 1.6.0 on main is about 30% faster on the 3DGUT MCMC path.

Licence note: because the project is non-commercial, Inria/Taming can now be used. But Faster-GS (Apache-2.0) is both faster and permissive, so the non-commercial licence buys little extra for training.

No LuciadRIA splat performance data was found.

## Plan changes

- Training phase: fix the default config as gsplat (or LichtFeld) MCMC, cap_max 2,000,000 (with a 3,000,000 variant), 30k steps, max image width 1600 px, sh_degree 3, packed=False. Add a VRAM/time logging step (torch.cuda.max_memory_allocated plus wall-clock) so the first forest run gives a measured 3080 Ti Laptop number.
- Export phase: produce two deliverables per scene: (a) a Spark .rad LoD file via build-lod --quality --max-sh=1 (mobile/default); (b) an optional SH3 .rad for desktop. Optionally add a SOG export for PlayCanvas/SuperSplat comparison.
- Viewer: cap the three.js renderer pixel ratio to min(devicePixelRatio, 1.5) on mobile, or 1.0 on low-end. Keep Spark's default lodSplatCount and expose lodSplatScale as a quality slider. Load SH0/SH1 on iOS to keep the paged pool under about 150 MB.
- Add a 'benchmark mode' to the web viewer: fixed path, fps percentiles, and device/GPU string via WEBGL_debug_renderer_info. Run it on coworkers' devices before the tropical-forest phase.
- Treat PlayCanvas WebGPU as a measured fallback option if Spark/WebGL2 is too slow on phones (about 2x fps on iPhone 13 Pro Max at 1-4M splats).
- Ask the Luciad team for LuciadRIA splat format support and performance numbers. There is no public data.

## Recommendations

- **Set the training target to MCMC cap_max 2M as the baseline and 3M as the 'high' variant, with sh_degree 3 during training. Cap images at max width 1600 px (perspective crops from the 360 video), keep packed=False unless VRAM exceeds about 12 GB, and run 30k steps.** — Spark draws at most 1M LoD splats on Android, 1.5M on iOS and 2.5M on desktop. Per measurements, 2-3M MCMC needs about 3.4-5 GB on gsplat at Mip-NeRF360 resolution, well inside 16 GB. The quality gain from 2M to 3M was +0.12 dB PSNR, against about 27% more training time. Large inputs (3840 px) are a documented cause of VRAM blow-ups. _Alt:_ 1M if phones are the main audience (MCMC 1M scored 29.18 vs 29.65 at 3M on Mip-NeRF360). 4M+ only if you want close-up desktop detail.
- **Ship Spark .rad files built with build-lod --quality. Use --max-sh=0 or 1 for the mobile/default file and keep an optional SH3 file for desktop. Cap renderer DPR at about 1.0-1.5 on phones and keep the default lodSplatCount.** — Per-splat GPU cost is 16 B at SH0, 24 B at SH1 and 56 B at SH3. At SH3 the iOS paged pool (6.29M splats) reaches about 352 MB, near the reported (unverified) 380 MB per-tab GPU limit on iOS. .rad costs about 16 MB/M at SH0 versus about 36 MB/M at SH3, and it streams in chunks. PlayCanvas's iPhone benchmark used a canvas of about 1.5 DPR. Under-canopy forest scenes look mostly diffuse, so SH matters less. _Alt:_ SOG (about 10-14 MB/M even at SH3) if you use PlayCanvas or SuperSplat, or as a compact non-LoD fallback. SPZ (about 20-26 MB/M at SH3) for interchange.
- **Build a small in-house benchmark page before freezing the target. Use a fixed camera path and log median and 1%-low frame times for 0.5, 1, 2 and 3M splats × SH0/SH1/SH3 × DPR 1/native. Run it on Spark 2.3.x with LoD on and off, and on PlayCanvas with WebGL2 and WebGPU. Test on the coworkers' actual phones and laptops.** — There is no published measured Spark data for phones or iGPUs, and nothing for Mali or Iris Xe. The available research-viewer data (Adreno 650 at about 9.5 fps for 1M) is a pessimistic bound. PlayCanvas WebGPU is about 2x WebGL2 on iPhone, and Spark is WebGL2-only, so the stack choice could swing phone fps by about 2x. _Alt:_ Rely on vendor budgets (Spark/PlayCanvas defaults) and skip benchmarking for the first 10x10 m test.
- **For training speed, try LichtFeld Studio (GPL-3.0, Windows binaries, MCMC + 3DGUT + 360 plugin) or Faster-GS (Apache-2.0) next to gsplat. The Inria/Taming non-commercial licence is now acceptable, but use Taming only if you want its deterministic 'budget' Gaussian count.** — Measured: LichtFeld MCMC 1M at about 7 min on an A4500 versus gsplat at about 16.6 min on a faster 3090. Faster-GS MCMC took 6m17s versus 27m22s for the original on a 4090. Inria with sparse_adam is still 2-4x slower than Faster-GS. The non-commercial licence therefore buys little for training speed; at best it adds Taming's budget mode. _Alt:_ Stay on gsplat for Python-pipeline integration. Use gsplat main (1.6.0-dev) to get the about 30% faster 3DGUT path when training on fisheye frames.

## Load-bearing findings

- [high] Spark 2.x's default LoD render budgets, by device, are effectively the ceiling for what is drawn per frame: 500K Oculus/Quest, 750K Vision Pro, 1M Android, 1.5M iOS, 2.5M desktop. GPU page pool (maxPagedSplats): desktop 16,777,216; iOS 6,291,456; other mobile 8,388,608. lodSplatScale multiplies the budget. — https://sparkjs.dev/docs/lod-getting-started/ https://sparkjs.dev/docs/spark-renderer/ https://sparkjs.dev/docs/new-spark-renderer/
- [high] Spark's non-LoD guidance is: Quest 3 at most 1M splats; Android phone 1-2M; iPhone 1-3M; computer 1-5M (10-20M+ on some desktops). SplatAccumulator overhead becomes a bottleneck around 1M splats. A high devicePixelRatio costs fill-rate. — https://sparkjs.dev/docs/performance/
- [high] No published, measured Spark 2.x fps exists for phones, Intel Iris Xe or AMD integrated GPUs, nor for LoD on vs off, SH0 vs SH3, or native vs capped DPR. The only Spark measurements found are: sort of 1M splats in 4-6 ms on desktop (issue #117, Jul 2025); about 10 fps on an M4 MacBook Air with pre-LoD 0.1.x (issue #202, Oct 2025); 2.8M splats slower than GaussianSplats3D (issue #225, Nov 2025, no numbers). Changelog 2.2.0 (11 Sep 2026): up to 14% fps gain, about 20% faster sort. — https://github.com/sparkjsdev/spark/issues/117 https://github.com/sparkjsdev/spark/issues/202 https://github.com/sparkjsdev/spark/issues/225
- [high] PlayCanvas Engine 2.19 (SuperSplat), measured WebGL2 vs WebGPU fps. iPhone 13 Pro Max, 642x1126 canvas: 1M 38.1/77.6; 2M 35.5/73.2; 3M 25.5/52.7; 4M 20.4/42.4. Apple M4 Max, 1298x962: 1M 137.2/138.7; 2M 140.4/153.6; 3M 124.8/135.5; 4M 113.6/146; 10M 48.1/124.1; 35M 13.3/75.8. — https://blog.playcanvas.com/new-in-supersplat-webgpu-and-streaming-bring-huge-performance-wins/ https://radiancefields.com/supersplat-ships-compute-based-webgpu-rendering-and-automatic-streamed-lod
- [medium] Measured frame times on Android, iPhone and iGPU come only from research web viewers (WebSplatter paper, Feb 2026). On the 1.06M bicycle-c scene: Snapdragon 8 Gen 3 / Adreno 750 is about 30 fps (WebGPU, 33.6 ms), 18 fps for antimatter15 WebGL (55.3 ms) and 13 fps for GaussianSplats3D (76.4 ms). Snapdragon 865 / Adreno 650 is about 9.5 fps (105 ms), with GaussianSplats3D at 183 ms. iPhone 15 Pro Max is 38.5 ms (about 26 fps). — https://arxiv.org/html/2602.03207
- [high] Spark GPU memory per splat: 16 B at SH0; 24 B with SH1 (+8 B, Sint7); 40 B with SH2 (+16 B, Sint8); 56 B with SH3 (+16 B, Sint6). On iOS the full 6.29M paged pool is therefore about 101 MB at SH0, 151 MB at SH1 and 352 MB at SH3. — https://sparkjs.dev/docs/packed-splats/ https://sparkjs.dev/docs/spark-renderer/
- [medium] iOS Safari has no fixed per-tab memory limit. Reported reload thresholds are about 3 GB on iPhone 15 Pro/Pro Max and about 1.5-3 GB on iPhone 12 Pro (it drifts down over days after a reboot). Low-RAM devices on iOS 26.2 crash at about 100 MB (3rd-gen iPhone SE) and about 200 MB (8th-gen iPad) in a JS-array test. A Spark reviewer stated that iOS Safari allows about 380 MB of GPU memory per tab. — https://developer.apple.com/forums/thread/761666 https://lapcatsoftware.com/articles/2026/1/7.html https://github.com/sparkjsdev/spark/pull/122
- [medium] SOG download size at SH3 is about 10.5-14 MB per million splats (measured). SH0 is not measured; my estimate is about 8-11 MB/M. Because SOG stores higher-order SH as a 64K-entry palette with 16-bit labels, SH1-SH3 add only about 2-3 MB/M, so SOG makes SH nearly free in download size. — https://blog.playcanvas.com/playcanvas-open-sources-sog-format-for-gaussian-splatting/ https://developer.playcanvas.com/user-manual/gaussian-splatting/formats/sog/ https://radiancefields.com/shrinking-3dgs-file-size
- [medium] SPZ v3 download size at SH3 is about 20-26 MB per million splats. SH0 is not measured; my estimate is about 10-15 MB/M. — https://www.worldlabs.ai/blog/spark-2.0 https://github.com/nianticlabs/spz https://note.com/izutsuya/n/nc0ada1ec35be?hl=en
- [medium] Spark .rad (build-lod, gzip), measured: 16.0 B per splat for non-SH data and 19.6 B for SH3, i.e. about 16 MB/M at SH0 and about 35.6 MB/M at SH3. An open (unmerged) zstd PR brings SH to 9.8 B, about 25.8 MB/M total. The LoD tree adds about 30-40% more splats than the input. Chunks are 64K splats and are fetched by HTTP Range request. — https://github.com/sparkjsdev/spark/pull/433 https://sparkjs.dev/docs/lod-getting-started/ https://www.worldlabs.ai/blog/spark-2.0
- [high] gsplat MCMC, measured, 30k steps on Mip-NeRF360 (data factor 4 outdoor / 2 indoor, about 1.0-1.6 MP images, close to the 1600 px target), A100: 1M Gaussians 1.98 GB / 15.4 min; 2M 3.43 GB / 21.8 min; 3M 4.99 GB / 27.6 min. Default densification (3.24M) uses 5.62 GB / 19.4 min. Memory grows about 1.5 GB per extra million, which extrapolates to about 6.5 GB at 4M. — https://docs.gsplat.studio/main/tests/eval.html https://arxiv.org/html/2409.06765 https://github.com/nerfstudio-project/gsplat/blob/main/examples/benchmarks/mcmc.sh
- [high] On a consumer RTX 3090, gsplat MCMC 1M averaged 995 s (16.6 min) at 1.37 GiB peak, and default densification took 1384 s at 4.56 GiB (Mip-NeRF360, 7 scenes). VkSplat (Vulkan, Apache-2.0, Windows/AMD/Intel) took 285 s at 0.93 GiB for MCMC 1M and fits 9M SH3 Gaussians in 8 GB. — https://arxiv.org/html/2605.00219v1 https://github.com/harry7557558/vksplat
- [medium] There are counter-examples where VRAM blows up. One user reported gsplat MCMC at about 13 GB for 2M splats versus about 4 GB for the default strategy (scene and resolution unknown, May 2025). LichtFeld on an RTX 5090 with 3840 px frames from a 360 camera (946 images) grew from 4.4 GB to 31 GB in 500-900 iterations and ran out of memory. The suggested fix was max_width 1920. — https://github.com/nerfstudio-project/gsplat/pull/238 https://github.com/nerfstudio-project/gsplat/issues/444 https://github.com/nerfstudio-project/gsplat/issues/487
- [medium] LichtFeld Studio MCMC 1M at 30k steps on an RTX A4500 (Ampere, 20 GB, roughly comparable to a 3080 Ti Laptop) took 5m00s-7m59s per Mip-NeRF360 scene, 6m55s on average. ImprovedGS+ 1M averaged about 5m04s; full ImprovedGS+ (1.69M) about 6m54s. — https://arxiv.org/html/2603.08661v1 https://github.com/MrNeRF/LichtFeld-Studio https://radiancefields.com/platforms/lichtfeld-studio
- [high] Comparison on RTX 4090, Mip-NeRF360, 30k steps (Faster-GS, CVPR 2026): Inria 3DGS 18m44s / 8.8 GiB / 2.74M; Taming-3DGS 10m49s / 8.9 GiB; Faster-GS 4m31s / 6.1 GiB. Original 3DGS-MCMC 27m22s / 8.9 GiB versus Faster-GS MCMC 6m17s / 7.2 GiB. On an RTX 3090: Inria 23m46s versus Faster-GS 6m03s. Faster-GS is Apache-2.0, supports Windows and MCMC. — https://arxiv.org/html/2602.09999v1 https://github.com/nerficg-project/faster-gaussian-splatting https://arxiv.org/html/2406.15643
- [low] Estimate for the RTX 3080 Ti Laptop (GA103, 16 GB): gsplat MCMC at about 1.6 MP takes roughly 25-30 min at 1M, 35-40 min at 2M, 45-55 min at 3M and 55-65 min at 4M, with peak VRAM of about 2-7 GB plus any GPU-cached images. LichtFeld or Faster-GS would take roughly 8-15 min for 1-3M. packed=True should not be needed below 4M at 1600 px. — https://arxiv.org/html/2605.00219v1 https://docs.gsplat.studio/main/tests/eval.html https://arxiv.org/html/2603.08661v1

## Key numbers

- Spark default lodSplatCount (Oculus / Vision Pro / Android / iOS / desktop): 500K / 750K / 1M / 1.5M / 2.5M (https://sparkjs.dev/docs/lod-getting-started/)
- Spark maxPagedSplats (desktop / iOS / other mobile): 16,777,216 / 6,291,456 / 8,388,608 (https://sparkjs.dev/docs/spark-renderer/)
- Spark GPU bytes per splat SH0/SH1/SH2/SH3: 16 / 24 / 40 / 56 B (https://sparkjs.dev/docs/packed-splats/)
- PlayCanvas iPhone 13 Pro Max fps, WebGL2 / WebGPU, at 1M / 2M / 3M splats (642x1126): 38.1/77.6, 35.5/73.2, 25.5/52.7 (https://blog.playcanvas.com/new-in-supersplat-webgpu-and-streaming-bring-huge-performance-wins/ (3 Jun 2026))
- Research WebGPU viewer, 1.06M splats, frame time: Snapdragon 8 Gen 3 / Snapdragon 865 / iPhone 15 Pro Max: 33.6 ms / 105.2 ms / 38.5 ms (https://arxiv.org/html/2602.03207 (Feb 2026))
- Spark CPU sort, 1M splats (desktop): 4.1-6.0 ms (https://github.com/sparkjsdev/spark/issues/117 (Jul 2025))
- SOG size SH3: about 10.5-13.75 MB per 1M splats (https://blog.playcanvas.com/playcanvas-open-sources-sog-format-for-gaussian-splatting/; https://radiancefields.com/shrinking-3dgs-file-size)
- SPZ v3 size SH3: about 20-26 MB per 1M splats (https://www.worldlabs.ai/blog/spark-2.0; https://www.polyvia3d.com/formats/spz)
- .rad size per splat (gzip): non-SH / SH3: 16.0 B / 19.6 B (about 16 / 35.6 MB per M); with zstd (unmerged) SH 9.8 B (https://github.com/sparkjsdev/spark/pull/433)
- iOS Safari tab reload threshold: about 3 GB iPhone 15 Pro; 1.5-3 GB iPhone 12 Pro; about 100-200 MB low-RAM devices (iOS 26.2) (https://developer.apple.com/forums/thread/761666; https://lapcatsoftware.com/articles/2026/1/7.html)
- gsplat MCMC 1M / 2M / 3M peak VRAM and time (A100, Mip-NeRF360, 30k): 1.98 GB 15.4 min / 3.43 GB 21.8 min / 4.99 GB 27.6 min (https://docs.gsplat.studio/main/tests/eval.html)
- gsplat MCMC 1M on RTX 3090 (time, VRAM): 995 s, 1.37 GiB; VkSplat 285 s, 0.93 GiB (https://arxiv.org/html/2605.00219v1)
- LichtFeld MCMC 1M per scene on RTX A4500: 5m00s-7m59s (avg 6m55s) (https://arxiv.org/html/2603.08661v1)
- Inria 3DGS / Taming / Faster-GS on RTX 4090 (time, VRAM): 18m44s 8.8 GiB / 10m49s 8.9 GiB / 4m31s 6.1 GiB (https://arxiv.org/html/2602.09999v1)
- 3DGS-MCMC original vs Faster-GS MCMC on RTX 4090: 27m22s 8.9 GiB vs 6m17s 7.2 GiB (https://arxiv.org/html/2602.09999v1)
- LichtFeld VRAM blow-up with 3840 px 360-camera frames (RTX 5090): 4.4 GB to 31 GB in 500-900 iterations; fix max_width 1920 (https://github.com/pgodlews/OSVplat/issues/7 (28 Sep 2026))

## Still unknown

- Measured Spark 2.x fps on any phone (Adreno 6xx/7xx, Mali-G7x, A14-A18) or integrated laptop GPU (Iris Xe, Radeon 680M/780M), with LoD on/off, at native vs capped DPR.
- Measured rendering cost of SH0 vs SH1-SH3 in Spark or PlayCanvas, in fps (only memory/byte costs are known).
- PlayCanvas WebGPU vs WebGL2 fps on Android and on Windows iGPUs (only M4 Max and iPhone 13 Pro Max published).
- Measured SOG and SPZ sizes at SH0/SH1/SH2. Only SH3 is measured; SH0 figures are derived estimates. .rad SH1/SH2 sizes also unmeasured.
- Whether the 18.3M splat count in Spark PR #433 includes LoD interior nodes, which affects .rad MB per million input splats.
- A hard, verified iOS Safari GPU-memory limit per tab. The about 380 MB figure is a single unverified comment, and process limits vary from 100 MB to 3 GB by device and uptime.
- Measured gsplat MCMC VRAM/time on a 12-16 GB consumer or laptop GPU at 2-4M Gaussians. Only the A100 (docs) and the 3090 at 1M (VkSplat) are measured, and no measurement isolates packed=True.
- Brush training benchmarks (none published); LichtFeld VRAM figures (none published); LuciadRIA splat performance (nothing found).
- Babylon.js forum, r/GaussianSplatting and Iris Xe-specific sources were not searched because the shared web-search budget ran out. A follow-up search could fill this gap.

## Questions for user

- Which phones and laptops will coworkers actually open the viewer on (models or GPU names)? The benchmark matrix should target those, since published Spark data for phones and iGPUs does not exist.
- Is close-up desktop detail important enough to justify a separate SH3 / 3M+ variant, or is one SH0/SH1 file at about 2M splats enough for the first 10x10 m forest test?
- Would you accept PlayCanvas/SuperSplat (WebGPU) as a fallback viewer if Spark (WebGL2) is too slow on phones, or must the viewer stay three.js/Spark?
- Can you ask the Luciad team whether LuciadRIA supports Gaussian splats (3D Tiles / KHR_gaussian_splatting), and for any performance figures?
