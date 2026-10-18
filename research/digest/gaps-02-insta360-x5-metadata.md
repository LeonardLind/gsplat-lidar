# gap: insta360-x5-metadata

## Summary

GAP: Insta360 X5 (then X4 / X4 Air) metadata and export behaviour, for rigid LiDAR calibration with body-fixed frames timed to sub-frame accuracy. Web search ran out partway through. Everything after that came from fetching known primary URLs (GyroView docs/ADRs/PRs, telemetry-parser source/PRs/issues, insta360-rs docs, insv-stitch source, ExifTool QuickTimeStream.pl, Insta360 online manual, a Gyroflow lens profile). Reddit was not checked.

PER-MODEL TABLE (V = verified on real files by at least one open project, S = single source, U = unknown/unverified)
X5:
- Rolling-shutter field: protobuf tag 25 `rolling_shutter_time` (f64, ms, for the recorded-resolution crop).
  - 8K30 ~21.2 ms (V, 2 sources: GyroView half-readout 10.6 ms; insv-stitch default 21.24 ms).
  - 5.7K60 ~8 ms (S: GyroView half-readout 4 ms).
  - One X5 file of unknown mode stores 11.837 ms (insta360-rs).
  - 4K modes: U.
  - Readout runs top to bottom in each decoded fisheye (insta360-rs). Skew is about 1 degree at 100 deg/s at 8K30 (GyroView).
- IMU: record 3, raw 20-byte layout (u64 timestamp in microseconds since boot, e.g. 921,648,752 us; 6x u16 offset-binary around 32768). 1 kHz (S: GyroView). Ranges 32 g / 2000 dps from tag 65 (2 sources: GyroView, insta360-rs).
- Gyro offset: tag 28 (ms) with flag tag 29. 1.6 ms on X5 (S).
- Exposure: record 4 holds a u64 camera timestamp plus f64 shutter in seconds, one entry per frame, starting about 6 frames before `first_frame_timestamp` (tag 24). Record 0x0C is a secondary exposure stream. Record 6 holds frame PTS for timelapse/TimeShift. Tag 78 holds a rational frame rate.
- Video: two square hvc1 tracks, one per lens, in one file. 3840 px square at 8K, 2880 px at 5.7K, 8-bit BT.709 (I-Log gives 10-bit). Sensor window 5376 cropped to 5312.
- Gyro-to-frame timing measured by GyroView: +0.4 +/- 2.6 ms (8K30, 1/50 s), +2.7 +/- 3.7 ms (5.7K60), -11 +/- 4 ms (a low-motion 8K30 clip). So the offset must be estimated for each recording.
X4: lens tracks are the same kind of square hvc1 tracks (GyroView docs). Readout, IMU rate and layout are all U. GyroView has no real X4 file; it defaults the IMU frame to identity with a warning. The telemetry-parser X4 orientation "yzX" came from a PR whose author wrote "I haven't tested it".
X4 Air: GyroView measured IMU axes (x, z, -y), the same as X5, from one upright clip only (provisional). Timing 0.6 +/- 2.5 ms. telemetry-parser has no X4 Air entry, so it falls back to the default "Xyz" and gets no cx fix. That is probably wrong (inference). Readout and rate: U.

(2) TELEMETRY-PARSER MASTER: it does the X5 basics correctly:
- raw/float layout detection, range scaling, microseconds to ms;
- subtracting `first_frame_timestamp`;
- applying tag 28 only when tag 29 is set (insta360-rs applies it whenever it is present: a difference of at most 1.6 ms);
- `frame_readout_time` taken from tag 25;
- X5 orientation "yzX" and the cx x2 fix (PR #48, 2026-02-04, tested on firmware v1.7.43).
The PyPI wheel 0.3.0 (2024-01-16) predates the X4/X5 handling, so build from master. ExifTool decodes the records with `-ee`, but it scales the 20-byte raw samples as (raw - 32768)/1000 and ignores the ranges, so it is not physically exact.
The axis conventions of GyroView, telemetry-parser and insta360-rs use different target frames and cannot be compared directly. Plan to estimate the camera-to-IMU rotation ourselves.
Issue #53 ("X5 firmware 1.10.7 writes no gyro") turned out to be a damaged camera. It still shows why every capture needs a check that the gyro record is present.

(3) BODY-FIXEDNESS: Insta360's official table says in-camera FlowState is "Not Supported" in 360 modes on X5, X4 and X4 Air. It exists only in single-lens / Me modes. So raw 360 tracks are body-fixed. Tag 130 ("encoded image rotation") was 0 on one X5 file. GyroView treats frames as body-fixed and works out the mounting from gravity.
Studio exports are only partly characterised:
- one 8K30 export mapped to the recording one-to-one in time;
- another export started 2.98 s into its recording;
- Studio's default heading on X5 was -168.8 deg from lens 0.
There is no proof that an export with everything off (FlowState, Direction Lock, horizon correction, tilt restoration) is identity-timed, has the same frame count, or keeps a constant rotation. Prefer the raw per-lens fisheye tracks. Equirect stitching assumes one centre over a ~30 mm lens baseline, which gives ~18 px ghosting under 3 m (insv-stitch). That matters in a forest.

(4) FRAME RATE: tag 20 holds an integer (30). Tag 78 can hold 30000/1001. A Gyroflow profile of an X4 export from the "8K 30" setting shows 29.97003 fps. Whether X5 .insv tracks are exactly 30 or 30000/1001 is U. The difference (0.1%) adds up to ~0.54 s over a 9-minute walk, so never use the nominal fps. Use the actual PTS and the exposure-record camera timestamps. Clock drift between the camera and the LiDAR (crystal ppm) is unmeasured, so fit both offset and scale.

(5) EXPOSURE: Modes are full auto, auto, manual, ISO priority and shutter priority (vendor camera_conf). AdaptiveTone (X5: Video/PureVideo; X4 Air: Video) exposes the two lenses independently and turns off manual ISO/shutter, Independent Exposure, filters and I-Log. Without it, reports say "the same lighting data for both lenses". Balanced Exposure applies only in Auto. Jitter Blur Reduction can darken and flicker in low light. Whether manual mode gives truly identical per-lens ISP/tone is U, because the opaque Dynamic ISP record 0x1B exists.

(6) TIMELAPSE: record 6 frame PTS plus tags 30 / 59 / 133 for the interval. Post-capture stabilization is offered for "all video modes", which implies the IMU is kept (inference). Audio: U. Do not use timelapse for the LiDAR fusion.

(7) LENSES: replaceable lenses (X5, X4 Air) need an in-camera Stitching Calibration after a swap. The file records the selected accessory (tag 68) and the detected one (tag 104: plastic, glass, off, ND...). The lens radial scale differs between units (96 vs 97 deg). Re-run our own intrinsic and LiDAR extrinsic calibration after any lens or guard change.

(8) PARSERS ON WINDOWS:
- telemetry-parser (Rust: `cargo build --release` in bin/gyro2bb; Python module via bin/python-module; wheels only up to Python 3.12);
- ExifTool `-ee -v3` (dumps only);
- GyroView `pnpm inspect` (Node 24, pnpm 11, MIT; Windows not documented);
- insta360-rs (Apache-2.0, Rust 1.90 or newer plus FFmpeg dev libraries; wheels not yet published; Windows D3D12 not yet qualified on real media; bundled vendor assets keep Insta360's licence);
- insv-stitch (MIT, Python 3.12, Linux-oriented; its IMU_TO_CAM matrix is for one unit and looks odd).

## Plan changes

- Pipeline input: replace the 'Insta360 Studio equirect export' step with raw dual-fisheye extraction from the .insv (ffmpeg -map 0:v:0 / 0:v:1, keep PTS) plus a per-lens fisheye camera model in SfM and 3DGS. Keep Studio export only as an optional preview path.
- Add a metadata ingest step that parses the .insv trailer and writes per-frame camera timestamps (record 4 matched to PTS, anchored at tag 24) plus fields 20/78 (fps), 25 (readout), 28/29 (gyro offset), 65 (ranges), 68/104 (lens guard), 130 (rotation) and firmware. Fail loudly if record 3 (gyro) is missing or empty.
- Add a time-sync stage: estimate offset and clock scale between X5 and BLK2GO from angular-rate cross-correlation. Add a 5 s brisk rotation 'sync wiggle' at the start and end of every capture to the capture protocol.
- Capture protocol settings: 360 Video 8K30 (5.7K60 fallback), Manual or Shutter-priority exposure, shutter 1/500 to 1/1000 s, fixed white balance, AdaptiveTone, Active HDR, PureVideo and Jitter Blur Reduction OFF, no timelapse/TimeShift/Me/InstaFrame. Record lens guard state and firmware. Keep the camera mounting fixed. Re-run Stitching Calibration and our own calibration after any lens or guard change.
- Verification test before the first forest run: a short indoor capture with a known rotation. Check (a) frame count and PTS of each lens track against exposure-record count and intervals (decides 30 vs 30000/1001), (b) that the BLK2GO body pixels stay fixed in the raw fisheye (and in any Studio export), (c) gyro timing residual against video at the chosen shutter.
- Model rolling shutter in pose refinement (or at least flag high angular-rate frames for down-weighting) using tag-25 readout, top-to-bottom per lens.
- Tooling on Windows: telemetry-parser built from master (Rust/MSVC; Python 3.12 or older for the module), plus GyroView `pnpm inspect` (Node 24) or insta360-rs `probe` as a cross-check. Note that the user profile path contains a space (C:\Users\Leonard Lind), so quote paths in cargo/pnpm/ffmpeg scripts.
- Deliverable: per the user's request, publish the final research brief as a private web page (artifact) the user can share with a coworker.

## Recommendations

- **Feed 3DGS/SfM from the two raw per-lens fisheye tracks of the .insv, not from Studio equirect exports. Extract them losslessly with ffmpeg and treat them as a 2-camera rig with self-calibrated fisheye intrinsics and lens-to-lens extrinsics.** — The raw tracks are body-fixed (no in-camera 360 stabilization on X4/X5/X4 Air), and their frame-to-timestamp mapping is direct. Studio exports have an undocumented heading (-168.8 deg), possible start trims (2.98 s seen) and unverified frame-rate behaviour. They also add stitch parallax (~18 px under 3 m), which is common in a forest. _Alt:_ A Studio export with FlowState, Direction Lock and horizon correction all off. Accept it only after the static-marker test (BLK2GO body pixels fixed in every frame) and a frame-count/PTS check.
- **Capture in 360 Video mode with: Manual exposure (or Shutter priority if light varies strongly), fixed shutter 1/500 to 1/1000 s, fixed white balance, AdaptiveTone OFF, Active HDR OFF, PureVideo OFF, Jitter Blur Reduction OFF, no filters, same lens guards for capture and calibration (ideally none). Note the firmware version.** — AdaptiveTone exposes each lens independently and adjusts tone in post. Balanced Exposure is Auto-only. A short fixed shutter makes the unresolved +/- S/2 timing convention negligible (at most 0.5 ms) and keeps it constant from frame to frame. _Alt:_ I-Log (10-bit) with manual exposure, if forest highlight clipping is severe. AdaptiveTone cannot be combined with I-Log anyway.
- **Default to 8K30. Treat 5.7K60 (~8 ms readout) as the fallback for fast handheld motion. Do rolling-shutter-aware pose handling with readout from tag 25, top-to-bottom per fisheye, or keep yaw rates low.** — 8K30 readout is ~21 ms, which gives up to ~1 deg skew at 100 deg/s, enough to blur splats. 5.7K60 has ~2.6x less skew and twice the frames, at lower resolution.
- **Time-sync the camera to the BLK2GO by cross-correlating the magnitude of the X5 gyro angular rate with the angular rate of the BLK2GO SLAM trajectory. Fit offset plus clock scale over windows at the start and end. Map each video frame to its exposure-record camera timestamp, not to nominal fps.** — Both devices run free clocks (X5 in microseconds since boot). The axis mapping between tools is inconsistent, but the rate magnitude does not depend on it. GyroView found per-file residuals up to -11 ms. The 30 vs 29.97 uncertainty (0.1%) would cause ~0.5 s error over a 9-minute walk. _Alt:_ Visual or flash events seen by both the BLK2GO cameras and the X5 (coarser).
- **Build telemetry-parser from master on Windows (Rust stable MSVC: `cargo build --release` in bin/gyro2bb, or maturin in bin/python-module with Python 3.12 or older). Cross-check its output against GyroView `pnpm inspect` or insta360-rs `probe --json` on the first file.** — PyPI 0.3.0 predates the X4/X5 handling. ExifTool mis-scales raw 20-byte samples. Cross-checking catches unit and offset errors (tag 28/29 handling differs between tools). _Alt:_ insta360-rs (Apache-2.0; needs FFmpeg dev libraries; wheels unpublished); own Python parser following GyroView FORMAT.md and insta360-rs INSV_FORMAT.md (simple trailer layout: magic + size at EOF, 6-byte record footers).
- **Estimate the camera-IMU rotation and the LiDAR-camera extrinsic for each unit and each lens/guard configuration. Redo both after any lens swap or in-camera Stitching Calibration.** — Unit-to-unit lens differences (96 vs 97 deg radial scale) and the replaceable lenses on X5/X4 Air make factory or community profiles unreliable at the precision needed.
- **If the camera turns out to be a plain X4, run a measurement campaign before relying on its metadata. Record a static clip, a 3-axis rotation clip and an LED-blinker readout clip (gyroflow/rollingshutter method).** — No open project has verified X4 real files. Its readout, IMU rate, layout and orientation are all unverified.

## Load-bearing findings

- [medium] X5 stores the rolling-shutter readout in info protobuf tag 25 (rolling_shutter_time, f64 ms, for the recorded-resolution crop). The value is about 21.2 ms at 8K30. — https://raw.githubusercontent.com/bubo-squared/GyroView/main/docs/adr/0034-a-frame-is-timed-half-way-through-its-shutter.md https://github.com/bubo-squared/GyroView/pull/13 https://raw.githubusercontent.com/BenjaminHenriksson/insv-stitch/main/x5_pipeline.py
- [medium] The X5 IMU is record 3 in a raw 20-byte layout: u64 timestamp in microseconds on the camera clock (since boot), plus 6x u16 offset-binary. It runs at about 1 kHz with 32 g / 2000 dps ranges. — https://raw.githubusercontent.com/bubo-squared/GyroView/main/docs/FORMAT.md https://raw.githubusercontent.com/OpenSpeleo/insta360-rs/master/docs/INSV_FORMAT.md https://raw.githubusercontent.com/bubo-squared/GyroView/main/packages/core/test/support/officeGyroSample.ts
- [medium] The gyro-to-video offset is tag 28 (ms) with presence flag tag 29. It is 1.6 ms on X5. The open tools disagree on whether the frame-centre time is exposure timestamp + S/2 or - S/2. — https://raw.githubusercontent.com/bubo-squared/GyroView/main/docs/adr/0034-a-frame-is-timed-half-way-through-its-shutter.md https://raw.githubusercontent.com/OpenSpeleo/insta360-rs/master/docs/INSV_FORMAT.md https://raw.githubusercontent.com/OpenSpeleo/insta360-rs/master/docs/stabilization.md
- [high] On X5, X4 and X4 Air the camera never stabilizes or rotates 360-mode recordings. Raw .insv lens tracks are body-fixed. FlowState and Direction Lock for 360 exist only in post (app or Studio). — https://onlinemanual.insta360.com/x4/en-us/operating_tutorials/capture-preview/shooting-parameters/flowstate https://raw.githubusercontent.com/bubo-squared/GyroView/main/docs/adr/0038-the-picture-stands-as-the-camera-was-mounted.md https://raw.githubusercontent.com/OpenSpeleo/insta360-rs/master/docs/INSV_FORMAT.md
- [low] No evidence shows that a Studio equirect export with all stabilization off is frame-for-frame identical to the .insv or has identity rotation. Evidence so far is partial and mixed. — https://raw.githubusercontent.com/bubo-squared/GyroView/main/docs/adr/0025-the-lens-pose-as-measured-against-studio.md https://raw.githubusercontent.com/bubo-squared/GyroView/main/docs/adr/0039-the-view-opens-where-studio-centres-the-recording.md https://onlinemanual.insta360.com/onex2/en-us/studio/import/basicsetting
- [low] Whether X5 '30 fps' is exactly 30 or 30000/1001 is unresolved. There are signs it may be 29.97. — https://onlinemanual.insta360.com/x5/en-us/specs/shooting-specs https://raw.githubusercontent.com/OpenSpeleo/insta360-rs/master/docs/INSV_FORMAT.md https://raw.githubusercontent.com/gyroflow/lens_profiles/main/Insta360/Insta360_X4_X4_8K%2030_4k_16by9_3840x2160-29.97fps.json
- [high] telemetry-parser master handles X5 correctly in principle but is lightly tested. X4 orientation is untested and X4 Air is not handled. The PyPI wheel is too old. — https://raw.githubusercontent.com/AdrianEddy/telemetry-parser/master/src/insta360/mod.rs https://raw.githubusercontent.com/AdrianEddy/telemetry-parser/master/src/insta360/record.rs https://github.com/AdrianEddy/telemetry-parser/pull/48
- [high] Real-file verification status: X5 is verified (3 files, 2 units, 5.7K60 and 8K30). X4 Air has 1 file (provisional). Plain X4 has no real-file verification in any open project found. — https://raw.githubusercontent.com/bubo-squared/GyroView/main/docs/ROADMAP.md https://raw.githubusercontent.com/bubo-squared/GyroView/main/README.md https://raw.githubusercontent.com/OpenSpeleo/insta360-rs/master/README.md
- [medium] X5 AdaptiveTone exposes each lens independently and turns off manual control. With it off, both lenses appear to share one exposure. Balanced Exposure is Auto-only. — https://onlinemanual.insta360.com/x5/en-us/operating_tutorials/capture-preview/shooting-function/tone-enhancement https://www.engadget.com/cameras/insta360s-x5-cam-update-brings-nd-filters-a-giant-battery-and-improved-exposure-150007247.html https://onlinemanual.insta360.com/x5/en-us/camera/basicuse/usingthescreen
- [high] X4/X5 .insv holds each lens as a separate square hvc1 track (3840 px at 8K, 2880 px at 5.7K). Per-lens fisheye extraction needs no stitching. — https://raw.githubusercontent.com/bubo-squared/GyroView/main/docs/FORMAT.md https://github.com/BenjaminHenriksson/insv-stitch

## Key numbers

- X5 8K30 rolling-shutter readout (tag 25): ~21.2 ms (half-readout 10.6 ms; insv-stitch default 21.24 ms) (GyroView PR #13 / ADR 0034; insv-stitch x5_pipeline.py)
- X5 5.7K60 rolling-shutter readout: ~8 ms (half-readout 4 ms); single source (GyroView PR #13)
- X5 readout on insta360-rs sample (mode unknown): 11.836874961853027 ms (insta360-rs docs/stabilization.md)
- X5 rolling-shutter skew at the image edge: ~1 deg at 100 deg/s (8K30) (GyroView ADR 0034)
- X5 IMU sample rate / layout: 1 kHz; 20-byte raw (u64 us timestamp + 6x u16 offset-binary) (GyroView FORMAT.md; insta360-rs INSV_FORMAT.md)
- X5 IMU ranges: accel 32 g, gyro 2000 dps (tag 65) (GyroView FORMAT.md / officeGyroSample.ts; insta360-rs stabilization.md)
- X5 gyro offset (tag 28): 1.6 ms (GyroView FORMAT.md)
- Measured gyro-to-frame timing residual, X5: +0.4 +/- 2.6 ms (8K30, 1/50 s); +2.7 +/- 3.7 ms (5.7K60); -11 +/- 4 ms (low-motion 8K30) (GyroView ADR 0034)
- Measured timing residual, X4 Air: 0.6 ms +/- 2.5 ms SE (GyroView PR #14 / ADR 0009)
- Example X5 camera clock value: 921,648,752 us (~922 s since boot) (GyroView officeGyroSample.ts)
- Exposure entries before first frame: ~6 frames (office file) (GyroView FORMAT.md)
- X5 per-lens encoded size: 3840x3840 (8K) / 2880x2880 (5.7K); sensor 5376 cropped to 5312 (GyroView FORMAT.md)
- X5 video shutter range: 1/8000 s to 1/fps (onlinemanual.insta360.com/x5 specs)
- X5 360 video modes: 8K 30/25/24; 5.7K+ 30/25/24; 5.7K 60/50/48/30/25/24; 4K up to 120 fps; max 180 Mbps (onlinemanual.insta360.com/x5 specs)
- Studio default heading vs lens 0 (X5 sailing): -168.8 deg (GyroView ADR 0039)
- Studio export start offset seen: 2.98 s into the recording (office export) (GyroView ADR 0025)
- X4 export fps in a Gyroflow lens profile (8K 30 setting): 29.97003 (gyroflow/lens_profiles)
- Timeline error if 30 vs 29.97 is confused: 0.1% = ~0.54 s over 9 min (calculated) (calculation)
- Stitch ghosting / lens baseline: ~18 px under 3 m; ~30 mm baseline (insv-stitch README)
- X5 minimum stitching distance: 0.6 m sides, 0.8 m bottom (Insta360 X5 stitching troubleshooting page)
- Radial scale difference between X5 units: 96 vs 97 deg (GyroView ROADMAP)
- telemetry-parser PyPI latest: 0.3.0, uploaded 2024-01-16 (before X4 support 2025-09-13 and X5 support 2026-02-04) (PyPI JSON; GitHub commits)
- insta360-rs version: 0.2.0, 2026-09-14; needs Rust 1.90 or newer (crates.io; insta360-rs README)

## Still unknown

- X5 4K-mode rolling-shutter readout values, and which mode gave insta360-rs's 11.84 ms. X5 5.7K60 has only one source (~8 ms).
- Any X4 or X4 Air readout values, IMU sample rate, raw vs float gyro layout, timestamp units and gyro offset. Plain X4 has no real-file verification anywhere.
- Whether X5 8K30 .insv tracks are exactly 30/1 or 30000/1001 (stts / tag 78 values), and the drift between the camera clock and the track timeline over long recordings.
- Whether a Studio export with FlowState, Direction Lock, horizon correction and tilt restoration all off has a constant rotation, the same frame count and the same start time as the .insv, and what fps the container gets.
- The correct sign of the half-shutter term in frame timing (GyroView +S/2, measured, vs insta360-rs/Gyroflow -S/2).
- Whether manual exposure gives identical ISP and tone processing on both lenses (opaque Dynamic ISP record 0x1B; meaning of secondary exposure record 0x0C).
- Whether X5 timelapse .insv contains audio and continuous IMU and exposure records.
- Whether long X5 recordings split into several segments, and whether the camera clock stays continuous across segments.
- How Insta360 Studio's 'Automatic horizontal correction' and 'tilt restoration' behave when FlowState is off (static leveling vs per-frame).
- Reddit (r/Insta360, r/GaussianSplatting) and the Insta360 zh-cn manual pages were not checked because the shared web-search budget ran out mid-task.

## Questions for user

- Which model does the .insv itself report (camera_type / firmware in the trailer, e.g. via ExifTool or telemetry-parser): X5, X4 or X4 Air? And which firmware version?
- How is the camera mounted under the BLK2GO: upright or inverted, and with lens 0 facing forward or sideways? Will the mount stay fixed between calibration and forest captures?
- Will you use lens guards (standard/premium) or bare lenses, and do you plan to swap X5 lenses between sessions?
- Can you share a short (10-30 s) test .insv at 8K30 and 5.7K60, so tag 25, tag 78, track stts and exposure-record intervals can be read before the forest trip?
- Is the slightly lower resolution of 5.7K60 acceptable in exchange for about 2.6x less rolling-shutter skew and twice the frames, or is 8K30 a hard requirement?
