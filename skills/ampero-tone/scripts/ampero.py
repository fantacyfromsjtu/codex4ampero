#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    configured = os.environ.get("VIBE_AMPERO_ROOT")
    if configured:
        return Path(configured)
    local_root = Path(__file__).resolve().parents[3]
    if (local_root / "src" / "ampero_control").is_dir():
        return local_root
    return Path(r"E:\vibe_ampere")


def _timeout_seconds(arguments) -> float:
    if "doctor" in arguments and "--scan" in arguments:
        return 10.0
    if "device" in arguments and "scan" in arguments:
        return 10.0
    if "device" in arguments and "snapshot" in arguments:
        return 30.0
    return 30.0


def _run_with_watchdog(arguments) -> int:
    root = _project_root()
    environment = os.environ.copy()
    current_pythonpath = environment.get("PYTHONPATH")
    source_path = str(root / "src")
    environment["PYTHONPATH"] = (
        source_path + os.pathsep + current_pythonpath
        if current_pythonpath
        else source_path
    )
    command = [sys.executable, "-m", "ampero_control", *arguments]
    timeout = _timeout_seconds(arguments)
    try:
        result = subprocess.run(
            command,
            cwd=str(root),
            env=environment,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        partial_stdout = (error.stdout or b"").decode("utf-8", errors="replace")
        partial_stderr = (error.stderr or b"").decode("utf-8", errors="replace")
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "WatchdogTimeout",
                    "message": (
                        f"Ampero control worker exceeded {timeout:g} seconds and was "
                        "forcibly terminated. The vendor DLL did not return."
                    ),
                    "stdout": partial_stdout,
                    "stderr": partial_stderr,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 124
    if result.stdout:
        sys.stdout.buffer.write(result.stdout)
    if result.stderr:
        sys.stderr.buffer.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(_run_with_watchdog(sys.argv[1:]))
