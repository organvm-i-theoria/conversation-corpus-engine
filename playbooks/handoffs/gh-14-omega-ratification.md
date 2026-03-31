# Agent Handoff: GH#14 — OM-MEM-001 Omega Ratification

**From:** Session S41 | **Date:** 2026-03-31 | **Phase:** HANDOFF
**Archetype:** THE GOVERNOR | **IRF:** IRF-CCE-015

## Current State

OM-MEM-001 is **proposed but not ratified**. The criterion states: "the system must
ingest its own session transcripts." No formal specification has been written yet.

### References

| Location | Content |
|----------|---------|
| `.claude/plans/2026-03-24-cce-exhaustive-roadmap.md:108-144` | Roadmap context: autopoietic loop, SpecStory adapter path |
| `.claude/plans/2026-03-30-s40-full-breath-session.md:120` | S40 plan: "Write the complete OM-MEM-001 criterion specification in a comment on #14" |
| `state/testaments/s33-testament.json:50` | IRF-CCE-015 reference |
| `state/testaments/s37-testament.json:40` | GH#14 opened |

### What "Ratification" Means

An omega criterion must have:
1. **Criterion statement** — a testable proposition ("X must be true")
2. **Evidence requirements** — what artifacts demonstrate compliance
3. **Measurement method** — how to verify pass/fail objectively
4. **Amendment route** — how the criterion was proposed and ratified

The specification must be posted as a comment on GH#14 in the format used by
existing omega criteria in `meta-organvm/organvm-corpvs-testamentvm/`.

## Completed Work

- [x] OM-MEM-001 proposed in roadmap (S33)
- [x] GH#14 opened to track ratification (S37)
- [x] IRF-CCE-015 created
- [x] Evidence partially assembled: testament files, session review protocol
- [ ] Read existing omega criteria format from meta-organvm
- [ ] Draft OM-MEM-001 specification
- [ ] Post specification as GH#14 comment
- [ ] Ratification (formal acceptance)
- [ ] Update omega state tracking

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| CCE is the evidence provider, not the ratifier | Omega criteria are system-level, governed in meta-organvm |
| SpecStory adapter identified as implementation path | `.specstory/history/*.json` is the closest existing transcript format |
| Testament events are partial evidence | They capture session metadata but not transcript content |

## Critical Context

- **Existing omega state:** 8/19 criteria met (per roadmap S5). OM-MEM-001 is one of
  three CCE-adjacent criteria that could advance the count.
- **The autopoietic loop:** OM-MEM-001 requires the CCE to ingest its own creation
  story. This means building an adapter that reads AI session transcripts (e.g.,
  SpecStory JSONL, Claude Code conversation logs) and normalizes them to corpus
  artifacts. The adapter does not exist yet.
- **Distinction: criterion vs. implementation.** Ratifying the criterion does NOT
  require implementing the adapter. It requires specifying *what done looks like*
  so that when the adapter is built, compliance can be objectively assessed.
- **Format precedent:** Look at `meta-organvm/organvm-corpvs-testamentvm/` for the
  existing omega criteria format. The specification must match that format exactly.
  Do NOT invent a new format.

## Next Actions

1. Read existing omega criteria in meta-organvm:
   ```bash
   ls ~/Workspace/meta-organvm/organvm-corpvs-testamentvm/omega/
   # or search for omega criterion files
   find ~/Workspace/meta-organvm/ -name "*omega*" -o -name "*criterion*" | head -20
   ```

2. Draft OM-MEM-001 specification following the existing format. Suggested content:
   - **Statement:** "The conversation corpus engine must be capable of ingesting
     transcripts from its own operational sessions as corpus artifacts."
   - **Evidence:** (a) Import adapter exists for at least one session transcript
     format, (b) at least one self-referential corpus exists in the registry,
     (c) the corpus passes all 8 evaluation gates.
   - **Measurement:** Run `cce evaluation run` against the self-referential corpus;
     all gates must pass.

3. Post the specification as a comment on GH#14

4. Initiate ratification per the omega governance process (likely requires
   human approval in meta-organvm)

5. Update IRF-CCE-015 and omega state tracking

## Risks & Warnings

- Do NOT conflate ratifying the criterion with implementing the solution.
  The criterion says what *done* looks like. The implementation (SpecStory adapter,
  `import_specstory_session_corpus.py`) is a separate task.
- The omega governance process may require changes in `meta-organvm` that this
  session cannot make unilaterally. The handoff recipient should check the
  current governance rules before posting.
- If existing omega criteria have evolved since the roadmap was written (2026-03-24),
  the format may have changed. Always read current state, not memory.
