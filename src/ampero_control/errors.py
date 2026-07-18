class AmperoError(Exception):
    """Base exception for expected application errors."""


class InstallationNotFoundError(AmperoError):
    """Raised when the official editor installation cannot be located."""


class NativeLibraryError(AmperoError):
    """Raised when the vendor communication library cannot be used."""


class DeviceNotFoundError(AmperoError):
    """Raised when no matching MIDI input/output pair is available."""


class DeviceBusyError(AmperoError):
    """Raised when the official editor may already own the device ports."""


class DeviceTimeoutError(AmperoError):
    """Raised when a device response does not arrive before the timeout."""


class DeviceWriteVerificationError(AmperoError):
    """Raised when a write cannot be confirmed by an immediate device readback."""


class PatchLocationUnknownError(AmperoError):
    """Raised when the device explicitly reports an unknown current patch index."""


class PlanValidationError(AmperoError):
    """Raised when a requested change is outside the supported safe subset."""


class PresetFormatError(AmperoError):
    """Raised when a current-preset payload is malformed or incomplete."""
