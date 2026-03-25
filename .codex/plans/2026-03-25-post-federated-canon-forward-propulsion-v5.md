# Post-Federated-Canon Forward Propulsion v5

**Date:** 2026-03-25
**Repository:** `conversation-corpus-engine`
**Basis:** post-review-assist operator surface

## Verified Current State

- `pytest -q` passes at `178 passed`.
- Every module under `src/conversation_corpus_engine/` has dedicated direct test coverage.
- The new `review assist` CLI surface groups open `entity-alias` items into stable anchor groups and batches with lexical relation hints.
- Live queue assist on the current project root reports:
  - `406` open `entity-alias` items
  - `266` anchor groups
  - `17` batches at batch size `25`
  - relation split: `400 disjoint`, `6 substring`
  - single source-pair origin: `claude-history-memory <> claude-local-session-memory`

## What Closed Since v4

- Operator workflow is no longer limited to raw queue listing plus auto-triage.
- Humans now have a conservative, non-destructive assist surface for the remaining review boundary:
  - stable batching
  - anchor grouping
  - lexical relation labels
  - review hints on likely weak versus stronger candidates

## New Frontier

The next leverage point is no longer discovering what remains; it is deciding how much of the remaining residue should be rejected quickly, reviewed manually, or receive a narrowly scoped semantic assist pass.

## Recommended Immediate Sequence

1. Add persistent artifact writing for review assist payloads and markdown reports if operator iteration would benefit from offline review.
2. Add filtering and sorting controls for the assist surface:
   - relation filter (`disjoint`, `substring`, etc.)
   - source-pair filter
   - anchor filter
3. Use the assist output to design a conservative next-step policy:
   - likely fast-path reject candidates for clearly disjoint labels
   - preserve manual review for the small substring residue and any context-dependent cases
4. Only then consider a new semantic assist heuristic, and only with explicit human-boundary regression tests.

## Guardrails

- Do not auto-reject or auto-accept the whole `disjoint` residue without validating a representative sample first.
- Keep assist tooling descriptive first, prescriptive second.
- Prefer reversible workflow improvements over irreversible queue mutation.
