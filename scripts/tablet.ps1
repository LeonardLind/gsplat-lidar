# Read-only tablet server for the explorer (walk + drone, touch controls), port 5180.
#   scripts\tablet.ps1                       the scene the studio last opened
#   scripts\tablet.ps1 -Scene forest         the forest demo (projects\forest-demo\export\imported\forest)
#   scripts\tablet.ps1 -Scene <export dir>   any exported scene folder
#   scripts\tablet.ps1 -Lan                  also listen on the local network and show a QR code for http://<PC address>:5180
# For a dev tunnel forward port 5180 only (never the dev server on 5173: it has the job API and the editor).
param([string]$Scene = "", [switch]$Lan, [int]$Port = 5180)
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path "$PSScriptRoot\..").Path
if ($Scene -eq "forest") { $Scene = "$Repo\projects\forest-demo\export\imported\forest" }
if ($Scene) {
    if (-not (Test-Path "$Scene\scene.json")) { throw "no scene.json in $Scene" }
    $env:GSL_SCENE_DIR = (Resolve-Path $Scene).Path
    Write-Host "scene: $env:GSL_SCENE_DIR"
} else { Write-Host "scene: whatever the studio opened last (set -Scene to pin one)" }
$env:TABLET_PORT = "$Port"
if ($Lan) {
    $env:TABLET_LAN = "1"
    $ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notmatch '^(127|169|172\.(1[6-9]|2\d|3[01])\.)' -and $_.PrefixOrigin -ne "WellKnown" } | Select-Object -First 1).IPAddress
    $url = "http://${ip}:$Port/"
    Write-Host "same-network address: $url"
    & C:\dev\envs\pipe\Scripts\python.exe "$PSScriptRoot\tablet_qr.py" $url "$Repo\projects\tablet_qr.png"
}
Set-Location "$Repo\web\viewer"
npm run tablet
