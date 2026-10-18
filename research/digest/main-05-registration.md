# registration

## Summary

Recommended approach: a staged, fused estimator. A robust Sim(3) on time-synced trajectories gives the initial alignment. Scaled ICP, then robust point-to-plane ICP on stable geometry (LiDAR ground plus tree trunks), fixes the world transform S (SfM world to LiDAR metric frame). After that the camera-to-LiDAR extrinsic X is read off per frame and checked against the tape measurement. The tape value is held out of the estimate.

The splat itself only needs S. Two consequences follow:
- The splat should not depend on time sync or on the extrinsic. Apply S to the COLMAP model with pycolmap Reconstruction.transform(Sim3d) or `colmap model_transformer` before training, so the splat is metric from the start.
- LiDAR depth supervision and LiDAR initialisation can also use S alone, by projecting LiDAR points into the transformed SfM cameras. No per-frame extrinsic or sync is needed for this.

The extrinsic and time offset are by-products that serve as a consistency check.

**1. Trajectory alignment.** Umeyama Sim(3) between SfM camera centres and LiDAR trajectory positions is available in several tools:
- evo 1.37.1 (2026-08-31, GPLv3): plain least squares, nearest-time association with max_diff 0.01 s and an offset parameter. It has no RANSAC.
- COLMAP model_aligner: RANSAC Sim3 with alignment_max_error, at least 3 images.
- pycolmap 4.2.1 (2026-09-29, BSD-3, Windows wheels CPU-only): align_reconstruction_to_locations with RANSACOptions, plus align_reconstructions_via_points and align_reconstructions_via_reprojections for joining Run 2 to Run 1.
- Open3D 0.20.0 (2026-09-16, MIT): TransformationEstimationPointToPoint(with_scaling=True).

The main pitfall is the lever arm. A position-only fit that ignores it is biased (my derivation):
- The vertical component (Insta360 taped about 10–15 cm below) is absorbed as a constant vertical shift of the whole splat.
- A lateral component l on a loop of radius about 5 m scales the camera loop, a scale bias of about l/R. For example, 5 cm gives about 1%.
- Horizontal components add about |l_h| of RMS residual.

So use full-pose alignment, T_L(t+dt)·X = S·T_C(t), solved jointly. Timing errors map to position error as v·dt: 10 ms at 1–1.4 m/s is 1–1.4 cm, and 0.6° at 60°/s.

Time sync: the clap only marks the Insta360 timeline, because the BLK2GO has no audio. A cross-device sync needs a motion event. Do 3–5 sharp yaw twists while standing still at the start and at the end. Cross-correlate the angular-speed magnitude |ω|, which does not depend on the frame, between:
- the differentiated BLK2GO trajectory, and
- the Insta360 gyro (X5 IMU logged at 1 kHz and readable by telemetry-parser; X4 is not listed) or the SfM rotations at full frame rate.

Estimate offset plus linear clock drift: an assumed 20–50 ppm over 10 min gives 12–30 ms.

**2. Hand-eye calibration.** OpenCV calibrateHandEye (AX=XB) and calibrateRobotWorldHandEye (AX=ZB; SHAH and LI methods) need at least 2 motions with non-parallel rotation axes. Neither estimates scale. Methods with unknown scale exist (Andreff, SfM hand-eye; Wodtko 2021 dual quaternions; Wise et al. IJRR 2026, certifiably optimal with identifiability criteria). In practice:
- Get scale from Sim(3) or geometry.
- Get R_X from the rotation axes, or Kabsch on angular velocities.
- Solve [(R_A−I) | −R_X t_B][t_X; s] = −t_A by linear least squares.
- Refine with scipy least_squares using a robust loss.

Walking a flat loop is degenerate for t_X along gravity, because (R_A−I) has the rotation axis in its null space. The information scales as 2·sin(φ/2):
- natural ±3° tilts with σ=1 cm per motion pair and N_eff=20 give σ_z ≈ 4 cm;
- deliberate ±30° pitch/roll moves give σ_z ≈ 0.4 cm.

If S comes from geometry, the per-frame X_i = T_L^-1·S·T_C is observable in all six degrees of freedom and this degeneracy goes away. Kalibr is ROS1/Ubuntu only and has no LiDAR support. The BLK2GO raw IMU and scans are not accessible anyway.

**3. Geometry registration.** FPFH is not scale invariant, so pre-scale first, from trajectory Sim3, targets, or camera height.
- Global options: Open3D RANSAC/FGR. TEASER++ (MIT; estimates scale; over 99% outliers) has no Windows support and is not on PyPI. KISS-Matcher 1.0.2 (MIT, May 2026) has no Windows wheels and is rigid only. probreg CPD with scale (MIT, 0.3.8, source distribution only) works on downsampled clouds.
- Refinement: Open3D scaled point-to-point ICP, then point-to-plane or GICP with Tukey/Cauchy kernels and shrinking correspondence distances (0.5, 0.2, 0.05 m). small_gicp 1.0.1 (MIT, Windows wheels) is fast but rigid only.
- In forests, restrict to LiDAR ground (CSF, Apache-2.0) and trunks. Use only SfM points with track length ≥4 and reprojection error <1 px. Exclude foliage, which moves in wind and gives mixed edge returns. Prefer SfM/MVS points over splat centres.

**4. Fused estimator and tape comparison.** Do a joint robust least squares over S, X, dt and drift, with pose-consistency and point-to-plane residuals. Get uncertainty from the Jacobian covariance plus a block bootstrap over 5–10 s segments. Compare against the tape in a gravity-aligned rig frame. Proposed pass thresholds are listed under the tape-comparison recommendation below.

What disagreement patterns mean:
- Residual along the direction of travel, proportional to speed: time offset.
- Error proportional to distance from the centroid, or per-side scale spread: scale error or drift.
- X varying over time or with turns: mount flex.
- Errors near 90°/180°, a flipped axis, or wxyz vs xyzw quaternion order: convention mistakes. Common causes are COLMAP storing cam_from_world, COLMAP's y-down/z-forward camera frame, and LAS being Z-up.
- A constant offset in the body frame while rotation agrees: the lever arm was measured to the wrong reference point. The BLK2GO trajectory reference point is undocumented, and the stitched Insta360 centre is roughly between the lenses.
- A vertical-only gap with large σ_z: weak observability, not a real disagreement.

**5. Loop closure.** A closed loop lets the BLK2GO SLAM correct its drift (not verified in Leica docs). On the SfM side, COLMAP sequential matching with vocab-tree loop detection plus global BA removes most scale drift, and a 360 camera sees revisited places from any heading. Monocular global scale stays unobservable but is fixed by S. Check for drift by fitting a Sim3 per side of the square: a scale spread above 0.5% means drift. If that happens, use pose_prior_mapper with LiDAR-derived camera positions.

**6. Validation.**
- LiDAR-friendly spheres and AprilTag boards (OpenCV aruco, Apache-2.0).
- Scale bars.
- Trunk diameter at 1.3 m fitted in both clouds as a forest-native scale check.
- Metrics: CloudCompare C2C/M3C2 or Open3D distances, reported per region (ground, trunks, canopy), per quadrant, and as the signed vertical bias on the ground.

Proposed targets: median below 2 cm on ground and trunks, P90 below 5 cm, independent target RMS below 2 cm. BLK2GO accuracy is about 6–15 mm relative (±10 mm indoor), so 1–2 cm is the floor.

Trainer pitfall: gsplat simple_trainer has normalize_world_space=True by default. The PLY is then saved in normalised coordinates (parser.transform). Set it to False or invert the transform. Also shift georeferenced coordinates to a local origin, because float32 precision breaks down at SWEREF-size values.

**8. Related systems.** FAST-LIVO2, GS-LIVO, Gaussian-LIC2, LiV-GS, LVI-GS, GS-LIVM, GS-SDF and LetsGo all use hardware-synced rigs with pre-calibrated extrinsics: FAST-Calib (circle-hole target), Kalibr. They run on Ubuntu/ROS and are mostly GPL. Not directly usable here.

Takeaways:
- LiDAR initialisation and sparse LiDAR depth supervision reduce floaters.
- Depth completion helps LiDAR-blind areas such as the canopy beyond 25 m.
- Calibration errors propagate directly into depth losses, which is another reason to supervise via S rather than via per-frame extrinsics.

Run 2 (no LiDAR): reconstruct jointly with Run 1, or align via align_reconstructions_via_points/reprojections, so it lands in the LiDAR frame without its own trajectory.

Note: the shared web-search budget ran out mid-research. The BLK2GO trajectory CSV columns, timestamp base and reference point, BLK2GO loop-closure details, and X4 IMU extraction could not be verified. They are listed as open questions.

## Recommendations

- **Implement a staged fused estimator in Python (numpy/scipy/Open3D/pycolmap): (0) coarse sync from file clocks, fine sync by |ω| cross-correlation of the start and end twists (offset + drift); (1) robust Sim3 (RANSAC or GNC-TLS Umeyama) of SfM rig-frame centres to LiDAR positions → S0; (2) scaled ICP, then robust point-to-plane ICP (Tukey/Cauchy, distances 0.5→0.2→0.05 m) of filtered SfM points against LiDAR ground and trunks → S_geo; (3) per-frame X_i = T_L(t_i+dt)^-1·S_geo·T_C(t_i), robust mean, and refine dt by minimising scatter of X_i; (4) joint scipy.optimize.least_squares over (S, X, dt, drift) with pose-consistency and point-to-plane residuals, soft_l1/cauchy loss; covariance from (JᵀJ)^-1·σ² plus a block bootstrap over 5–10 s segments.** — Geometry fixes all 7 DoF of S, including the vertical, without relying on motion richness or sync. The trajectory gives fast initialisation plus the extrinsic. The joint solve reconciles the two, and disagreement between them is itself a diagnostic. _Alternatives:_ Trajectory-only full-pose AX=ZB (OpenCV calibrateRobotWorldHandEye after scaling), weaker in z under planar motion. Sync-free anchoring with BLK2GO posed rectified images from E57 WayPoint export, aligned via model_aligner. Targets-only Sim3.
- **Make the splat metric from the start: apply S to the COLMAP model (pycolmap Reconstruction.transform(Sim3d) or colmap model_transformer), recentre to a local origin, then train with gsplat normalize_world_space=False (or invert parser.transform at export). Feed LiDAR depth and initialisation via S only.** — Avoids a post-hoc transform of Gaussian covariances and SH coefficients, keeps metric densification thresholds, and decouples splat quality from sync, extrinsic and mount-flex errors. _Alternatives:_ Train in SfM coordinates and apply the Sim3 to the PLY afterwards: scale positions and log-scales, rotate quaternions, and rotate SH coefficients above degree 0, which is error-prone.
- **Capture protocol: at the start and end of every run, stand still for 5 s, do 3–5 sharp yaw twists, then 20–30 s of ±30° pitch and roll 'calibration wiggle' facing textured structure 2–5 m away. Walk the loop closed, ending at the start. Keep the clap only as an Insta360-internal marker. Prefer an Insta360 X5 or newer (IMU readable at 1 kHz via telemetry-parser).** — The twists give a cross-device sync event that the BLK2GO actually records (it has no audio). The wiggle makes vertical lever-arm components observable (σ_z ≈ 4 cm drops to about 0.4 cm by my estimate). Start/end events give clock drift. _Alternatives:_ Sync only from SfM rotations (requires full-frame-rate extraction of the twist segments). Physical tap/jolt events.
- **Compare the tape measurement against the estimate in a gravity-aligned rig frame (z up from LiDAR ground/gravity, x = BLK2GO forward). Keep the tape value out of the estimate. Report a per-component difference with σ and a verdict. Proposed thresholds: lever-arm norm ≤2 cm and each component ≤max(3 cm, 3σ) PASS, 3–6 cm WARN, more than 6 cm or more than 5σ FAIL; rotation ≤2° PASS, 2–5° WARN, more than 5° FAIL; trajectory vs geometry scale agreement ≤0.3%; sync σ ≤5 ms.** — Tape and phone-inclinometer accuracy is about ±1–2 cm and ±1–3°, the BLK2GO floor is about 1 cm, and a taped mount flexes. These thresholds are my engineering proposal, not from a source. _Alternatives:_ After a PASS, re-run with the tape as a soft prior to tighten weak (vertical) components.
- **Diagnose disagreements automatically: regress residuals on velocity (slope = dt); fit per-side and per-segment Sim3 (scale spread = SfM drift); fit piecewise-constant X per segment and test against a single X with AIC/F-test (mount flex); flag rotation errors near 90°/180°, axis flips and quaternion-order swaps (convention: COLMAP cam_from_world, y-down/z-forward camera, LAS Z-up, three.js Y-up); flag a constant body-frame offset with matching rotation (lever arm measured to the wrong reference point).** — Each error source leaves a distinct signature, so the report can say why the two estimates disagree, not just that they do. _Alternatives:_ Manual inspection in CloudCompare.
- **Validate with independent scene targets visible to both sensors: 4–6 spheres (about 15–20 cm) on stakes at varied heights around the loop, AprilTag tag36h11 boards (OpenCV aruco) with spheres at known offsets, one measured scale bar, plus trunk diameter at 1.3 m fitted in both clouds. Report C2C/M3C2 (CloudCompare 2.13.2 or Open3D) per region (ground, trunks, canopy), per quadrant, and the signed ground bias. Targets: median ≤2 cm and P90 ≤5 cm on hard surfaces, target RMS ≤2 cm, ground bias ≤1 cm.** — Targets are not used by the estimator, so they give an honest check. Region-wise metrics keep wind-blown foliage from hiding real errors. _Alternatives:_ Natural features only (trunks, stones), cheaper but weaker.
- **Bring Run 2 (Insta360 only) into the LiDAR frame by reconstructing it jointly with Run 1 frames in one COLMAP model, or aligning separate models with pycolmap align_reconstructions_via_points/reprojections, then apply S. Capture both runs back-to-back.** — Run 2 has no LiDAR trajectory. Shared features with Run 1 carry S over to it. Short time between runs limits wind and lighting changes. _Alternatives:_ Geometry-only ICP of the Run 2 SfM to LiDAR, needing scale pre-estimation.
- **Library choices for Windows: Open3D 0.20.0, small_gicp 1.0.1, pycolmap 4.2.1, scipy 1.18.1, laspy 2.7.0 + lazrs, pye57 0.4.19, cloth-simulation-filter, opencv-contrib-python; evo only as a CLI and diagnostic (GPLv3). Skip TEASER++ and KISS-Matcher on Windows (use WSL2 if needed); probreg only if a scaled CPD fallback is required (needs MSVC build).** — All have Windows wheels and permissive licenses; the initial guess from the trajectory makes global matchers unnecessary. _Alternatives:_ GTSAM factor graph for the fused estimator (Windows wheels not verified).

## Load-bearing findings (claim + sources)

- [high] Position-only Umeyama Sim(3) between SfM camera centres and LiDAR trajectory is biased by the lever arm; use full-pose alignment or include the lever arm. — https://raw.githubusercontent.com/MichaelGrupp/evo/master/evo/core/geometry.py https://github.com/MichaelGrupp/evo/wiki/Metrics
- [high] COLMAP/pycolmap provide robust Sim3 alignment and model transforms: model_aligner (RANSAC, alignment_max_error, ≥3 images), model_transformer, pose_prior_mapper; pycolmap.align_reconstruction_to_locations(src, names, locations, min_common_images, ransac_options), align_reconstructions_via_points / via_reprojections, Reconstruction.transform(Sim3d). — https://colmap.github.io/changelog.html https://github.com/colmap/colmap/releases/tag/4.1.0 https://pypi.org/project/pycolmap/
- [medium] Time sync must come from a shared motion signal, not the clap: the clap only exists in Insta360 audio, which is already on the camera's own clock. — https://github.com/OVR-Platform/imu-metric-scale https://github.com/AdrianEddy/telemetry-parser/blob/master/README.md https://docs.gyroflow.xyz/app/getting-started/supported-cameras/insta360
- [medium] Walking a flat loop makes the lever-arm component along gravity weakly observable in motion-based hand-eye; deliberate tilt motions fix it. — https://arxiv.org/abs/2308.06045 https://arxiv.org/pdf/2311.12655 https://arxiv.org/abs/2311.11808
- [high] Scale-aware refinement: Open3D point-to-point ICP with with_scaling=True (Sim3 ICP) and probreg CPD (rigid + scale), then rigid point-to-plane or GICP with robust kernels. — https://www.open3d.org/docs/latest/python_api/open3d.pipelines.registration.TransformationEstimationPointToPoint.html https://www.open3d.org/docs/latest/tutorial/pipelines/robust_kernels.html https://pypi.org/project/open3d/
- [medium] In forests, register only on stable structure: LiDAR ground (CSF) and trunks, with filtered SfM points; foliage and splat centres are unreliable. — https://github.com/jianboqi/CSF https://www.cloudcompare.org/release/ https://www.open3d.org/docs/latest/tutorial/pipelines/robust_kernels.html
- [high] The splat only needs the world transform S; the extrinsic X and time offset are validation by-products. LiDAR depth supervision and initialisation can also use S alone. — https://github.com/isl-org/TanksAndTemples/tree/master/python_toolbox/evaluation https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/examples/datasets/colmap.py
- [high] gsplat simple_trainer defaults to normalize_world_space=True (T = optional flip · align_principal_axes · similarity_from_cameras, stored in parser.transform), and its exported PLY stays in normalised coordinates. — https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/examples/simple_trainer.py https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/examples/datasets/colmap.py https://pypi.org/pypi/gsplat/json
- [medium] Cyclone REGISTER 360 PLUS can export the BLK2GO trajectory to CSV, and E57 with WayPoints and rectified images (WORKFLOW license; formerly the b2g2trajectory CLI). The BLK2GO panoramic cameras capture about 1 image per second. — https://rcdocs.leica-geosystems.com/cyclone-register-360/latest/workflow-for-cyclone-field-360-and-blk-kinematic-scanners https://rcdocs.leica-geosystems.com/docs/cyclone-register-360-export-blk-kinematic-data-to-e57-with-waypoints-and-images.md https://rcdocs.leica-geosystems.com/cyclone-register-360/latest/blk2go-support

## Key numbers

- COLMAP / pycolmap latest: 4.2.1, 2026-09-29 (4.0.0 2026-03-14 GLOMAP integrated; 4.1.0 2026-06-26 equirectangular cameras + Caspar BA; 3.13.0 2025-11-07) (https://colmap.github.io/changelog.html)
- Open3D latest: 0.20.0, 2026-09-16, MIT, win_amd64 cp310–cp314 (https://pypi.org/project/open3d/)
- small_gicp latest: 1.0.1, 2026-06-13, MIT, Windows wheels py3.10–3.14 (https://pypi.org/project/small-gicp/)
- evo latest: 1.37.1, 2026-08-31, GPLv3 (https://pypi.org/project/evo/)
- evo default association tolerance: max_diff = 0.01 s, nearest-time (https://raw.githubusercontent.com/MichaelGrupp/evo/master/evo/core/sync.py)
- KISS-Matcher latest: 1.0.2, 2026-05-10, MIT, Linux/macOS wheels only (https://pypi.org/project/kiss-matcher/)
- probreg latest: 0.3.8, 2024-05-11, MIT, sdist only (https://pypi.org/pypi/probreg/json)
- TEASER outlier robustness: >99% outliers; estimates scale (https://arxiv.org/abs/2001.07715)
- Insta360 X5/X6 IMU rate: 1 kHz gyro + accel in .insv (https://github.com/OVR-Platform/imu-metric-scale)
- BLK2GO LiDAR: 420,000 pts/s, range 0.5–25 m, range noise ±3 mm, ±10 mm indoor / 6–15 mm relative (https://leica-geosystems.com/products/laser-scanners/scanners/leica-blk2go)
- BLK2GO panoramic image rate: about 1 image per second (3 cameras) (https://rcdocs.leica-geosystems.com/cyclone-register-360/latest/blk2go-support)
- Position error per 10 ms sync error: 1.0–1.4 cm at 1.0–1.4 m/s walking; 0.6° at 60°/s (derived) (derived)
- Vertical lever-arm σ from hand-eye: about 4 cm with ±3° natural tilt vs about 0.4 cm with ±30° wiggle (σ_t=1 cm, N_eff=20; derived) (derived)
- Scale bias from ignoring lateral lever arm: ≈ l_lat/R, e.g. 5 cm / 5 m = 1% (derived) (derived)
- Clock drift over 10 min: 12–30 ms at 20–50 ppm (assumed crystal tolerance) (background knowledge (low confidence))
- Open3D FPFH defaults: normal radius 2×voxel, feature radius 5×voxel, RANSAC 100k iterations / 0.999 confidence, FGR 0.5×voxel, ICP 0.4×voxel (https://www.open3d.org/docs/latest/tutorial/pipelines/global_registration.html)
- gsplat latest / defaults: 1.5.3 (2025-07-04); normalize_world_space=True; depth_loss=False; depth_lambda=1e-2 (https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/examples/simple_trainer.py)
- LiV-GS speed: 7.98 FPS mapping (https://arxiv.org/abs/2411.12185)

## Tools & licenses

- Open3D | 0.20.0 (2026-09-16) | MIT | win: pip wheels cp310–cp314 | Sim3 point-to-point ICP (with_scaling), robust-kernel point-to-plane, GICP, FPFH+RANSAC, FGR, correspondence RANSAC
- small_gicp | 1.0.1 (2026-06-13) | MIT | win: pip wheels py3.10–3.14 | ICP, PLANE_ICP, GICP, VGICP; rigid only; fast
- pycolmap / COLMAP | 4.2.1 (2026-09-29) | BSD-3-Clause | win: pycolmap CPU wheels; COLMAP static Windows CUDA builds since 4.0 | Sim3d, align_reconstruction_to_locations (RANSAC), align_reconstructions_via_points/reprojections, Reconstruction.transform, model_aligner, pose_prior_mapper, rigs, panorama
- evo | 1.37.1 (2026-08-31) | GPL-3.0 | win: yes (pure Python) | Umeyama SE3/Sim3, APE/RPE, plotting; no RANSAC; avoid linking into distributed code
- TEASER++ / teaserpp-python | no PyPI release; conda saedrna 0.1.0 (2025-03-25) | MIT | win: not officially supported; WinTeaser VS2015 C++ only; use WSL2 | certifiable robust registration, estimates scale
- KISS-Matcher | 1.0.2 (2026-05-10) | MIT | win: no wheels (source build only) | Faster-PFH + k-core pruning; rigid
- probreg | 0.3.8 (2024-05-11) | MIT | win: sdist only, needs MSVC build | CPD rigid+scale, FilterReg, GMMTree, SVR, BCPD; CuPy GPU
- scipy | 1.18.1 | BSD-3-Clause | win: wheels | least_squares with robust losses, Rotation/Slerp for trajectory interpolation
- opencv-contrib-python | 5.0.0.93 | Apache-2.0 | win: wheels | calibrateHandEye, calibrateRobotWorldHandEye (documented in 4.13), aruco/AprilTag detection
- laspy (+lazrs) | 2.7.0 (2026-01-14) | BSD-2-Clause | win: wheels | LAS/LAZ IO
- pye57 | 0.4.19 | MIT | win: wheels py3.10–3.14 | E57 points and scan poses; images not documented
- CSF (cloth-simulation-filter) | latest pip (date not verified) | Apache-2.0 | win: yes | ground segmentation for LiDAR
- telemetry-parser | not verified | MIT or Apache-2.0 | win: Python module on PyPI | Insta360 gyro/accel; lists X5, not X3/X4
- CloudCompare | 2.13.2 stable (2024-08-07); 2.14 beta (2026-10-03) | GPL (application) | win: installer incl. Python and 3DFin plugins | C2C/M3C2 validation, manual checks
- gsplat | 1.5.3 (2025-07-04) | Apache-2.0 (background knowledge; PyPI metadata blank) | win: wheel available | normalize_world_space default True; experimental depth_loss
- Kalibr | last notable update 2022-11-24 | BSD-3-Clause | win: no (ROS1 Ubuntu / Docker) | camera-IMU, multi-camera; no LiDAR; not applicable
- direct_visual_lidar_calibration | ICRA 2023, maintained | MIT | win: no (ROS/Docker; WSL2) | targetless NID LiDAR-camera; optional check
- FAST-LIVO2 / FAST-Calib / GS-SDF / Gaussian-LIC2 | 2025–2026 | GPL-2.0 / GPL-2.0 / GPL-2.0 / GPL-3.0 | win: no (Ubuntu/ROS) | reference designs only; require hardware-synced raw sensor streams

## risks

- BLK2GO trajectory CSV contents (timestamp base, sample rate, body-frame axes and reference point, whether it shares the exported cloud's frame after WayPoint moves) are undocumented; wrong assumptions cause convention or reference-point errors.
- The exported trajectory may be SLAM-smoothed or low-rate, which would weaken |ω| cross-correlation; the SfM-rotation fallback needs full-frame-rate extraction of the sync segments.
- Insta360 X4 IMU extraction is unverified (telemetry-parser lists X5, not X4); the Gyroflow app does not support 360 cameras.
- A taped mount flexes, so X is not constant; the extrinsic check may show WARN even when the splat alignment is fine.
- Equirectangular stitching assumes a single centre while the dual lenses sit a few cm apart (background knowledge); stitch-line parallax at <2 m distorts SfM. Rolling shutter adds skew during fast twists.
- Foliage motion in wind and sparse SfM points in dark forest can bias ICP; restrict to ground and trunks.
- Position-only Sim3 that ignores the lever arm silently shifts the splat vertically by the mount offset and can bias scale by about 1%.
- Trainer renormalisation (gsplat normalize_world_space=True; nerfstudio auto-orient/scale, background knowledge) silently breaks the metric frame.
- Georeferenced coordinates break float32 splat precision unless shifted to a local origin.
- GPL tools (evo, FAST-LIVO2 family) carry licensing implications if code is redistributed.
- The shared web-search budget ran out mid-research; some claims (BLK2GO loop closure, CSV format, Insta360 rolling-shutter timing, lens baseline) rest on background knowledge.

## open_questions

- Exact format of the Cyclone BLK2GO trajectory CSV: columns, time base (GPS time or seconds since start), rate, orientation convention, and reference point on the device.
- Does the user's Cyclone license include the WORKFLOW option needed for E57 export with WayPoints and rectified, posed images (a sync-free anchor route)?
- Does the Cyclone LAS/E57 export carry per-point timestamps that could help sync?
- Does the BLK2GO SLAM run explicit loop closure on-device or in Cyclone, and does it report per-segment confidence?
- Can Insta360 X4 .insv gyro be extracted (telemetry-parser/exiftool), or is X5+ required?
- Where is the optical reference of the stitched Insta360 output relative to the body, and what is the dual-lens baseline? This is needed to define the tape-measure reference point.
- Is the OpenCV hand-eye API unchanged in OpenCV 5.0 Python bindings?
- Windows install status of GTSAM wheels (if a factor-graph estimator is preferred over scipy).

## questions_for_user

- Which Insta360 model will you use? X5 or newer has 1 kHz IMU extraction supported; X4 is uncertain.
- Which Cyclone REGISTER 360 edition and license do you have (PLUS, and whether it includes WORKFLOW for E57 with WayPoints and images)?
- Can you export one sample BLK2GO trajectory CSV so the time base, rate and axes can be confirmed?
- From which physical points will you tape-measure (BLK2GO dome centre or handle mount, Insta360 lens midpoint or tripod screw), and can you also record tilt with a phone inclinometer?
- Can you add the start/end twist plus pitch/roll wiggle routine, and place 4–6 spheres or AprilTag boards around the loop?
- Will the LiDAR data stay in a local SLAM frame, or be georeferenced (e.g. SWEREF99) in Cyclone?

## FACT-CHECK: non-confirmed verdicts

- **REFUTED**: Run 2 (Insta360 only) can be brought into the LiDAR frame by aligning separately reconstructed models with pycolmap align_reconstructions_via_points / align_reconstructions_via_reprojections. → Both functions need images registered in BOTH reconstructions. via_reprojections and via_proj_centers say 'finding images that are registered in both reconstructions'. via_points walks each source point's track (image_id, point2D_idx) and looks up the same image in the target, so it needs a shared database and shared images. Two independent SfM models of different videos share no images, so these calls fail. What works instead:
- Reconstruct both runs in ONE database and model, with cross-run matching (vocab-tree or exhaustive between runs).
- Register Run 2 frames into the Run 1 model (image_registrator, then BA).
- Fall back to geometric ICP with pre-scaling.
Run 2 is filmed from a different height and angle in a windy forest, so cross-run matching may be weak. Test it early. (https://raw.githubusercontent.com/colmap/colmap/main/src/colmap/estimators/alignment.h https://raw.githubusercontent.com/colmap/colmap/main/src/colmap/estimators/alignment.cc)
- **CORRECTED**: evo 1.37.1 (2026-08-31, GPLv3, Windows OK) does plain least-squares Umeyama with no RANSAC or weights; association is nearest-timestamp with max_diff=0.01 s and offset_2. → Version, date, license, Windows support and the plain Umeyama (umeyama_alignment(x, y, with_scale), no weights or RANSAC; PosePath3D.align(correct_scale, correct_only_scale, n)) are all confirmed. However, associate_trajectories also has SyncMethod.interpolation, which resamples at the sparser trajectory's timestamps, besides the default nearest_time. Use interpolation for a low-rate BLK2GO trajectory. (https://pypi.org/project/evo/ https://raw.githubusercontent.com/MichaelGrupp/evo/master/evo/core/sync.py)
- **CORRECTED**: gsplat latest is 1.5.3 (2025-07-04). simple_trainer defaults: normalize_world_space=True, depth_loss=False, depth_lambda=1e-2. init_type supports 'sfm', 'lidar' (NCore) and 'random'. The exported PLY stays in normalised coordinates. License Apache-2.0. → Confirmed:
- 1.5.3 (2025-07-04) is still the latest; there are no newer releases on PyPI or GitHub.
- The defaults are as stated.
- export_splats does not invert parser.transform.
- The LICENSE file is Apache-2.0.
Corrections:
- init_type 'lidar' and the NCore options exist only on the main branch. The v1.5.3 simple_trainer accepts only 'sfm' or 'random'.
- The PyPI wheel is py3-none-any and JIT-compiles CUDA on first use, which needs MSVC and the CUDA toolkit on Windows. Prebuilt Windows/Linux wheels are on docs.gsplat.studio/whl.
- The main-branch parser reads via pycolmap.Reconstruction and supports only perspective and OPENCV_FISHEYE cameras. It has no equirectangular model and no evident rig support, so COLMAP 4.1 native spherical SfM still needs perspective views for training. (https://pypi.org/pypi/gsplat/json https://github.com/nerfstudio-project/gsplat/releases)
- **CORRECTED**: Using LiDAR depth in gsplat requires a custom loader, or swapping LiDAR points into points3D. → Swapping LiDAR points into points3D does NOT give depth supervision. The parser builds point_indices[image_name] from each point's track elements, and depth is computed only for points observed in that image. LiDAR points have no tracks.
A custom loader is required. It must project LiDAR points with occlusion handling (z-buffer or splat-radius depth test). Naive projection puts depths from behind trunks into the foreground, which is severe in a forest. Swapping points only works for initialisation (init from parser.points). (https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/examples/datasets/colmap.py)
- **CORRECTED**: The Insta360 X5 IMU is logged at 1 kHz and readable by telemetry-parser, which lists X5 but not X3/X4 and is available as a Python module on PyPI. → Confirmed:
- The README support list includes 'X5' but not X3/X4.
- The license is MIT or Apache-2.0.
- The OVR imu-metric-scale repo states that X5/X6 store gyro and accelerometer at 1 kHz.
Corrections:
- The PyPI Python module's latest release is 0.3.0 from 2024-01-16, and the GitHub release v0.3.0 is the same. That predates the X5 launch (2025-04-22).
- Its Windows wheels are cp3xx-none tags only up to cp312, so they do not cover Python 3.13/3.14.
- X5 support is documented on master. OVR's requirements.txt uses plain PyPI telemetry-parser and claims X5/X6 work, so it may still parse, but treat this as unverified until a sample .insv is tested.
- Fallback: build telemetry-parser from source (Rust/maturin). (https://github.com/AdrianEddy/telemetry-parser/blob/master/README.md https://pypi.org/pypi/telemetry-parser/0.3.0/json)
- **UNVERIFIABLE**: An Insta360 X6 exists ('X5/X6 store gyro at 1 kHz'). → Only the OVR repo mentions an X6. Wikipedia (last updated June 2026) lists the X5 (launched 2025-04-22) as the newest X model. Insta360's own site returned 403. Plan around the X5 unless the user confirms an X6. (https://github.com/OVR-Platform/imu-metric-scale https://en.wikipedia.org/wiki/Insta360)
- **UNVERIFIABLE**: BLK2GO specs: 420k pts/s, range 0.5–25 m, range noise ±3 mm, ±10 mm indoor or 6–15 mm relative accuracy, GrandSLAM, 12 MP detail camera, 3×4.8 MP panoramic, 775 g. → Leica's product page confirms 420,000 pts/s, GRANDSLAM (LiDAR + visual + IMU), the 12 MP detail camera, 3 panoramic cameras and 775 g with battery (plus 45 min scanning). It does NOT state the range, noise, accuracy, panoramic resolution or FOV. The datasheet PDF (2019) could not be parsed, and the shop, reseller and MDPI pages returned 403. Treat the 1–2 cm accuracy floor as plausible but unsourced. (https://leica-geosystems.com/products/laser-scanners/scanners/leica-blk2go https://www.gefos-leica.cz/data/original/skenery/blk2go/leica-blk2go-datasheet.pdf)
- **UNVERIFIABLE**: BLK2GO SLAM performs loop closure on a closed loop. → No Cyclone REGISTER 360 page checked (processing, review/optimize, import options, on-device processing) mentions loop closure, drift correction or trajectory optimisation. Keep this as an assumption and validate it empirically with the per-side Sim3 and target residuals. (https://rcdocs.leica-geosystems.com/docs/cyclone-register-360-blk2go-review-optimize-workflow.md https://rcdocs.leica-geosystems.com/docs/cyclone-register-360-processing-blk-kinematic-data-in-cyclone-register-360-plus.md)
- **CORRECTED**: CloudCompare 2.13.2 is the stable release (2024-08-07) and 2.14 beta came out 2026-10-03; the Windows installer includes the Python and 3DFin plugins. → 2.13.2 'Kharkiv' dates from July 2024: the release page says July 8, 2024 and the GitHub tag says 11 Jul. The report's 2024-08-07 is probably a day/month swap. 2.14.beta (2026-10-03) and the bundled Python and 3DFin plugins are confirmed; 3DFin is now a standard plugin. (https://www.cloudcompare.org/release/ https://github.com/CloudCompare/CloudCompare/releases/tag/v2.13.2)
- **CORRECTED**: CSF (cloth-simulation-filter) is Apache-2.0, pip-installable, and works on Windows. → The latest is 1.1.7 (2025-08-13), Apache-2.0. Its Windows wheels cover only cp39–cp312; there is no cp313 or cp314 file. With Python 3.13/3.14 it needs an MSVC source build. Pin the pipeline environment to Python 3.12, which telemetry-parser also needs (Windows wheels only up to cp312). (https://pypi.org/pypi/cloth-simulation-filter/1.1.7/json https://github.com/jianboqi/CSF)
- **CORRECTED**: Windows availability of GTSAM wheels is an open question. → The latest, gtsam 4.3.0 (2026-09-19), has NO Windows wheels. gtsam 4.2.2 (2026-08-04) has win_amd64 wheels for cp311–cp314. The license is simplified BSD. If a factor graph is wanted, pin gtsam==4.2.2 on Windows. (https://pypi.org/pypi/gtsam/4.3.0/json https://pypi.org/pypi/gtsam/json)

_26 of 37 checked claims confirmed._


## FACT-CHECK: missed developments

- Insta360 stabilisation (FlowState, Direction Lock, horizon levelling) must be disabled for every export used in SfM, extrinsic estimation or sync.: Stabilised 360 exports re-orient each frame with gyro data, so the rotation between the BLK2GO and the 'camera' changes per frame. That breaks the rigid-X assumption, inflates X_i scatter (it would look like 'mount flex'), and suppresses the SfM-rotation |ω| signal used for sync. Export with stabilisation and direction lock OFF, or explicitly confirm that the exported frames have a fixed body orientation. This was not in the report. Confidence is medium (background knowledge); the Insta360 manual pages are JS-rendered and returned no content. (background knowledge; attempted https://onlinemanual.insta360.com/x5/en-us/ (no content retrievable))
- OVR-Platform imu-metric-scale (2026): recovers metric scale, gravity direction and camera-IMU rotation from a COLMAP model plus Insta360 X5 .insv IMU, and includes a video-gyro sync tool.: Useful as an independent metric-scale and gravity check for Run 2 (no LiDAR), and as a sync building block. The README reports camera-IMU residual offset within ±5 ms and a 3.4% scale bias over ten surveys with external reference. License is 'To be decided before publication', so do not vendor it; reimplement or use it only as a diagnostic. (https://github.com/OVR-Platform/imu-metric-scale https://raw.githubusercontent.com/OVR-Platform/imu-metric-scale/main/README.md)
- Open3D 0.20.0 (2026-09-16) added symmetric ICP (legacy and Tensor), 3D NDT registration (Python API), rendering of 3D Gaussian splats from PLY/SPLAT/SPZ with depth occlusion alongside meshes, and a Windows CUDA preview wheel. 0.19 added Chamfer, Hausdorff and F-score metrics.: Symmetric ICP and NDT are extra refinement options for noisy SfM-vs-LiDAR. Splat rendering in Open3D allows a Python-side visual QA overlay of the LiDAR and the metric splat before building the web viewer. The geometry metrics complement CloudCompare C2C/M3C2. (https://github.com/isl-org/Open3D/releases/tag/v0.20.0 https://github.com/isl-org/Open3D/releases)
- MapAnything (Meta; arXiv 2509.13414, v1 Sept 2025, revised Jan 2026) is a feed-forward METRIC 3D reconstruction (poses, depth, metric scale factor). Code is Apache-2.0, and an Apache-2.0 weights variant (facebook/map-anything-apache) exists alongside a CC-BY-NC one.: Can give a coarse metric pre-scale for FPFH/RANSAC fallback registration and for Run 2, removing the need for a trajectory-based initial scale. Use it only as an initialisation (expect percent-level scale error). Windows support and VRAM needs are not documented: its profiling cites 2000 views on 140 GB, so subsample frames heavily on a 16 GB GPU. (https://arxiv.org/abs/2509.13414 https://github.com/facebookresearch/map-anything)
- Python-version pinning constraint on Windows: CSF wheels go only to cp312, telemetry-parser wheels only to cp312, KISS-Matcher to cp312 (and no Windows), and gtsam 4.3.0 has no Windows wheels (4.2.2 does).: Recommend a single Python 3.12 environment. Open3D 0.20, pycolmap 4.2.1, small_gicp 1.0.1, pye57 0.4.19, laspy 2.7.0 and gtsam 4.2.2 all have cp312 win_amd64 wheels. gsplat on PyPI is pure Python with JIT CUDA compilation, so prefer the prebuilt wheels from docs.gsplat.studio/whl matched to the torch/CUDA version. (https://pypi.org/pypi/cloth-simulation-filter/1.1.7/json https://pypi.org/pypi/telemetry-parser/0.3.0/json)
- COLMAP 4.2.0 multi-component global mapping (GlobalMapper.multiple_models, min_model_size) reconstructs disconnected view-graph components instead of failing.: If Run 1 and Run 2 are put in one database and cross-run matching is weak, the global mapper may return two components. These still need aligning, and the reconstruction-to-reconstruction aligners cannot do it without shared images. The intended route is to force connectivity: overlapping segments, deliberate shared viewpoints, or extra frames from an intermediate height. (https://github.com/colmap/colmap/releases/tag/4.2.0 https://raw.githubusercontent.com/colmap/colmap/main/src/colmap/estimators/alignment.h)
- gsplat main branch (not release 1.5.3) has init_type='lidar' (NCore datasets) and a pycolmap-based parser.: Using these features means pinning a main-branch commit rather than the 1.5.3 release; the planner should state the exact commit. Neither path handles BLK2GO LAS directly, so a custom loader is still needed for LiDAR init and depth. (https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/examples/simple_trainer.py https://raw.githubusercontent.com/nerfstudio-project/gsplat/v1.5.3/examples/simple_trainer.py)

## FACT-CHECK: recommendation assessment

The core architecture holds up. The staged estimator is sound: robust Sim3 on trajectories for initialisation, then scaled ICP, then robust point-to-plane ICP on ground and trunks to fix S. Recovering X and dt only as by-products, and building a metric splat by transforming the COLMAP model first, is also sound. The Tanks and Temples toolbox uses the same pattern (RANSAC Sim3 on camera centres, then scaled ICP). Tool versions, licenses and Windows statuses are mostly accurate as of 2026-10.

Changes I would make:

(1) Run 2 recommendation is wrong as written. pycolmap align_reconstructions_via_points, via_reprojections and via_proj_centers all need images registered in both models (shared database, image IDs and tracks), so they cannot align two independently reconstructed videos. Do this instead:
- Make the default a joint single-database reconstruction of Run 1 plus Run 2 with cross-run matching, or register Run 2 frames into the Run 1 model (image_registrator, then BA). Then apply S.
- Fallback: geometric registration of a Run 2 SfM to LiDAR, pre-scaled by MapAnything, Insta360 IMU scale (imu-metric-scale approach) or targets.
- Because Run 2 is higher and at a different angle, test cross-run matchability on the first capture.

(2) "Splat needs only S" is right for pose framing. But LiDAR depth supervision via S assumes the SfM is rigid-consistent with the LiDAR to about 1–2 cm everywhere.
- Add a step after S: check per-quadrant and per-image residuals. If SfM bending exceeds about 2 cm, re-run BA with LiDAR-derived position priors (pose_prior_mapper; COLMAP 4.2 fixed rig pose-prior scale handling) before training.
- Depth supervision needs a custom gsplat loader with occlusion-aware (z-buffered) LiDAR projection. gsplat's depth loss only uses track-observed SfM points, so swapping LiDAR into points3D does not supervise depth.
- init_type='lidar' exists only on gsplat main, not 1.5.3.
- Exclude canopy and foliage LiDAR from depth supervision.

(3) Add to the capture and export protocol: disable Insta360 FlowState stabilisation, direction lock and horizon levelling for all frames used. Otherwise X is not rigid and both the extrinsic check and the SfM-rotation sync fail.

(4) Sync plan: the |ω| cross-correlation with start and end twists is reasonable.
- Moderate the twists (about 60–90°/s, a few cycles). Rapid spins may degrade BLK2GO SLAM (unverified) and blur 360 frames. Exclude the twist segments from SfM and splat training.
- Do not assume telemetry-parser works for X5. The PyPI module is 0.3.0 from Jan 2024 with Windows wheels only to cp312. Test a sample .insv immediately; fall back to a source build.
- Plan for the BLK2GO CSV being low-rate or smoothed. The CSV schema is undocumented, so ask for a sample. Use evo's interpolation sync rather than nearest-time.

(5) The tape-comparison thresholds are reasonable as proposals but too tight for the first, taped test.
- The BLK2GO trajectory reference point is undocumented and the stitched Insta360 centre is ambiguous. Report the lever-arm difference with an explicit reference-point uncertainty term. Use a 3 cm / 3σ PASS per horizontal component.
- Judge the vertical component only against its σ_z.
- Split rotation into pitch/roll (inclinometer, ≤2° PASS) and yaw (hand-measured, ≤5° PASS).
- Keep the stricter thresholds for the rigid mount.

(6) Library list:
- Pin Python 3.12 on Windows (CSF and telemetry-parser wheels stop at cp312).
- Use gtsam 4.2.2 if a factor graph is wanted (4.3.0 has no Windows wheels).
- OpenCV hand-eye exists in 5.x (calib module), so plain opencv-python suffices.
- The Wise et al. certifiable solver is Julia, a cross-check only.
- Note that Open3D's scaled point-to-point ICP has no robust kernel, so use tight correspondence gating.
- TEASER++'s scale estimation does not help with FPFH correspondences.

(7) BLK2GO accuracy numbers (range, noise, ±10 mm / 6–15 mm) and on-device or Cyclone loop closure could not be verified from Leica primary sources. Validate them empirically with the planned spheres, AprilTag boards and the per-side Sim3 drift test rather than relying on them as a floor.

Note: the shared web-search budget was exhausted, so this check relied on direct fetches of primary pages; claims marked unverifiable may be checkable with further searches.
