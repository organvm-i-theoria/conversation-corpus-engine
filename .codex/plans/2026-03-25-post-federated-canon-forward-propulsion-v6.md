# Post-Federated-Canon Forward Propulsion v6

**Date:** 2026-03-25
**Repository:** `conversation-corpus-engine`
**Basis:** post-filtered review-assist artifacts

## Verified Current State

- `pytest -q` passes at `181 passed`.
- `review assist` now supports:
  - relation filters
  - source-pair filter
  - anchor substring filter
  - persistent JSON and Markdown artifact writing under `reports/`
- Live filtered assist run with `--relation disjoint --write` produced:
  - `400` filtered items from `406` open queue items
  - `261` groups
  - `17` batches
  - artifacts at:
    - `reports/review-assist-latest.json`
    - `reports/review-assist-latest.md`
    - `reports/review-assist-2026-03-25.md`

## What Closed Since v5

- The review-assist surface is now usable for offline review, not just terminal inspection.
- Operators can isolate the dominant `disjoint` residue or smaller subsets without custom scripting.

## New Frontier

The next leverage point is to decide whether the `disjoint` residue is safe to sample for a conservative reject workflow, or whether the better next move is richer review artifacts such as per-batch exports, rationale ranking, and candidate checklists.

## Recommended Immediate Sequence

1. Add per-batch selection or export so an operator can work one batch at a time without scanning the full report.
2. Add stronger rationale ranking inside groups:
   - lexical relation
   - score
   - source-pair consistency
   - possible generic-term flags
3. Sample the `disjoint` residue manually and quantify whether a conservative reject policy is warranted.
4. Only after that sample, consider a new reversible workflow for bulk review assistance.

## Guardrails

- Treat the `disjoint` label as a review hint, not an auto-rejection command.
- Keep all next-step automation reversible and evidence-backed.
