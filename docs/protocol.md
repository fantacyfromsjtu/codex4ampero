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
| `0x02000000` | Read current routing template | empty request; response contains a template header and routing topology |
| `0x02000003` | Select factory routing template | template ID `int32`; verified through the `0x02000000` response |
| `0x03000001` | Change/read current scene | scene `int8` for writes |
| `0x05000000` | Save live buffer to preset | target index `int32` plus a zero-padded 17-byte UTF-8 preset name |

Integers and IEEE-754 floats are little-endian. Preset save is exposed only through
the exact-target, journal-bound save workflow. Delete, firmware, bootloader,
factory-reset, global I/O, and unknown command addresses remain excluded.

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

`device routing` reads `0x02000000` directly and does not depend on the larger
current-preset response. Routing rollback preflight uses this bounded query so a
temporary `0x01000000` timeout does not block an otherwise verifiable template
change.

The official editor limits preset names to 16 supported printable ASCII
characters and transmits them in a 17-byte zero-padded field. `plan save` uses the
same encoding. The command is bound to a successful apply journal, requires the
device to report that exact target during a recorded preflight, and waits for the
official save response. The current firmware may stop answering normal direct
requests in the same session after save, and it does not reliably answer
independent preset-name or edit-flag queries. Those post-save reads are therefore
not used as false proof of failure.

## Verification Status

On July 18, 2026, a connected Ampero II Stomp was verified with the official
editor closed:

- DLL loading and port enumeration succeeded (`input 0`, `output 1`).
- Current-scene request `0x03000001` returned scene `0`.
- Slot-model request `0x01040002` returned an empty slot for slot `0`.
- Complete current-preset request `0x01000000` returned 5,072 bytes.
- Exact patch location `A50-1` mapped to and read back as linear index `150`.
- A twelve-slot preset named `Hana Solo` was parsed with its scene, routing,
  enabled-state, model, and parameter data.
- The formal Skill `device snapshot --include-parameters` completed successfully
  through the compiled bridge.
- Serial routing, a drive-model replacement, and parameter changes were applied as
  a 21-command plan; all 21 writes received immediate verified readbacks.
- The preset-save payload was observed to persist on hardware in one trial even
  when this firmware stopped returning the official save response. The controller
  correctly leaves such a session unverified rather than claiming success.

Write paths remain guarded by exact plan preview, explicit
`--execute --confirm APPLY`, preflight reads, a command whitelist, immediate
readbacks, and rollback journaling. Preset save remains a separate irreversible
step requiring the target-specific `SAVE:Axx-y` token.
