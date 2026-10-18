# Full-quality joint run of the office capture (clips 068 + 069, both heights). Not started yet:
# the user wants it only after the 069 test splat is good. Expect ~20 h on the RTX 3080, GPU only for this job.
#   powershell -ExecutionPolicy Bypass -File scripts\run_joint_office.ps1
# Each step can be rerun on its own; outputs go to projects\office\{views,sfm,train,export}\all\...
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$py = "C:\dev\envs\pipe\Scripts\python.exe"
$tree = "C:\dev\tools\vocab\vocab_tree_faiss_flickr100K_words64K_aliked_n16rot.bin"

function Step($title, [scriptblock]$cmd) {
    Write-Host "`n===== $title  ($(Get-Date -Format 'yyyy-MM-dd HH:mm'))" -ForegroundColor Cyan
    & $cmd
    if ($LASTEXITCODE -ne 0) { throw "step failed: $title" }
}

# Views of both clips merged (hard links): already done on 2026-10-17; harmless to repeat.
Step "merge views"      { & $py -m app merge-views office --clips 068,069 --name all }
Step "people + SfM masks (GPU, ~1 h)" { & $py -m app people office --views all }
Step "SfM: ALIKED + LightGlue, loop detection (GPU, ~16 h)" {
    & $py -m app sfm office --views all --vocab-tree $tree --name aliked_global
}
Step "orient"           { & $py -m app orient office --views all --sfm aliked_global }
Step "classify people, training masks" { & $py -m app people-classify office --views all --sfm aliked_global }
Step "train (GPU, ~3-4 h)" {
    & $py -m app train office --views all --sfm aliked_global --steps 60000 --cap 2000000 --packed --name full_2m_60k
}
Step "export for the browser viewer" { & $py -m app export office --views all --run full_2m_60k --formats sog,html }
Write-Host "`nDone. Review projects\office\views\all\mask_sheet.jpg and the SfM report before trusting the splat." -ForegroundColor Green
