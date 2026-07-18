# Tone Plan Schema

Use UTF-8 JSON with `schema_version: 1`.

```json
{
  "schema_version": 1,
  "title": "Clear rhythm starting point",
  "reason": "Reduce gain and ambience while preserving pick attack.",
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

Use `expected_before` only when it is known from a prior verified read or user-provided editor value. It is a rollback fallback, not a guess.

Parameter actions following `set_model` for the same slot must reference the same effect. Query the catalog for valid parameter ranges before choosing values.
