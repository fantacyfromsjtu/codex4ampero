import ctypes
import os
import platform
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from .constants import DEVICE_NAME, MessageFlag
from .errors import NativeLibraryError
from .installation import EditorInstallation
from .protocol import ReceivedMessage


ScanCallback = ctypes.CFUNCTYPE(
    None, ctypes.POINTER(ctypes.c_int32), ctypes.c_int32
)
ReceiveCallback = ctypes.CFUNCTYPE(
    None,
    ctypes.c_void_p,
    ctypes.c_uint32,
    ctypes.c_void_p,
    ctypes.c_uint32,
    ctypes.c_int32,
)
StateCallback = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int32)
SendCallback = ctypes.CFUNCTYPE(
    None, ctypes.c_void_p, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32
)


def official_editor_is_running() -> bool:
    if os.name != "nt":
        return False
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq Ampero II.exe", "/FO", "CSV", "/NH"],
        check=False,
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return "Ampero II.exe" in result.stdout


class NativeTransport:
    def __init__(self, installation: EditorInstallation):
        if os.name != "nt":
            raise NativeLibraryError("the vendor communication library requires Windows")
        if ctypes.sizeof(ctypes.c_void_p) != 8:
            raise NativeLibraryError("a 64-bit Python interpreter is required")
        self.installation = installation
        self._dll_directories = []
        if hasattr(os, "add_dll_directory"):
            self._dll_directories.append(os.add_dll_directory(str(installation.root)))
            self._dll_directories.append(
                os.add_dll_directory(str(installation.native_library.parent))
            )
        try:
            self._library = ctypes.CDLL(str(installation.native_library))
        except OSError as error:
            raise NativeLibraryError(f"failed to load {installation.native_library}: {error}")
        self._configure_functions()
        self._device = None
        self._messages: "queue.Queue[ReceivedMessage]" = queue.Queue()
        self._send_events: "queue.Queue[tuple[int, int, int]]" = queue.Queue()
        self._state_events: "queue.Queue[int]" = queue.Queue()
        self._callback_lock = threading.Lock()
        self._scan_callbacks = []
        self._receive_callback = ReceiveCallback(self._on_receive)
        self._state_callback = StateCallback(self._on_state)
        self._send_callback = SendCallback(self._on_send)

    def _configure_functions(self) -> None:
        self._library.scanInDevice.argtypes = [ctypes.c_char_p, ScanCallback]
        self._library.scanInDevice.restype = None
        self._library.scanOutDevice.argtypes = [ctypes.c_char_p, ScanCallback]
        self._library.scanOutDevice.restype = None
        self._library.connectDevice.argtypes = [
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_char_p,
            ReceiveCallback,
            StateCallback,
            SendCallback,
        ]
        self._library.connectDevice.restype = ctypes.c_void_p
        self._library.disConnectDevice.argtypes = [ctypes.c_void_p]
        self._library.disConnectDevice.restype = None
        self._library.sendMidiMessage.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int32,
            ctypes.c_void_p,
            ctypes.c_int32,
            ctypes.c_int32,
        ]
        self._library.sendMidiMessage.restype = ctypes.c_int32
        self._library.timerCallback.argtypes = [ctypes.c_void_p, ctypes.c_int32]
        self._library.timerCallback.restype = None

    def scan(self, device_name: str = DEVICE_NAME) -> dict:
        return {
            "device_name": device_name,
            "input_indices": self._scan_function("scanInDevice", device_name),
            "output_indices": self._scan_function("scanOutDevice", device_name),
        }

    def _scan_function(self, function_name: str, device_name: str) -> list[int]:
        completed = threading.Event()
        values = []

        def callback(pointer, size):
            with self._callback_lock:
                values.extend(pointer[index] for index in range(size) if pointer)
            completed.set()

        native_callback = ScanCallback(callback)
        self._scan_callbacks.append(native_callback)
        getattr(self._library, function_name)(device_name.encode("utf-8"), native_callback)
        completed.wait(0.75)
        return values

    def connect(
        self,
        input_index: Optional[int] = None,
        output_index: Optional[int] = None,
        *,
        device_name: str = DEVICE_NAME,
        allow_editor_running: bool = False,
    ) -> None:
        raise NativeLibraryError(
            "direct Python device connections are unsupported because the vendor DLL "
            "delivers responses through a Dart NativePort; use DartBridgeTransport"
        )

    def send(self, address: int, data: bytes, flag: MessageFlag) -> int:
        raise NativeLibraryError(
            "direct Python sends are unsupported; use DartBridgeTransport"
        )

    def request(self, address: int, data: bytes = b"", timeout: float = 2.0) -> ReceivedMessage:
        raise NativeLibraryError(
            "direct Python requests are unsupported; use DartBridgeTransport"
        )

    def close(self) -> None:
        if self._device:
            self._library.disConnectDevice(self._device)
            self._device = None

    def _on_receive(self, device, address, data, data_size, flag) -> None:
        payload = ctypes.string_at(data, data_size) if data and data_size else b""
        self._messages.put(
            ReceivedMessage(
                address=int(address),
                data=payload,
                flag=int(flag),
                received_at=time.time(),
            )
        )

    def _on_state(self, device, event) -> None:
        self._state_events.put(int(event))

    def _on_send(self, device, message_id, event, address) -> None:
        self._send_events.put((int(message_id), int(event), int(address)))

    def _pump_once(self) -> None:
        self._library.timerCallback(None, 9)
        if self._device:
            self._library.timerCallback(self._device, 0)

    def __enter__(self) -> "NativeTransport":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    @property
    def diagnostics(self) -> dict:
        return {
            "python_architecture": platform.architecture()[0],
            "library": str(self.installation.native_library),
            "library_loaded": True,
            "official_editor_running": official_editor_is_running(),
        }
