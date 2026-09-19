
# Packing the mod into an archive and installing from it, like any other mod.
# Every path is in config/build.json.
#
#   tools\package.ps1           show what would be done
#   tools\package.ps1 -Apply    pack, put into downloads and install
#
# WHY AN ARCHIVE AND NOT A COPY INTO mods\. A mod that appears in mods\ by itself is
# a mod MO2 never installed: no source archive, no entry in its own database, nothing
# to reinstall or remove by the usual means. Ours goes in the same way everybody
# else's does - an archive in the downloads folder, and MO2 installs it through the
# bridge.
param([switch]$Apply)
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$cfg  = Get-Content -LiteralPath (Join-Path $root 'config\build.json') -Raw | ConvertFrom-Json
$d    = $cfg.deploy
$enc  = New-Object Text.UTF8Encoding($false)

function Expand-Path([string]$p) { $p.Replace('{root}', $root) }

$game = @(Get-Process -Name SkyrimVR,SkyrimSE -ErrorAction SilentlyContinue)
if ($game.Count) { throw "The game is running ($($game.Name -join ', ')) - the make-up of the build must not be changed" }
if (-not (Test-Path -LiteralPath $d.sevenZip)) { throw "7-Zip not found: $($d.sevenZip)" }

# dist is built by the staging script: one logic for both paths.
& (Join-Path $PSScriptRoot 'stage.ps1') | Out-Null

$dist = Join-Path $root 'dist'
$mods = @(Get-ChildItem -LiteralPath $dist -Directory)
if (-not $mods) { throw "dist is empty - build the plugin first" }

$plan = foreach ($m in $mods) {
    [pscustomobject]@{
        Name    = $m.Name
        Source  = $m.FullName
        Archive = Join-Path $d.downloadsRoot ("{0}-{1}.7z" -f $m.Name, $d.version)
        Files   = @(Get-ChildItem -LiteralPath $m.FullName -Recurse -File).Count
    }
}

'--- plan ---'
foreach ($p in $plan) { '  {0,-30} {1} files -> {2}' -f $p.Name, $p.Files, (Split-Path -Leaf $p.Archive) }
if (-not $Apply) { ''; 'dry run - add -Apply'; return }

$bridgeToken = Expand-Path $d.bridgeToken
$token = (Get-Content -LiteralPath $bridgeToken -Raw).Trim()

''
foreach ($p in $plan) {
    Remove-Item -LiteralPath $p.Archive -Force -ErrorAction SilentlyContinue
    Push-Location $p.Source
    try {
        & $d.sevenZip a -t7z -mx=5 -bso0 -bsp0 $p.Archive '*' | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "7-Zip returned $LASTEXITCODE" }
    } finally { Pop-Location }

    # The .meta beside the archive is what MO2 reads to show where a download came
    # from. Ours came from nowhere, and saying so plainly is better than leaving the
    # fields to be guessed at.
    $meta = @(
        '[General]'
        'gameName=SkyrimSE'
        'modID=0'
        'fileID=0'
        "name=$($p.Name)"
        "modName=$($p.Name)"
        "version=$($d.version).0"
        'newestVersion='
        'fileCategory=1'
        'repository='
        'installed=true'
        'uninstalled=false'
        'paused=false'
        'removed=false'
    )
    [IO.File]::WriteAllLines("$($p.Archive).meta", $meta, $enc)
    '  archive: {0} ({1:N0} b)' -f (Split-Path -Leaf $p.Archive), (Get-Item $p.Archive).Length

    # MO2 installs it, not us. The /install route of the bridge creates the mod through
    # createMod and unpacks the archive itself - without a single dialogue. Unpacking
    # past MO2 would give a mod it had never created.
    #
    # merge, not replace: replace sends the previous contents to the Recycle Bin and the
    # bridge rightly asks for a confirmation key before doing that. Ours is one DLL laid
    # over the same one DLL, so there is nothing to lose by merging - and a mod folder
    # that is not there yet needs no mode at all.
    $body = @{ archive = $p.Archive; name = $p.Name; paths = @(''); mode = 'merge' } |
            ConvertTo-Json -Compress
    $res = Invoke-RestMethod "$($d.bridgeUrl)/install" -Method Post `
        -Body ([Text.Encoding]::UTF8.GetBytes($body)) `
        -ContentType 'application/json; charset=utf-8' `
        -Headers @{ 'X-Token' = $token } -TimeoutSec 600

    # The answer is printed rather than swallowed. A refusal comes back as an ordinary
    # answer with an error in it, and a script that hides it reports an install that
    # never happened - which is exactly what this one did once.
    if ($res.error) { throw "the bridge refused to install $($p.Name): $($res.error)" }
    '  installed through MO2: {0} ({1}, {2} files, {3} overwritten)' -f `
        $p.Name, $res.mode, $res.addedCount, $res.overwrittenCount
}

# An MO2 that is already open will not see the new mod until it rereads its list.
try {
    Invoke-RestMethod "$($d.bridgeUrl)/refresh" -Method Post -Headers @{ 'X-Token' = $token } -TimeoutSec 20 | Out-Null
    '  MO2 refreshed its list of mods'
} catch {
    "  the bridge did not answer, refresh the list in MO2 by hand: $($_.Exception.Message)"
}

& $d.indexScript -Owner $d.indexOwner -Mods $plan.Name -Note "$($d.modName) $($d.version) installed from an archive"
