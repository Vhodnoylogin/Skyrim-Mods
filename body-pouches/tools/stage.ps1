
# Gathering the mod into dist\, ready to be packed. Every path and name is in
# config/build.json.
#
#   tools\stage.ps1     build dist\<mod>\ and list what is in it
#
# This script touches nothing outside dist\: it does not copy into mods\ and never
# will. Our mods enter the build the way everybody else's do - as an archive in the
# downloads folder, installed by MO2 itself. That is tools\package.ps1.
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$cfg  = Get-Content -LiteralPath (Join-Path $root 'config\build.json') -Raw | ConvertFrom-Json
$d    = $cfg.deploy

function Expand-Path([string]$p) { $p.Replace('{root}', $root) }

# The library is the mod. A missing build is a refusal rather than a warning:
# packing quietly would ship last week's DLL and the next run would be testing that.
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

Write-Host "dist: $mod"
Get-ChildItem -Recurse -File $mod | ForEach-Object {
    Write-Host ("  " + $_.FullName.Substring($mod.Length + 1))
}
