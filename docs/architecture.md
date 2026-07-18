# Architecture

## Components

- `skills/ampero-tone`: Codex workflow, tone-language guidance, plan schema,
  safety policy, and the watchdog-wrapped hardware entry point.
- `src/ampero_control/catalog.py`: reads the newest algorithm catalog installed
  with the official editor.
- `src/ampero_control/plan.py`: converts human-reviewed JSON plans into
  catalog-resolved protocol commands.
- `src/ampero_control/safety.py`: blocks unsupported ranges and
  output-sensitive values.
- `src/ampero_control/native.py`: loads the vendor DLL for installation
  diagnostics and input/output scanning only. It intentionally rejects connected
  requests and sends from Python.
- `bridge/bin/ampero_bridge.dart`: initializes the Dart DL API, registers a real
  `ReceivePort.nativePort`, runs the vendor timer pump, and exposes a JSON-line
  request/send service.
- `src/ampero_control/dart_bridge.py`: supervises the compiled bridge process,
  applies request timeouts, and adapts it to the Python transport interface.
- `src/ampero_control/preset.py`: parses the complete current-preset TLV payload
  into metadata, dimensions, scene data, slot models, states, and parameters.
- `src/ampero_control/controller.py`: reads live snapshots, performs preflight
  reads, writes a journal, applies commands sequentially, and rolls back after a
  failed write sequence.
- `src/ampero_control/cli.py`: JSON-oriented process boundary used by Codex and
  tests.

## Transport Boundary

The vendor DLL's scan callbacks work through ordinary native callbacks and may be
used by the Python diagnostic transport. Connected responses depend on the Dart
DL API and a registered Dart NativePort. A Python-only `ctypes` connection can
receive an initial native event and then terminate the process, so connected
operations are deliberately restricted to `DartBridgeTransport`.

The bridge runs as a supervised child process. The Skill wrapper adds a second,
outer process watchdog: scans are limited to 10 seconds and snapshots to 30
seconds. A timeout terminates the worker and returns a structured
`WatchdogTimeout` error instead of leaving the Codex session blocked.

## Trust Boundary

Codex may choose models and parameter values, but it never sends raw arbitrary
device messages. The deterministic control layer resolves names against the
installed catalog, validates ranges, allows only a small command whitelist,
previews encoded payloads, and requires explicit execution confirmation.

The repository does not contain or redistribute `HTUSBTools.dll` or the official
algorithm catalog. Both are discovered at runtime from the user's official editor
installation.

## Product Shape

The Codex Skill is the user-facing agent. The Python CLI and compiled Dart bridge
are internal, testable process boundaries rather than a redundant chat UI or a
general-purpose `amperoctl.exe`. An MCP server could later wrap the same package
for persistent typed tools, but it should not duplicate protocol or safety logic.
