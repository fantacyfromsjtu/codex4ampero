# Protocol Compatibility Notes

These notes document the independently implemented compatibility subset used by
this project. They are not an official HOTONE API.

## Native Interface

The installed Windows editor provides `assets/HTUSBTools.dll`. The verified
subset uses these exports:

- `InitDartApiDL(NativeApi.initializeApiDLData)`
- `scanInDevice(name, callback)`
- `scanOutDevice(name, callback)`
- `connectDevice(inIndex, outIndex, productId, receive, state, send)`
- `registerSendPort(device, ReceivePort.nativePort)`
- `sendMidiMessage(device, address, data, dataSize, flag)`
- `timerCallback(device, mode)`
- `disConnectDevice(device)`

The Ampero II Stomp editor uses device name `Ampero II Stomp` and product
identifier `97`.

Input/output scanning is safe through Python `ctypes`. Connected response delivery
requires the Dart DL API and a real Dart NativePort, so requests and sends use the
compiled Dart bridge. The bridge pumps `timerCallback(nullptr, 9)` and
`timerCallback(device, 0)` approximately every 30 milliseconds.

## Message Flags

- Request: `0x11`
- Send: `0x12`
- Error: `0x13`
- Acknowledge: `0x14`
- Retry: `0x15`

## Supported Commands

| Address | Purpose | Payload |
| --- | --- | --- |
| `0x01000000` | Read complete current preset | empty request; response contains a preset identifier followed by TLV blocks |
| `0x01040002` | Set/read slot model | slot `int8`, category `int8`, model code `int32`, enabled `int8` |
| `0x01040003` | Set/read one parameter | slot `int16`, parameter ID `int16`, value `float32` |
| `0x01090004` | Set scene slot states | scene `int8`, then slot-state bytes |
| `0x01090005` | Set one scene's slot parameter array | scene `int16`, slot `int16`, then `float32[]` |
| `0x03000001` | Change/read current scene | scene `int8` for writes |

Integers and IEEE-754 floats are little-endian. Current code intentionally
excludes save, delete, firmware, bootloader, global I/O, and unknown command
addresses.

## Current-Preset Parsing

`device snapshot` first requests the current scene and then requests the complete
current preset. The preset response is parsed as a four-byte identifier followed
by typed length-value blocks. The implemented parser uses:

- type `0`: dimensions such as slot and scene counts;
- type `1`: preset name, author, description, and type;
- type `4`: slot order, category IDs, and model codes;
- type `5`: per-scene parameters, enabled states, volume/tempo metadata, and
  scene names.

Unknown TLV types remain ignored rather than being interpreted speculatively.
Model and parameter names are added only when the installed algorithm catalog
contains an exact category/model match.

## Verification Status

On July 18, 2026, a connected Ampero II Stomp was verified with the official
editor closed:

- DLL loading and port enumeration succeeded (`input 0`, `output 1`).
- Current-scene request `0x03000001` returned scene `0`.
- Slot-model request `0x01040002` returned an empty slot for slot `0`.
- Complete current-preset request `0x01000000` returned 5,072 bytes.
- The parsed preset was named `Empty`, contained three scenes and twelve ordered
  slots, and all twelve slots reported category/model `-1`.
- The formal Skill `device snapshot --include-parameters` completed successfully
  through the compiled bridge.

No real model/parameter write or rollback has been executed. Write paths remain
guarded by exact plan preview, explicit `--execute --confirm APPLY`, preflight
reads, a command whitelist, and rollback journaling.
