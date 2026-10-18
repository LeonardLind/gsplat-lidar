# gap: aerial-ground-forest-evidence

## Summary

Bottom line: for a 10x10 m Swedish forest plot, a consumer-drone splat adds one thing that neither the BLK2GO/Insta360 capture nor Lantmäteriet's open data provides: a same-day, centimetre-scale top-of-canopy layer (crown-top shape and colour). Under a closed Nordic canopy it adds almost nothing at walking height (stems, forest floor). Lantmäteriet's open data cover context and coarse georeferencing for free. Recommendation: keep the drone as an optional, separately registered aerial layer, skip it for the first test unless the viewer will offer above-canopy viewpoints, and if it is flown, run our own with/without-aerial ablation, because no paper found reports one.

Literature (2023-2026), what was found:
(1) TreeDGS (arXiv 2601.12823; Remote Sensing 18(6):867, 2026). Aerial-only 3DGS in a managed loblolly pine stand in Arkansas. DJI Matrice 4E (an enterprise drone, not consumer), oblique and mixed views at 70/90 m, GSD about 1.84 cm. 10 plots of 0.2 acre; 210 of 458 field stems paired. DBH RMSE 4.79 cm vs 7.66 cm for UAV LiDAR (Hesai XT-32, about 1407 pts/m²). Trees had a mean of only 8.2 unoccluded views, with the trunk about 15 px wide. The authors skipped SfM/MVS because there were too few breast-height trunk points. No code released.
(2) LiDAR-Guided Semantic 3DGS (Remote Sensing 18(11):1696, May 2026). The closest match to our setup: handheld LiDAR plus UAV images, with LiDAR anchors used to initialise the Gaussians. 3 plots; PSNR 24.94, SSIM 0.773, LPIPS 0.231; DBH RMSE 2.705 cm. The authors limit it to open-canopy urban and campus forests. The full text was blocked (MDPI 403), so sensors, altitudes, pose tying, any ablation without UAV images, and code are all unknown.
(3) Castorena (arXiv 2401.15029, MICAI 2023). Ponderosa and mixed conifer, New Mexico. Mavic 2 Pro 4K images plus ALS (about 10 pts/m²) plus TLS; Instant-NGP with a LiDAR depth loss. Tree-count RMSE per plot: 10.61 from imagery-only neural field, 1.77 from TLS, 1.32 from fused. Key quote: neural fields cannot create information behind occluded areas.
(4) Tian, Chen, Huang (Remote Sensing 17(9):1520, 2025). Urban forest plots, smartphone and UAV sequences reconstructed separately. NeRF had ground errors when views were limited. 3DGS gave sparse trunk points. The drone sets gave more accurate tree parameters than ground phone images.
(5) Under-canopy terrain NeRF (WACV 2026 CV4EO workshop, arXiv 2601.22861). Public AOS drone data, conifer and broadleaf. Instant-NGP with a low-light loss and canopy removal produces canopy-free ground views. Person-detection AP 80.5%, or 89.6% excluding low-quality scenes. It needs near-nadir views, about 20-25 samples per ground point, 1-2 cm GSD and diffuse light; dense broadleaf canopy defeated it in 3 scenes. So a drone can see the floor through gaps, but only with a special dense nadir capture.
(6) Sapling-NeRF (arXiv 2602.22731, Oxford; Evo, Finland and Wytham Woods). Ground-only: handheld LiDAR SLAM plus cameras, COLMAP poses scaled to SLAM by Umeyama. A good template for our ground pipeline.
(7) Aerial-ground matching (arXiv 2509.19898) and similar aerial-to-ground 3DGS work were tested on urban scenes only. Rendering intermediate views gave 3.7x and 5.4x more correct matches; no forest demonstration was found.

No paper found reports ground-level novel-view metrics with and without aerial images in a real forest. No tropical-forest UAV+ground splat study was found.

Stem and forest-floor recovery from drone photogrammetry:
- No Swedish or Finnish study was found that measures stem or floor recovery from above-canopy oblique photogrammetry by stand density in Scots pine, Norway spruce or birch.
- Proxies from elsewhere:
  - Ponderosa pine, Colorado: more than 90% of trees detected, but DBH extracted for only more than 40% of trees, and only with off-nadir camera plus crosshatch flights.
  - Birch woodland, Bulgaria: best at about 25 m above canopy with 60° camera tilt; DBH RMSE under 12.5%.
  - Semi-dense urban forest: nadir plus 45° double grid at 1.54 cm GSD; recall 0.90, DBH RMSE 3.02 cm.
  - Czech spruce at 290 trees/ha: all 123 trees found, but only by flying inside the canopy at 8 m.
  - BC conifer: drone-photogrammetry terrain model under 1.5 m RMSE over only 52-57% of the area; vegetation density mattered more than slope.
  - Reviews and Nordic practice (White 2013; Puliti 2015 in Norway; Bohlin 2012 in Sweden): image-matched point clouds capture the outer canopy only, and a LiDAR terrain model is still needed.
- Finnish LiDAR benchmarks (Muhojoki 2024): under-canopy capture beats above-canopy; helicopter ALS lost completeness in difficult plots.

Lantmäteriet open data (checked 2026):
- Laserdata Nedladdning, skog: 1-2 pts/m², scanned 2018 onward; third scan from 2024 in LAS 1.4; covers about 75% of Sweden. Licence CC0 (product pages, OSM wiki). Since 2026-06-01 it is delivered only via a STAC API as COPC LAZ in 10x10 km tiles. Laser data is now treated as personal data (GDPR), so new terms of use must be accepted when ordering; whether CC0 still holds under the new terms is not confirmed.
- Laserdata Nedladdning, NH: 0.5-1 pts/m² (0.25 in the mountains), 2009-2019. Not open: a licence and fee are required (metadata dated 2026-06-15).
- Markhöjdmodell Nedladdning, grid 1+ (1 m terrain model): CC BY 4.0 (metadata 2026-06-22). STAC endpoint api.lantmateriet.se/stac-hojd/v1, COG/GeoTIFF.
- Ortofoto Nedladdning: 0.16 m and 0.4 m, 4-band, from 2019. Free since 2025-02-03 under CC BY 4.0. STAC endpoint api.lantmateriet.se/stac-bild/v1; tiles about 640 MB each.
- Historical orthophotos: CC0.
- Access route for all of these: a Geotorget account plus an API authorisation (OAuth2 consumer key and secret), and a stated intended use for datasets that contain personal data.

What this means at 10x10 m:
- Laserdata Skog gives about 100-200 points over the whole plot.
- The terrain model gives 100 cells.
- The 0.16 m orthophoto gives about 3,900 pixels.
- A consumer drone at 1.5 cm GSD gives about 444k pixels per nadir view, plus oblique crown sides.
- For comparison, the BLK2GO sample is about 1.1e5 pts/m².

So open data cannot replace the canopy-top detail, but that detail only matters if viewers leave the ground. Floor and stems come from the BLK2GO and Insta360 capture. The drone adds the crown tops the ground scanner cannot see, at the cost of hard aerial-ground registration in a forest (repetitive foliage, little shared surface). That registration should rely on shared targets placed in canopy gaps, not on feature matching.

Non-commercial tools: Instant-NGP (NVIDIA non-commercial licence; used by papers 3 and 5) and Inria-licence large-scene 3DGS code (Hierarchical-3DGS, about 16 GB VRAM default) are now acceptable. Their exact licence text was not verified in this pass.

Research limit: the shared web-search budget ran out partway through. After that only known primary URLs were fetched, so the Nordic-specific and tropical evidence is thinner than intended.

## Plan changes

- Downgrade the drone phase from 'planned layer' to 'optional, only if the viewer needs above-canopy views'; drop it from the first Swedish test.
- Add a phase 'Lantmäteriet open-data context': create a Geotorget account, order STAC API authorisation (OAuth2 consumer key and secret) for Markhöjdmodell, Ortofoto and Laserdata skog, accept the GDPR terms of use for laser data, and stream only the plot's bounding box from the COPC/COG tiles (10x10 km laser tiles; about 640 MB orthophoto tiles).
- Do not plan on Laserdata NH (licence and fee required); use Laserdata skog (CC0) instead.
- Viewer: add an optional terrain-plus-orthophoto context layer outside the 10x10 m plot, with the attribution '© Lantmäteriet (CC BY 4.0)' in the viewer.
- Capture protocol (only if a drone is flown): place 3-5 targets in canopy gaps that both the BLK2GO and the drone can see, and check visibility from above before scanning; record the stand type (pine, spruce or birch), approximate canopy cover and leaf state.
- Evaluation: add a with/without-aerial ablation protocol (held-out ground frames plus elevated test views) before any aerial layer counts as useful.
- Georeferencing (optional): the BLK2GO data is in a local frame; consider coarse placement in SWEREF 99 TM by matching the BLK2GO ground to the 1 m terrain model plus a few GNSS points (accuracy limited to roughly decimetres to a metre).

## Recommendations

- **Skip the drone for the first Swedish 10x10 m test; use the BLK2GO + Insta360 splat for all walking-height content.** — No published forest study shows that aerial images improve ground-level novel views. Evidence points to aerial images contributing canopy tops only: imagery-only neural-field tree-count RMSE 10.61 vs 1.32 fused; insufficient SfM trunk points at 70-90 m even in a pine plantation. Swedish spruce and pine stands occlude more. _Alt:_ Fly the drone only if the viewer will offer above-canopy or fly-over viewpoints.
- **Add an open-data context layer from Lantmäteriet: Markhöjdmodell 1 m (CC BY 4.0) for the surrounding terrain mesh, Ortofoto 0.16 m (CC BY 4.0) as a top-down texture, and Laserdata skog (CC0, COPC) for surrounding canopy heights. Show the attribution '© Lantmäteriet'.** — Free, nationwide, georeferenced (SWEREF 99 TM / RH 2000), and enough to place the 10x10 m plot in its landscape and support coarse georeferencing. Laserdata NH is fee-based, so avoid it. _Alt:_ Skip the context layer entirely; or use historical orthophotos (CC0) if the BY attribution is a problem.
- **If a drone is flown later, treat it as a separate canopy-top layer registered via shared targets placed in canopy gaps and visible to both the BLK2GO and the drone. Do not rely on aerial-ground feature matching or a joint splat.** — Aerial-ground matching gains were demonstrated only on urban scenes; forests have repetitive foliage and little shared surface between the top-down drone view and the BLK2GO's crown-underside view. _Alt:_ Register the drone's canopy-top points to BLK2GO tree tops and stems at gap edges with ICP (unproven; low confidence).
- **If a drone is flown, capture: GSD ≤1.5 cm; side overlap over 80%; oblique 45-60° orbits about 20-30 m above canopy plus a dense near-nadir grid; overcast light; leaf-off for birch stands.** — Off-nadir + crosshatch raised DBH extraction above 40%; 60° tilt at 25 m above canopy was best in birch; near-nadir with 20-25 samples per point and diffuse light is needed to see the floor through gaps; ≤1.5 cm and over 80% side-lap help terrain-model replicability. _Alt:_ An enterprise drone at 70-90 m (TreeDGS) gives better trunk measurement but costs more and still sees few trunks.
- **Build an in-house ablation: hold out about 10% of the ground 360 frames plus a few elevated views (for example a pole camera at 3-5 m). Train ground-only vs ground+aerial and compare PSNR/SSIM/LPIPS per view type.** — This is the single most important unknown, and no paper provides it. _Alt:_ Judge the difference visually only (weaker evidence).
- **Consider non-commercial research code where it is clearly better, for example Hierarchical-3DGS (Inria licence) for multi-chunk or aerial+ground scenes on 16 GB, and Instant-NGP-based under-canopy methods. Verify each LICENSE file before use.** — Non-commercial terms are now acceptable for this hobby project; these tools are the published state of the art for large or mixed scenes. _Alt:_ Stay with the permissive gsplat / nerfstudio stack.

## Load-bearing findings

- [medium] No 2023-2026 paper found reports ground-level novel-view metrics for a real forest with vs without aerial images; the value of aerial images at walking height is undemonstrated. — https://arxiv.org/html/2601.12823 https://doi.org/10.3390/rs18111696 https://arxiv.org/html/2401.15029v1
- [high] TreeDGS: aerial-only 3DGS measures DBH in a managed loblolly pine stand from an enterprise drone (DJI Matrice 4E) at 70/90 m with oblique views (GSD about 1.84 cm); DBH RMSE 4.79 cm vs 7.66 cm for UAV LiDAR; SfM/MVS gave too few trunk points to benchmark. — https://arxiv.org/abs/2601.12823 https://arxiv.org/html/2601.12823 https://doi.org/10.3390/rs18060867
- [medium] LiDAR-Guided Semantic 3DGS (Remote Sensing 18(11):1696, 2026) fuses handheld LiDAR with UAV imagery: LiDAR anchors initialise 3DGS, with semantic trunk/canopy regularisation. Average PSNR 24.94 dB, SSIM 0.773, LPIPS 0.231; DBH R² 0.848, RMSE 2.705 cm; limited by the authors to open-canopy urban and campus forests. — https://doi.org/10.3390/rs18111696 https://api.semanticscholar.org/graph/v1/paper/DOI:10.3390/rs18111696
- [medium] In mixed conifer, a neural field trained on UAV imagery alone badly undercounts sub-canopy trees (tree-count RMSE 10.61 per plot) vs TLS (1.77) and the fused neural field plus ALS plus TLS (1.32). The authors state that neural fields cannot create information behind occluded areas. — https://arxiv.org/html/2401.15029v1 https://arxiv.org/abs/2401.15029
- [medium] Drone images can reveal the forest floor through dense canopy only with a special capture: near-nadir views, about 20-25 samples per ground point, about 1-2 cm GSD and diffuse light. Even then, dense broadleaf canopy defeats it in some scenes. — https://arxiv.org/html/2601.22861 https://arxiv.org/abs/2601.22861
- [medium] Aerial-ground cross-view work with 3DGS was demonstrated only on urban scenes: rendering intermediate views gave 3.72x and 5.35x more correct matches than SuperPoint+SuperGlue alone (ISPRS CENTER/ZECHE), but only 0.81x on a campus scene. No forest test was found. — https://arxiv.org/html/2509.19898v1
- [medium] Above-canopy drone photogrammetry recovers stems only partially, and only with oblique views, even in open stands. No Scots pine, Norway spruce or birch measurement by stand density or canopy cover from Sweden or Finland was found. — https://pmc.ncbi.nlm.nih.gov/articles/PMC9157555/ https://api.semanticscholar.org/graph/v1/paper/DOI:10.3390/drones5020043 https://api.semanticscholar.org/graph/v1/paper/DOI:10.1111/phor.70061
- [medium] In Nordic practice, image-matched point clouds capture only the outer canopy surface and need a LiDAR terrain model for height normalisation. The forest floor is not reliably reconstructed from aerial or drone images in closed boreal stands. — https://api.semanticscholar.org/graph/v1/paper/DOI:10.3390/f4030518 https://api.semanticscholar.org/graph/v1/paper/DOI:10.3390/rs70809632 https://api.semanticscholar.org/graph/v1/paper/DOI:10.3390/rs16101721
- [high] Laserdata Nedladdning, skog (1-2 pts/m², scanned 2018 onward, about 75% of Sweden) is open data under CC0. Since 2026-06-01 it is delivered only via a STAC API as COPC LAZ in 10x10 km tiles, and users must accept new terms of use because laser data is now treated as personal data (GDPR). — https://www.lantmateriet.se/sv/geodata/vara-produkter/Produktnyheter/Geografisk-information/uppdatering-angaende-tillhandahallandet-av-laserdata-nedladdning-skog/ https://www.lantmateriet.se/sv/geodata/vara-produkter/Produktnyheter/Geografisk-information/h/ https://www.lantmateriet.se/sv/geodata/vara-produkter/Produktnyheter/Geografisk-information/nytt-format-for-laserdata-skog/
- [high] Laserdata Nedladdning, NH (0.5-1 pts/m², 0.25 in mountain areas, scanned 2009-2019, national coverage) is NOT open: a licence is required and fees apply. — https://ext-geodatakatalog-forv.lansstyrelsen.se/PlaneringsKatalogen/GetMetaDataById?id=8f5e284e-1cff-4f38-a023-1545c501f989_C https://catalogue.arctic-sdi.org/geonetwork/srv/api/records/8f5e284e-1cff-4f38-a023-1545c501f989 https://via.tt.se/pressmeddelande/3776001/lantmateriets-vardefulla-data-blir-avgiftsfria?publisherId=3236286&lang=sv
- [high] Markhöjdmodell Nedladdning, grid 1+ (1 m terrain model from ALS ground and water points, updated continuously) is free under CC BY 4.0 with attribution to Lantmäteriet. Delivered via STAC at api.lantmateriet.se/stac-hojd/v1. — https://ext-geodatakatalog-forv.lansstyrelsen.se/PlaneringsKatalogen/GetMetaDataById?id=c510e63f-0bf3-46c9-ab8b-3b37a898af85_C https://github.com/matself/LM-STAC-Downloader https://via.tt.se/pressmeddelande/3776001/lantmateriets-vardefulla-data-blir-avgiftsfria?publisherId=3236286&lang=sv
- [high] Ortofoto Nedladdning is free since 2025-02-03 under CC BY 4.0: 0.16 m and 0.4 m from 2019 onward (4-band colour plus NIR only), 0.25 and 0.5 m for earlier years. Delivered as COG via STAC at api.lantmateriet.se/stac-bild/v1. Historical orthophotos are CC0. — https://geotorget.lantmateriet.se/dokumentation/GEODOK/44/latest/atkomst-och-leverans.html https://www.lantmateriet.se/sv/geotorget-produktstod/om-tillhandahallandet/ https://github.com/matself/LM-STAC-Downloader
- [medium] Conclusion: for a 10x10 m plot, a consumer-drone aerial splat adds information beyond open data only in the top-of-canopy layer (cm-scale crown-top geometry and same-day colour). It adds little for stems or the forest floor under closed Swedish canopy, which the BLK2GO and Insta360 capture already covers far better. — https://arxiv.org/html/2601.12823 https://arxiv.org/html/2401.15029v1 https://arxiv.org/html/2601.22861

## Key numbers

- TreeDGS DBH RMSE, aerial 3DGS (pine, 70-90 m, GSD 1.84 cm): 4.79 cm (ME -0.38 cm) vs UAV LiDAR 7.66 cm (https://arxiv.org/html/2601.12823)
- TreeDGS mean unoccluded views per tree / trunk width in pixels: 8.2 views / about 15.4 px (https://arxiv.org/html/2601.12823)
- TreeDGS paired stems / field stems: 210 / 458 (10 plots of 0.2 acre) (https://arxiv.org/html/2601.12823)
- LiDAR-guided semantic 3DGS (handheld LiDAR + UAV) novel-view metrics: PSNR 24.94 dB, SSIM 0.773, LPIPS 0.231; DBH R² 0.848, RMSE 2.705 cm (https://doi.org/10.3390/rs18111696)
- Castorena tree-count RMSE per plot: UAV-imagery neural field / TLS / neural field + ALS + TLS: 10.61 / 1.77 / 1.32 (https://arxiv.org/html/2401.15029v1)
- Under-canopy NeRF person-detection AP (AOS data): 80.5% (89.6% excluding low-quality scenes) (https://arxiv.org/html/2601.22861)
- Under-canopy NeRF capture requirement: near-nadir, about 20-25 samples per ground point, about 1-2 cm GSD, diffuse light (https://arxiv.org/html/2601.22861)
- Ponderosa pine drone photogrammetry: share of trees with DBH extracted: more than 40%, only with off-nadir + crosshatch (tree detection more than 90%) (https://pmc.ncbi.nlm.nih.gov/articles/PMC9157555/)
- Birch woodland (Bulgaria) best drone DBH configuration: about 25 m above canopy, 60° tilt, RMSE under 12.5% (https://api.semanticscholar.org/graph/v1/paper/DOI:10.3390/drones5020043)
- Oblique + nadir urban-forest photogrammetry: recall / DBH RMSE: 0.90 (108/120) / 3.02 cm at 1.54 cm GSD (https://api.semanticscholar.org/graph/v1/paper/DOI:10.1111/phor.70061)
- Drone-photogrammetry terrain model in BC conifer: share of area with RMSE under 1.5 m: 51.6-56.5% (https://api.semanticscholar.org/graph/v1/paper/DOI:10.3390/rs11010084)
- Laserdata skog point density / licence: 1-2 pts/m² / CC0 (new GDPR terms from 2026-06-01) (https://www.lantmateriet.se/oppnadata)
- Laserdata NH point density / licence: 0.5-1 pts/m² (0.25 in mountains), 2009-2019 / licence and fee required (https://ext-geodatakatalog-forv.lansstyrelsen.se/PlaneringsKatalogen/GetMetaDataById?id=8f5e284e-1cff-4f38-a023-1545c501f989_C)
- Laserdata skog delivery from 2026-06-01: STAC API, COPC LAZ, 10x10 km tiles (previously 2.5 km) (https://www.lantmateriet.se/sv/geodata/vara-produkter/Produktnyheter/Geografisk-information/uppdatering-angaende-tillhandahallandet-av-laserdata-nedladdning-skog/)
- Markhöjdmodell grid 1+ licence / STAC endpoint: CC BY 4.0 / https://api.lantmateriet.se/stac-hojd/v1 (https://ext-geodatakatalog-forv.lansstyrelsen.se/PlaneringsKatalogen/GetMetaDataById?id=c510e63f-0bf3-46c9-ab8b-3b37a898af85_C)
- Ortofoto resolution / licence / STAC endpoint: 0.16 and 0.4 m (4-band, 2019 onward) / CC BY 4.0 (free since 2025-02-03) / https://api.lantmateriet.se/stac-bild/v1 (https://github.com/matself/LM-STAC-Downloader)
- Open-data samples over a 10x10 m plot (derived): orthophoto about 3,900 px; terrain model 100 cells; Laserdata skog about 100-200 points (derived from product specs)
- BLK2GO sample density (derived): about 1.1e5 pts/m² (46.07 M points over about 412 m²) (user-supplied sample-data facts)
- Hierarchical-3DGS default VRAM budget: 16 GB (+ up to 1.5 GB for rendering) (https://github.com/graphdeco-inria/hierarchical-3d-gaussians)

## Still unknown

- Any real-forest study reporting ground-level novel-view metrics with vs without aerial images (none found).
- Full methods of 'LiDAR-Guided Semantic 3DGS for Forest Digital Twins' (UAV model and altitude, pose tying, view types behind the metrics, ablation without UAV, code or licence): MDPI returned 403.
- Measured share of stems or forest floor recovered by above-canopy oblique drone photogrammetry in Swedish or Finnish Scots pine, Norway spruce and birch stands by density or canopy cover (no study found; web-search budget ran out mid-task).
- Tropical-forest UAV + ground splat or NeRF evidence (none found).
- Whether Laserdata skog stays CC0 under the new terms of use in force since 2026-06-01 (GDPR classification).
- Orthophoto 0.16 m coverage, capture year and season for the specific Swedish test site; whether Lantmäteriet's image-matched surface model is open.
- Licence text of Hierarchical-3DGS (LICENSE.md not read) and Horizon-GS (repo not reached).

## Questions for user

- Will the web viewer let users rise above the canopy (fly-over or bird's-eye view), or stay at walking height only? This decides whether a drone layer has any value.
- Which drone would you use (model, camera), and is flying it at the Swedish site practical and permitted for you?
- What stand type is the Swedish test plot (Scots pine, Norway spruce, birch or mixed), roughly how closed is the canopy, and will you capture leaf-on or leaf-off?
- Do you need the result georeferenced in SWEREF 99 TM (to overlay Lantmäteriet data), or is a local frame fine?
- Are you OK showing '© Lantmäteriet' attribution in a publicly shared viewer, and accepting their GDPR terms of use to download laser data?
