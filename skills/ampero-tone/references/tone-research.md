# Tone Research Workflow

Use this workflow for artist-, song-, album-, era-, or recording-specific tone
requests. The goal is not to collect trivia; it is to turn traceable evidence into
device-valid model and parameter decisions.

## 1. Decide Whether Web Research Is Required

Web research is required when:

- the user names a song, artist, album, performance, producer, or recording era;
- the user asks for an accurate, professional, researched, or current result;
- the requested equipment, firmware, catalog, or public rig may have changed; or
- the user explicitly asks to search or browse the internet.

Skip browsing only when the user explicitly asks for an offline answer. In that
case, label the result as inference-only and lower the confidence.

## 2. Use a Source Hierarchy

Prefer independent sources and classify each source in the plan research block:

1. **Tier 1**: official releases, isolated tracks published by the rights holder,
   artist/engineer interviews, official rig rundowns, manufacturer documentation,
   and the locally installed Ampero algorithm catalog.
2. **Tier 2**: reputable transcriptions, specialist music publications, established
   gear databases, and detailed performance analysis with disclosed equipment.
3. **Tier 3**: community discussions, covers, short-form tutorials, marketplace
   descriptions, and unsourced preset recipes.

Use Tier 3 sources only as supporting evidence. Do not turn one community post or
one cover player's settings into an asserted fact about the original recording.

## 3. Research the Recording, Not Just the Artist

Collect only facts that can change the tone plan:

- guitar and pickup family;
- amp family and clean/crunch/high-gain operating point;
- drive, boost, fuzz, compression, modulation, delay, and reverb clues;
- tempo or rhythmic subdivision when it affects delay time;
- whether the audible part is single-tracked, doubled, layered, or stereo-treated;
- live-versus-studio differences and relevant production context.

An artist's general rig is supporting context, not proof that every item appears on
the target song.

## 4. Separate Facts From Inferences

Present two explicit groups:

- **Facts**: statements directly supported by a cited source or the installed
  catalog.
- **Inferences**: listening- or engineering-based conclusions used to translate the
  facts into an Ampero plan.

State important limitations, such as unavailable isolated stems, conflicting rig
reports, a cover rather than the master recording, or unknown post-production.

## 5. Map Evidence to the Installed Catalog

For every proposed Ampero model:

1. Query the installed official catalog.
2. Read the exact model description and parameter ranges.
3. Explain why its documented behavior matches the research evidence.
4. Prefer the smallest model or parameter change that fixes the user's complaint.
5. Never copy third-party numeric settings without adapting them to the user's
   guitar, pickup, output system, and current preset.

The catalog is authoritative for model names, categories, parameter names, ranges,
and enum values. Web sources are context for tone intent, not protocol authority.

## 6. Record Research in the Plan

Named-tone plans should include the optional schema-version-1 `research` object:

- `target`: requested artist/song/recording;
- `researched_on`: ISO date in `YYYY-MM-DD` format;
- `confidence`: `low`, `medium`, or `high`;
- `facts`: sourced observations;
- `inferences`: tone-design conclusions;
- `limitations`: reasons the result remains a starting point;
- `sources`: title, source type, tier, finding, and optional reference.

The preview and journal preserve this block so the user can audit why each model
and parameter was selected.

## 7. Proposal Standard

Before asking for write approval, provide:

- current-chain diagnosis;
- proposed serial signal chain and bypassed slots;
- detailed model and parameter values;
- pickup and guitar-control recommendation;
- brief reason for each important change;
- expected audible result and likely failure modes;
- research confidence and limitations.

Do not claim an exact match without direct listening comparison. Treat the first
write as a researched starting point and refine from the user's recorded or live
listening feedback.
