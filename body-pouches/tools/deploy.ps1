
# Laying body-pouches out into mods\. Every path and name is in config/build.json.
#
#   tools\deploy.ps1            show what would be done
#   tools\deploy.ps1 -Apply     do it
#
# The mod is one DLL. Its settings file and its table of text are written by the
# plugin itself on first run, so there is nothing here to keep in step with them -
# the only thing that can go stale is the library, and a missing build is refused
# rather than warned about: laying out quietly would leave last week's DLL in mods\
# and the next run would be testing that.
param([switch]$Apply)
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$cfg  = Get-Content -LiteralPath (Join-Path $root 'config\build.json') -Raw | ConvertFrom-Json
$d    = $cfg.deploy

# The build may not be touched while the game or a tool under MO2 is running.
$busy = @(Get-Process -Name SkyrimVR,SkyrimSE,ModOrganizer -ErrorAction SilentlyContinue)
if ($busy.Count) { throw "Running: $($busy.Name -join ', ') - laying out is not allowed" }

function Expand-Path([string]$p) { $p.Replace('{root}', $root) }

$dll = Expand-Path $d.dll
if (-not (Test-Path -LiteralPath $dll)) {
    throw "the library is not built: $dll"
}

$dist = Join-Path $root 'dist'
Remove-Item -LiteralPath $dist -Recurse -Force -ErrorAction SilentlyContinue
$mod = Join-Path $dist $d.modName

New-Item -ItemType Directory -Force (Join-Path $mod $d.dllTargetRel) | Out-Null
Copy-Item -LiteralPath $dll -Destination (Join-Path $mod $d.dllTargetRel) -Force

foreach ($doc in $d.docs) {
    $path = Expand-Path $doc
    if (Test-Path -LiteralPath $path) { Copy-Item -LiteralPath $path -Destination $mod -Force }
}

$target = Join-Path $d.modsRoot $d.modName
Write-Host "mod:    $mod"
Write-Host "target: $target"
Get-ChildItem -Recurse -File $mod | ForEach-Object {
    Write-Host ("  " + $_.FullName.Substring($mod.Length + 1))
}

if (-not $Apply) {
    Write-Host "`n(dry run - pass -Apply to copy into mods\)"
    return
}

New-Item -ItemType Directory -Force $target | Out-Null
Copy-Item -Path (Join-Path $mod '*') -Destination $target -Recurse -Force
Write-Host "`nlaid out: $target"
Write-Host "MO2 shows the mod once it is refreshed; it still has to be enabled there."
