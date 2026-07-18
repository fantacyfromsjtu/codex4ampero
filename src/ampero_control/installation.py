import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from .errors import InstallationNotFoundError


@dataclass(frozen=True)
class EditorInstallation:
    root: Path
    executable: Path
    native_library: Path
    catalog_directory: Path


def _candidate_roots() -> Iterator[Path]:
    configured = os.environ.get("AMPERO_EDITOR_DIR")
    if configured:
        yield Path(configured)

    yield Path(r"D:\Ampero II")
    yield Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Ampero II"
    yield Path(os.environ.get("LOCALAPPDATA", "")) / "Ampero II"

    if os.name != "nt":
        return

    try:
        import winreg
    except ImportError:
        return

    registry_roots = (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ),
    )
    for hive, key_path in registry_roots:
        try:
            with winreg.OpenKey(hive, key_path) as parent:
                count = winreg.QueryInfoKey(parent)[0]
                for index in range(count):
                    try:
                        subkey_name = winreg.EnumKey(parent, index)
                        with winreg.OpenKey(parent, subkey_name) as subkey:
                            name = _registry_value(subkey, "DisplayName") or ""
                            if "ampero ii" not in name.lower():
                                continue
                            location = _registry_value(subkey, "InstallLocation")
                            if location:
                                yield Path(location)
                            icon = _registry_value(subkey, "DisplayIcon")
                            if icon:
                                icon_path = re.sub(r",\d+$", "", icon.strip('"'))
                                yield Path(icon_path).parent
                    except OSError:
                        continue
        except OSError:
            continue


def _registry_value(key, name: str) -> Optional[str]:
    try:
        return str(__import__("winreg").QueryValueEx(key, name)[0])
    except OSError:
        return None


def locate_editor(explicit_root: Optional[Path] = None) -> EditorInstallation:
    candidates = [explicit_root] if explicit_root else list(_candidate_roots())
    seen = set()
    for candidate in candidates:
        if candidate is None:
            continue
        root = candidate.expanduser()
        key = str(root).casefold()
        if key in seen:
            continue
        seen.add(key)
        executable = root / "Ampero II.exe"
        native_library = root / "assets" / "HTUSBTools.dll"
        catalog_directory = root / "data" / "flutter_assets" / "assets" / "data"
        if executable.is_file() and native_library.is_file() and catalog_directory.is_dir():
            return EditorInstallation(
                root=root.resolve(),
                executable=executable.resolve(),
                native_library=native_library.resolve(),
                catalog_directory=catalog_directory.resolve(),
            )
    searched = ", ".join(str(path) for path in candidates if path)
    raise InstallationNotFoundError(
        "Ampero II editor installation was not found. "
        "Set AMPERO_EDITOR_DIR or pass --editor-dir. "
        f"Searched: {searched}"
    )
