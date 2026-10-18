# GPU checks on the office PC after setup_office.ps1 (about 5 minutes). Each test prints PASS or FAIL.
#     powershell -ExecutionPolicy Bypass -File scripts\office_setup\check_office.ps1 -Clip D:\...\VID_..._069.insv
# 1. torch + gsplat render/backward on the RTX 5060 (sm_120 kernels), plus the training benchmark
# 2. COLMAP ALIKED feature extraction + LightGlue matching on 20 real views, with peak VRAM: the
#    home PC used ~9.9 GB for ALIKED, so on 8 GB this is the step most likely to need a smaller setting
param([string]$Clip = "", [string]$Dev = "C:\dev")
$ErrorActionPreference = "Continue"
$Repo = (Resolve-Path "$PSScriptRoot\..\..").Path
$gsPy = "$Dev\envs\gs\Scripts\python.exe"
$pipePy = "$Dev\envs\pipe\Scripts\python.exe"
$work = "$Dev\build\check"
New-Item -ItemType Directory -Force $work | Out-Null
$results = @()
function Result($name, $ok, $detail) {
    $script:results += "{0,-34} {1}  {2}" -f $name, $(if ($ok) { "PASS" } else { "FAIL" }), $detail
    Write-Host ("{0}: {1} {2}" -f $name, $(if ($ok) { "PASS" } else { "FAIL" }), $detail) -ForegroundColor $(if ($ok) { "Green" } else { "Red" })
}

Write-Host "`n== 1. torch + gsplat" -ForegroundColor Cyan
$out = & $gsPy -c "import torch, gsplat; from gsplat import rasterization; print(torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0)); m=torch.randn(1000,3,device='cuda',requires_grad=True); q=torch.randn(1000,4,device='cuda'); s=torch.full((1000,3),0.02,device='cuda'); o=torch.full((1000,),0.8,device='cuda'); c=torch.rand(1000,3,device='cuda'); v=torch.eye(4,device='cuda'); v[2,3]=3; K=torch.tensor([[300.,0,200],[0,300,200],[0,0,1]],device='cuda'); img,_,_=rasterization(m,q,s,o,c,v[None],K[None],400,400); img.sum().backward(); print('render+backward OK', float(img.mean()), float(m.grad.abs().sum())>0)" 2>&1
$out | ForEach-Object { Write-Host "   $_" }
Result "gsplat render + backward" ($LASTEXITCODE -eq 0 -and ($out -join " ") -match "render\+backward OK") ""
& $pipePy -m app bench 2>&1 | ForEach-Object { Write-Host "   $_" }
Result "training benchmark (saved for estimates)" ($LASTEXITCODE -eq 0) ""

Write-Host "`n== 2. COLMAP ALIKED + LightGlue on real views" -ForegroundColor Cyan
if (-not $Clip) { Write-Host "   skipped: pass -Clip <an .insv file> to test it"; } else {
    Push-Location $Repo
    $proj = "office-check"
    & $pipePy -m app init $proj --insv $Clip | Out-Null
    & $pipePy -m app probe $proj | Out-Null
    $cid = (Get-Item $Clip).BaseName.Split("_")[-1]
    & $pipePy -m app frames $proj --clip $cid --start 20 --end 24 --window 2 | Out-Null   # 2 frames x 10 views = 20 images
    & $pipePy -m app views $proj --clip $cid | Out-Null
    $vram = [System.Collections.Generic.List[int]]::new()
    # A background job starts in another folder: give it the project folder explicitly.
    $job = Start-Job { param($repo, $cmd) Set-Location $repo; & $cmd[0] $cmd[1..($cmd.Length - 1)] 2>&1 } `
        -ArgumentList $Repo, @($pipePy, "-m", "app", "sfm", $proj, "--clip", $cid, "--name", "check")
    while ($job.State -eq "Running") { $vram.Add([int](& nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)); Start-Sleep -Milliseconds 500 }
    $log = Receive-Job $job; Remove-Job $job
    $peak = ($vram | Measure-Object -Maximum).Maximum
    $total = [int](& nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits)
    $clog = "projects\$proj\sfm\$cid\check\colmap.log"
    $ext = (Test-Path $clog) -and ((Get-Content $clog -Raw) -match "Processed file \[(\d+)/\1\]")
    $cudaErr = (Test-Path $clog) -and ((Get-Content $clog -Raw) -match "no kernel image|CUDA error|CUDAExecutionProvider.*(fail|not available)|out of memory")
    Result "ALIKED extraction (real views)" ($ext -and -not $cudaErr) "peak VRAM $peak of $total MB"
    $matched = (Test-Path $clog) -and ((Get-Content $clog -Raw) -match "Feature matching|Matching")
    Result "LightGlue matching" ($matched -and -not $cudaErr) ""
    if ($cudaErr) { Select-String -Path $clog -Pattern "no kernel image|CUDA error|out of memory|ExecutionProvider" | Select-Object -First 5 | ForEach-Object { Write-Host "   $($_.Line)" } }
    # ONNX Runtime reserves most free VRAM up front (home 3080: ~9.8 of 10 GB with 8192 or 4096 features), so a
    # high peak is normal. Only an out-of-memory failure means the setting must change.
    if ($cudaErr -and ((Get-Content $clog -Raw) -match "out of memory")) {
        Write-Host "   out of GPU memory: pick 4096 features per view in the studio (or --max-features 4096)" -ForegroundColor Yellow
    }
    Pop-Location
    Write-Host "   (test project projects\$proj can be deleted)"
}

Write-Host "`n================ SUMMARY" -ForegroundColor Cyan
$results | ForEach-Object { Write-Host $_ }
$results | Set-Content -Encoding utf8 "$work\check_results.txt"
Write-Host "saved: $work\check_results.txt"
