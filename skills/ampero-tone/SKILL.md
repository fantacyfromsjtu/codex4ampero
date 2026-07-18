---
name: ampero-tone
description: Control and iteratively tune a locally connected HOTONE Ampero II Stomp from Codex. Use when the user asks to inspect, research, design, preview, apply, compare, refine, save, or roll back guitar tone/effect-chain changes on Ampero II hardware, including natural-language requests such as warmer, clearer, less harsh, more ambient, or similar to a song or artist. This skill uses the local codex4ampero Python control layer and the official editor's installed algorithm catalog and communication DLL.
---

# Ampero Tone

Use the bundled `scripts/ampero.py` tool as the only hardware interface. Do not construct raw DLL calls or arbitrary command addresses.

The bundled script runs native-DLL operations in an isolated worker process. Treat a `WatchdogTimeout` response as a failed read, never as permission to retry indefinitely or proceed with writes.

For tone-design or hardware-write conversations, read and follow
`references/conversation-flow.md`. It defines the required question order,
proposal gate, destination gate, final write confirmation, and post-write save
question. Diagnostics-only requests may skip the tone intake flow.

## Workflow

1. Collect missing guitar context first, then missing output/monitoring context.
   Ask one question at a time and do not repeat facts already supplied.
2. After context is known, run the doctor before the first hardware operation:

   `py scripts/ampero.py --json doctor --scan`

3. If no device is present, continue in plan-only mode and clearly say that hardware execution was not tested.
4. When a device is present, read the live slot layout before planning:

   `py scripts/ampero.py --json device snapshot`

   Add `--include-parameters` when the user wants a parameter-level diff. Treat any per-slot `read_error` as unknown state rather than guessing.
   When only routing state is needed, or a full preset snapshot times out, use the bounded read-only routing query:

   `py scripts/ampero.py --json device routing --timeout 5`
5. Research the requested tone, then translate it into effect choices and conservative parameter changes. Read `references/tone-language.md` when interpreting subjective tone words. For song-, artist-, album-, era-, or recording-specific requests, also read and follow `references/tone-research.md`; browse the web unless the user explicitly requests an offline answer.
6. Query the installed catalog instead of inventing model or parameter names:

   `py scripts/ampero.py --json catalog search "QUERY" --category "CATEGORY"`

   `py scripts/ampero.py --json catalog show "EXACT NAME" --category "CATEGORY"`

7. Present the proposed chain, detailed parameters, brief reasons, expected result,
   and caveats. Ask for the user's opinion and revise until the tone direction is
   explicitly approved. Do not ask for the write destination before this approval.
8. After tone approval, ask for or confirm the exact `Axx-y` write destination.
9. Write a target-bound schema-version-1 JSON plan. Read `references/plan-schema.md` before creating or modifying a plan.
10. Validate and preview every plan:

   `py scripts/ampero.py --json plan validate PLAN.json`

   `py scripts/ampero.py --json plan preview PLAN.json`

11. Present the exact target patch, automatic-selection behavior, routing, effect
    and parameter diff, warnings, and command count. A destination answer is not
    approval; require a final explicit confirmation of this target-bound preview.
12. After final approval, execute exactly the reviewed plan:

   `py scripts/ampero.py --json plan apply PLAN.json --execute --confirm APPLY`

13. Prefer plans with `save_preview_name` when the destination and preset name are
    already known. After a successful apply, the CLI returns an exact journal-bound
    save preview; present it immediately and ask the user to reply with the shown
    `SAVE:Axx-y` token or decline saving, without first asking a generic save
    question. If no save preview name was planned, ask for the name and prepare
    `plan save`. Never silently save as part of `plan apply`.
14. Ask for a short listening result such as too bright, too dark, too wet, too compressed, noisy, or correct. Prefer small parameter-only follow-up plans.
15. If the result is unsafe or unwanted, use the journal path returned by apply:

   `py scripts/ampero.py --json plan rollback JOURNAL.json --execute --confirm ROLLBACK`

## Guardrails

- Read `references/safety-rules.md` before hardware execution.
- Keep the official Ampero II editor closed during direct device access.
- Treat slots as zero-based protocol IDs. Describe them to users as slot ID values, not visual positions, unless the current preset layout has been read and verified.
- Never call firmware, bootloader, factory-reset, global-output, preset-delete, or raw-message functionality.
- Never use `--allow-unverified-reads` without explicit user approval after explaining that rollback may be incomplete.
- Preset save is exposed only through `plan save` bound to a successful apply journal. It requires an exact target, valid preset name, matching current device patch, an irreversible-save preview, and the exact `SAVE:Axx-y` confirmation token.
- For named tones, distinguish sourced facts from tonal inference, use multiple source tiers when available, and preserve the research summary in the plan instead of presenting unsupported certainty.
- Do not claim a sound matches a recording without listening evidence. Describe it as a starting point and iterate from user feedback.
