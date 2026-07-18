# Safety Model

- Preview is the default mode, including when `plan apply` is called without execution flags.
- Actual writes require both `--execute` and the literal confirmation token `APPLY`.
- Rollback writes require both `--execute` and the literal token `ROLLBACK`.
- The official editor process blocks direct connection by default.
- The Codex Skill wrapper isolates native-DLL calls in a worker process and forcibly terminates blocked scans after a bounded timeout.
- Effect and parameter names must exist in the installed catalog.
- Values must remain inside catalog-declared ranges.
- Parameters named level, output, master, or volume are capped at 75% of their range.
- Parameter/model changes attempt a device preflight read before writing.
- Each successful preflight result is persisted to a journal before the corresponding write.
- Mid-plan failures trigger reverse-order rollback using journal entries already captured.
- Unknown, firmware, factory-reset, delete, and preset-save commands are not exposed.

`--allow-unverified-reads` exists only for controlled protocol testing. It can make rollback incomplete and must not be used automatically by the Skill.
