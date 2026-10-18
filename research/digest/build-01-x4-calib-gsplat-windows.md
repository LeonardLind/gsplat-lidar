# build-01: X4 factory calibration, trailer records, gsplat + COLMAP on Windows

Researched 2026-10-17. Sources are primary (source code, repo docs, release metadata) unless marked. Confidence: **H** = several independent sources or code agree; **M** = one source, or reverse-engineered with an empirical caveat; **L** = inference.

## 0. Decisions (TL;DR)

1. **X4 intrinsics.** The `offset` string is fully decodable (H). Its pixel space is not the 2880x2880 track. It is a side-by-side canvas of two **8000x6000** frames, which is the native 1/2-inch 48 MP sensor (M/L). How the 5.7K track is cropped and scaled out of that frame is **not** settled (L). So use the factory values only to initialise and sanity-check. **Calibrate the intrinsics ourselves** (section 1.8), then render pinhole virtual views from that calibration and give COLMAP fixed `PINHOLE` cameras in a rig.
2. **COLMAP 4.2.1 cannot model >180 deg.** Every perspective and fisheye model, EUCM included, rejects rays with z <= 0 (H, from source). So feed it virtual pinhole views, or raw fisheye limited to the inner hemisphere. Do not feed it the full 200 deg circle.
3. **gsplat on Windows.** There are no prebuilt wheels for torch 2.8, cu128 or cp311. Build `main` from source with the open MSVC fix PR #1055 (or #1085) merged on top, in a VS 2022 x64 prompt with torch **2.8.0+cu128** and CUDA 12.8.1. Stay on torch 2.8.0: torch 2.9 and later headers break Windows nvcc extension builds (C2872). Recipe in section 3.4.

---

## 1. Q1 - Insta360 X4 lens calibration in the .insv trailer

### 1.1 Where it lives
- Trailer record **id 1 = Metadata, format 1 = protobuf** (`ExtraMetadata`). Calibration strings are proto string fields:
  - 5 `offset` (V1)
  - 17 `original_offset`
  - 53 `offset_v2`
  - 54 `offset_v3`
  - 55 / 56 `original_offset_v2` / `_v3`
  - 111 `offset_v6`
  - 112 `original_offset_v6`
- Other fields you need:
  - 19 `dimension` (coded track size)
  - 27 `window_crop_info` {1 src_w, 2 src_h, 3 dst_w, 4 dst_h, 5 off_x (sint), 6 off_y}
  - 25 `rolling_shutter_time` (ms)
  - 131 `stream_type` (3 = two tracks in lens order, 4 = two tracks in reverse order)
  - 136 `capture_offset_version` (advisory only; the enum ordinal V6 = 4)
- Sources: [telemetry-parser extra_info.rs](https://github.com/AdrianEddy/telemetry-parser/blob/master/src/insta360/extra_info.rs), [record.rs](https://github.com/AdrianEddy/telemetry-parser/blob/master/src/insta360/record.rs), [GyroView FORMAT.md](https://github.com/bubo-squared/GyroView/blob/main/docs/FORMAT.md), [insta360-rs INSV_FORMAT.md](https://github.com/OpenSpeleo/insta360-rs/blob/master/docs/INSV_FORMAT.md). (H)
- The **generation comes from the last token** (packed word), not from the token count:
  - `version = packed >> 16` (0 = V1, 2, 3, 6)
  - `X = (packed >> 8) & 0xff`; X == 5 means lens 0 is mirrored
  - For V1 only: `lens_type = packed & 0x3ff`
- Tokens for two lenses: V1 = 16, V2 = 34, V3 = 40, V6 = 56. The vendor player prefers v6 > v3 > v2 > v1. Source: [telemetry-parser rig.rs](https://github.com/AdrianEddy/telemetry-parser/blob/master/src/insta360/rig.rs), insta360-rs [calibration.md](https://github.com/OpenSpeleo/insta360-rs/blob/master/docs/calibration.md). (H)

### 1.2 Our string decoded (V1)
`2 | 2911.140 4007.810 3005.670 0.156 0.125 90.031 | 2888.420 11997.380 2998.160 -0.336 0.175 90.625 | 16000 6000 | 1095`

| Token(s) | Meaning |
|---|---|
| `2` | lens count |
| lens 0 | radius R0 = 2911.14 px (image radius **at the lens type's half-FOV, 100 deg**); cx0 = 4007.81; cy0 = 3005.67; Euler angles (string order "yaw, pitch, roll" per telemetry-parser, "ex, ey, ez" per insta360-rs) = 0.156, 0.125, 90.031 deg |
| lens 1 | R1 = 2888.42; cx1 = 11997.38 (that is 3997.38 in its own frame, because lens 1 sits one frame width to the right); cy1 = 2998.16; angles -0.336, 0.175, 90.625 |
| `16000 6000` | **whole** calibration canvas: both lenses side by side, so **8000x6000 per lens** |
| `1095` = 0x0447 | V1. lens_type = 0x47 = **71**. X = 4, so no mirror |

- Lens type 71 is `INSLensTypeOneX4586PanoHongJing`, the bare X4 lens: full FOV class 200 deg, default blend 190 deg. Source: [insta360-rs housing-catalog.md](https://github.com/OpenSpeleo/insta360-rs/blob/master/docs/housing-catalog.md). (H)
- **Pixel space.** It is neither a stitched panorama nor track pixels. The per-lens canvas is 8000x6000, which is exactly 48 MP at 4:3. The vendor's physical polynomial gives 2.307 mm image height at 100 deg, and 2.307 mm / 2911 px = 0.79 um, about the 0.8 um pitch of a 1/2-inch 48 MP sensor. So the coordinates are almost certainly **native sensor pixels of each lens's full sensor** (M/L: inference from consistent numbers).
- **Mapping canvas to the 2880x2880 track: unresolved (L).**
  - Each tool does it differently:
    - telemetry-parser maps with a uniform scale `track_w / canvas_lens_w` (2880/8000). For this 4:3 canvas that would put cy at about 1082, i.e. off-centre, which is clearly wrong. **Its V1 path is not valid for the X4.**
    - insta360-rs applies `window_crop_info`, crop centred plus offsets: `c' = (c+0.5)*s - 0.5 - left`, then rescales to the decoded size. Its code explicitly **refuses V1 crop conversion**.
    - GyroView found that on the X5 (square canvas) ignoring the crop fitted the image circle better (ADR 0014).
  - A plausible reading is a centred 6000x6000 crop scaled by 0.48. That gives lens 0: cx ~ 1443.5, cy ~ 1442.5, R(100 deg) ~ 1397 px. Lens 1: cx ~ 1438.5, cy ~ 1438.9, R ~ 1386 px. Every value is near the frame centre, which supports the reading.
  - **To verify:** read field 27 from our file, and fit the image-circle rim on a decoded frame (GyroView's method). Note the half-pixel convention: COLMAP puts pixel centres at +0.5 (see the header of [colmap models.h](https://github.com/colmap/colmap/blob/4.2.1/src/colmap/sensor/models.h)).

### 1.3 Projection models (camera-frame unit ray P = (X, Y, Z); x right, y down, z along the optical axis; rho = hypot(X, Y); theta = atan2(rho, Z))
- **V1, lens type 71** (vendor `PolyPinholeModel`). The degree polynomial comes from the lens-ID table, and the radius is normalised at F/2 = 100 deg:
  - `P(t) = 0.02249 t - 5.79e-5 t^2 + 1.932e-6 t^3 - 1.295e-8 t^4` (t = theta in **degrees**; P(100) = 2.307)
  - `r = R * P(theta_deg) / P(100)`; `u = cx + r X/rho`; `v = cy + r Y/rho`
  - Paraxial focal = R * 0.02249 * (180/pi) / P(100) = **1626 canvas px** for lens 0 (~780 px in the track if the scale is 0.48). An equidistant fit gives 1668.
  - Values: r(60 deg) = 1755, r(90 deg) = 2668, r(98 deg) = 2867 canvas px.
  - Sources: telemetry-parser `lens_model` (V1) and [rig_mask_coefficients.rs](https://github.com/AdrianEddy/telemetry-parser/blob/master/src/insta360/rig_mask_coefficients.rs); insta360-rs calibration.md ("V1/V2 share native degree-to-radian polynomial normalization", from `GetDegreeCoeffs` / `PolyPinholeModelToInstrinsicParams` in the iOS SDK 1.10.4). (H for the formula; M for accuracy)
  - Caveat: GyroView measured on two X5 units against Insta360 Studio exports. Read with an equidistant model, the X5 legacy radius fits best at **96-97 deg**, not 100 deg. That is a 1-4 % radial-scale uncertainty between units, and it differs between the 8K and 5.7K modes ([ADR 0023](https://github.com/bubo-squared/GyroView/blob/main/docs/adr/0023-the-legacy-radius-spans-96-degrees.md)). (M)
- **V2:** `radius cx cy e1 e2 e3 tx ty tz c0..c3 width height type`. Radial polynomial in radians, with focal = radius / r(theta_max).
- **V3 (Mei / unified sphere + Brown):** fields `xi fx fy cx cy e1 e2 e3 tx ty tz k1 k2 k3 p1 p2 width height type`.
  - `d = |P|`; `m = (X, Y) / (Z + xi d)`; `r2 = |m|^2`
  - `xd = mx (1 + k1 r2 + k2 r2^2 + k3 r2^3) + 2 p1 mx my + p2 (r2 + 2 mx^2)`; yd is analogous
  - `u = cx + fx xd`; `v = cy + fy yd`
  - Valid while `Z/d >= cos(fov_limit)`.
- **V6 (Mei + RadtanPro, 13 terms):**
  - `R = 1 + d0 r^2 + ... + d4 r^10`
  - `xd = mx R + (r^2 + 2 mx^2)(d5 + d7 r^2) + 2 mx my (d6 + d8 r^2) + d9 r^2 + d11 r^4`; yd is analogous with d6/d5, d8/d7, d10, d12
  - The tangential pair is ordered **opposite** to V3.
  - Source: [video-types geometry.rs](https://crates.io/crates/video-types) (`LensModel::Mei`, `MeiDistortion`), GyroView [ADR 0032](https://github.com/bubo-squared/GyroView/blob/main/docs/adr/0032-the-v6-string-is-a-mei-model-with-more-terms.md). (H for the form)
- Translation `t` (v2 and later) is in metres per telemetry-parser (the X5 baseline is 31.9 mm, and it measurably matters for the seam). insta360-rs calls the unit unestablished.

### 1.4 Field of view
- Lens 71: 200 deg class (`GetFov`).
- Studio reads each fisheye only inside a mask disc at `GetFov/2 - 2 deg` = **98 deg** half-angle.
- The two-lens video blend is about 6 deg wide around the 90 deg seam (telemetry-parser). insta360-rs gives 190 deg blend support.
- The real image extends to about 101-102 deg (measured on the X5). (H/M)

### 1.5 Lens order, front/back, lens-to-lens rotation
- **The 180 deg half-turn between the lenses is not in the string.** Both lenses carry about 90 deg "roll" (sensor mounting) plus sub-degree residuals. Each tool adds the half-turn itself, and **the three tools use three different Euler compositions:**
  - telemetry-parser: `R = Ry(e2 + 90) Rz(e1) Rx(e3)`, with lens 0 right-multiplied by `Rz(180)`
  - insta360-rs: `R = Rz(e3) Ry(e2 + 90) Rx(e1)`, then `Ry(180) R` for lens 1
  - GyroView (measured against Studio on the X5): yaw and pitch in the body frame, then a half-turn about the lateral axis, then roll mirrored about the nearest quarter-turn ([ADR 0025](https://github.com/bubo-squared/GyroView/blob/main/docs/adr/0025-the-lens-pose-as-measured-against-studio.md))
- The relative residual in our file is about 0.5-0.6 deg. **Treat the factory relative rotation as a prior only; let COLMAP's rig estimation decide it.** (M)
- **Track to lens:** use field 131. With `3`, track i is lens i. With `4` (what the X5 declares), the order is reversed. Not verified on X4 (L).
- File-name convention (split-file bodies): `_00_` is lens 0 and `_10_` is lens 1. GyroView calls lens 1 the screen side. The tools disagree on whether "front" or "back" names lens 0. **Check against a frame** (the screen-side lens sees whoever holds the camera in a selfie hold).

### 1.6 Does the X4 carry richer calibration?
- Probably yes, but our file must be checked.
  - telemetry-parser's IMU-orientation table lists the X4 (`yzX`) in its `has_offset_v3` branch, which implies X4 files carry `offset_v3` (field 54).
  - insta360-rs ships verified X4 **V6** housing-conversion routes (lens 86/87), which implies X4 firmware writes `offset_v6` (field 111). (M)
- **Action:** dump fields 53/54/111 from our file. If v3 or v6 is present, prefer it: it carries xi, fx, fy and distortion, and every tool reads it first.
- **How to decode:** the protobuf strings are plain wire-type-2 fields (a 30-line Python parser following FORMAT.md is enough). Ready-made options:
  - **insta360-rs 0.2.0** has a `win_amd64` abi3 wheel on [PyPI](https://pypi.org/project/insta360-rs/), published 2026-09-14 (this corrects gaps-02's "wheels unpublished"). Use `insta360_rs.probe(...)`. Note that it bundles licensed Insta360 assets; see its README.
  - telemetry-parser built from master. PyPI 0.3.0 is from 2024 and too old.

### 1.7 Confidence summary
- Field layout: **H** (three independent reverse-engineering sources agree).
- V1 radial profile: **M** (vendor code normalises at 100 deg; X5 empirical results say 96-97 deg with a different model).
- Canvas-to-track crop for X4 5.7K: **L** (unverified).
- Relative pose convention: **M** (the tools disagree).
- Conclusion: factory V1 values are **not** precise enough to fix intrinsics for 3DGS. Use them to initialise.

### 1.8 Self-calibration route (recommended)
- **COLMAP 4.2.1 camera models** (from [models.h @4.2.1](https://github.com/colmap/colmap/blob/4.2.1/src/colmap/sensor/models.h)):
  - pinhole: SIMPLE_PINHOLE, PINHOLE, SIMPLE_RADIAL, RADIAL, OPENCV, FULL_OPENCV
  - fisheye and others: OPENCV_FISHEYE, FOV, SIMPLE_RADIAL_FISHEYE, RADIAL_FISHEYE, THIN_PRISM_FISHEYE, **RAD_TAN_THIN_PRISM_FISHEYE** (Aria Fisheye624; fx fy cx cy k0..k5 p0 p1 s0..s3), SIMPLE_DIVISION, DIVISION, SIMPLE_FISHEYE, FISHEYE, **EUCM** (fx fy cx cy alpha beta), EQUIRECTANGULAR
- **No COLMAP model handles >180 deg.**
  - Every `ImgFromCam` begins with `HasProjectableDepth(w)`, which rejects w <= eps.
  - EUCM even classes as a "pinhole-type" model and checks the denominator.
  - `CamRayFromImg` is documented as "correct for perspective and fisheye-with-FOV <= 180 deg, rz > 0 always".
  - So the 90-100 deg ring of each lens is unusable inside COLMAP. That is acceptable, because the other lens covers it.
- **The COLMAP undistorter** (`image_undistorter`) produces **one PINHOLE image per input** ([undistortion.cc](https://github.com/colmap/colmap/blob/4.2.1/src/colmap/image/undistortion.cc)). That is useless for a 200 deg circle.
- `pycolmap.panorama` / `examples/panorama_sfm.py` render virtual pinhole rigs, but **only from equirectangular input**. Write our own fisheye-to-pinhole remap (cv2.remap with the chosen model).
- **Plan:**
  1. **Intrinsics per lens, offline.** Either:
     - (a) ChArUco or checkerboard calibration with OpenCV `cv2.omnidir` (Mei + radtan, the same family as v3; supports >180 deg), or
     - (b) COLMAP self-calibration on a short, well-textured clip of raw fisheye frames, with `OPENCV_FISHEYE` (KB, 4 params; stable for theta < 90 deg) initialised to f ~ 780 px and c ~ (1440, 1440). Use `RAD_TAN_THIN_PRISM_FISHEYE` only if the residuals demand it.
     - Compare the result with the decoded factory model (V1, or v3/v6 if present).
  2. **Render virtual views.** Use 4-6 pinhole views per lens (about 90 deg FOV, axes within ~45-50 deg of the optical axis, so all sampled rays are at <= ~90 deg).
  3. **Main SfM.** Give COLMAP fixed `PINHOLE` cameras, using the rig configurator: the virtual cameras of one lens share a centre, and the relative pose of the second lens comes from SfM or the prior.
- Alternative for later: gsplat main supports fisheye / FTheta cameras beyond 180 deg in 3DGUT mode (`--with_ut --with_eval3d`; commit [96f18e7](https://github.com/nerfstudio-project/gsplat/commit/96f18e762a), #1050). It could train directly on fisheye frames once poses exist.

---

## 2. Q2 - X4 gyro/accel and exposure records (brief)

- **Trailer footer** (the last 72 bytes):
  - 32 reserved bytes
  - u32 trailer size
  - u32 version (3)
  - 32-byte ASCII magic `8db42d694ccc418790edff439fe026bf`
- **Record descriptors:** each record payload is followed by a 6-byte descriptor `u8 format, u8 id, u32 size`. The descriptor nearest the footer sits at EOF-78.
- **Index:** on X4/X5 that nearest record is an **index (id 0)**: 10-byte slots `u8 id, u8 format, u32 size, u32 offset_from_payload_start`. Trust the index; X5/X6 records sit in 128 KiB-aligned slots.
- Sources: [telemetry-parser mod.rs](https://github.com/AdrianEddy/telemetry-parser/blob/master/src/insta360/mod.rs), GyroView FORMAT.md.
- **Record 3, gyro + accel.** The layout is chosen by protobuf field 62 `is_raw_gyro`; payload size alone is ambiguous.
  - Raw: 20-byte samples `u64 t_us, u16 ax ay az, u16 gx gy gz`. Values are offset-binary: `(raw - 32768) * range / 32768`. Ranges come from field 65 {1 acc g, 2 gyro dps}. The X5 runs at 1 kHz.
  - Float: 56-byte samples `u64 t_ms, f64 ax ay az (g), f64 gx gy gz (rad/s)`.
  - Which layout and rate the X4 uses is **unverified**: read field 62 from our file.
- **Record 4, exposure** (and **12** = `ExposureTimeVin1`, the second sensor's exposures): 16-byte entries `u64 capture timestamp (same unit as gyro), f64 exposure s`, one per captured frame.
  - The entries start a few frames before `first_frame_timestamp` (field 24).
  - Frame k = the entry at or after field 24, plus k.
  - Gyro timestamps are additionally shifted by field 28 (ms) when field 29 is set.
  - Field 25 is the rolling-shutter readout (ms).
- Other ids:
  - 7 GPS (53-byte entries)
  - 9 AAA (48 bytes)
  - 6 timelapse timestamps
  - 13 magnetic, 14 euler, 15 secondary gyro, 25 quaternion: undecoded
  - Sources: telemetry-parser record.rs, insta360-rs INSV_FORMAT.md.

---

## 3. Q3 - gsplat on Windows (state on 2026-10-17)

### 3.1 Release and repo state
- **PyPI latest: 1.5.3, uploaded 2025-07-04.** A pure `py3-none-any` wheel plus sdist, with CUDA compiled at first import or on sdist install ([PyPI](https://pypi.org/project/gsplat/)).
- No v1.6.0 tag or release exists. On **main**, `gsplat/version.py` reads `1.6.0` (bumped 2026-08-14). The latest commit is `512d366b67`, 2026-09-19.
- main requires `torch>=2.7` (setup.py and pyproject), but `examples/requirements.txt` pins `torch==2.9.1`, `torchvision==0.24.1` and `torchmetrics==1.8.2`. **Strip the torch and torchvision pins** for a torch 2.8 environment.
- main builds with **C++20** (`/std:c++20 /Zc:preprocessor -DWIN32_LEAN_AND_MEAN` on Windows; see [gsplat/cuda/build.py](https://github.com/nerfstudio-project/gsplat/blob/main/gsplat/cuda/build.py)).
- A second, experimental extension also builds by default; set `BUILD_EXPERIMENTAL=0` to skip it.

### 3.2 MSVC fixes: NOT merged
- [PR #1055](https://github.com/nerfstudio-project/gsplat/pull/1055) (open; GitHub reports it mergeable/clean against base `28e794c`) fixes:
  - `__builtin_clzll`, replaced with `_BitScanReverse64`
  - C3495, by making `constexpr` locals in lambdas `static constexpr` (six .cu files)
  - LNK2001 from the `bool` vs `const bool fwd_only` mismatch
  - the private `at::cuda::cub::radix_sort_pairs<int64_t, ...>` instantiation (not exported by `torch_cuda.dll`), replaced with a direct `cub::DeviceRadixSort::SortPairs`
  - plus CUDA 13-only items (device `std::isfinite`, zero-size `std::array`, `uint`)
- Overlapping PRs: [#1085](https://github.com/nerfstudio-project/gsplat/pull/1085) (open, 2026-10-13; uses `at::sort` instead and adds `docs/INSTALL_WIN_CUDA13.md`) and [#1008](https://github.com/nerfstudio-project/gsplat/pull/1008) / issue [#1007](https://github.com/nerfstudio-project/gsplat/issues/1007) (clzll only).
- **Confirmed on main:** `__builtin_clzll` is still at `RasterizeToPixelsFromWorld3DGSParallelBatchBwd.cu:190`, `at::cuda::cub::radix_sort_pairs` at line 234, and `constexpr uint32_t CDIM` at Bwd:1096 and Fwd:1614.
- These are MSVC problems, not CUDA 13 problems, so **they also hit CUDA 12.8**. (H)
- Both PRs were tested only with CUDA 13 + MSVC 14.44, not with 12.8 (L risk).

### 3.3 Prebuilt Windows wheels
- `https://docs.gsplat.studio/whl/gsplat/` lists Windows wheels **only for cp310**, up to `1.5.3+pt24cu124`. 1.4.0-1.5.2 have pt20-pt24 with cu118/121/124.
- **Nothing exists for torch 2.5 or later, cu126/128, or cp311.** So: build from source. (H)

### 3.4 Recommended install (Windows 11, Python 3.11, torch 2.8.0+cu128, CUDA 12.8.1, MSVC 14.44)
- **Why torch 2.8.0 and not 2.9 or later:**
  - From torch 2.9 the `compiled_autograd.h` Windows guard became `_WIN32 && (USE_CUDA || USE_ROCM)`. Extension builds never define those macros, so nvcc hits `C2872 'std': ambiguous symbol`.
  - 2.8.0 has a plain `#ifdef _WIN32` guard, and users report downgrading to 2.8.0 fixes it ([pytorch#166123](https://github.com/pytorch/pytorch/issues/166123), [#173232](https://github.com/pytorch/pytorch/issues/173232); fix PR [#188952](https://github.com/pytorch/pytorch/pull/188952) is still open).
- **Why MSVC 14.44 is fine:** older CUDA `host_config.h` versions accept `_MSC_VER` 19.4x, and only VS 18 (19.5x) needs `-allow-unsupported-compiler` (see the comment in COLMAP's [build-windows.yml](https://github.com/colmap/colmap/blob/4.2.1/.github/workflows/build-windows.yml)).

```bat
:: "x64 Native Tools Command Prompt for VS 2022" (toolset 14.44)
set CUDA_HOME=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8
set PATH=%CUDA_HOME%\bin;%PATH%
set DISTUTILS_USE_SDK=1
set TORCH_CUDA_ARCH_LIST=8.6
set CUDA_ARCHITECTURES=86
set BUILD_EXPERIMENTAL=0
set MAX_JOBS=6
py -3.11 -m venv .venv && .venv\Scripts\activate
python -m pip install -U pip setuptools wheel ninja
pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu128
git clone https://github.com/nerfstudio-project/gsplat.git && cd gsplat
git checkout 512d366b67
git fetch origin pull/1055/head:pr1055 && git merge --no-edit pr1055
pip install --no-build-isolation -v .
python -c "import torch, gsplat; from gsplat import csrc; print(torch.__version__, gsplat.__version__)"
:: extras used by examples/simple_trainer.py
pip install --no-build-isolation git+https://github.com/rahul-goel/fused-ssim@a7c48d6dd7ac6dc39a7958c7c4452e0b10418f38
pip install --no-build-isolation git+https://github.com/harry7557558/fused-bilagrid@49f0ef06c9f81810fb9b5dd9027cf1844950cc16
pip install --no-build-isolation git+https://github.com/nv-tlabs/ppisp@v1.2.1
:: then examples/requirements.txt with the torch/torchvision lines removed (pycolmap 4.2.1 has a cp311 win wheel)
```

- **Wheel availability:** `torch-2.8.0+cu128-cp311-cp311-win_amd64.whl` and `torchvision-0.23.0+cu128-cp311-...` exist on download.pytorch.org (checked).
- **Smoke test:** after the build, run `examples/simple_trainer.py default` on a small dataset for about 200 steps.
- **Fallback** if the merge fails: build the **v1.5.3** sdist (`pip install --no-binary=gsplat gsplat==1.5.3 --no-build-isolation`). It predates the ParallelBatch kernels, and an official Windows wheel was built from it. However, its trainer has masks but **no PPISP**.
- **Build flags for the extras:**
  - **fused-ssim** needs `--no-build-isolation`, otherwise pip builds it against a CPU-only torch in the isolated environment ([README](https://github.com/rahul-goel/fused-ssim)). Set the arch via `CUDA_ARCHITECTURES=86`. Its fallback list has no sm_86, so set the variable or have the GPU visible. The `-O3` it passes to cl is only a warning. It was tested on Windows 11 (torch 2.5.1/cu126). The open Windows issues [#42](https://github.com/rahul-goel/fused-ssim/issues/42) and [#40](https://github.com/rahul-goel/fused-ssim/issues/40) are about torch 2.10 (C2872) and missing build isolation.
  - **fused-bilagrid** must be at commit `49f0ef0` or newer. Older pins fail on MSVC with C2398 narrowing ([issue #4](https://github.com/harry7557558/fused-bilagrid/issues/4)). It detects the arch from `torch.cuda` at build time.
  - **PPISP** v1.2.1 honours `TORCH_CUDA_ARCH_LIST`. No Windows report either way (L), but it is a single .cu file, so the risk is low.

### 3.5 Masks and PPISP in examples/simple_trainer.py (main)
- **Masks.**
  - Format: `data["mask"]` is a bool tensor of shape [1, H, W], True = valid.
  - What the trainer does with it: sets `render_colors[~masks] = 0`, computes L1 only on masked pixels, and runs SSIM on images with the masked pixels zeroed. Evaluation uses masks the same way.
  - Limitation: the **COLMAP parser on main only fills `mask` with the per-camera fisheye-undistortion ROI**. It has **no per-image mask folder** (`examples/datasets/colmap.py`, `mask_dict[camera_id]`). For operator or tripod masks, add a small patch: load `masks/<image_name>.png` in `Dataset.__getitem__` and set `data["mask"]`.
  - Watch out: `patch_size` cropping does not crop the mask.
  - The ncore dataset path has native masks (`ncore_masks_component_group`). Even v1.5.3's trainer already consumes `data["mask"]`.
- **PPISP:** `--post_processing ppisp`, which requires `batch_size=1`. Options: `--ppisp_use_controller`, `--ppisp_controller_distillation`, `--ppisp_controller_activation_num_steps 25000`. PPISP reports are exported at the end. Enabled for all densification strategies since [#1003](https://github.com/nerfstudio-project/gsplat/commit/bf302ef532). The alternative is `--post_processing bilateral_grid` (fused-bilagrid).

### 3.6 COLMAP 4.2.1 Windows
- Release [4.2.1](https://github.com/colmap/colmap/releases/tag/4.2.1), published 2026-09-29. Assets:
  - `colmap-x64-windows-cuda.zip` (414.7 MB): https://github.com/colmap/colmap/releases/download/4.2.1/colmap-x64-windows-cuda.zip
  - `colmap-x64-windows-nocuda.zip` (127.7 MB)
  - `colmap-arm64-macos.zip`
- The CUDA build uses **CUDA 13.2.0**, all-major architectures 75-120 (sm_80 code runs on sm_86), so it needs an R595+ driver (see gaps-05). It is independent of the CUDA 12.8 toolkit that gsplat uses.
- pycolmap 4.2.1 has a cp311 `win_amd64` wheel on PyPI.
