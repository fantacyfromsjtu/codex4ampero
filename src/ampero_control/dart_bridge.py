import json
import os
import queue
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional

from .constants import DEVICE_NAME, MessageFlag
from .errors import (
    DeviceBusyError,
    DeviceTimeoutError,
    NativeLibraryError,
)
from .installation import EditorInstallation
from .native import official_editor_is_running
from .protocol import ReceivedMessage


class DartBridgeTransport:
    def __init__(self, installation: EditorInstallation):
        self.installation = installation
        self.project_root = Path(__file__).resolve().parents[2]
        self.bridge_root = self.project_root / "bridge"
        self.bridge_script = self.bridge_root / "bin" / "ampero_bridge.dart"
        self.bridge_executable = self.project_root / ".tools" / "ampero_bridge.exe"
        self.dart_executable = (
            None if self.bridge_executable.is_file() else self._locate_dart()
        )
        self._process: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._ready: "queue.Queue[dict]" = queue.Queue()
        self._responses: dict[int, "queue.Queue[dict]"] = {}
        self._responses_lock = threading.Lock()
        self._request_id = 0
        self._scan: Optional[dict] = None
        self._logs: list[str] = []

    def _locate_dart(self) -> Path:
        configured = os.environ.get("AMPERO_DART_EXE")
        candidates = [
            Path(configured) if configured else None,
            self.project_root / ".tools" / "dart-sdk" / "bin" / "dart.exe",
        ]
        system_dart = shutil.which("dart")
        if system_dart:
            candidates.append(Path(system_dart))
        for candidate in candidates:
            if candidate and candidate.is_file():
                return candidate.resolve()
        raise NativeLibraryError(
            "Dart SDK was not found. Set AMPERO_DART_EXE or install the project SDK "
            f"under {self.project_root / '.tools' / 'dart-sdk'}."
        )

    def scan(self, device_name: str = DEVICE_NAME) -> dict:
        if device_name != DEVICE_NAME:
            raise NativeLibraryError(f"unsupported device name: {device_name}")
        self._ensure_started()
        assert self._scan is not None
        return {
            "device_name": DEVICE_NAME,
            "input_indices": list(self._scan.get("inputs", [])),
            "output_indices": list(self._scan.get("outputs", [])),
        }

    def connect(
        self,
        input_index: Optional[int] = None,
        output_index: Optional[int] = None,
        *,
        device_name: str = DEVICE_NAME,
        allow_editor_running: bool = False,
    ) -> None:
        if not allow_editor_running and official_editor_is_running():
            raise DeviceBusyError(
                "Ampero II.exe is running. Close the official editor before connecting."
            )
        scan = self.scan(device_name)
        if input_index is not None and input_index not in scan["input_indices"]:
            raise NativeLibraryError(f"input MIDI index is unavailable: {input_index}")
        if output_index is not None and output_index not in scan["output_indices"]:
            raise NativeLibraryError(f"output MIDI index is unavailable: {output_index}")

    def request(
        self, address: int, data: bytes = b"", timeout: float = 2.0
    ) -> ReceivedMessage:
        response = self._call(
            {
                "op": "request",
                "address": int(address),
                "data_hex": data.hex(),
                "timeout_ms": max(100, int(timeout * 1000)),
            },
            timeout=timeout + 2.0,
        )
        return ReceivedMessage(
            address=int(response["address"]),
            data=bytes(int(value) for value in response.get("data", [])),
            flag=int(response["flag"]),
            received_at=0.0,
        )

    def send(self, address: int, data: bytes, flag: MessageFlag) -> int:
        response = self._call(
            {
                "op": "send",
                "address": int(address),
                "data_hex": data.hex(),
                "flag": int(flag),
            },
            timeout=3.0,
        )
        return int(response["message_id"])

    def send_and_wait(
        self,
        address: int,
        response_address: int,
        data: bytes,
        flag: MessageFlag,
        timeout: float = 3.0,
    ) -> tuple[int, ReceivedMessage]:
        response = self._call(
            {
                "op": "send_and_wait",
                "address": int(address),
                "response_address": int(response_address),
                "data_hex": data.hex(),
                "flag": int(flag),
                "timeout_ms": max(1, int(timeout * 1000)),
            },
            timeout=timeout + 1.0,
        )
        return int(response["message_id"]), ReceivedMessage(
            address=int(response["address"]),
            data=bytes(int(value) for value in response.get("data", [])),
            flag=int(response["flag"]),
            received_at=0.0,
        )

    def diagnostics_trace(self) -> dict:
        response = self._call({"op": "diagnostics"}, timeout=3.0)
        return dict(response.get("trace", {}))

    def _ensure_started(self) -> None:
        if self._process and self._process.poll() is None:
            return
        if official_editor_is_running():
            raise DeviceBusyError(
                "Ampero II.exe is running. Close the official editor before connecting."
            )
        environment = os.environ.copy()
        environment["PATH"] = os.pathsep.join(
            (
                str(self.installation.root),
                str(self.installation.native_library.parent),
                environment.get("PATH", ""),
            )
        )
        if self.bridge_executable.is_file():
            command = [
                str(self.bridge_executable),
                "serve",
                str(self.installation.native_library),
            ]
        else:
            command = [
                str(self.dart_executable),
                "run",
                str(self.bridge_script),
                "serve",
                str(self.installation.native_library),
            ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._process = subprocess.Popen(
            command,
            cwd=str(self.bridge_root),
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
        )
        self._reader_thread = threading.Thread(target=self._read_output, daemon=True)
        self._reader_thread.start()
        try:
            ready = self._ready.get(timeout=10.0)
        except queue.Empty as error:
            self._terminate()
            raise DeviceTimeoutError("Dart bridge did not become ready within 10 seconds") from error
        if not ready.get("ok"):
            self._terminate()
            raise NativeLibraryError(str(ready.get("error", "Dart bridge startup failed")))
        self._scan = ready.get("scan", {})

    def _call(self, request: dict, *, timeout: float) -> dict:
        self._ensure_started()
        assert self._process is not None and self._process.stdin is not None
        with self._responses_lock:
            self._request_id += 1
            request_id = self._request_id
            response_queue: "queue.Queue[dict]" = queue.Queue(maxsize=1)
            self._responses[request_id] = response_queue
        request = {"id": request_id, **request}
        try:
            self._process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            self._process.stdin.flush()
            try:
                response = response_queue.get(timeout=timeout)
            except queue.Empty as error:
                self._terminate()
                raise DeviceTimeoutError(
                    f"Dart bridge operation timed out after {timeout:g} seconds"
                ) from error
            if not response.get("ok"):
                message = str(response.get("error", "Dart bridge operation failed"))
                if "TimeoutException" in message:
                    raise DeviceTimeoutError(message)
                raise NativeLibraryError(message)
            return response
        finally:
            with self._responses_lock:
                self._responses.pop(request_id, None)

    def _read_output(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        for line in self._process.stdout:
            line = line.rstrip("\r\n")
            if line.startswith("AMPERO_READY:"):
                self._ready.put(json.loads(line.split(":", 1)[1]))
                continue
            if line.startswith("AMPERO_RESPONSE:"):
                response = json.loads(line.split(":", 1)[1])
                request_id = response.get("id")
                with self._responses_lock:
                    response_queue = self._responses.get(request_id)
                if response_queue:
                    response_queue.put(response)
                continue
            if line:
                self._logs.append(line)
        failure = {
            "ok": False,
            "error": (
                f"Dart bridge exited with code {self._process.poll()}; "
                f"logs: {' | '.join(self._logs[-8:])}"
            ),
        }
        self._ready.put(failure)
        with self._responses_lock:
            pending = list(self._responses.values())
        for response_queue in pending:
            if response_queue.empty():
                response_queue.put(failure)

    def close(self) -> None:
        if not self._process:
            return
        if self._process.poll() is None:
            try:
                self._call({"op": "close"}, timeout=2.0)
            except Exception:
                pass
        self._terminate()

    def _terminate(self) -> None:
        process = self._process
        if process and process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                pass
        self._process = None

    def __enter__(self) -> "DartBridgeTransport":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    @property
    def diagnostics(self) -> dict:
        return {
            "runtime": (
                "compiled_executable"
                if self.bridge_executable.is_file()
                else "dart_sdk"
            ),
            "bridge_executable": str(self.bridge_executable),
            "dart_executable": (
                str(self.dart_executable) if self.dart_executable else None
            ),
            "bridge_script": str(self.bridge_script),
            "bridge_available": (
                self.bridge_executable.is_file() or self.bridge_script.is_file()
            ),
        }
