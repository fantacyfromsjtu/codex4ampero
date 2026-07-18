param(
    [string]$CodexHome = "$HOME\.codex",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$source = Join-Path $projectRoot "skills\ampero-tone"
$destinationRoot = Join-Path $CodexHome "skills"
$destination = Join-Path $destinationRoot "ampero-tone"

if (Test-Path $destination) {
    if (-not $Force) {
        throw "Skill already exists at $destination. Re-run with -Force to replace it."
    }
    Remove-Item -LiteralPath $destination -Recurse -Force
}

New-Item -ItemType Directory -Path $destinationRoot -Force | Out-Null
Copy-Item -LiteralPath $source -Destination $destination -Recurse

[Environment]::SetEnvironmentVariable("VIBE_AMPERO_ROOT", $projectRoot, "User")
Write-Output "Installed ampero-tone skill to $destination"
Write-Output "Set user environment variable VIBE_AMPERO_ROOT=$projectRoot"
Write-Output "Restart Codex before using the skill."
