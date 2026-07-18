# Tone Plan Schema

Use UTF-8 JSON with `schema_version: 1`.

```json
{
  "schema_version": 1,
  "title": "Clear rhythm starting point",
  "reason": "Reduce gain and ambience while preserving pick attack.",
  "research": {
    "target": "Example artist studio lead tone",
    "researched_on": "2026-07-18",
    "confidence": "medium",
    "facts": ["The transcribed part is labeled as overdriven guitar."],
    "inferences": ["Use moderate pedal drive into an articulate amp."],
    "limitations": ["No isolated studio stem was available."],
    "sources": [
      {
        "title": "Official algorithm catalog",
        "source_type": "local_catalog",
        "tier": 1,
        "finding": "The selected model is classified as overdrive.",
        "reference": "v1.0.8_alg_data.json"
      }
    ]
  },
  "save_preview_name": "Hana Solo",
  "target_patch": "A50-1",
  "select_target_patch": false,
  "actions": [
    {
      "type": "set_model",
      "slot": 3,
      "effect": {"name": "Tweed Lux", "category": "AMP"},
      "enabled": true
    },
    {
      "type": "set_parameter",
      "slot": 3,
      "effect": {"name": "Tweed Lux", "category": "AMP"},
      "parameter": "Volume",
      "value": 30,
      "expected_before": 50
    },
    {
      "type": "set_scene",
      "scene": 0
    }
  ]
}
```

## Actions

- `set_model`: requires zero-based `slot`, exact catalog effect `name`, optional `category`, and optional `enabled`.
- `set_parameter`: requires zero-based `slot`, exact effect reference, parameter name or numeric ID, and numeric `value`.
- `set_scene`: accepts scene IDs `0..4`.
- `set_routing_template`: selects one official factory routing template. Supported
  values are `Parallel`, `Split->Mix`, `A/B->Y`, `Y->A/B`, and `Serial`.
  The controller reads the current template and records it for rollback.
  `expected_before` is optional; when supplied, execution refuses if the device
  topology does not match that exact factory template.

Use `expected_before` only when it is known from a prior verified read or user-provided editor value. It is a rollback fallback, not a guess.

Use `target_patch` for hardware execution. Ampero II Stomp labels use `A00-1`
through `Axx-3`; the controller reads address `0x00090000` immediately before
writing and refuses the plan if the current patch does not exactly match. Empty
patches may explicitly return `0xffff`; in that case execution still refuses by
default and requires a fresh physical-display confirmation passed as
`--confirm-device-patch Axx-y`. The confirmed label must exactly equal
`target_patch` and is recorded in the journal.

Set `select_target_patch` to `true` only when the exact preview explicitly includes
automatic patch loading. The controller writes the target's four-byte linear index,
loads the preset, and requires an exact protocol readback before any tone action.
Loading a patch can discard unsaved changes in the current live edit buffer, so this
field defaults to `false`.

Parameter actions following `set_model` for the same slot must reference the same effect. Query the catalog for valid parameter ranges before choosing values.

## Post-Apply Save Preview

Use optional `save_preview_name` when the exact target and intended preset name are
known during tone-plan review. It requires `target_patch` and accepts the same
official-editor-compatible name as `plan save` (1-16 supported ASCII characters).

The tone preview includes an unbound save preview so the user can see the target,
name, payload, irreversible warning, and future confirmation token. `plan apply`
still modifies only the live buffer and never saves automatically.

After a successful apply, the CLI binds the preview to the successful apply journal
and returns it in `save_preview`. The conversation can then ask directly for the
shown `SAVE:Axx-y` token or allow the user to decline, removing the redundant
general save question without weakening the irreversible-save gate.

## Research Metadata

`research` is optional for generic utility changes and recommended for all named
artist/song/recording plans. When present, it is validated and preserved in plan
previews and execution journals.

- `target`: required description of the requested recording or tone.
- `researched_on`: required ISO date using `YYYY-MM-DD`.
- `confidence`: `low`, `medium`, or `high`.
- `facts`, `inferences`, and `limitations`: arrays of non-empty strings. At least
  one fact or inference is required.
- `sources`: non-empty array of traceable source records.
- `source_type`: one of `official_release`, `artist_interview`, `manufacturer`,
  `transcription`, `technical_reference`, `community`, or `local_catalog`.
- `tier`: source quality level `1`, `2`, or `3` as defined in
  `tone-research.md`.
- `reference`: optional URL, publication identifier, catalog filename, or other
  stable lookup reference.
