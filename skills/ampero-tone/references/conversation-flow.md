# Conversation Flow

Use this state machine for tone-design and hardware-write conversations. Respond
in the user's language and ask one concise question at a time. Facts the user has
already supplied count as answered; never ask for the same fact twice.

Diagnostics-only requests such as `doctor`, scan, snapshot, or catalog lookup do
not require this intake flow unless the user also asks for a tone design.

## Stage 1 - Guitar Context

Before researching or designing a tone, establish the guitar context. If it is
missing, ask for the guitar model or type and pickup configuration. A concise
question should cover both, for example:

> What guitar are you using, and are the pickups single-coil, humbucker, P90, or active?

Do not ask for the output system in the same message. If the user already gave a
guitar model, infer only widely established properties; ask about pickups when a
model can ship with materially different configurations.

## Stage 2 - Output Context

After guitar context is known, check whether the output or monitoring path is
known. If it is missing, ask where the Ampero output goes. Useful categories are:

- headphones, studio monitors, or FRFR;
- audio interface or DAW;
- mixer or PA;
- guitar amplifier input;
- amplifier effects return or external power amp.

This distinction changes cabinet simulation, high/low cuts, stereo choices, and
level assumptions. Do not start tone research until both guitar and output context
are known, unless the user explicitly asks for a context-independent draft.

## Stage 3 - Tone Research

After context collection, research the requested sound without writing hardware:

1. Run bounded `doctor --scan` before the first hardware operation.
2. Read a bounded device snapshot when the current chain matters. If the complete
   preset snapshot times out and only routing is needed, use `device routing`.
3. Search the installed official algorithm catalog for every proposed model and
   parameter; never invent names, IDs, ranges, or enum values.
4. For a named song, artist, album, era, or recording, read and follow
   `tone-research.md`. Browse the web unless the user explicitly requests an
   offline answer. Prefer official/primary evidence, corroborate with specialist
   sources, and treat community presets or covers only as supporting evidence.
5. Clearly separate sourced facts, catalog facts, tonal inference, and known
   limitations. Record the research date, confidence, and traceable sources in the
   plan's `research` object.
6. Translate the target into recording characteristics such as gain structure,
   compression, attack, frequency balance, modulation, delay, reverb, and stereo
   width. Do not claim an exact match without listening evidence.

## Stage 4 - Detailed Proposal

Present a reviewable proposal before asking for a destination preset. Include:

1. **Goal and assumptions**: guitar, pickups, output path, musical role, and any
   uncertain assumptions.
2. **Signal chain**: exact serial/parallel order and enabled state.
3. **Detailed parameters**: effect name, parameter name, proposed value, unit or
   legal range when useful, and the current value when it was read successfully.
4. **Brief reasons**: one concise reason for each effect block or related parameter
   group, tied to the requested sound and the user's equipment.
5. **Expected result and caveats**: what should change, what may still require
   listening adjustment, and any output-level warning.

Use compact tables where they improve readability. Describe artist/song presets as
a starting point rather than a verified reproduction.

End with one opinion question, for example:

> Does this direction look right, or should I make it brighter, warmer, drier, cleaner, or more saturated before writing anything?

## Stage 5 - Tone Approval

Treat comments such as "too bright" or "use less delay" as revision requests, not
write approval. Revise the proposal and ask for the user's opinion again.

Tone approval authorizes preparation of a target-bound plan; it does not authorize
a hardware write by itself. Do not ask for the destination before the proposal is
approved. If the user supplied a destination earlier, remember it and confirm it
at the next stage instead of silently using it.

## Stage 6 - Write Destination

After tone approval, ask for or confirm the exact destination shown by the Ampero
II Stomp, using the `Axx-y` format such as `A50-1`. Also establish whether Codex may
automatically select that patch.

If automatic selection is requested, explain that loading the target can discard
unsaved live edits. Never interpret a bank-only value such as `50` as an exact
patch location.

## Stage 7 - Final Write Gate

Build and validate the schema-version-1 plan only after the destination is known.
The final preview must include:

- exact `target_patch` and linear protocol index;
- whether `select_target_patch` is enabled;
- routing topology and complete effect order;
- every model and parameter command;
- output-sensitive warnings and the unsaved-edit warning;
- total command count.

Ask for one final explicit write confirmation after presenting this target-bound
preview. A destination answer alone is not write approval. Execute only the exact
reviewed plan with `--execute --confirm APPLY`.

## Stage 8 - Write Result

On success, report the verified target patch, routing, command count, immediate
readback result, and journal path. On timeout or verification failure, stop,
preserve the journal, and report whether rollback completed. Never describe a
partial or unverified operation as successful.

## Stage 9 - Save Decision

When the destination and preset name are known before writing, include
`save_preview_name` in the reviewed tone plan. The tone preview must show that a
post-apply save preview will be prepared, but that `plan apply` will not save.

After a successful apply, the CLI uses the successful apply journal to return the
exact target, name, 21-byte command, irreversible overwrite warning, and
confirmation token. Present this exact save preview immediately and ask the user to
reply with `SAVE:Axx-y` or decline saving. Do not add an intermediate generic
"Do you want to save?" question.

If the preset name was not known when the tone plan was reviewed, ask for or
confirm a valid name of at most 16 official-editor characters after apply, then
prepare `plan save` from the successful apply journal. A general yes answer is not
execution approval; require the exact `SAVE:Axx-y` confirmation after the preview.

Execute only:

`py scripts/ampero.py --json plan save APPLY_JOURNAL.json --name "NAME" --execute --confirm SAVE:Axx-y`

The save command must verify that the device is on the journal's exact target
before sending, record that preflight stage, and wait for the official save
response. Some firmware stops answering normal requests in the same direct-control
session after save, so do not create a false failure by requiring a post-save
request. Saving cannot be rolled back by the control layer. If the user says no,
warn that changing patches or powering off can discard the live edits. Never claim
the preset is saved unless target preflight and the official save response both
succeed.

After the save decision, ask for a short listening result and prefer small,
parameter-only refinement plans.
