# Development

## Requirements

- Windows x64
- Python 3.9 or newer, x64
- Official Ampero II editor installed
- Dart SDK when rebuilding the bridge
- Ampero II Stomp connected by USB for hardware tests

## Python Commands

Prefer the Skill wrapper for hardware operations because it adds a worker-process
watchdog:

```powershell
$python = if ($env:AMPERO_PYTHON) {
    $env:AMPERO_PYTHON
} else {
    (Get-Command python).Source
}

& $python .\skills\ampero-tone\scripts\ampero.py --json doctor --scan
& $python .\skills\ampero-tone\scripts\ampero.py --json device snapshot --include-parameters
& $python .\skills\ampero-tone\scripts\ampero.py --json device routing --timeout 5
& $python .\skills\ampero-tone\scripts\ampero.py --json catalog search "clean" --category AMP
& $python .\skills\ampero-tone\scripts\ampero.py --json plan preview .\examples\clear-rhythm.plan.json
& $python .\skills\ampero-tone\scripts\ampero.py --json plan save .\.ampero_journals\APPLY.journal.json --name "My Preset"
```

## Tests

```powershell
.\scripts\test.ps1
```

Override Python discovery when necessary:

```powershell
$env:AMPERO_PYTHON = "C:\Path\To\python.exe"
.\scripts\test.ps1
```

## Dart Bridge

The build script first checks `.tools/dart-sdk/bin/dart.exe`, then `dart.exe` on
`PATH`. A different SDK can be supplied explicitly:

```powershell
.\scripts\build-bridge.ps1 -DartExe C:\Path\To\dart.exe
```

The generated `.tools/ampero_bridge.exe`, Dart SDK, package cache, journals, and
vendor binaries are ignored by Git.

## Skill Installation

Install or refresh the Skill after tests pass:

```powershell
.\scripts\install-skill.ps1 -Force
```

Restart Codex after installation. Do not commit generated journals, bridge
binaries, the official algorithm catalog, or `HTUSBTools.dll`.
