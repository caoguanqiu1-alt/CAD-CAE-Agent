param([string]$InstallDir = 'D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS')
$ErrorActionPreference = 'Stop'
$outDir = Join-Path $PSScriptRoot '..\local_state\simulation\bin'
New-Item -ItemType Directory -Force $outDir | Out-Null
$redist = Join-Path $InstallDir 'api\redist'
$refs = @('sldworks','swconst','cosworks') | ForEach-Object { Join-Path $redist ('SolidWorks.Interop.' + $_ + '.dll') }
foreach ($ref in $refs) { if (!(Test-Path -LiteralPath $ref)) { throw "INTEROP_MISSING: $ref" } }
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$argsList = @('/nologo','/target:exe','/platform:x64',('/out:' + (Join-Path $outDir 'SimulationBridge.exe')), '/r:System.Web.Extensions.dll')
$argsList += $refs | ForEach-Object { '/r:' + $_ }
$argsList += Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.cs' | Select-Object -ExpandProperty FullName
& $compiler $argsList
if ($LASTEXITCODE -ne 0) { throw 'Bridge compilation failed' }
foreach ($ref in $refs) { Copy-Item -LiteralPath $ref -Destination $outDir -Force }
Write-Output (Join-Path $outDir 'SimulationBridge.exe')
