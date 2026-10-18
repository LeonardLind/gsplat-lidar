# gap: drone-lidar-target-tie

## Summary

Short answer: tying a drone block to a BLK2GO cloud through shared targets is technically feasible. The weak link in a forest is whether the drone can see the targets, not how well they can be measured. Leica's own figure for target error in BLK2GO data is about ±8 mm. A drone block at 1-3 cm GSD can realistically be tied with about 2-4 cm horizontal and 3-6 cm vertical RMS at the targets (my estimate, not measured). That only holds if at least 5 targets are visible both from above and along the BLK2GO walk. Under closed canopy (Swedish spruce/pine, and even more so in tropical forest) that visibility is the main risk.

(1) Leica software. Cyclone REGISTER 360 2022.1.0 added Auto B&W target extraction for BLK2GO walks. The release notes recommend walking 1-2 m from each target with a 1-2 s stop, and state an "expected target error +/- 8mm for the 6-inch printable B&W targets". With at least 3 targets, Apply Control can be run on a single BLK2GO Walk. Control files are just coordinate lists, so in principle a local frame works. I found no documentation of a GCP-constrained (non-rigid) SLAM or trajectory adjustment for BLK2GO, so Apply Control should be treated as a rigid fit. The Cyclone FIELD 360 in-field georeferencing workflow is RTC360-only (firmware 7.0 or later; 4.5-inch and 6-inch B&W or natural targets). For BLK2GO, FIELD 360 offers only cloud-to-cloud links and GeoTags. REGISTER 360 also offers Re-Run SLAM and Re-observation at import. Re-observation recalculates points over the whole dataset to cut drift and double walls, and adds about 20-25% import time.

Intensity: BLK2GO raw data does have intensity, for three reasons. B&W target extraction works on BLK2GO data. Cyclone 3DR's documentation says B&W and blue/white target extraction needs the intensity mode, while sphere extraction uses geometry. A reviewer of Leica's sample BLK2GO E57 described the intensity as "excellent". So the all-zero intensity in your LAS was lost on the way out, not missing from the scan. Cyclone 3DR before 2024.1 stored intensity as an inspection scalar that analysis steps could overwrite: 2024.1 notes "Intensity is now a specific attribute and is therefore preserved after doing an analysis". 2025.1.1 normalises intensity to 0-1. Leica's export documentation says PTS and PTX carry XYZ plus intensity. Re-exporting from the original B2G or REGISTER 360 project as PTS or E57 should give intensity back, but I have not checked this on BLK2GO data.

(2) Target-centre accuracy. The only primary number specific to BLK2GO is Leica's ±8 mm for 6-inch B&W targets. Specs: range noise ±3 mm; relative accuracy 6-15 mm; absolute 20 mm indoors in a 2-minute controlled scan; 420k pts/s; range 0.5-25 m; 830 nm. I found no measured sphere or pyramid centre accuracy for BLK2GO. The noise-only error of a sphere fit with N points is roughly 3 mm × sqrt(3/N), under 0.5 mm for N > 100. The real floor is how well overlapping passes line up, about 5-10 mm (estimate). Cyclone 3DR fits spheres with free or fixed radius and reports RMS. 3DR 2026.1 added the script call SCloud.ExtractSurveyTarget (planar B&W, blue/white, or spherical).

(3) Drift. I found no published BLK2GO forest test with independent checkpoints over 20-100 m loops. What exists:
- Gharineiat et al. 2024 (Remote Sensing 16:3256): about 5 mm indoors versus 10-60 mm outdoors against total station and Z+F TLS.
- Kelly et al. IGARSS 2024: under 0.020 m RMSE when stationary, but walking tests showed systematic errors that needed scale-factor adjustment.
- Other handheld scanners in forests, as a proxy: tree-position RMSE 25.3 cm (ZEB REVO), 28.4 cm (ZEB Horizon), 17.9 cm (ZEB Horizon) and 17.3 cm (Stonex X120GO) over plot-scale walks.
For the 10×10 m loop, the device's 6-15 mm local consistency should hold. For 50-100 m walks in forest, plan for several cm to decimetres unless the loops are closed.

(4) Target design. Pix4D's rule is a target about 5-10× GSD for manual marking, and marking cannot be more precise than about 1/10 GSD. The 20× GSD rule for automatic detection is not verified. At 2-3 cm GSD that means at least 15-30 cm for manual marking, or 40-60 cm if automatic detection is wanted. My proposed design (not tested) is a square pyramid about 50 cm across. Its four faces alternate black and white, so from above it looks like a standard checker GCP whose centre is the apex. The BLK2GO gets the apex by fitting four planes and intersecting them, which needs no intensity. A 200 mm matte sphere mounted at a measured offset is another option. Mount targets 0.5-1.5 m above the understorey, in canopy gaps or clearings. For the 360 camera: at 8K equirectangular, one pixel covers about 0.8 mrad, so a 50 cm target spans about 120 px at 5 m (resolution from memory, not checked).

(5) Software:
- **Agisoft Metashape Pro** ($3,499; the $179 Standard edition has no GCP, marker or coded-target support). From memory, not re-checked: it supports "Local Coordinates (m)" and reads DJI XMP.
- **RealityScan 2.x** is free for individuals and businesses under $1M revenue. Its GCP and local Euclidean coordinate support is from memory, not re-checked.
- **ODM 3.6.x** (AGPL-3.0, native Windows installer): the GCP file needs an EPSG code, a "WGS84 UTM" zone or a PROJ string. A local frame would need a fake projection such as tmerc (not tested). ODM parses DJI XMP tags (Flight/Gimbal yaw/pitch/roll, RTK std) and has a rolling-shutter option.
- **OpenSfM**: GCPs in WGS84, UTM or proj4.
- **COLMAP**: no support for GCPs marked in images. model_aligner only does a similarity fit to 3 or more image positions (cartesian allowed), and GPS priors come from EXIF. A custom GCP residual is practical with pycolmap plus pyceres (Apache-2.0; v2.6 of Nov 2025; Windows wheels for Python 3.9-3.14).

Non-commercial licences change nothing for this part: no research-only tool beats Metashape Pro, the free RealityScan, or ODM for adjusting a block with GCPs.

What this means for the plan: keep the BLK2GO frame as the master. Get target centres from geometry (Python fitting, or 3DR/REGISTER 360). Feed them in as local-frame GCPs, use 5 or more targets with 1-2 held out as checkpoints, and run a 7-parameter similarity check to catch BLK2GO scale error. Recover intensity as a bonus, not a dependency. Note: the shared web-search budget ran out partway through, so several items above could not be checked against a second source.

## Plan changes

- Add a target-design and target-extraction module: our own Python sphere and plane-intersection fitting on BLK2GO points (no intensity dependency), cross-checked with Cyclone 3DR (2026.1 SCloud.ExtractSurveyTarget) or REGISTER 360 Auto B&W.
- Capture protocol: place ≥5 dual-use targets where the sky is visible (canopy gaps, the forest edge, or extend the walk to a nearby clearing within the 25 m range). Mount them above the understorey. Walk 1-2 m from each with a 1-2 s stop. Keep walks to 10-15 min, closed loops, starting and ending on the base plate.
- Data ingest: request the original B2G or REGISTER 360 project and export PTS or E57 with intensity. Enable Re-Run SLAM and Re-observation. Treat the Cyclone 3DR LAS as geometry/RGB-only.
- Drone-layer pipeline: choose RealityScan (free) or Metashape Pro for the GCP adjustment in the BLK2GO local frame. Keep ODM with a fake projection, or COLMAP+pycolmap+pyceres with a custom GCP residual, as open fallbacks. Enable rolling-shutter compensation for DJI cameras.
- QA: hold out 1-2 targets as checkpoints, report horizontal and vertical RMS and the similarity scale factor, and plan for about 2-4 cm horizontal / 3-6 cm vertical RMS at 2 cm GSD.
- Make the drone layer explicitly conditional on canopy openness. Under closed canopy, decide whether to drop it for the first 10×10 m test or to move the test next to a clearing.
- Do not plan on Cyclone FIELD 360 georeferencing (RTC360 only) or on GCP-constrained SLAM correction for BLK2GO (not documented); Apply Control on a Walk is rigid.

## Recommendations

- **Make the BLK2GO frame the master. Extract target centres from geometry (spheres or plane-intersection pyramids), use them as local-frame GCPs in the drone bundle adjustment, and treat intensity-based B&W extraction as an optional cross-check.** — The user's current export has intensity = 0. Geometric extraction (3DR sphere fit, 3DR 2026.1 SCloud.ExtractSurveyTarget, or our own Python RANSAC) works without intensity. Leica's ±8 mm B&W figure shows targets can be measured to under 1 cm in BLK2GO data. _Alt:_ Re-export with intensity and use REGISTER 360's Auto B&W target extraction (documented for BLK2GO).
- **Build a dual-use target: a square pyramid about 50 cm across (60 cm if GSD reaches 3 cm) with alternating matte black and white faces. Seen from above it reads as a checker GCP whose centre is the apex; the BLK2GO gets the apex by fitting four planes and intersecting them. Mount it 0.5-1.5 m above the understorey in canopy gaps. Optionally add a 200 mm matte sphere at a measured offset.** — It meets the Pix4D 5-10× GSD rule at 2-3 cm GSD with margin for automatic detection. It spans about 120 px in an 8K 360 frame at 5 m. Plane intersection uses thousands of points, so precision is limited by how well passes overlap (5-10 mm), not by range noise. _Alt:_ A 2×2 checker board plus a sphere on a pole; AprilTag or ArUco boards for the 360 camera only; Leica 6-inch B&W printables (BLK2GO-tested, too small for the drone).
- **For the GCP adjustment, use RealityScan (free for individuals) or Metashape Pro (trial, or a licence if one is available). Use ODM with a fake projection, or COLMAP plus pyceres with a custom GCP residual, if a fully open pipeline is needed.** — Metashape Standard has no GCP support. ODM and OpenSfM need a CRS header. COLMAP only does a similarity fit to camera positions. Non-commercial licences offer nothing better here. _Alt:_ MicMac (open source, handles arbitrary local frames; from memory, not verified); Leica Infinity (unverified).
- **Get intensity back by exporting from the original B2G or REGISTER 360 project as PTS (documented to carry intensity) or E57. If Cyclone 3DR is used, use version 2024.1 or later and check SCloud.HasIntensity before cropping.** — Before 2024.1, 3DR stored intensity as an inspection scalar that analysis steps could overwrite. Intensity enables B&W targets and helps with QA. _Alt:_ Stay geometry-only.
- **When capturing the BLK2GO data, walk 1-2 m from each target with a 1-2 s stop. Keep walks to 10-15 min, close loops, start and end on the base plate, and enable Re-Run SLAM and Re-observation at import.** — These are Leica's and the dealer's documented best practices. Re-observation reduces drift and double walls in areas scanned more than once.
- **Use at least 5 shared targets. Hold 1-2 out as checkpoints, fit a 7-parameter similarity between the drone and BLK2GO coordinates, and report the scale factor.** — IGARSS 2024 reports systematic BLK2GO scale errors while walking. Checkpoints are the only independent accuracy evidence available without GNSS or a total station. _Alt:_ Add tape-measured distances between targets, or total-station checkpoints if Hexagon equipment can be borrowed.

## Load-bearing findings

- [high] Cyclone REGISTER 360 (since 2022.1.0) supports Auto B&W target extraction on BLK2GO walks, with a stated expected target error of +/-8 mm for 6-inch printable B&W targets, and a 1-2 m walking distance with a 1-2 s stop in front of each target. — https://rcdocs.leica-geosystems.com/v1/docs/cyclone-register-360-2022-1-0-cyclone-register-360-release-notes https://knowledgebase.globalsurvey.co.nz/blk2go-best-practice-tips
- [medium] In Cyclone REGISTER 360 PLUS, control can be applied to a single BLK2GO Walk with at least 3 targets. I found no documented GCP-constrained (non-rigid) SLAM or trajectory correction for BLK2GO. — https://rcdocs.leica-geosystems.com/cyclone-register-360/latest/advanced-applied-control-techniques https://rcdocs.leica-geosystems.com/cyclone-register-360/latest/general-settings https://rcdocs.leica-geosystems.com/cyclone-register-360/latest/2025-0-0-cyclone-register-360-plus-release-notes
- [medium] BLK2GO raw data contains intensity. The all-zero intensity in the user's Cyclone 3DR LAS export was most likely lost on the export path, not missing from the device. — https://rcdocs.leica-geosystems.com/docs/cyclone-3dr-automatic-extraction-of-the-center-of-surveying-ta.md https://www.linkedin.com/pulse/first-impressions-leica-blk2go-shane-maclaughlin https://cyclone3dr.com/downloads.php
- [high] BLK2GO manufacturer specs: range noise ±3 mm, relative accuracy 6-15 mm, absolute position accuracy 20 mm indoors (controlled environment, 2-minute scan), 420k pts/s, range 0.5-25 m, field of view 360°×270°, 830 nm, class 1. — https://www.sccssurvey.co.uk/blk2go.html https://atgusa.com/product_specs/leica-blk2go-product-specifications/ https://www.thefuture3d.com/equipment/compare/leica-blk2go-vs-blk2go-pulse/
- [medium] Measured BLK2GO accuracy: about 5 mm indoors and 10-60 mm outdoors against total station and TLS. Walking tests show systematic errors that need scale-factor adjustment. — https://www.mdpi.com/2072-4292/16/17/3256 https://api.semanticscholar.org/graph/v1/paper/DOI:10.3390/rs16173256 https://ieeexplore.ieee.org/document/10641469/
- [high] Pix4D sizing rule: a GCP target about 5-10× GSD, at least 3 GCPs (5-10 usually enough), and GCP coordinates need be no more accurate than about 1/10 GSD. — https://support.pix4d.com/hc/en-us/articles/202557489
- [medium] Metashape GCPs need the Professional edition ($3,499 node-locked). Standard ($179) lacks ground control and checkpoints, markers and scale bars, coded-target detection, and Python. — https://www.agisoft.com/features/compare/ https://www.agisoft.com/buy/online-store/ https://agisoft.freshdesk.com/support/solutions/articles/31000153696
- [medium] RealityScan (formerly RealityCapture) is free with all features for individuals and businesses under $1M revenue; above that it costs $1,250 per seat per year. — https://www.realityscan.com/en-US/license
- [low] Expected accuracy for tying a drone block to the BLK2GO cloud (estimate): about 2-4 cm horizontal and 3-6 cm vertical RMS at the targets, at 1-2 cm GSD with 5 or more well-distributed targets. Error grows away from the targets, toward the canopy. — https://rcdocs.leica-geosystems.com/v1/docs/cyclone-register-360-2022-1-0-cyclone-register-360-release-notes https://support.pix4d.com/hc/en-us/articles/202557489

## Key numbers

- Expected B&W target error, BLK2GO, 6-inch printable target: ±8 mm (https://rcdocs.leica-geosystems.com/v1/docs/cyclone-register-360-2022-1-0-cyclone-register-360-release-notes)
- Recommended BLK2GO walking distance to targets / stop time: 1-2 m / 1-2 s (https://rcdocs.leica-geosystems.com/v1/docs/cyclone-register-360-2022-1-0-cyclone-register-360-release-notes)
- Minimum targets to apply control to a BLK2GO Walk: 3 (https://rcdocs.leica-geosystems.com/cyclone-register-360/latest/advanced-applied-control-techniques)
- BLK2GO range noise / relative accuracy / absolute accuracy indoors: ±3 mm / 6-15 mm / 20 mm (2-min controlled scan) (https://www.sccssurvey.co.uk/blk2go.html)
- BLK2GO range / rate / wavelength: 0.5-25 m / 420,000 pts/s / 830 nm (https://atgusa.com/product_specs/leica-blk2go-product-specifications/)
- BLK2GO measured accuracy indoor vs outdoor: 5 mm vs 10-60 mm (https://www.mdpi.com/2072-4292/16/17/3256)
- BLK2GO stationary RMSE: <0.020 m (systematic errors and scale issues when walking) (https://ieeexplore.ieee.org/document/10641469/)
- Handheld SLAM tree-position RMSE in forest (ZEB REVO / ZEB Horizon): 25.3 cm / 28.4 cm (https://api.semanticscholar.org/graph/v1/paper/DOI:10.5194/isprs-archives-XLIII-B1-2020-211-2020)
- Handheld SLAM tree-position RMSE in forest (ZEB Horizon / Stonex X120GO): 17.91 cm / 17.33 cm (https://api.semanticscholar.org/graph/v1/paper/DOI:10.3390/land13010093)
- Re-observation extra import time: up to 20-25% (https://rcdocs.leica-geosystems.com/v1/docs/cyclone-register-360-2022-1-0-cyclone-register-360-release-notes)
- Recommended BLK2GO walk length (dealer advice): 10-15 min (https://knowledgebase.globalsurvey.co.nz/blk2go-best-practice-tips)
- Pix4D GCP target size: 5-10× GSD (manual); 20× GSD for automatic detection is unverified (https://support.pix4d.com/hc/en-us/articles/202557489)
- Pix4D GCP accuracy floor: about 1/10 GSD (https://support.pix4d.com/hc/en-us/articles/202557489)
- ODM recommended GCP count: ≥5 (8-10 for large jobs), each in ≥3 images (https://docs.opendronemap.org/gcp/)
- Metashape Pro / Standard price (node-locked): $3,499 / $179 (Standard has no GCP support) (https://www.agisoft.com/buy/online-store/)
- RealityScan price: Free under $1M revenue; otherwise $1,250 per seat per year (https://www.realityscan.com/en-US/license)
- pyceres latest version: 2.6 (5 Nov 2025), Windows wheels for Python 3.9-3.14, Apache-2.0 (https://pypi.org/project/pyceres/)
- FIELD 360 georeferencing target range (RTC360 only): 5-10 m @12 mm, 10-15 m @6 mm, 20-25 m @3 mm resolution (https://rcdocs.leica-geosystems.com/cyclone-field-360/latest/georeferencing-workflow-cyclone-field-360)
- Cyclone 3DR latest build: 2026.1.4.50569 (28 Sep 2026) (https://cyclone3dr.com/downloads.php)
- Insta360 8K equirectangular angular resolution (X4/X5 assumed 7680 px wide): about 0.82 mrad/px, i.e. about 4 mm/px at 5 m (from memory, not checked)
- Estimated drone-to-BLK2GO tie at targets (2 cm GSD, ≥5 targets): about 2-4 cm horizontal, 3-6 cm vertical RMS (my estimate)

## Still unknown

- Measured BLK2GO SLAM drift or relative accuracy in forests over 20-100 m loops with independent checkpoints: no study found.
- Measured centre accuracy of spheres or pyramids in BLK2GO clouds; the only BLK2GO-specific figure is Leica's ±8 mm for 6-inch B&W targets.
- Whether REGISTER 360 Auto Sphere Target works on BLK2GO walks, and whether Apply Control on a Walk is strictly rigid.
- Which BLK2GO export paths actually keep intensity (PTS is documented to carry it, E57 not explicitly), and the exact cause of intensity = 0 in the user's 3DR LAS.
- The Pix4D '20× GSD for automatic detection' rule (not verified).
- Whether RealityScan 2.x supports local Euclidean GCPs and DJI XMP priors, and whether Metashape Pro's 'Local Coordinates' and DJI XMP reading work as expected (both from memory, not re-verified here).
- Whether ODM/OpenSfM give correct results with a fake projection for a local frame (untested).
- Leica Infinity's UAV photogrammetry and GCP abilities, and whether they are in the user's licence.
- Whether black matte faces cause a range bias or noise at 830 nm on the BLK2GO, which would affect a black/white pyramid target.
- Several items could not be checked against a second source because the shared web-search budget ran out; MDPI and ResearchGate full texts were blocked and Leica PDFs could not be parsed.

## Questions for user

- Which drone and camera will be used (shutter type, RTK or not, sensor and resolution) and at what flight height or GSD?
- How open is the canopy at the Swedish test site: are there gaps or a clearing within 25 m of the planned 10×10 m loop?
- Do you have the original BLK2GO B2G or REGISTER 360 projects (needed for intensity re-export and Re-Run SLAM), and which REGISTER 360 PLUS and Cyclone 3DR versions does your EPP licence install?
- Could you borrow a total station or GNSS rover through Hexagon to measure independent checkpoints, even once?
- Can you get Metashape Pro (trial or licence), or should the pipeline assume RealityScan (free) or open-source only?
