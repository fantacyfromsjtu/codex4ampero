param(
    [string]$PythonExecutable = $env:AMPERO_PYTHON
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $projectRoot "src"

if (-not $PythonExecutable) {
    $localPython = Get-ChildItem `
        -Path (Join-Path $env:LOCALAPPDATA "Programs\Python\Python*\python.exe") `
        -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        Select-Object -First 1
    if ($localPython) {
        $PythonExecutable = $localPython.FullName
    } else {
        $pathPython = Get-Command python -ErrorAction SilentlyContinue
        if ($pathPython) {
            $PythonExecutable = $pathPython.Source
        }
    }
}

if (-not $PythonExecutable -or -not (Test-Path -LiteralPath $PythonExecutable)) {
    throw "Python 3.9+ was not found. Set AMPERO_PYTHON or pass -PythonExecutable."
}

& $PythonExecutable -B -m unittest discover -s (Join-Path $projectRoot "tests") -v
exit $LASTEXITCODE
