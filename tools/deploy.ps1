# Раскладка Envoy в mods\. Все пути и имена - в config/build.json, в коде их нет.
#
#   tools\deploy.ps1            показать, что будет сделано
#   tools\deploy.ps1 -Apply     выполнить
#
# Состав профилей этот скрипт НЕ трогает: включение мода делается через мост MO2Bridge.
param([switch]$Apply, [switch]$NoIndex)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$cfg  = Get-Content -LiteralPath (Join-Path $root 'config\build.json') -Raw | ConvertFrom-Json
$d    = $cfg.deploy
$enc  = New-Object Text.UTF8Encoding($false)

$game = @(Get-Process -Name SkyrimVR,SkyrimSE -ErrorAction SilentlyContinue)
if ($game.Count) { throw "Игра запущена ($($game.Name -join ', ')) - раскладка запрещена" }

$pex = Join-Path $root 'build\pex'
if (-not (Test-Path -LiteralPath $pex)) { throw "Нет собранных скриптов. Сначала tools\build-papyrus.ps1" }

$dist = Join-Path $root 'dist'
Remove-Item -LiteralPath $dist -Recurse -Force -ErrorAction SilentlyContinue

function New-Mod([string]$name, [string[]]$scripts, [string]$esp, [string]$notes) {
    $mod = Join-Path $dist $name
    New-Item -ItemType Directory -Force (Join-Path $mod 'Scripts\Source') | Out-Null
    foreach ($s in $scripts) {
        Copy-Item -LiteralPath (Join-Path $pex "$s.pex")            -Destination (Join-Path $mod 'Scripts') -Force
        Copy-Item -LiteralPath (Join-Path $root "papyrus\$s.psc")   -Destination (Join-Path $mod 'Scripts\Source') -Force
    }
    Copy-Item -LiteralPath (Join-Path $root "esp\$esp") -Destination $mod -Force

    $dll = Join-Path $root 'build\Release\Envoy.dll'
    if ((Test-Path -LiteralPath $dll) -and $name -eq $d.modName) {
        New-Item -ItemType Directory -Force (Join-Path $mod 'SKSE\Plugins\envoy') | Out-Null
        Copy-Item -LiteralPath $dll -Destination (Join-Path $mod 'SKSE\Plugins') -Force
        Copy-Item -LiteralPath (Join-Path $root 'config\envoy.default.json') `
                  -Destination (Join-Path $mod 'SKSE\Plugins\envoy\envoy.json') -Force
    }

    $meta = @(
        '[General]'
        'gameName=SkyrimSE'
        'modid=0'
        "version=$($d.version)"
        "newestVersion=$($d.version)"
        'category="0,"'
        'installationFile='
        "notes=$notes"
        ''
        '[installedFiles]'
        'size=0'
    )
    [IO.File]::WriteAllLines((Join-Path $mod 'meta.ini'), $meta, $enc)
    return $mod
}

function New-AdapterMod {
    # Адаптер - такой же мод, как остальные: он несёт сам себя и конфиг,
    # описывающий, где лежит модель. Включается и выключается галочкой.
    $mod = Join-Path $dist $d.adapterModName
    $inner = Join-Path $mod $d.adapterTargetRel
    New-Item -ItemType Directory -Force $inner | Out-Null

    # Адаптер теперь плагин SKSE: рядом с настройками едет его библиотека.
    $src = $d.adapterSource.Replace('{root}', $root)
    Get-ChildItem -LiteralPath $src -File -Filter '*.json' |
        ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $inner -Force }

    $dll = $d.adapterDll.Replace('{root}', $root)
    if (Test-Path -LiteralPath $dll) {
        $plugins = Join-Path $mod 'SKSE\Plugins'
        New-Item -ItemType Directory -Force $plugins | Out-Null
        Copy-Item -LiteralPath $dll -Destination $plugins -Force
    } else {
        Write-Warning "библиотека адаптера не собрана: $dll"
    }

    $meta = @(
        '[General]'
        'gameName=SkyrimSE'
        'modid=0'
        "version=$($d.version)"
        "newestVersion=$($d.version)"
        'category="0,"'
        'installationFile='
        'notes=Адаптер Envoy к службе распознавания и синтеза речи. Знает обе стороны; мост о модели не знает.'
        ''
        '[installedFiles]'
        'size=0'
    )
    [IO.File]::WriteAllLines((Join-Path $mod 'meta.ini'), $meta, $enc)
    return $mod
}

$made = @()
$made += New-Mod $d.modName     @('Envoy','EnvoyQuest') 'Envoy.esp'     'Envoy Framework. Собран из Envoy Framework/, версия по config/build.json.'
$made += New-Mod $d.demoModName @('EnvoyDemoObserver','EnvoyDemoGreedy','EnvoyDemoShared') 'EnvoyDemo.esp' 'Демонстрационные подписчики Envoy: наблюдатель, жадный и делящийся. В рабочие профили не нужны.'
$made += New-AdapterMod

'--- будет разложено ---'
foreach ($m in $made) {
    $rel = $m.Substring($dist.Length + 1)
    $n = @(Get-ChildItem -LiteralPath $m -Recurse -File).Count
    '  {0,-40} {1} файлов' -f $rel, $n
}
if (-not $Apply) { ''; 'сухой прогон - добавь -Apply'; return }

foreach ($m in $made) {
    $name = Split-Path -Leaf $m
    $target = Join-Path $d.modsRoot $name
    New-Item -ItemType Directory -Force $target | Out-Null
    Copy-Item -LiteralPath (Join-Path $m '*') -Destination $target -Recurse -Force
    "  разложено: $name"
}

if (-not $NoIndex) {
    & $d.indexScript -Owner $d.indexOwner -Mods $d.modName, $d.demoModName -Note "Envoy Framework deploy $($d.version)"
}

''
'Мод разложен, но НЕ включён. Включение и порядок - через мост MO2Bridge.'




