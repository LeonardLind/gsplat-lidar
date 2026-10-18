# On the HOME PC: put everything the office PC needs into one folder (a USB drive, a network share...).
#     powershell -ExecutionPolicy Bypass -File scripts\office_setup\make_transfer.ps1 -Target E:\gsl_transfer
# Copies: the project code (without derived data: frames, views, SfM, training runs), the raw office clips,
# the COLMAP zip, the vocab trees and the CUDA 12.8.1 installer. About 9 GB; robocopy resumes if interrupted.
param([Parameter(Mandatory = $true)][string]$Target, [switch]$NoCuda, [string]$Dev = "C:\dev")
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path "$PSScriptRoot\..\..").Path
New-Item -ItemType Directory -Force $Target | Out-Null

Write-Host "== project code -> $Target\Gsplat+Lidar" -ForegroundColor Cyan
# /XD: derived pipeline data (rebuilt on the office PC), dependencies, the 4 GB demo/LiDAR samples.
# /XJ: do not follow junctions (export\current points at another export). *.lrv: the camera's low-res previews.
robocopy $Repo "$Target\Gsplat+Lidar" /E /XJ /NFL /NDL /NP /R:1 /W:1 `
    /XD node_modules dist .git frames views sfm train thumbs _server laz-testdata external `
    /XF *.tmp *.lrv | Out-Null
# The raw clips live under data\raw (kept); the office project gets a fresh project.json pointing at them.
Write-Host "== tools"
robocopy "$Dev\tools\vocab" "$Target\vocab" /E /NFL /NDL /NP | Out-Null
robocopy "$Dev\cache\torch\checkpoints" "$Target\torch_checkpoints" /E /NFL /NDL /NP | Out-Null  # person detector weights
Copy-Item "$Dev\dl\colmap-4.2.1-x64-windows-cuda.zip" $Target -Force
if (-not $NoCuda) { Copy-Item "$Dev\dl\cuda_12.8.1_572.61_windows.exe" $Target -Force }
$size = (Get-ChildItem $Target -Recurse -File | Measure-Object Length -Sum).Sum / 1GB
Write-Host ("done: {0:N1} GB in {1}" -f $size, $Target) -ForegroundColor Green
Write-Host "On the office PC: copy Gsplat+Lidar to the Desktop\Code folder, then follow scripts\office_setup\README.md"
