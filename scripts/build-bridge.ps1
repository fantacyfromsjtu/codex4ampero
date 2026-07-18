param(
    [string]$DartExe
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$bridgeRoot = Join-Path $projectRoot "bridge"
$output = Join-Path $projectRoot ".tools\ampero_bridge.exe"

if (-not $DartExe) {
    $localDart = Join-Path $projectRoot ".tools\dart-sdk\bin\dart.exe"
    if (Test-Path $localDart) {
        $DartExe = $localDart
    } else {
        $pathDart = Get-Command dart -ErrorAction SilentlyContinue
        if ($pathDart) {
            $DartExe = $pathDart.Source
        }
    }
}

if (-not $DartExe -or -not (Test-Path $DartExe)) {
    throw "Dart SDK not found. Install Dart, add dart.exe to PATH, or pass -DartExe."
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
