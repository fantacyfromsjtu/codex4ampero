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
10. Do not issue firmware, factory-reset, delete, save-overwrite, global I/O, or unknown commands.
