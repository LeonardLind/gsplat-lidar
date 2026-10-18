# gap: forest-360-evidence

## Summary

I found no peer-reviewed study or detailed practitioner report (2023 to Oct 2026) that does exactly what this project plans: a consumer Insta360 X4/X5 on a handheld SLAM LiDAR (BLK2GO or similar), under canopy, trained as a 3DGS. I also found no published BLK2GO drift or loop-closure numbers for any forest, Brazilian or otherwise. The evidence comes as pieces. Note: the shared web-search budget ran out partway through. After that I only fetched known primary URLs. MDPI, ScienceDirect and ResearchGate returned 403, so several numbers come from search-result abstracts and not from the full papers.

Closest analogues (table: study | sensors and capture | SfM and registration | accuracy and quality | failure modes):
1. Zero-shot UAV nav via relightable 3DGS (arXiv 2602.07101, 2026) | handheld rig with a stereo fisheye camera pair, LiDAR and RTK; 10 forest scenes of about 60x60 m | RTK poses plus LiDAR point cloud to initialise 3DGS (no SfM) | trained on an RTX 3090 (24 GB) | "geometric noise". This is the nearest copy of our setup and it skips SfM entirely.
2. LiDAR-guided semantic 3DGS forest digital twin (Remote Sens. 18(11):1696, 2026) | handheld laser scanner plus UAV images | ICP refinement; LiDAR anchors to initialise 3DGS; separate handling of trunk and canopy | PSNR 24.94 / SSIM 0.773 / LPIPS 0.231; DBH R² 0.848, RMSE 2.705 cm | trunk swelling and floaters if initialisation is poor.
3. Insta360 Pro 2 videogrammetry (Ecological Informatics 2025, S1574954125004078) | 6-fisheye professional rig, video | SfM compared with TLS | M3C2 vs TLS mean 0 cm, SD 15–22 cm; tree position error 5.2–18.8 cm; DBH error 0.9–1.9 cm | full text not reachable.
4. He et al., UPenn (arXiv 2505.03093 v3, Apr 2026) | consumer Insta360 (model not stated) on a backpack tower plus drone orbits | Metashape on native equirectangular frames; scale from a 1 m ArUco board | 61 captures of 43 trees; median absolute relative DBH error 5–9%, 2–4% worse than LiDAR (Ouster + Faster-LIO) | motion blur, drift, partial visibility.
5. RedwoodNeRF (Korycki et al., arXiv 2410.07418) | iPhone 14 with ARKit poses; 166 and 847 images | no COLMAP; Nerfacto, 15 min | DBH RMSE 1.68 cm (convex hull) vs 4.27 cm (cylinder fit); LIO-SAM MLS 2.15 cm | dark understory; stems under 8 cm dropped. Code and data are open.
6. Tian, Chen and Huang (Remote Sens. 17(9):1520; arXiv 2410.05772) | photogrammetry vs NeRF vs 3DGS, with LiDAR reference | COLMAP took over 450 min vs 12–15 min for NeRF | 3DGS gave the worst DBH (sparse, clumped trunk points, underestimates) | photogrammetry produced duplicated trunks in complex stands.
7. Karjalainen et al., FGI (arXiv 2501.12073; boreal, Evo, Finland) | RealSense D435 stereo under the canopy | Metashape aligned every image; 3 GCPs cut planimetric RMSE from 11.4 cm to 1.4 cm | DBH RMSE 3.3–4.0 cm; 61–79% of trees captured | thin dry spruce branches.
Aerial only: TreeDGS (DBH 4.79 cm vs ULS 7.66 cm) and ForestSplat (mangrove canopy height MAE 0.17 m). A 2026 commentary (Lyu et al.) gives NeRF/3DGS DBH RMSE of 1.68–5 cm vs 1–4.5 cm for LiDAR, and warns that invented geometry in occluded areas can bias results by 5–10%.

SLAM drift:
- BLK2GO, IGARSS 2024: outdoors without man-made features the cloud was "considerably distorted" by orientation drift. Correcting it against TLS gave about ±10 cm.
- Another BLK2GO assessment: stationary RMSE under 2 cm, but mobile runs show systematic errors. It recommends scale-factor adjustment and walking the path again in reverse.
- NavVis VLX / BLK2GO study (Remote Sens. 2024): outdoor error 10–60 mm vs 5 mm indoors.
- BLK2GO vs RTC360 on a structure (not a forest, 2026): mean deviation 1.2 cm vertical, 4.8 cm horizontal.
- Tropical, Thailand (Kaewjampa et al. 2026, scanner processed in GreenValley LiDAR360): loop-closure residuals 3.2 cm (open forest) and 4.7 cm (closed forest); DBH RMSE 1.82 / 7.01 cm; 6.38 m GNSS bias; reflective-tape anchor trees found automatically through the intensity channel.
- Boreal, GeoSLAM ZEB: tree position RMSE 25–28 cm; graph-SLAM correction took internal mismatch from 0.7 m to 1 cm.
- Practitioners keep sessions under about 10 min under dense canopy (XGRIDS L2 Pro case study; LiBackpack study in Slovakia, 2026).
- Hexagon's R-evolution used a BLK2GO in Costa Rican rainforest (La Gamba) but published no accuracy numbers. That team is a possible internal contact.

Research methods: WildGaussians, RobustSplat(++) and SpotLessSplats are tested only on transient and lighting benchmarks (NeRF On-the-go, RobustNeRF, PhotoTourism). None has a forest benchmark. ForestSplats is not about forests; it handles transient objects and builds on WildGaussians. Wind is the main unsolved problem: a 2026 workshop paper ("Wind on Trees") shows that monocular reconstruction of wind-blown vegetation is badly underconstrained. Hierarchical 3DGS was tested on Windows 11, peaks at 11–16 GB per chunk, uses 50x50 m chunks and was captured with a helmet of 6 GoPro HERO6 cameras. It, CityGS and Horizon-GS are overkill for a 10x10 m plot; Horizon-GS becomes relevant once drone imagery is added. Now that the licence is not a blocker, Inria-licensed methods that model surfaces (RaDe-GS, which TreeDGS uses, or 2DGS/PGSR) are better than plain 3DGS for trunks. MASt3R-SfM (CC BY-NC-SA, now acceptable) and VGGT are fallbacks if COLMAP fails, but neither has been tested on forests.

Reusable open pipeline: lichtfeld-360-plugin (GPL-3.0, Windows). It reads .insv from X5/X4, picks sharp frames, masks the operator with SAM 3, and solves natively in COLMAP 4.1 (equirectangular, dual-fisheye or fisheye, with SIFT/ALIKED features and LightGlue matching). It outputs COLMAP format plus transforms.json, but cannot import LiDAR data or external poses. Train in LichtFeld Studio (GPLv3; MCMC, bilateral-grid appearance model, 3DGUT for distorted cameras) or gsplat/3DGRUT (Apache; Windows since July 2025). Then align SfM to the BLK2GO cloud with Sim(3) + ICP and initialise from LiDAR points. RedwoodNeRF/TreeTool cover DBH checks. Side note: Insta360 Spatial Capture now also runs on the X5 and X4 Air (cloud processing, 2-minute clips, 4 scenes/month free). It is fine for a quick visual comparison but gives no metric poses.

## Plan changes

- Make 'LiDAR-anchored camera poses' the primary design. SfM-only registration becomes a fallback, plus a Sim(3)+ICP step with C2C/M3C2 QA against the BLK2GO cloud.
- Add a time-sync and trajectory-export step (BLK2GO trajectory from Cyclone REGISTER 360 PLUS) to support pose priors and validate the 125 MHz tick hypothesis.
- Change the BLK2GO export path to E57/LGS with intensity; do not rely on 3DR LAS crops (intensity 0).
- Capture protocol: forward plus reverse loop, ≤1 m/s, sessions under 10 min, 3–5 dual-visible targets, calm overcast weather, sharpness-based frame selection, SAM 3 operator masking.
- Pipeline: lichtfeld-360-plugin, then COLMAP 4.1 native fisheye/equirect, then align to BLK2GO, then LichtFeld Studio / gsplat with 3DGUT, MCMC and bilateral grid, initialised from LiDAR points.
- Add evaluation metrics: held-out PSNR/SSIM/LPIPS (literature forest baseline about 25 dB / 0.77 / 0.23), M3C2 SfM-vs-LiDAR (literature SD 15–22 cm for Insta360 Pro 2 vs TLS; aim for ≤5 cm after LiDAR anchoring), DBH on 5–10 stems from LiDAR only.
- Leave Hierarchical 3DGS / CityGS / Horizon-GS out of phase 1. Reserve Horizon-GS-style aerial+ground fusion for the drone phase.
- Tropical phase: assume GNSS is useless (5–15 m error), plan stem/girth-based or target-based anchoring, and plan ≤10 m trajectory spacing.

## Recommendations

- **Treat the BLK2GO as the metric reference. Solve 360 SfM with lichtfeld-360-plugin (COLMAP 4.1, native dual-fisheye or fisheye), then fit a Sim(3) transform and refine with ICP onto the BLK2GO cloud. Initialise 3DGS from BLK2GO points. Plan a fallback that uses BLK2GO trajectory poses (time-synced) as pose priors if COLMAP fragments under canopy.** — Every forest analogue that worked well used external metric poses (ARKit, RTK/LiDAR) or LiDAR initialisation. Pure SfM needed GCPs for cm-level scale, and COLMAP was slow and fragile on vegetation. _Alt:_ Metashape (spherical camera model) if a licence is available; MASt3R-SfM / VGGT (non-commercial OK) for broken segments; RealityScan.
- **Train with LichtFeld Studio (Windows, MCMC, bilateral grid, 3DGUT fisheye) or gsplat with 3DGUT on native fisheye frames instead of stitched equirectangular.** — Avoids stitch seams (Seam360GS, ICCV 2025, documents dual-fisheye seam errors). The bilateral grid absorbs exposure swings under canopy, and all of these run on Windows with 16 GB at 10x10 m scale. _Alt:_ Inria 3DGS / RaDe-GS / 2DGS / PGSR (non-commercial licence now OK) when trunk geometry matters; Hierarchical 3DGS / Horizon-GS only when adding drone layers.
- **Do not take DBH or geometry from the splat. Use LiDAR for trunk metrics and navigation, and the splat for appearance only. Validate the splat against LiDAR with cloud-to-cloud (M3C2) and held-out PSNR.** — 3DGS gave the worst DBH in the Tian et al. comparison, and the commentary warns of 5–10% bias from invented geometry in occluded areas. _Alt:_ If splat geometry is needed, use LiDAR-regularised or surface methods (RaDe-GS, 2DGS) and check against BLK2GO stems.
- **Capture protocol: calm, overcast day; walk at 1 m/s or slower; close the loop at the start point; walk the same loop again in reverse; keep each BLK2GO session under 10 min; stay within about 10 m of all target trees; place 3–5 targets visible to both LiDAR and camera (ArUco/checkerboard on a rigid board plus spheres or reflective tape) for scale and registration checks.** — Reverse repetition is recommended specifically for BLK2GO mobile errors. GCPs cut SfM planimetric error from about 11 cm to about 1.4 cm. Wind is the main unsolved failure mode, and drift grows past about 10 min under canopy. _Alt:_ Natural tie features (stems via girth matching) when targets are not possible, which is often the case in tropical plots.
- **Export BLK2GO data with intensity and trajectory from Cyclone REGISTER 360 PLUS (E57/LGS), not the Cyclone 3DR LAS crop.** — The sample LAS has intensity = 0 everywhere, which rules out reflective-tape or target detection (used in the tropical study) and intensity-based QA. The trajectory is needed for pose priors and time sync. _Alt:_ Use RGB-based target detection if intensity really cannot be exported.
- **Contact Hexagon R-evolution (La Gamba, Costa Rica BLK2GO rainforest work) and the Luciad team for BLK2GO tropical drift experience before the tropical phase.** — No published BLK2GO forest drift numbers exist; R-evolution has unpublished operational BLK2GO rainforest data. _Alt:_ Ask Leica support for GrandSLAM forest guidance.

## Load-bearing findings

- [medium] No study or practitioner report found that combines a consumer Insta360 X4/X5 with a BLK2GO (or other handheld SLAM LiDAR) under forest canopy for SfM/3DGS. The closest is a handheld rig with stereo fisheye cameras, LiDAR and RTK, used for 10 forest scenes of about 60x60 m, where 3DGS was initialised from LiDAR points and RTK camera poses without SfM. — https://arxiv.org/html/2602.07101 https://arxiv.org/abs/2602.07101
- [medium] Handheld laser scanning fused with UAV images in a LiDAR-guided semantic 3DGS gives PSNR 24.94 dB, SSIM 0.773, LPIPS 0.231 and DBH RMSE 2.705 cm (R² 0.848) on forest plots. — https://doi.org/10.3390/rs18111696 https://www.mdpi.com/2072-4292/18/11/1696
- [medium] 360-camera forest videogrammetry (Insta360 Pro 2, 6 fisheye lenses) matched TLS with M3C2 mean 0 cm and SD 15–22 cm; tree position errors 5.2–18.8 cm; DBH errors 0.9–1.9 cm. — https://www.sciencedirect.com/science/article/pii/S1574954125004078
- [high] A consumer Insta360 on a backpack tower (and drone orbits) with Metashape on equirectangular frames reached median absolute relative DBH error of 5–9% over 61 acquisitions of 43 trees, 2–4% worse than LiDAR. Metric scale came from a manually measured 1 m ArUco board. — https://arxiv.org/abs/2505.03093 https://arxiv.org/html/2505.03093
- [medium] BLK2GO outdoors without man-made features shows significant orientation drift ('considerably distorted' point cloud). A TLS-referenced correction got it to about ±10 cm. Mobile runs show systematic errors, and scale-factor adjustment plus reverse-repeating the path are recommended (stationary RMSE <2 cm). — https://ieeexplore.ieee.org/document/10641469/ https://www.researchgate.net/publication/383806514_Assessment_of_Slam_Lidar_-_An_Accuracy_Assessment_and_Drift_Anaylsis_of_the_Leica_BLK2GO https://www.mdpi.com/2072-4292/16/17/3256
- [medium] No peer-reviewed BLK2GO forest drift or loop-closure study was found, and none for Brazilian, Amazon or Atlantic forest. The only tropical BLK2GO deployment found is Hexagon R-evolution's La Gamba (Costa Rica) rainforest digital twin, which published no accuracy numbers. — https://lidarmag.com/2024/05/04/digital-twins-open-up-new-possibilities-for-rainforest-conservation/
- [medium] Tropical handheld SLAM (Thailand, LiDAR360 / GreenValley processing) reported loop-closure residuals of 3.2 cm (open dry dipterocarp forest) and 4.7 cm (closed dry evergreen forest). DBH RMSE was 1.82 cm and 7.01 cm, GNSS bias under canopy was 6.38 m, and reflective-tape anchor trees were detected automatically through the intensity channel. — https://doi.org/10.3390/rs18121920 https://www.mdpi.com/2072-4292/18/12/1920
- [high] ForestSplats (WACV 2026) is not a forest method. It is a transient-object 'in-the-wild' 3DGS built on WildGaussians, and its code includes only the masking and densification strategies. — https://github.com/WongiPark0628/ForestSplats https://arxiv.org/abs/2503.06179 https://github.com/jkulhanek/wild-gaussians
- [high] Wind-driven vegetation is the main open problem for 3DGS: monocular reconstruction is badly underconstrained, a moving canopy gives few reliable correspondences, and almost the whole scene moves. — https://arxiv.org/abs/2609.17810 https://realhorizons.ai/blog/outdoor-gaussian-splatting-capture-guide/
- [high] lichtfeld-360-plugin is a reusable open pipeline for Insta360 X5/X4: .insv demux and stitch, sharpness-based frame selection, SAM 3 operator masking, COLMAP 4.1 native solves (equirectangular, dual-fisheye or single fisheye; SIFT/ALIKED features, LightGlue matching), output as COLMAP plus transforms.json. It is GPL-3.0, Windows-focused, and has no LiDAR or external-pose import. — https://github.com/alexmgee/lichtfeld-360-plugin https://github.com/colmap/colmap/releases
- [high] LichtFeld Studio (GPLv3) runs on Windows: free to build from source, prebuilt binaries via the paid LichtFeld Portal. It needs an NVIDIA GPU with compute capability 7.5+ and driver 570+ (CUDA 12.8). It supports MCMC, a bilateral-grid appearance model and 3DGUT for distorted (fisheye) cameras. 3DGRUT (Apache-2.0) has had full Windows support since July 2025, and gsplat also supports 3DGUT. — https://github.com/MrNeRF/LichtFeld-Studio https://github.com/nv-tlabs/3dgrut

## Key numbers

- Insta360 Pro 2 forest SfM vs TLS, M3C2 error: mean 0 cm, SD 15–22 cm; DBH error 0.9–1.9 cm; tree position 5.2–18.8 cm (Ecological Informatics 2025, S1574954125004078)
- Consumer Insta360 + Metashape, DBH median absolute relative error: 5–9% (61 acquisitions, 43 trees); 2–4% worse than LiDAR (arXiv 2505.03093)
- LiDAR-guided forest 3DGS image quality: PSNR 24.94 dB, SSIM 0.773, LPIPS 0.231; DBH RMSE 2.705 cm (R² 0.848) (Remote Sens. 18(11):1696)
- NeRF (iPhone + ARKit) DBH RMSE: 1.68 cm convex hull vs 4.27 cm cylinder; MLS LIO-SAM 2.15 cm (arXiv 2410.07418)
- COLMAP vs NeRF processing time, forest plot: >450 min vs 12–15 min (arXiv 2410.05772 / Remote Sens. 17(9):1520)
- Boreal under-canopy SfM planimetric RMSE without vs with 3 GCPs: 11.36–11.72 cm vs 1.41 cm (arXiv 2501.12073)
- BLK2GO outdoor accuracy (non-forest): 10–60 mm outdoor vs 5 mm indoor; drift-corrected vs TLS about ±10 cm (Remote Sens. 16(17):3256; IGARSS 2024 (IEEE 10641469))
- BLK2GO vs RTC360 deviation (structure): mean 1.2 cm vertical, 4.8 cm horizontal (Springer chapter 10.1007/1345_2026_339)
- Tropical handheld SLAM loop-closure residual: 3.2 cm (open dry dipterocarp) / 4.7 cm (closed dry evergreen) (Remote Sens. 18(12):1920 (Thailand))
- GNSS bias under closed tropical canopy: 6.38 m (typical 5–15 m) (Remote Sens. 18(12):1920)
- ZEB REVO / Horizon tree-position RMSE: 25.3 / 28.4 cm (Chudá et al. 2020, ISPRS Archives)
- Max practical session under dense canopy before drift issues: about 10 min (XGRIDS L2 Pro case study; LiBackpack Slovakia 2026)
- Dense-stand tree detection distance for handheld MLS: all large trees detected within 10 m of the trajectory (Kuželka 2025, ISPRS J. (S0924271625003831))
- Hierarchical 3DGS peak memory per chunk: 2–5 / 8–10 / 11–16 GB (coarse / chunk / hierarchy), V100 (arXiv 2406.12080)
- Forest 3DGS training GPU in nearest analogue: RTX 3090 24 GB, ten 60x60 m scenes (arXiv 2602.07101)
- VGGT memory (background, pre-May-2026 fix): about 11.4 GB @50 frames, about 21 GB @100 frames (H100); 2–3x more frames after fix (VGGT README (memory) + github.com/facebookresearch/vggt)
- Insta360 Spatial Capture limits: X6/X5/X4 Air; 2 min clips; 4 free scenes/month; 1–2 h cloud processing (dronedj.com 2026-09-29)

## Still unknown

- No published registration rate (fraction of frames registered) for consumer Insta360 X4/X5 under forest canopy, boreal or tropical.
- No peer-reviewed BLK2GO drift or loop-closure numbers in any forest, including Brazilian, Amazon or Atlantic forest.
- Walking pattern, frame count, SfM tool and registration details of the Insta360 Pro 2 forest study (full text blocked).
- Which robust in-the-wild 3DGS method (WildGaussians, RobustSplat++, SpotLessSplats, ForestSplats) works best on forest data; no forest benchmark exists. WildGaussians appears Linux-focused (Windows untested).
- Whether MASt3R-SfM or VGGT handle long under-canopy 360/fisheye sequences; no forest results; exact frames-per-16 GB after the May 2026 VGGT fix not verified.
- Scanner model in the Thailand tropical loop-closure study (LiDAR360 suggests GreenValley).
- Capture device and exact RMSEs in Tian et al. 2025 (PDF not parseable).
- Licence of RobustSplat and Hierarchical 3DGS repos (LICENSE.md present; probably Inria-derived, not verified).
- Web search budget ran out partway through the research. Searches for 2DGS/PGSR forest trunk studies, DigiForests camera details and r/GaussianSplatting forest threads were not done.

## Questions for user

- Which X5 recording mode will you use (8K30 360 video vs 5.7K/4K at higher fps, or timelapse photos)? Can you record the raw .insv dual-fisheye files?
- Can Cyclone REGISTER 360 PLUS export the BLK2GO trajectory with timestamps and an E57 with intensity for the forest scans?
- Can you place 3–5 targets (ArUco/checkerboard board plus spheres or reflective tape) in the Swedish test plot, and walk the loop twice (forward and reverse)?
- Do you want to contact Hexagon R-evolution (La Gamba, Costa Rica BLK2GO rainforest project) for unpublished tropical BLK2GO drift experience?
