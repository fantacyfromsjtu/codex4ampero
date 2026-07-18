param(
    [string]$DartExe
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$bridgeRoot = Join-Path $projectRoot "bridge"
$output = Join-Path $projectRoot ".tools\ampero_bridge.exe"

if (-not $DartExe) {
    $DartExe = Join-Path $projectRoot ".tools\dart-sdk\bin\dart.exe"
}

if (-not (Test-Path $DartExe)) {
    throw "Dart SDK not found at $DartExe"
}

Push-Location $bridgeRoot
try {
    & $DartExe pub get
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $DartExe analyze
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $DartExe compile exe "bin\ampero_bridge.dart" -o $output
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}

Write-Output "Built $output"
