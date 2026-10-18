# Office PC: setup and the long 068 + 069 run

Office PC: Core Ultra 9 285 (24 cores), 64 GB RAM, **RTX 5060 8 GB** (Blackwell, compute capability 12.0).
The home PC's builds target the RTX 3080 (sm_86), so gsplat and its CUDA extras are rebuilt here for sm_120.
Same folder layout as at home: everything under `C:\dev`, the project on the Desktop.

## 0. On the home PC (before leaving)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\office_setup\make_transfer.ps1 -Target E:\gsl_transfer
```

This makes about 9 GB: the code, the two raw clips, the COLMAP zip, the vocab trees and the CUDA 12.8.1 installer.
Derived data (frames, views, SfM, training runs) is left out; the office PC makes its own.

## 1. Install by hand (once, needs admin)

| What | How |
|---|---|
| NVIDIA driver 572 or newer | NVIDIA app / nvidia.com (Studio or Game Ready) |
| Visual Studio 2022 Build Tools | "Desktop development with C++", add **MSVC v143 – 14.44** and a Windows 11 SDK |
| CUDA 12.8.1 | `cuda_12.8.1_572.61_windows.exe` from the transfer folder (untick the driver if yours is newer) |
| uv, git, Node.js, ffmpeg | `winget install astral-sh.uv Git.Git OpenJS.NodeJS.LTS Gyan.FFmpeg` |

Open a new PowerShell afterwards so the PATH changes apply.

## 2. Copy the project and run the setup (about 30–45 min, mostly compiling)

Copy `E:\gsl_transfer\Gsplat+Lidar` to `C:\Users\<you>\Desktop\Code\Gsplat+Lidar`, then in that folder:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\office_setup\setup_office.ps1 -Transfer E:\gsl_transfer
```

It checks the prerequisites, creates the `pipe` (Python 3.12) and `gs` (Python 3.11, torch 2.8 + CUDA 12.8)
environments with the home PC's exact package versions, builds gsplat (main 512d366 + our Windows patch),
fused-ssim, fused-bilagrid and PPISP for sm_120, unpacks COLMAP 4.2.1 and installs splat-transform and the
viewer's npm packages. Log: `C:\dev\build\setup_office.log`. It can be run again; finished steps are skipped.

## 3. Check the GPU stages (about 5 min)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\office_setup\check_office.ps1 -Clip "<path>\VID_20261016_143913_00_069.insv"
```

| Check | If it fails |
|---|---|
| gsplat render + backward | The build did not produce sm_120 kernels: look at the log; `TORCH_CUDA_ARCH_LIST` must be 12.0 |
| Training benchmark | Same as above. When it passes, the studio's estimates use this PC's speed |
| ALIKED extraction, peak VRAM | "no kernel image" / CUDA error: COLMAP's ONNX Runtime has no Blackwell kernels; tell Claude (fallbacks: a newer COLMAP build, or SIFT). A peak close to 8 GB is normal (ONNX Runtime reserves most free memory; at home it took 9.8 of 10 GB with either feature count). Only if it fails **out of memory**: pick **4096 features per view** in the studio |
| LightGlue matching | As for ALIKED |

## 4. Smoke test, then the real run

Start the two servers (two PowerShell windows, both in the project folder):

```powershell
C:\dev\envs\pipe\Scripts\python.exe -m app serve
cd web\viewer; npm run dev
```

Open http://127.0.0.1:5173/studio.html.

1. **Smoke test (about 15 min):** `C:\dev\envs\pipe\Scripts\python.exe web\viewer\tools\test_pipeline.py "<path>\VID_..._069.insv"`.
   It runs every stage on 15 s of clip 069 in a throwaway project `studio-test`. All steps should end "done".
2. **The real run:** in the studio, make a new project (e.g. `office-x4`), **Add clips…** and pick both
   `VID_20261016_141637_00_068.insv` and `VID_20261016_143913_00_069.insv`. They are combined automatically (same
   camera, 14 min apart). Keep 2.5 fps and 1 M Gaussians, leave "Remove the camera operator and people walking by"
   on, check the estimate, and press **Build the splat**. Then the PC can be left alone; the job survives closing the
   browser (not shutting down or sleeping: set Windows power to "never sleep" while it runs).

The job can be watched from the studio's Jobs and Training sections. If anything fails, **Retry from the failed
step** continues from there; the finished stages are kept.
