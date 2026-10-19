# Set up the splat toolchain on the office PC (RTX 5060 8 GB, Blackwell = compute capability 12.0).
# Same layout and versions as the home PC (C:\dev), but gsplat and its CUDA extras are compiled for sm_120.
# Run from the copied project folder, in a normal PowerShell (not admin):
#     powershell -ExecutionPolicy Bypass -File scripts\office_setup\setup_office.ps1 -Transfer E:\gsl_transfer
# Safe to run again: finished steps are skipped. Log: C:\dev\build\setup_office.log
param(
    [string]$Transfer = "",           # folder made by make_transfer.ps1 (COLMAP zip, vocab trees); empty = download
    [string]$Dev = "C:\dev",
    [string]$Arch = "12.0"            # TORCH_CUDA_ARCH_LIST; 12.0 = RTX 50 series
)
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path "$PSScriptRoot\..\..").Path
$Here = $PSScriptRoot
New-Item -ItemType Directory -Force "$Dev\build", "$Dev\envs", "$Dev\src", "$Dev\tools", "$Dev\cache\uv", "$Dev\cache\torch", "$Dev\dl" | Out-Null
Start-Transcript -Path "$Dev\build\setup_office.log" -Append | Out-Null
$env:UV_CACHE_DIR = "$Dev\cache\uv"

function Step($name) { Write-Host "`n===== $name" -ForegroundColor Cyan }
function Need($ok, $msg) { if (-not $ok) { Write-Host "MISSING: $msg" -ForegroundColor Red; Stop-Transcript | Out-Null; exit 1 } }

Step "Prerequisites"
$smi = (& nvidia-smi --query-gpu=name,driver_version,compute_cap --format=csv,noheader 2>$null)
Need ($smi) "NVIDIA driver (nvidia-smi). Install the current Game Ready / Studio driver."
Write-Host "GPU: $smi"
$drv = [double](($smi -split ",")[1].Trim().Split(".")[0])
Need ($drv -ge 572) "driver 572 or newer (CUDA 12.8 on Blackwell); found $drv"
$vcvars = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat"
if (-not (Test-Path $vcvars)) { $vcvars = "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" }
Need (Test-Path $vcvars) "Visual Studio 2022 Build Tools with 'Desktop development with C++' and MSVC v14.44"
$cuda = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8"
Need (Test-Path "$cuda\bin\nvcc.exe") "CUDA toolkit 12.8 (cuda_12.8.1_572.61_windows.exe, in the transfer folder)"
Need (Get-Command uv -ErrorAction SilentlyContinue) "uv:   winget install astral-sh.uv"
Need (Get-Command git -ErrorAction SilentlyContinue) "git:  winget install Git.Git"
Need (Get-Command node -ErrorAction SilentlyContinue) "Node.js 24:  winget install OpenJS.NodeJS.LTS"
Need (Get-Command ffprobe -ErrorAction SilentlyContinue) "ffmpeg (ffprobe):  winget install Gyan.FFmpeg"
Write-Host "all prerequisites found"

Step "Python environment 'pipe' (pipeline, studio server)"
if (-not (Test-Path "$Dev\envs\pipe\Scripts\python.exe")) { uv venv --python 3.12 "$Dev\envs\pipe" }
uv pip install --python "$Dev\envs\pipe\Scripts\python.exe" -r "$Here\pipe-freeze.txt"

Step "Python environment 'gs' (torch 2.8 cu128 + gsplat)"
if (-not (Test-Path "$Dev\envs\gs\Scripts\python.exe")) { uv venv --python 3.11 "$Dev\envs\gs" }
$gsPy = "$Dev\envs\gs\Scripts\python.exe"
# Everything from the home PC except the packages compiled here for sm_120.
$req = "$Dev\build\gs-req.txt"
Get-Content "$Here\gs-freeze.txt" | Where-Object { $_ -notmatch "^(gsplat|fused-ssim|fused-bilagrid|ppisp) " } | Set-Content -Encoding ascii $req
uv pip install --python $gsPy -r $req --extra-index-url https://download.pytorch.org/whl/cu128 --index-strategy unsafe-best-match
& $gsPy -c "import torch; print('torch', torch.__version__, 'cuda', torch.version.cuda, 'arch list', torch.cuda.get_arch_list()); assert 'sm_120' in torch.cuda.get_arch_list(), 'this torch build has no sm_120'"

Step "gsplat source (main 512d366 + our Windows patch)"
if (-not (Test-Path "$Dev\src\gsplat\.git")) { git clone https://github.com/nerfstudio-project/gsplat.git "$Dev\src\gsplat" }
Push-Location "$Dev\src\gsplat"
$head = (git rev-parse --short=7 HEAD)
if ($head -ne "512d366") { git checkout -f 512d366 }
# A fresh clone can already be at 512d366 (unpatched), so test the patch itself instead of assuming.
git submodule update --init --recursive
$patch = "$Repo\app\trainers\gsplat_fork\patches\gsplat-512d366-windows.patch"
git apply --check $patch 2>$null
if ($LASTEXITCODE -eq 0) { git apply $patch; Write-Host "patch applied" }
else {
    git apply --check --reverse $patch 2>$null
    Need ($LASTEXITCODE -eq 0) "the gsplat tree at $Dev\src\gsplat neither takes nor already has the Windows patch (delete the folder and re-run)"
    Write-Host "patch already applied"
}
Pop-Location

Step "Build gsplat + fused-ssim + fused-bilagrid + ppisp for sm_$($Arch.Replace('.',''))"
$bat = "$Dev\build\build_gs_office.bat"
@"
@echo off
call "$vcvars" x64 -vcvars_ver=14.44 || call "$vcvars" x64 || exit /b 1
set CUDA_HOME=$cuda
set CUDA_PATH=%CUDA_HOME%
set PATH=%CUDA_HOME%\bin;$Dev\envs\gs\Scripts;%PATH%
set DISTUTILS_USE_SDK=1
set TORCH_CUDA_ARCH_LIST=$Arch
set BUILD_EXPERIMENTAL=0
set MAX_JOBS=12
set UV_CACHE_DIR=$Dev\cache\uv
set PY=$gsPy
uv pip install --python %PY% setuptools wheel ninja numpy || exit /b 1
pushd $Dev\src\gsplat
%PY% setup.py bdist_wheel || (popd & exit /b 1)
popd
for %%W in ($Dev\src\gsplat\dist\gsplat-*.whl) do set WHEEL=%%W
uv pip install --python %PY% --reinstall-package gsplat "%WHEEL%" || exit /b 1
uv pip install --python %PY% --no-build-isolation --reinstall "git+https://github.com/rahul-goel/fused-ssim@a7c48d6dd7ac6dc39a7958c7c4452e0b10418f38" || exit /b 1
uv pip install --python %PY% --no-build-isolation --reinstall "git+https://github.com/harry7557558/fused-bilagrid@49f0ef06c9f81810fb9b5dd9027cf1844950cc16" || exit /b 1
uv pip install --python %PY% --no-build-isolation --reinstall "git+https://github.com/nv-tlabs/ppisp@v1.2.1" || exit /b 1
echo BUILD OK
"@ | Set-Content -Encoding ascii $bat
cmd /c $bat
Need ($LASTEXITCODE -eq 0) "the gsplat build failed: see $Dev\build\setup_office.log"

Step "COLMAP 4.2.1 (CUDA) and vocab trees"
if (-not (Test-Path "$Dev\tools\colmap-4.2.1\bin\colmap.exe")) {
    $zip = if ($Transfer) { "$Transfer\colmap-4.2.1-x64-windows-cuda.zip" } else { "$Dev\dl\colmap-4.2.1-x64-windows-cuda.zip" }
    if (-not (Test-Path $zip)) {
        Invoke-WebRequest "https://github.com/colmap/colmap/releases/download/4.2.1/colmap-x64-windows-cuda.zip" -OutFile "$Dev\dl\colmap-4.2.1-x64-windows-cuda.zip"
        $zip = "$Dev\dl\colmap-4.2.1-x64-windows-cuda.zip"
    }
    $tmp = "$Dev\tools\_colmap_unzip"
    Expand-Archive -Force $zip $tmp
    $inner = Get-ChildItem $tmp -Directory | Select-Object -First 1
    Move-Item $(if (Test-Path "$tmp\bin") { $tmp } else { $inner.FullName }) "$Dev\tools\colmap-4.2.1"
    if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
}
& "$Dev\tools\colmap-4.2.1\bin\colmap.exe" help | Select-Object -First 2
if ($Transfer -and (Test-Path "$Transfer\vocab")) { Copy-Item -Recurse -Force "$Transfer\vocab" "$Dev\tools\" }
if ($Transfer -and (Test-Path "$Transfer\torch_checkpoints")) {  # Mask R-CNN weights for the people masks
    New-Item -ItemType Directory -Force "$Dev\cache\torch\checkpoints" | Out-Null
    Copy-Item -Force "$Transfer\torch_checkpoints\*" "$Dev\cache\torch\checkpoints\"
}

Step "splat-transform 3.10.1"
New-Item -ItemType Directory -Force "$Dev\tools\splat-transform" | Out-Null
Push-Location "$Dev\tools\splat-transform"
if (-not (Test-Path "node_modules\.bin\splat-transform.cmd")) { npm install "@playcanvas/splat-transform@3.10.1" --no-audit --no-fund }
Pop-Location

Step "Browser viewer / studio (npm)"
Push-Location "$Repo\web\viewer"
npm ci --no-audit --no-fund
Pop-Location

Write-Host "`nSETUP DONE. Next: scripts\office_setup\check_office.ps1" -ForegroundColor Green
Stop-Transcript | Out-Null
