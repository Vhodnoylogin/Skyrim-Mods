
# Building the VRIK-slots overlay for body-pouches, packing it and installing it.
#
#   tools\slots-mod.ps1                 show what would be done (slot 13 by default)
#   tools\slots-mod.ps1 -Apply
#   tools\slots-mod.ps1 -Slots 13,1,2 -Type Small -Apply
#
# WHY THIS MOD EXISTS. VRIK ignores a slot that allows no weapon type at all - its
# author says so in the file itself: "set all weapon types to 0 to disable a slot".
# A disabled slot is not detected, so a hand brought to it raises no event and a pouch
# there would be dead. The slots a build does not use for weapons are exactly the ones
# that are switched off that way, which is to say exactly the ones a pouch wants.
#
# So the slot has to be switched on - and then immediately suspended by the plugin, so
# that VRIK detects the hand but neither draws from the slot nor puts anything into it.
#
# WHY A SEPARATE MOD AND NOT AN EDIT. Files inside somebody else's mod are not ours to
# change: an edit is invisible in MO2, is lost on reinstall and does not travel between
# profiles. The copy is taken WHOLE, because MO2 overrides files and not lines - a
# trimmed copy would silently reset every other setting to its default.
param(
    [int[]]$Slots = @(13),
    [ValidateSet('Small', 'Medium', 'Large', 'Ranged', 'Shield', 'Torch')]
    [string]$Type = 'Small',
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$cfg  = Get-Content -LiteralPath (Join-Path $root 'config\build.json') -Raw | ConvertFrom-Json
$d    = $cfg.deploy
$enc  = New-Object Text.UTF8Encoding($false)

function Expand-Path([string]$p) { $p.Replace('{root}', $root) }

$game = @(Get-Process -Name SkyrimVR,SkyrimSE -ErrorAction SilentlyContinue)
if ($game.Count) { throw "The game is running ($($game.Name -join ', ')) - the make-up of the build must not be changed" }

$token = (Get-Content -LiteralPath (Expand-Path $d.bridgeToken) -Raw).Trim()
$rel   = 'SKSE/Plugins/vrikslots.ini'

$modName = "$($d.modName) - VRIK Slots"

# The copy is taken from whichever mod would win the file IF WE WERE NOT THERE - asking
# MO2 for every provider in order and skipping our own overlay. Copying the winner
# outright looked simpler and was wrong: on the second run the overlay would find itself
# at the top and copy its own output, freezing the build's VRIK settings at whatever they
# were the first time and quietly ignoring any later change to them.
$providers = Invoke-RestMethod "$($d.bridgeUrl)/origins?path=$([uri]::EscapeDataString($rel))" `
                 -Headers @{ 'X-Token' = $token } -TimeoutSec 30

# The order MO2 lists providers in is not the order in which they win - taking the first
# one gave the base VRIK mod and would have thrown away every setting the build's own
# config mod had changed. Winning is decided by priority: the higher number sits lower in
# the MO2 window and overrides the rest. So each provider is asked for its priority and
# the highest one that is not us is the file we copy.
$owner = @($providers.origins |
           Where-Object { $_ -ne $modName } |
           ForEach-Object {
               $info = Invoke-RestMethod "$($d.bridgeUrl)/mod?name=$([uri]::EscapeDataString($_))" `
                           -Headers @{ 'X-Token' = $token } -TimeoutSec 30
               [pscustomobject]@{ Name = $_; Priority = [int]$info.priority }
           } |
           Sort-Object Priority -Descending |
           Select-Object -First 1).Name
if (-not $owner) {
    throw "nobody but us serves $rel - is VRIK installed and enabled?"
}
$source = Join-Path $d.modsRoot (Join-Path $owner ($rel -replace '/', '\'))
if (-not (Test-Path -LiteralPath $source)) {
    throw "the provider MO2 named has no such file: $source"
}
"source: $owner"

$lines = [IO.File]::ReadAllLines($source)
$changed = @()

foreach ($slot in $Slots) {
    if ($slot -lt 1 -or $slot -gt 14) { throw "slot out of range: $slot (VRIK has 1..14)" }

    # One allowed weapon type is all it takes for VRIK to consider the slot alive; the
    # plugin suspends it straight afterwards, so nothing is ever actually holstered there.
    # visible is turned on as well, so that VRIK has somewhere to draw what is in it.
    $wanted = @{
        "allow${Type}Slot$slot" = '1'
        "visibleSlot$slot"      = '1'
        "handSlot$slot"         = '0'   # either hand
    }

    for ($i = 0; $i -lt $lines.Count; $i++) {
        foreach ($key in @($wanted.Keys)) {
            if ($lines[$i] -match "^\s*$key\s*=") {
                $was = ($lines[$i] -split '=', 2)[1].Trim()
                if ($was -ne $wanted[$key]) {
                    $lines[$i] = "$key = $($wanted[$key])"
                    $changed += "  slot {0}: {1} {2} -> {3}" -f $slot, $key, $was, $wanted[$key]
                }
                $wanted.Remove($key)
            }
        }
    }
    foreach ($key in $wanted.Keys) { throw "key not found in $rel : $key" }
}

if (-not $changed) { '  nothing to change - the slots are already on' } else { $changed }

$dist = Join-Path $root 'dist-slots'
Remove-Item -LiteralPath $dist -Recurse -Force -ErrorAction SilentlyContinue
$target = Join-Path (Join-Path $dist $modName) 'SKSE\Plugins'
New-Item -ItemType Directory -Force $target | Out-Null
[IO.File]::WriteAllLines((Join-Path $target 'vrikslots.ini'), $lines, $enc)

$archive = Join-Path $d.downloadsRoot ("{0}-{1}.7z" -f $modName, $d.version)
"mod:     $modName"
"archive: $archive"
if (-not $Apply) { ''; 'dry run - add -Apply'; return }

Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
Push-Location (Join-Path $dist $modName)
try {
    & $d.sevenZip a -t7z -mx=5 -bso0 -bsp0 $archive '*' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "7-Zip returned $LASTEXITCODE" }
} finally { Pop-Location }

$meta = @(
    '[General]'
    'gameName=SkyrimSE'
    'modID=0'
    'fileID=0'
    "name=$modName"
    "modName=$modName"
    "version=$($d.version).0"
    'newestVersion='
    'fileCategory=1'
    'repository='
    'installed=true'
    'uninstalled=false'
    'paused=false'
    'removed=false'
)
[IO.File]::WriteAllLines("$archive.meta", $meta, $enc)

$body = @{ archive = $archive; name = $modName; paths = @(''); mode = 'merge' } | ConvertTo-Json -Compress
$res = Invoke-RestMethod "$($d.bridgeUrl)/install" -Method Post `
           -Body ([Text.Encoding]::UTF8.GetBytes($body)) `
           -ContentType 'application/json; charset=utf-8' `
           -Headers @{ 'X-Token' = $token } -TimeoutSec 600
if ($res.error) { throw "the bridge refused to install ${modName}: $($res.error)" }
'  installed through MO2: {0} ({1}, {2} files, {3} overwritten)' -f $modName, $res.mode, $res.addedCount, $res.overwrittenCount

$on = Invoke-RestMethod "$($d.bridgeUrl)/toggle" -Method Post `
          -Body ([Text.Encoding]::UTF8.GetBytes((@{ mod = $modName; active = $true } | ConvertTo-Json -Compress))) `
          -ContentType 'application/json; charset=utf-8' `
          -Headers @{ 'X-Token' = $token } -TimeoutSec 60
if ($on.error) { throw "the bridge refused to enable ${modName}: $($on.error)" }
'  enabled in the current profile'

Invoke-RestMethod "$($d.bridgeUrl)/refresh" -Method Post -Headers @{ 'X-Token' = $token } -TimeoutSec 20 | Out-Null

# The overlay is worth nothing unless it WINS the file, and a newly installed mod lands
# at the bottom of the MO2 window, which is where winning happens. So nothing is moved
# here: the priority route sits behind the bridge's irreversible-operation lock for good
# reason, and reordering somebody's build to save a check is not worth the key.
#
# What is done instead is the only honest proof - ask MO2 who serves the file now.
#
# Asked once, straight after the refresh, the answer is still the old one: MO2 rebuilds
# its virtual tree on its own schedule and the first reply named the mod we had just
# overridden. So the question is repeated until the tree has caught up, and only a
# silence that outlasts that is worth a warning.
$after = $null
foreach ($try in 1..6) {
    $after = Invoke-RestMethod "$($d.bridgeUrl)/resolve?path=$([uri]::EscapeDataString($rel))" `
                 -Headers @{ 'X-Token' = $token } -TimeoutSec 30
    if ($after.real -like "*$modName*") { break }
    Start-Sleep -Seconds 1
}
"  $rel is now served by: $($after.real)"
if ($after.real -notlike "*$modName*") {
    Write-Warning ("The overlay does NOT win the file. Move '{0}' below '{1}' in the MO2 window by hand." -f `
        $modName, $owner)
}

& $d.indexScript -Owner $d.indexOwner -Mods $modName -Note "$modName installed: VRIK slots $($Slots -join ',') switched on"
