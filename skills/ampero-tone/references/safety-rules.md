# Safety Rules

1. Start with monitors, headphones, amp return, or FRFR output at a low physical volume.
2. Preview first. Hardware writes require the exact `--execute --confirm APPLY` pair.
3. Close `Ampero II.exe`; direct and official-editor connections must not compete for MIDI ports or state.
4. Avoid changing multiple gain/output stages upward in one plan.
5. The control layer rejects output-sensitive values above 75% of their declared range.
6. Prefer parameter changes within 10-20% of the declared range per listening iteration.
7. Model changes require a verified preflight read for rollback. Do not bypass this by default.
8. Keep the returned journal until the user accepts the result.
9. Roll back immediately on sudden level increase, silence, unstable connection, or unexpected slot changes.
10. Do not issue firmware, factory-reset, delete, global I/O, or unknown commands. Preset save is allowed only through the dedicated journal-bound save workflow.
11. If the device explicitly reports patch index `0xffff`, hardware execution remains blocked unless the plan has an exact `target_patch` and the user freshly confirms the same label shown on the physical device display. Record that label with `--confirm-device-patch`.
12. Automatic target-patch loading must appear in the exact plan preview as `select_target_patch: true`. Explain that loading the target can discard unsaved live edits, and require fresh approval before execution.
13. Tone approval and hardware-write approval are separate gates. Ask for the exact destination only after tone approval, then require final confirmation of the target-bound preview.
14. When `save_preview_name` is present, show the journal-bound save preview immediately after apply and ask directly for the exact `SAVE:Axx-y` token or a decline. Otherwise ask for the preset name first. Never include saving automatically in `plan apply`.
15. A save must be bound to a successful apply journal, use its exact target, record a verified target preflight before sending, and receive the official save response. Save has no automatic rollback. Do not require a post-save request when firmware resets the direct-control session.
