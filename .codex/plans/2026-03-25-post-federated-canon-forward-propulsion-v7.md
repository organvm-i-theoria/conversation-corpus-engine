# Post-Federated-Canon Forward Propulsion v7

**Date:** 2026-03-25
**Repository:** `conversation-corpus-engine`
**Basis:** review-assist batch selection and batch-scoped export flow

## Verified Current State

- `python3 -m pytest -q` passes at `186 passed`.
- `review assist` now supports:
  - relation filters
  - source-pair filter
  - anchor substring filter
  - persistent full-report writing under `reports/`
  - batch selection via `--batch-id`
  - batch-scoped JSON and Markdown artifact writing
- Live batch run with `--relation disjoint --batch-id entity-alias-batch-001 --write --json` produced:
  - `23` selected items
  - from `400` filtered disjoint items
  - from `406` total open entity-alias items
  - `6` groups
  - selected batch `1/17`
  - artifacts at:
    - `reports/review-assist-entity-alias-batch-001.json`
    - `reports/review-assist-entity-alias-batch-001.md`
    - `reports/review-assist-2026-03-25-entity-alias-batch-001.md`

## What Closed Since v6

- Operators can now work the review residue one batch at a time without scanning or rewriting the full report.
- Batch exports are stable and non-destructive relative to the main dated full-report artifacts.
- The batch-focused JSON payload preserves both total filtered counts and selected-batch scope, which is enough to support downstream checklist or audit tooling.

## New Frontier

The next leverage point is no longer basic batch access. It is improving operator throughput inside each batch while preserving the human boundary on `entity-alias`.

## Recommended Immediate Sequence

1. Add per-group ranking and checklist cues inside selected batches:
   - generic-term flags
   - score ordering already exists; add explicit review-rationale ordering aids
   - optional “likely reject” hint buckets without auto-resolution
2. Add a compact batch manifest or checklist export for human review notes.
3. Sample several `disjoint` batches manually and quantify precision for a conservative reject workflow.
4. Only if that sample is strong, design a reversible reject-assist command that proposes decisions without mutating the queue by default.

## Guardrails

- Keep `entity-alias` batch tooling advisory, not self-executing.
- Preserve batch artifact history; prefer date-suffixed outputs for review sessions.
- Do not promote any auto-reject path without measured sampling on the live residue.
