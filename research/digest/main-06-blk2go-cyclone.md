# blk2go-cyclone

## Summary

Note: the shared WebSearch budget ran out partway through. After that, research continued only by fetching known primary URLs (Leica RCDOCS including its llms.txt index, spec-sheet PDFs, PyPI JSON, GitHub, Luciad docs). The Leica shop HTML pages returned 403. Wherever a claim rests on background knowledge it is marked low confidence.

HARDWARE. The original BLK2GO is the right tool for forests: 420,000 pts/s, 830 nm Class 1, FoV 360°x270°, range 0.5-25 m, 'designed for indoor and outdoor use', IP54. The current datasheet (May 2021, also on the entertainment site) gives range noise ±3 mm and indoor accuracy ±10 mm (1 sigma, controlled 2-minute scan), operating 0 to +40 °C. The older 2019 sheet still on the shop gives 6-15 mm relative, 20 mm absolute and +5 °C. GrandSLAM fuses LiDAR SLAM, visual SLAM (three global-shutter panoramic cameras, 4.8 MP total, 300°x135°) and an IMU whose specs are not published. A 12 MP rolling-shutter detail camera (90°x120°) fires on button press and creates a GeoTag. The panoramic cameras capture about every second (≈1 Hz); those frames colourise the cloud and become WayPoint panoramas. Physical: 650 g (775 g with battery), 279x80 mm, 45-50 min battery.

The BLK2GO PULSE is a different, indoor-only device and is unsuitable for forests: two 940 nm ToF sensors, 7,816 spots at 5 fps, 210°x85°, 0.5-10 m, ±2 cm indoor accuracy, 850 g. No public document gives the BLK2GO's trajectory reference point or the axes of its body frame. Assume a local, gravity-aligned frame with its origin near the start pose (low confidence) and calibrate it from the data.

EXPORTS. Keep the raw .b2g as master; Leica says E57 cannot be re-imported. Four export routes exist:
- **Cyclone REGISTER 360 PLUS** (latest 2026.1.1; the BLK2GO driver installer was dropped in Aug 2026, but USB import still works). Publishes E57 (one file or separate setups; structured or unstructured), PTS, PTX (XYZ + intensity), PTG, RCP, LAS (unstructured, no images), SEMA, LGS/LGSx, TruView and JetStream. Panoramas export as JPEG (EXR needs WORKFLOW) with a TXT of positions and orientations. TruView Local writes SWLocation.xml with panorama coordinates.
- **E57 with WayPoints and rectified images.** Most metadata-rich route, but needs a Cyclone WORKFLOW license. Available as Report > Export Options for E57 > Separate Setups, or the CLI `Register360.exe -b2g2trajectory <b2g dir> <out dir>` with options `recimage`, `interval=n` and `geotag-waypoints`. The E57 contains the main cloud, a second point cloud holding the trajectory as points, all panorama locations and orientations along the trajectory, per-point normals, and optional rectified images. Image headers store pose as quaternion (w,x,y,z) plus translation, with pinhole (focal length, pixel size, principal point) or spherical representations linked by GUID. Use version 2026.0.0 or later: it fixed missing WayPoints and panoramas in Separate-Setups E57 export.
- **BLK Live app** (free; v2.0.0 Dec 2023 onward, latest 3.0.2 Jul 2025), BLK Data Manager and Cyclone FIELD 360. These export .e57, detail-image .jpg and trajectory .csv.
- **Cyclone 3DR** (2025.2 / 2026.x). Exports LAS/LAZ 1.4 with an optional timestamps attribute, and E57 with timestamps and images. It handles LGSx trajectories and can display timestamps as a colour mode.

Not found in any reachable source:
- The trajectory CSV columns, sample rate, orientation representation and time base.
- Whether BLK2GO LAS/E57 exports carry per-point time.

The only time evidence found is that WayPoints report time and distance from the walk start (relative time). The E57 standard defines a per-point timeStamp plus acquisitionStart/End in GPS seconds. There is no documented access to raw IMU, and there is no BLK2GO SDK; that matches the 'no proprietary SDK' constraint anyway. The first action should therefore be a test export, then inspecting the E57 XML and the CSV header.

FUSION IMPLICATIONS. Two bridges are available:
1. **Motion-based time sync.** Cross-correlate the angular rate derived from the BLK2GO trajectory with the Insta360 gyro, using deliberate twists while the rig is stationary at start and end. The clap cannot reach the BLK2GO: it has no audio, and its panoramic frames are about 1 Hz. A GeoTag button press gives at most a coarse event.
2. **BLK2GO images with poses.** Rectified pinhole images and WayPoint panoramas already sit in the LiDAR metric frame. They can be added to SfM as pose-fixed anchors, or matched against Insta360 crops to give a time-free metric registration. That makes an independent check on the trajectory/ICP-derived extrinsic and on the tape-measured offset.

They are poor primary splat-training images: low resolution, operator visible, 1 Hz.

HEXAGON SPLAT LANDSCAPE (Oct 2026). No Gaussian-splat feature turned up in the Cyclone REGISTER 360 PLUS 2026.x, Cyclone 3DR 2025.1-2026.1, Cyclone FIELD 360 7.1 or Reality Cloud Studio 2025 release notes. Reality Cloud Studio was renamed Hexagon GeoCloud on 2026-04-20; its 2026 notes index showed no splat items. LuciadRIA 2026.1 and LuciadCPillar 2026.1 render Gaussian splats delivered as OGC 3D Tiles with glTF KHR_gaussian_splatting or KHR_gaussian_splatting_compression_spz_2. The open pipeline can therefore emit a 3D Tiles splat tileset for the optional Luciad path without depending on any Leica product.

PYTHON ON WINDOWS. Options:
- **laspy** 2.7.0 (2026-01-14, BSD-2, Python ≥3.10, LAS 1.0-1.4, point formats 0-10, COPC, chunked I/O) with **lazrs** 0.8.2 (2026-07-27, MIT, win_amd64 wheels for cp310-cp314, multithreaded).
- **pye57** 0.4.19 (2025-11-26, MIT, win_amd64 wheels for cp310-cp314). Its libe57 bindings expose BlobNode.read_buffer, so image2D JPEGs and poses can be extracted.
- **PDAL** 2.10.0 (2026-02-13, BSD) through conda-forge only on Windows; python-pdal 3.5.5. Its E57 reader ignores images and spherical clouds.
- The **cry-inc e57** Rust CLI (MIT) has e57-extract-xml, e57-to-image and e57-unpack for inspection.

Pitfalls:
- x/y/z are scaled doubles; X/Y/Z are raw int32. At scale 0.001 the int32 range is only ±2,147 km, so SWEREF 99 TM northings (~6.5e6 m) need an offset.
- float32 spacing at 6.5e6 m is 0.5 m, so recentre before sending to the GPU.
- Point formats 6-10 force a GPS time field, which may be all zeros.
- Unit settings (international or US survey feet) can leak into exports.
- E57 files written with libE57Format 3.3.0 can break older readers; Cyclone 3DR 2026.0.1 added a compatibility option.
- BLK2GO data is in a local frame with no CRS unless registered to control.

## Recommendations

- **Use the original BLK2GO, not the BLK2GO PULSE, for all forest captures.** — The PULSE is specified 'for indoor use' with 0.5-10 m range and 940 nm ToF sensors; the BLK2GO is indoor/outdoor with 25 m range and ±3 mm range noise. _Alternatives:_ If only a PULSE is available, expect degraded outdoor performance; treat it as a pipeline test only.
- **Run a metadata discovery export on day 1, before writing fusion code. Import the walk into REGISTER 360 PLUS ≥2026.0.0, export E57 via Separate Setups (WayPoints + rectified images; WORKFLOW license) or the CLI `Register360.exe -b2g2trajectory <b2g> <out>` with recimage and interval=1, also export the trajectory CSV from BLK Live, FIELD 360 or BLK Data Manager, and dump the E57 XML (cry-inc e57-extract-xml or pye57.libe57).** — Trajectory CSV columns, rate, orientation, time base and per-point timestamps are undocumented, and every downstream design choice (time sync, hand-eye calibration, de-skew) depends on them. _Alternatives:_ Ask Leica/Hexagon colleagues internally for the B2G-export CSV spec; Cyclone 3DR via LGSx (trajectory object) as a further path.
- **Keep the .b2g as master. Produce three derived artefacts: (a) E57 with trajectory cloud, WayPoint panoramas and rectified images (metadata); (b) LAS 1.4/LAZ (or E57 converted to LAZ in Python with laspy[lazrs]) for the point cloud; (c) trajectory CSV.** — Leica says E57 cannot be re-imported into REGISTER 360; LAS carries no images or structure; the E57 is the only container with poses and images. LAZ is not a REGISTER 360 export, so convert in Python. _Alternatives:_ Cyclone 3DR exports LAS/LAZ 1.4 with timestamps and E57 with images if those attributes exist in the source.
- **Time sync: use motion-signature cross-correlation (BLK2GO trajectory angular rate vs Insta360 gyro) with deliberate rig twists while stationary at start and end, solving for offset and drift. Use the clap only to align Insta360 audio across runs and devices. Use a BLK2GO detail-image button press (GeoTag) as a coarse cross-check event.** — The BLK2GO has no audio and its cameras run at about 1 Hz, so the clap cannot reach the LiDAR timeline. Motion correlation gives sub-frame accuracy if the trajectory includes orientation at ≥10 Hz. _Alternatives:_ If the trajectory has position only or low rate, search the time offset jointly with Sim3 alignment of SfM camera centres vs the BLK2GO trajectory, or skip time entirely and use image-based or point-cloud registration (next item).
- **Estimate the BLK2GO-to-splat transform by two independent, time-free methods. First, Sim3 registration of SfM sparse points or splat centres to the LiDAR (coarse via BLK2GO WayPoint/rectified-image matching, then ICP). Second, rectified BLK2GO images with known poses added to SfM as fixed anchors. Then compare with the trajectory-based extrinsic and with the tape-measured offset.** — The BLK2GO images are already in the LiDAR metric frame, which gives metric scale and frame directly and makes the agreement check the user wants possible without trusting time sync. _Alternatives:_ Ground-control targets (checkerboards or spheres) visible to both sensors for a gold-standard check.
- **Define the physical offset prior against a documented physical feature of the BLK2GO (e.g., dome top centre or base), and empirically locate Leica's trajectory reference point by static start/end poses at a measured height over ground.** — The BLK2GO trajectory reference point and axes are undocumented; an unknown lever arm of several cm would otherwise look like disagreement between the measured and estimated offsets. _Alternatives:_ Estimate the reference from the WayPoint panorama poses relative to trajectory points if both are in the E57.
- **Mount the Insta360 below the handle, inside the BLK2GO's lower ~90° LiDAR blind cone (FoV 360x270°). Mask the rig and operator in Insta360 frames before SfM and splatting, and expect the Insta360 to appear in some BLK2GO panoramas.** — This avoids occluding the LiDAR, and avoids splat floaters and SfM outliers from the rig. _Alternatives:_ A rigid pole-mounted offset later; calibrate once indoors with targets.
- **Python stack: laspy[lazrs] (LAS/LAZ), pye57 (E57 points plus images and poses via libe57 BlobNode), PDAL via conda-forge only if pipelines or reprojection are needed. Recentre to a local origin, store the offset as metadata, and use float32 only after recentring.** — All are permissively licensed (BSD-2, MIT, BSL-1.0, BSD) with win_amd64 wheels for cp310-cp314 (PDAL via conda). This avoids int32 and float32 precision pitfalls when georeferencing in SWEREF 99 TM. _Alternatives:_ Open3D or CloudCompare for inspection; cry-inc e57 Rust CLI for quick image extraction.
- **For the optional Luciad delivery path, export the splat as OGC 3D Tiles with glTF KHR_gaussian_splatting (or KHR_gaussian_splatting_compression_spz_2) in addition to the web-viewer format.** — LuciadRIA 2026.1 and LuciadCPillar 2026.1 consume exactly that. No Leica Cyclone or GeoCloud splat product was found, so Luciad is the only in-house splat consumer and needs no proprietary SDK for data production. _Alternatives:_ Skip Luciad entirely; the Three.js viewer stays primary.
- **Capture protocol per walk: stationary 10 s at start, rig twists for sync, slow walk (≤1 m/s), no fast yaw, 2 laps of the 10x10 m loop ending at the start pose, stationary twists and 10 s at end; keep each walk to 2-5 min; record at ≥0 °C.** — Leica accuracy specs assume short (2-3 min) scans; loop closure and static ends help SLAM and give sync and lever-arm calibration events; the BLK2GO is specified only 0 to +40 °C. _Alternatives:_ Split long tropical loops into several overlapping walks registered in REGISTER 360 PLUS.

## Load-bearing findings (claim + sources)

- [high] BLK2GO (original) core specs: 420,000 pts/s; 830 nm Class 1; FoV 360° H x 270° V; range 0.5-25 m; 12 MP detail camera 90°x120° rolling shutter; 3-camera panoramic system 4.8 MP 300°x135° global shutter; 650 g (775 g with battery); 279 mm x 80 mm; 45-50 min battery; 24 h compressed / 6 h uncompressed storage; IP54; designed for indoor and outdoor use. — https://entertainment.leica-geosystems.com/wp-content/uploads/2024/08/BLK2GO_SpecSheet.pdf https://leica-geosystems.com/-/media/files/leicageosystems/products/datasheets/leica-blk2go-ds-0521.pdf https://shop.leica-geosystems.com/sites/default/files/2025-09/BLK2GO_SpecSheet.pdf
- [high] GrandSLAM = LiDAR SLAM + visual SLAM (panoramic cameras) + IMU. The IMU model and specs are not published. The 3 panoramic cameras capture images about every second (≈1 Hz); these colourise the cloud and become WayPoint panoramas. — https://www.ecedesign.com/wp-content/uploads/Leica-Cyclone-REGISTER-360-2020-REL-18032020.pdf https://rcdocs.leica-geosystems.com/cyclone-register-360/latest/blk2go-support https://leica-geosystems.com/products/laser-scanners/scanners/leica-blk2go
- [high] The BLK2GO PULSE is a different, indoor-only first-person scanner and is not suitable for forest capture. — https://shop.leica-geosystems.com/sites/default/files/2023-11/BLK2GO_PULSE_SpecSheet.pdf https://www.thefuture3d.com/equipment/compare/leica-blk2go-vs-blk2go-pulse/
- [low] No public Leica document gives the BLK2GO trajectory reference point or the body-frame axis convention. — https://rcdocs.leica-geosystems.com/llms.txt
- [medium] Cyclone REGISTER 360 PLUS publish formats: E57 (one file or separate files; structured or unstructured), RCP (unified or setups), PTS, PTX (XYZ + intensity), PTG, LAS (unstructured, no images or structure), SEMA, LGS/LGSx, TruView Local/Enterprise/Cloud and JetStream. BLK2GO data is handled as unstructured. — https://rcdocs.leica-geosystems.com/cyclone-register-360/latest/third-party-file-export https://rcdocs.leica-geosystems.com/cyclone-register-360/latest/export-settings https://www.ecedesign.com/wp-content/uploads/Leica-Cyclone-REGISTER-360-2020-REL-18032020.pdf
- [high] The E57 export of BLK kinematic data with WayPoints and rectified images (GUI or CLI b2g2trajectory) holds the richest metadata available without an SDK. It requires a Cyclone WORKFLOW license. — https://rcdocs.leica-geosystems.com/cyclone-register-360/latest/b2g-to-e57 https://rcdocs.leica-geosystems.com/docs/cyclone-register-360-export-blk-kinematic-data-to-e57-with-waypoints-and-images.md https://rcdocs.leica-geosystems.com/cyclone-register-360/latest/2023-1-0-cyclone-register-360-plus-release-notes
- [high] The trajectory can be exported to CSV from the BLK Live app (free), Cyclone FIELD 360 and BLK Data Manager; the CSV column layout, sample rate, orientation representation and time base are undocumented. — https://apps.apple.com/us/app/blk-live/id1608854881 https://hexagondownloads.blob.core.windows.net/public/Leica/TLS%20Software%20Installers/Cyclone%20Installers/BLK%20Data%20Manager%20Installer/Leica%20BLK%20Data%20Manager%20Release%20Notes.pdf https://rcdocs.leica-geosystems.com/cyclone-register-360/latest/workflow-for-cyclone-field-360-and-blk-kinematic-scanners
- [medium] Timestamps: Cyclone shows WayPoint 'time and distance from the start point' (relative time base), plus track duration/length and acquisition date/time. Whether BLK2GO LAS/E57 point exports carry per-point time could not be verified. — https://rcdocs.leica-geosystems.com/docs/cyclone-register-360-tracks-and-waypoints-properties-and-navigation.md https://raw.githubusercontent.com/asmaloney/libE57Format/master/include/E57SimpleData.h https://rcdocs.leica-geosystems.com/cyclone-3dr/2026.1/ExportC
- [medium] BLK2GO images can be exported with poses: WayPoint panoramas (JPEG; EXR with WORKFLOW) with a TXT of positions and orientations, panorama coordinates via TruView Local SWLocation.xml, detail images as JPEG GeoTags, and rectified images inside E57 with quaternion+translation poses and pinhole intrinsics. — https://rcdocs.leica-geosystems.com/cyclone-register-360/latest/export-import-and-re-import-panoramic-images https://webapp.atis.cloud/support/article/49 https://rcdocs.leica-geosystems.com/cyclone-register-360/latest/b2g-to-e57
- [high] Python reading stack on Windows: laspy 2.7.0 + lazrs 0.8.2 for LAS/LAZ; pye57 0.4.19 for E57 points and, via its libe57 bindings, images2D blobs and poses; PDAL 2.10.0 through conda-forge for pipelines. — https://pypi.org/pypi/laspy/json https://laspy.readthedocs.io/en/latest/installation.html https://laspy.readthedocs.io/en/latest/intro.html

## Key numbers

- BLK2GO point rate: 420,000 pts/s (https://entertainment.leica-geosystems.com/wp-content/uploads/2024/08/BLK2GO_SpecSheet.pdf)
- BLK2GO range: 0.5 - 25 m; 830 nm; FoV 360° x 270° (https://entertainment.leica-geosystems.com/wp-content/uploads/2024/08/BLK2GO_SpecSheet.pdf)
- BLK2GO range noise / indoor accuracy (current sheet): ±3 mm / ±10 mm (1 sigma, 2-min controlled scan) (https://entertainment.leica-geosystems.com/wp-content/uploads/2024/08/BLK2GO_SpecSheet.pdf)
- BLK2GO relative / absolute indoor accuracy (2019 sheet): 6-15 mm / 20 mm (https://shop.leica-geosystems.com/sites/default/files/2025-09/BLK2GO_SpecSheet.pdf)
- BLK2GO cameras: 12 MP 90°x120° rolling-shutter detail cam; 3-camera panoramic 4.8 MP 300°x135° global shutter (https://entertainment.leica-geosystems.com/wp-content/uploads/2024/08/BLK2GO_SpecSheet.pdf)
- Panoramic image capture rate: ~1 Hz ('every second') (https://www.ecedesign.com/wp-content/uploads/Leica-Cyclone-REGISTER-360-2020-REL-18032020.pdf)
- BLK2GO weight / size / battery: 650 g (775 g with battery); 279 x 80 mm; 45-50 min (https://entertainment.leica-geosystems.com/wp-content/uploads/2024/08/BLK2GO_SpecSheet.pdf)
- BLK2GO operating temperature: 0 to +40 °C (2021 sheet); +5 to +40 °C (2019 sheet); IP54 (https://entertainment.leica-geosystems.com/wp-content/uploads/2024/08/BLK2GO_SpecSheet.pdf)
- BLK2GO PULSE LiDAR: 2 ToF sensors, 7,816 spots, 5 fps, 210°x85°, 0.5-10 m, 940 nm; accuracy indoor ±2 cm; range noise ±15 mm RT / ±5 mm PP (https://shop.leica-geosystems.com/sites/default/files/2023-11/BLK2GO_PULSE_SpecSheet.pdf)
- WayPoint interval: default 10 m, minimum 1 m (https://www.ecedesign.com/wp-content/uploads/Leica-Cyclone-REGISTER-360-2020-REL-18032020.pdf)
- Example walk size: 156 s walk = 1.8 GB .b2g; example walk 115,772,253 points (https://www.ecedesign.com/wp-content/uploads/Leica-Cyclone-REGISTER-360-2020-REL-18032020.pdf)
- BLK Live latest version: 3.0.2 (2025-07-22); BLK2GO e57/jpeg/csv-trajectory export since 2.0.0 (2023-12-13) (https://apps.apple.com/us/app/blk-live/id1608854881)
- Cyclone REGISTER 360 PLUS latest: 2026.1.1 (BLK2GO driver installer discontinued; update note dated 2026-08-12) (https://rcdocs.leica-geosystems.com/cyclone-register-360/latest/2026-1-1-cyclone-register-360-plus-release-notes)
- Cyclone 3DR 2025.2.0 release date: 2025-11-06 (https://rcdocs.leica-geosystems.com/v1/docs/cyclone-3dr-2025-2-0-cyclone-3dr-release-notes)
- Reality Cloud Studio rebrand: Renamed Hexagon GeoCloud on 2026-04-20 (https://rcdocs.leica-geosystems.com/docs/hexagon-geocloud-2026-hexagon-geocloud-release-notes.md)
- Luciad Gaussian splat support: LuciadRIA 2026.1 and LuciadCPillar 2026.1: OGC 3D Tiles + glTF KHR_gaussian_splatting / KHR_gaussian_splatting_compression_spz_2 (https://dev.luciad.com/portal/productDocumentation/LuciadRIA/docs/releasenotes.html)
- laspy: 2.7.0, 2026-01-14, BSD-2-Clause, Python >=3.10 (https://pypi.org/pypi/laspy/json)
- lazrs: 0.8.2, 2026-07-27, MIT, win_amd64 cp310-cp314 (https://pypi.org/pypi/lazrs/0.8.2/json)
- pye57: 0.4.19, 2025-11-26, MIT, win_amd64 cp310-cp314 (+cp314t) (https://pypi.org/pypi/pye57/0.4.19/json)
- PDAL: 2.10.0 released 2026-02-13 (BSD), Windows via conda-forge; python-pdal 3.5.5 (2026-07-31) (https://pdal.io/en/latest/download.html)
- LAS int32 coordinate limit at scale 0.001: ±2,147,483 m (offset required for SWEREF 99 TM northings ~6.5e6 m) (arithmetic from LAS int32 storage per https://laspy.readthedocs.io/en/latest/intro.html)
- float32 spacing at 6.5e6 m: 0.5 m (recentre before GPU upload) (arithmetic (IEEE-754 24-bit mantissa))

## Tools & licenses

- Leica Cyclone REGISTER 360 PLUS (incl. BLK Edition) | 2026.1.1 (2026) | Proprietary (Leica; CCP/subscription). WORKFLOW add-on needed for kinematic E57 with WayPoints and images, EXR panoramas and b2g2trajectory. | win: Yes (Windows only) | Imports B2G. Exports E57/PTS/PTX/PTG/RCP/LAS/SEMA/LGS(x)/TruView. CLI: Register360.exe -b2g2trajectory.
- Leica Cyclone 3DR | 2025.2.0 (2025-11-06); 2026.0.1; 2026.1.0 | Proprietary (Leica) | win: Yes | Exports LAS/LAZ 1.4 with optional timestamps, classification and returns, and E57 with timestamps and images. LGSx trajectory import/export.
- BLK Live app | 3.0.2 (2025-07-22) | Proprietary, free app | win: No (iOS/Android) | Exports BLK2GO point cloud .e57, detail images .jpg and trajectory .csv.
- BLK Data Manager | 2026.1.1 | Proprietary (Leica); free-of-charge status not confirmed | win: Yes | Downloads B2G, .b2gjob XML and assets. Exports E57/PTX, JPEG detail images and CSV trajectories (per 2024.0.1 notes).
- Cyclone FIELD 360 | 7.1 (2026-09) | Proprietary (Leica) | win: No (iOS/Android) | Exports E57/PTX, trajectory CSV and detail JPEGs for BLK kinematic scanners.
- LuciadRIA / LuciadCPillar | 2026.1 | Proprietary (Hexagon) | win: RIA: browser; CPillar: native | Renders Gaussian splats from OGC 3D Tiles with glTF KHR_gaussian_splatting / KHR_gaussian_splatting_compression_spz_2.
- laspy | 2.7.0 (2026-01-14) | BSD-2-Clause | win: Yes (pip) | LAS 1.0-1.4, point formats 0-10, COPC, chunked I/O, CRS via pyproj.
- lazrs (lazrs-python) | 0.8.2 (2026-07-27) | MIT | win: Yes, win_amd64 cp310-cp314 | Multithreaded LAZ backend for laspy; no waveform support.
- laszip (laszip-python) | not checked | LGPL-2.1 for the LASzip library (background knowledge; not verified this session) | win: Yes (pip) | Single-threaded alternative LAZ backend; supports waveforms.
- pye57 | 0.4.19 (2025-11-26) | MIT (wraps libE57Format BSL-1.0) | win: Yes, win_amd64 cp310-cp314 | read_scan / read_scan_raw; libe57 bindings expose BlobNode.read_buffer for images2D.
- libE57Format | 3.3.x (used by PDAL 2.10 and Cyclone 3DR 2026) | BSL-1.0 | win: Yes | Reference C++ E57 implementation.
- PDAL (+ python-pdal) | PDAL 2.10.0 (2026-02-13); python-pdal 3.5.5 (2026-07-31) | BSD | win: Yes via conda-forge (64-bit only) | readers.e57 ignores images and spherical clouds; useful for reprojection, filters and COPC writing.
- cry-inc e57 (Rust crate + CLI tools) | not checked | MIT | win: Yes (build or cargo) | e57-extract-xml, e57-to-image, e57-unpack, e57-to-laz: quick inspection of Leica E57 metadata and images.
- e57 (Python, dancergraham) | 0.2.3 (2024) | MIT | win: Yes | Rust-backed E57 point reader; less feature-complete than pye57 for images.

## risks

- The trajectory CSV may lack orientation or be low-rate. That would weaken motion-based time sync and hand-eye calibration, forcing reliance on image or point-cloud registration.
- Per-point timestamps may be absent from BLK2GO exports, so LiDAR timing cannot be used directly.
- Leica's trajectory reference point is undocumented, so a cm-level lever-arm mismatch could make the measured and estimated offsets 'disagree' spuriously.
- License gating: E57 with WayPoints and rectified images (and b2g2trajectory) requires Cyclone WORKFLOW. EXR panoramas and panorama re-import need WORKFLOW. LAS publishing historically required PUBLISHER Pro.
- Software churn: REGISTER 360 PLUS 2026.1.1 dropped the BLK2GO driver installer (USB import still works). E57 Separate-Setups exports before 2026.0.0 could drop WayPoints and panoramas. libE57Format 3.3.0 E57s may break older readers.
- Unit settings may export in feet; enforce metres.
- Environmental limits: 0 °C lower bound (Swedish autumn/winter), IP54 with condensation risk in tropics. Leica accuracy specs are indoor, 2-minute, controlled scans; forest SLAM drift is unquantified.
- The rig is visible in both sensors' imagery: BLK2GO colourisation and panorama artefacts, and Insta360 frames containing the BLK2GO and operator, so masks are needed.
- BLK2GO images are low-resolution, about 1 Hz and include the operator, so they are unsuitable as primary splat training data.
- Large point counts (tens to hundreds of millions) mean memory pressure in numpy; chunked I/O and voxel decimation are needed.
- Research gap: the WebSearch budget ran out, so capture guidance and community knowledge (Reddit/LinkedIn/forums) on trajectory CSV contents could not be verified.

## open_questions

- What exact columns, sample rate, orientation representation (quaternion or Euler or none) and time base does the BLK2GO trajectory CSV from BLK Live, FIELD 360 or BLK Data Manager contain?
- Does the E57 'trajectory as points' cloud from b2g2trajectory carry per-point timeStamp and/or orientation (e.g., encoded as normals), and at what rate?
- Do BLK2GO LAS/E57 point exports contain non-zero per-point timestamps (GpsTime/timeStamp)? If so, what epoch (device clock, walk start)?
- Where is the BLK2GO's trajectory/body reference point (LiDAR centre, IMU, panoramic-rig centre), and what are the body axes?
- Are the 'rectified images' in the E57 per-camera pinhole images with full intrinsics and acquisition times? What is their resolution and count per second?
- Which Cyclone licenses (REGISTER 360 PLUS standard vs BLK Edition, WORKFLOW, PUBLISHER Pro, Cyclone 3DR) does the user's Hexagon account include, and is LAS export gated?
- Is there an unreleased or preview Hexagon splat feature (e.g., in GeoCloud) not visible in public release notes? The search budget was exhausted before trade press could be checked.
- Real-world BLK2GO SLAM drift in dense forest (Swedish conifer, tropical): no primary numbers retrieved.

## questions_for_user

- Is your scanner the original BLK2GO or the BLK2GO PULSE, and which firmware version?
- Which Cyclone products and licenses do you have: REGISTER 360 PLUS (standard or BLK Edition), Cyclone WORKFLOW (needed for E57 with WayPoints and rectified images / b2g2trajectory), PUBLISHER Pro, Cyclone 3DR?
- Do you record with BLK Live, Cyclone FIELD 360, or button-only? That decides where the trajectory CSV comes from.
- Can you do one short test walk and share the first lines of the trajectory CSV plus the E57 XML header (e.g., from e57-extract-xml) so the planner can lock the sync and extrinsic method?
- Will the Swedish test happen at or above 0 °C? The BLK2GO is specified for 0 to +40 °C.
- Do you want the final data georeferenced (e.g., SWEREF 99 TM + RH 2000 via control points), or kept in the BLK2GO local frame?
- Can you reach internal Leica/Hexagon contacts for the B2G trajectory export spec or the BLK2GO reference-point definition?

## FACT-CHECK: non-confirmed verdicts

- **CORRECTED**: BLK Live 2.0.0 (2023-12-13) introduced BLK2GO export of point cloud to .e57, detail images to .jpeg and trajectory to .csv. 2.1.0 (2024-04-11) added PULSE and RCS upload. The latest is 3.0.2 (2025-07-22). → The App Store history gives:
- 2.0.0 (2023-12-13): 'Support of BLK2GO and BLK2GO PULSE', a new immersive capture mode.
- 2.1.0 (2024-04-11): 'Export of the point cloud to .e57, detail images to .jpeg and trajectory to .csv'. The CSV trajectory export arrived here, not in 2.0.0.
- 2.2.0 (2024-09-23): full point-cloud streaming.
- 3.0.0 (2025-05-20): in-app firmware updates and an 'Image security setting allows you to disable image creation on BLK2GO'. That setting must stay OFF, or there will be no panoramas, colour or WayPoints.
- 3.0.2 (2025-07-22): latest. The app is free; the seller is Leica Geosystems AG. (https://apps.apple.com/us/app/blk-live/id1608854881)
- **CORRECTED**: BLK Data Manager (2024.0.1 notes) exports E57/PTX, JPEG detail images and CSV trajectories. → The report misreads the 2024.0.1 notes. The bullet list containing 'Exporting detailed images to JPEG and trajectories to CSV' and 'Exporting ... to the E57 or PTX file format' describes Cyclone FIELD 360 features, in the context of BLK ARC.

What the notes document for BLK Data Manager: it downloads jobs over USB-C/Wi-Fi into a folder of .b2g files, a .b2gjob XML (pre-alignment links, asset links) and assets (.jpg/.mov), which are then dragged into REGISTER 360 PLUS. The 2026.x Data Manager releases are compatibility-only.

The documented CSV trajectory sources for BLK2GO are BLK Live (≥2.1.0) and Cyclone FIELD 360 (BLK2GO/PULSE support from 5.0). The REGISTER 360 PLUS 2023.1.0 notes say so too. (https://hexagondownloads.blob.core.windows.net/public/Leica/TLS%20Software%20Installers/Cyclone%20Installers/BLK%20Data%20Manager%20Installer/Leica%20BLK%20Data%20Manager%20Release%20Notes.pdf https://rcdocs.leica-geosystems.com/cyclone-register-360/latest/workflow-for-cyclone-field-360-and-blk-kinematic-scanners)
- **CORRECTED**: REGISTER 360 PLUS 2026.1.0 lists a known issue where panoramas fail to display when BLK2GO data is linked with RTC360 data. FAFx import is not supported for BLK2GO. → FAFx being unsupported for BLK2GO and BLK ARC is confirmed. The panorama-display problem with BLK2GO linked to RTC360 is listed as a FIXED issue in 2026.1.0, not an open known issue. (https://rcdocs.leica-geosystems.com/cyclone-register-360/latest/2026-1-0-cyclone-register-360-plus-release-notes)
- **CORRECTED**: Leica says E57 cannot be re-imported into REGISTER 360, so keep the .b2g as master. → The source statement is version-specific and dated 2020: BLK2GO E57s 'CANNOT be imported into REGISTER 360 2020 or earlier'. Current docs treat unstructured sources (BLK2GO, LGS, LAS) as normal inputs, and E57 import exists in 2026.x (2026.1.0 fixes a Trimble E57 import bug). The recommendation to keep the B2G as master still holds, for a different reason: only the B2G retains the WayPoints, GeoTags, track editing and re-export options. The same 2020 notes also describe 'Export E57 to folder' at import, which writes a colourised E57 straight from the B2G without importing. (https://www.ecedesign.com/wp-content/uploads/Leica-Cyclone-REGISTER-360-2020-REL-18032020.pdf https://rcdocs.leica-geosystems.com/cyclone-register-360/latest/third-party-file-export)
- **CORRECTED**: Cyclone 3DR exports LAS/LAZ 1.4 with optional timestamps, and E57 with timestamps and images. 2026.0.1 added an E57 backward-compatibility option because the libE57Format 3.3.0 update broke some readers. 2025.2.0 released 2025-11-06 with LGSx trajectory import/export. The latest is 2026.1.0. → All feature claims are confirmed. ExportC reads: 'LAS/LAZ format file (version 1.4)' with 'timestamps', and E57 'including ... timestamp ... if available' plus 'perspective, cubefaces, spherical images'. The 2025.2.0 date and 'Trajectory (mobile scanner)' LGSx import/export are confirmed. 2025.2.0 Convert Project also splits Mobile from Static clouds and uses BLK2GO as its example.

The version is wrong: the latest Cyclone 3DR is 2026.1.4 (2026-09-30), after 2026.1.1 (07-01), 2026.1.2 (08-04) and 2026.1.3 (08-31). The 2026.1.0 note page is stamped 2026-09-07. 2026.1.0 itself adds no splat feature. (https://rcdocs.leica-geosystems.com/cyclone-3dr/2026.1/ExportC https://rcdocs.leica-geosystems.com/cyclone-3dr/2026.0/2026-0-1-cyclone-3dr-release-notes)
- **CORRECTED**: Hexagon Luciad 2026.1 (LuciadRIA, LuciadCPillar) renders Gaussian splats delivered as OGC 3D Tiles with glTF KHR_gaussian_splatting or KHR_gaussian_splatting_compression_spz_2. It depends on tinyply and spz. Luciad is the in-house Hexagon splat consumer. → The technical part is confirmed verbatim from the LuciadRIA release notes and the CPillar new-features page (GaussianSplatsStyle). KHR_gaussian_splatting is now 'Complete, Ratified by the Khronos Group'.

The ownership framing is outdated. Octave's own site says: 'In 2025, Hexagon AB initiated a spin-off of its Asset Lifecycle Intelligence and Safety, Infrastructure and Geospatial divisions ... that spin-off became Octave', which 'operates as a separate, standalone company'. Luciad was rebranded Octave Alto:
- LuciadRIA became 'Octave Alto Browser'.
- LuciadCPillar became 'Octave Alto Universal'.
- LuciadLightspeed became 'Octave Alto Lightspeed'.
- LuciadFusion became 'Octave Alto Server'.

luciad.com now redirects to hexagon.com and returns 403. The dev.luciad.com 2026.1 docs still carry '©2026 Hexagon AB'. Luciad is therefore no longer clearly a Hexagon in-house product, and the user's licence access should be re-checked. (https://dev.luciad.com/portal/productDocumentation/LuciadRIA/docs/releasenotes.html https://dev.luciad.com/portal/productDocumentation/LuciadCPillar/docs/articles/tutorial/releaseguide/newfeatures.html)
- **CORRECTED**: cry-inc e57 (Rust, MIT) provides e57-extract-xml, e57-to-image, e57-unpack and e57-to-laz; libE57Format 3.3.x is BSL-1.0. → cry-inc e57 is confirmed: MIT, crate version 0.11.13. Its tools also include e57-to-pano, e57-extract-scan-info, e57-check-crc, e57-to-xyz and e57-from-xyz.

libE57Format is BSL-1.0, but the version is stale. The latest is 3.4.1 (2026-09-20), after 3.4.0 (2026-08-21) and 3.3.0 (2025-10-24). The 3.3.0 changelog lists a XercesC 3.2 requirement and no file-format change; the reader breakage is documented only in the Cyclone 3DR note. (https://raw.githubusercontent.com/cry-inc/e57/master/Cargo.toml https://github.com/cry-inc/e57/tree/master/tools)
- **UNVERIFIABLE**: No public document gives the BLK2GO trajectory reference point or body axes; the trajectory CSV columns, rate, orientation and time base are undocumented. → An absence cannot be proven. None of the roughly 30 RCDOCS pages, spec sheets and release notes fetched here defines them. Searches of community forums and Reddit were impossible because the search budget was exhausted. (https://rcdocs.leica-geosystems.com/llms.txt https://rcdocs.leica-geosystems.com/cyclone-register-360/latest/b2g-to-e57)
- **UNVERIFIABLE**: Capture guidance (static initialisation, slow walk, avoid whip turns, close loops, 2-5 min walks). → No Leica primary guidance could be retrieved: the shop support pages return 403. The only primary hints:
- FIELD 360 offers 'SLAM Guidance Feedback: Users will be guided with appropriate messages to follow best practices during initialization and scanning' (stated for BLK ARC).
- BLK Live offers 'Smart sensor feedback & guidance' (PULSE sheet).
- The BLK2GO light guide 'provides user guidance while scanning'.
- The accuracy specs assume 2-min (BLK2GO) and 3-min (PULSE) controlled scans. (https://hexagondownloads.blob.core.windows.net/public/Leica/TLS%20Software%20Installers/Cyclone%20Installers/BLK%20Data%20Manager%20Installer/Leica%20BLK%20Data%20Manager%20Release%20Notes.pdf https://shop.leica-geosystems.com/sites/default/files/2023-11/BLK2GO_PULSE_SpecSheet.pdf)
- **UNVERIFIABLE**: The laszip-python backend is LGPL-2.1. → Not checked this session. The report itself flags it as background knowledge. laspy docs confirm only that laszip is single-threaded and supports waveforms. (https://laspy.readthedocs.io/en/latest/installation.html)

_19 of 29 checked claims confirmed._


## FACT-CHECK: missed developments

- Hexagon spun off its software divisions, including Luciad, into Octave, a standalone company. Luciad products were rebranded Octave Alto.: Octave's site says: 'In 2025, Hexagon AB initiated a spin-off of its Asset Lifecycle Intelligence and Safety, Infrastructure and Geospatial divisions. Along with ETQ and Bricsys, that spin-off became Octave', and that it 'operates as a separate, standalone company'.

Renames from octave.com/alto:
- LuciadRIA became Octave Alto Browser.
- LuciadCPillar became Octave Alto Universal.
- LuciadLightspeed became Octave Alto Lightspeed.
- LuciadFusion became Octave Alto Server.
- ERDAS APOLLO became Octave Alto Data Management.

The footer reads '© 2026 Octave Intelligence plc'. luciad.com redirects to hexagon.com and returns 403. dev.luciad.com 2026.1 docs still show ©Hexagon AB.

Impact: Luciad is no longer clearly an 'in-house' Hexagon product for this user. Licence access and naming may change, which reinforces 'Luciad must not be a hard dependency'. (https://octave.com/about https://octave.com/alto)
- KHR_gaussian_splatting is now a ratified Khronos glTF extension.: The extension README status is 'Complete, Ratified by the Khronos Group'. Compression extensions are expected to extend it. This lowers the risk of the 3D Tiles + glTF splat export path for Luciad/Octave Alto and other viewers. The SPZ_2 compression extension did not appear in the Khronos folder listing. LuciadRIA notes reference it, so its location and status should be checked separately. (https://github.com/KhronosGroup/glTF/tree/main/extensions/2.0/Khronos/KHR_gaussian_splatting https://dev.luciad.com/portal/productDocumentation/LuciadRIA/docs/releasenotes.html)
- BLK Live 3.0.0 (2025-05-20) added a setting that can disable BLK2GO image creation.: 'Image security setting allows you to disable image creation on BLK2GO'. If it is enabled (for example, on a shared or company-configured device), there will be no panoramas, colourisation, WayPoint images or rectified images, and the image-based registration bridge disappears. The same release added in-app firmware updates for all BLK scanners. 3.0.2 (2025-07-22) is current. (https://apps.apple.com/us/app/blk-live/id1608854881)
- REGISTER 360 PLUS 2026.0.0 removed a 100-WayPoint-per-walk cap and added an Advanced Colorizer for B2G imports.: Two items from the 2026.0.0 notes:
- 'Fixed an issue that prevented users from creating more than 100 WayPoints in a single walk'. With interval=1 m, any walk over 100 m (long tropical loops, or 3 or more laps) would previously have been truncated.
- 'Advanced Colorizer option available in the Properties panel of the Import area' for B2G files.

Also fixed: GeoTag mispositioning when several BLK2GO jobs were imported directly. Advanced Colorizer does not work for BLK2FLY. (https://rcdocs.leica-geosystems.com/docs/cyclone-register-360-2026-0-0-cyclone-register-360-plus-release-notes)
- In the b2g2trajectory E57, pinhole rectified images use a fixed 6 µm pixel size, and the CLI silently reuses the last GUI import settings.: From the B2G-to-E57 page:
- Pinhole images have a 'Fixed pixel size: 6 micrometers'; focal length is in metres per the E57 standard.
- Spherical images use pixelWidth = 2π/width and pixelHeight = π/height.
- Pose quaternions come from the camera-to-panorama transformation.
- 'When users import .b2g data directly as E57, the Cyclone REGISTER 360 settings are not applied'; the CLI uses settings from the last BLK import.

For intrinsics: f_px = focalLength / 6e-6. Run one GUI import with the desired WayPoint and colour settings before using the CLI. (https://rcdocs.leica-geosystems.com/cyclone-register-360/latest/b2g-to-e57)
- PDAL's E57 reader merges every point cloud in a file and keeps only the dimensions they share.: readers.e57 'reads all the points from all of the internal point clouds as one' and 'only dimensions present in all of the point clouds will be read'. On a b2g2trajectory E57 (main cloud plus trajectory-as-points cloud), PDAL would mix trajectory points into the scene. It could also drop RGB, intensity and normals if the trajectory cloud lacks them. Use pye57 read_scan(index) per Data3D, or cry-inc e57-unpack. (https://pdal.io/en/latest/stages/readers.e57.html https://rcdocs.leica-geosystems.com/cyclone-register-360/latest/b2g-to-e57)
- Newer versions exist than the report lists.: Version updates:
- Cyclone 3DR 2026.1.1 (2026-07-01), 2026.1.2 (2026-08-04), 2026.1.3 (2026-08-31) and 2026.1.4 (2026-09-30) postdate the report's 'latest' of 2026.1.0.
- libE57Format is at 3.4.1 (2026-09-20), after 3.4.0 (2026-08-21). 3.3.0 dates from 2025-10-24.
- Cyclone FIELD 360 7.1 was released 2026-09-15.
- GeoCloud has 28 updates in 2026, through 2026-10-05.

Other updates:
- GeoCloud: on 2025-05-27, B2G uploads from BLK2GO, PULSE and ARC began importing the full dataset, not a filtered one.
- GeoCloud: on 2026-07-06, scans began opening in the registration coordinate system. (https://rcdocs.leica-geosystems.com/docs/cyclone-3dr-2026-cyclone-3dr-release-notes.md https://raw.githubusercontent.com/asmaloney/libE57Format/master/CHANGELOG.md)
- Cyclone 3DR 2025.2 offers a further trajectory route: Convert Project on multi-sensor LGSx, plus LGSx trajectory import/export.: 3DR 2025.2.0 (2025-11-06) imports and exports 'Trajectory (mobile scanner)' as LGSx. Convert Project has 'All | Static | Mobile' modes and uses BLK2GO as its mobile example; it works with LGSx from REGISTER 360 PLUS 2025.0+. If the CSV from BLK Live or FIELD 360 lacks orientation, the trajectory object in 3DR is another place to look for poses, possibly with time and colour-by-timestamp display. Whether 3DR exports a trajectory to an open text format is unverified. (https://rcdocs.leica-geosystems.com/v1/docs/cyclone-3dr-2025-2-0-cyclone-3dr-release-notes https://rcdocs.leica-geosystems.com/cyclone-3dr/2026.1/ExportC)

## FACT-CHECK: recommendation assessment

Note on method: the shared WebSearch budget was already used up when this check started. Everything above was verified by fetching primary URLs directly (RCDOCS, spec-sheet PDFs read page by page, App Store, PyPI JSON, GitHub, pdal.io, Luciad docs, octave.com). Trade press and community forums could not be checked.

The core recommendations survive:
- Use the original BLK2GO, not the PULSE.
- Do a day-1 metadata-discovery export.
- Keep the B2G as master.
- Derive E57, LAZ and CSV artefacts.
- Use two independent, time-free registration methods compared against the tape-measured prior.
- Use the laspy[lazrs] / pye57 / conda-PDAL stack with recentring.
- Optionally export 3D Tiles + KHR_gaussian_splatting.

Changes I would make:

1. **Trajectory sources.** Drop BLK Data Manager as a CSV trajectory source; that was a misread of FIELD 360 features. Record every walk through BLK Live (version 2.1.0 or later; 3.0.2 is current) or Cyclone FIELD 360 (5.0 or later; 7.1 is current), because those are the documented BLK2GO CSV trajectory exporters. Before capture, check that BLK Live's 3.0.0 'Image security' setting has not disabled BLK2GO image creation, and that the REGISTER 360 'create WayPoints and colorize' setting is on. Otherwise there will be no panoramas, colour or WayPoints.

2. **REGISTER 360 PLUS version.** Pin 2026.0.0 or later for two reasons: the fix for missing WayPoints/panoramas in one-file Separate-Setups E57 export, and the fix for the 100-WayPoint cap. The cap matters at interval=1 m on long tropical walks. Note that the CLI reuses the settings of the last GUI BLK import, so do one GUI import with the intended settings first.

3. **Time sync is weaker than presented.** The E57 gives camera and pano poses only at WayPoint spacing (at least 1 m, so roughly 40 poses per lap of a 10x10 m loop). It cannot support gyro cross-correlation. Motion-signature sync is viable only if the CSV turns out to hold orientation at 10 Hz or more. Make the fallback the primary plan: a joint search over time offset plus Sim3 between SfM camera centres and timestamped CSV positions. Add one cheap visual event (low confidence, background knowledge): film the BLK2GO's start-button press and light-ring change with the Insta360 (and hear the press in Insta360 audio), then test empirically whether trajectory t=0 equals scan start.

4. **Python E57 reading.** Read b2g2trajectory E57s per scan with pye57, not PDAL. readers.e57 merges all clouds and keeps only common dimensions, so the trajectory cloud would pollute the scene cloud and could strip RGB, intensity and normals.

5. **Re-import rationale.** Replace 'E57 cannot be re-imported' with: keep the B2G because only it retains WayPoints, GeoTags and track editing. The 2020 statement applied to REGISTER 360 2020 and earlier. For LAS, the 2020 table shows LAS publishing requires PUBLISHER Pro, so converting E57 to LAZ in Python (laspy) remains the safest licence-independent path.

6. **Luciad.** Reframe it as an optional third-party target. Luciad is now Octave Alto (LuciadRIA became Octave Alto Browser) under Octave, a standalone spin-off from Hexagon. The user should confirm continued licence access, and keep the Three.js viewer primary. The 3D Tiles + KHR_gaussian_splatting path is still sound: the base extension is now Khronos-ratified, and Alto Browser 2026.1 also accepts the SPZ_2 compression extension.

7. **Smaller version fixes.** Cyclone 3DR's latest is 2026.1.4 (2026-09-30), and libE57Format's is 3.4.1 (2026-09-20). Expect BLK2GO panoramas to contain the operator, as Leica's own screenshot shows, as well as the Insta360. Mask them if they are used as SfM anchors.
