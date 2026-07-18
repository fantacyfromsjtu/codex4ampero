---
name: ampero-tone
description: Control and iteratively tune a locally connected HOTONE Ampero II Stomp from Codex. Use when the user asks to inspect, design, preview, apply, compare, refine, or roll back guitar tone/effect-chain changes on Ampero II hardware, including natural-language requests such as warmer, clearer, less harsh, more ambient, or similar to a song/artist. This skill uses the local vibe_ampere Python control layer and the official editor's installed algorithm catalog and communication DLL.
---

# Ampero Tone

Use the bundled `scripts/ampero.py` tool as the only hardware interface. Do not construct raw DLL calls or arbitrary command addresses.

The bundled script runs native-DLL operations in an isolated worker process. Treat a `WatchdogTimeout` response as a failed read, never as permission to retry indefinitely or proceed with writes.

## Workflow

1. Run the doctor before the first hardware operation:

   `py scripts/ampero.py --json doctor --scan`

2. If no device is present, continue in plan-only mode and clearly say that hardware execution was not tested.
3. When a device is present, read the live slot layout before planning:

   `py scripts/ampero.py --json device snapshot`

   Add `--include-parameters` when the user wants a parameter-level diff. Treat any per-slot `read_error` as unknown state rather than guessing.
4. Translate the user's tone description into effect choices and conservative parameter changes. Read `references/tone-language.md` when interpreting subjective tone words.
5. Query the installed catalog instead of inventing model or parameter names:

   `py scripts/ampero.py --json catalog search "QUERY" --category "CATEGORY"`

   `py scripts/ampero.py --json catalog show "EXACT NAME" --category "CATEGORY"`

6. Write a schema-version-1 JSON plan. Read `references/plan-schema.md` before creating or modifying a plan.
7. Validate and preview every plan:

   `py scripts/ampero.py --json plan validate PLAN.json`

   `py scripts/ampero.py --json plan preview PLAN.json`

8. Present the exact effect and parameter diff to the user. Do not execute until the user explicitly approves that preview.
9. After approval, execute exactly the reviewed plan:

   `py scripts/ampero.py --json plan apply PLAN.json --execute --confirm APPLY`

10. Ask for a short listening result such as too bright, too dark, too wet, too compressed, noisy, or correct. Prefer small parameter-only follow-up plans.
11. If the result is unsafe or unwanted, use the journal path returned by apply:

   `py scripts/ampero.py --json plan rollback JOURNAL.json --execute --confirm ROLLBACK`

## Guardrails

- Read `references/safety-rules.md` before hardware execution.
- Keep the official Ampero II editor closed during direct device access.
- Treat slots as zero-based protocol IDs. Describe them to users as slot ID values, not visual positions, unless the current preset layout has been read and verified.
- Never call firmware, bootloader, factory-reset, global-output, preset-delete, or raw-message functionality.
- Never use `--allow-unverified-reads` without explicit user approval after explaining that rollback may be incomplete.
- Do not save over a stored preset unless a future supported command and a separate user confirmation are added. Current plans modify the live edit buffer only.
- Do not claim a sound matches a recording without listening evidence. Describe it as a starting point and iterate from user feedback.
