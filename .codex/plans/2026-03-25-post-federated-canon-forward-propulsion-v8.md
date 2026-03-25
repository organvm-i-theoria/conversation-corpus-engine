# Post-Federated-Canon Forward Propulsion v8

**Date:** 2026-03-25
**Repository:** `conversation-corpus-engine`
**Basis:** batch-scoped review guidance and checklist export

## Verified Current State

- `python3 -m pytest -q` passes at `187 passed`.
- `review assist` batch mode now produces:
  - selected-batch payload narrowing
  - group-level review buckets
  - signal flags
  - explicit checklist actions
  - dedicated batch checklist Markdown export
- Live run with `--relation disjoint --batch-id entity-alias-batch-001 --write --json` produced:
  - `23` selected items
  - from `400` filtered disjoint items
  - from `406` open entity-alias items
  - `6` groups in batch `1/17`
  - bucket mix:
    - `5` `likely-reject`
    - `1` `needs-context`
  - signal mix:
    - `6` groups with `all-zero-overlap`
    - `5` groups with `has-low-specificity-labels`
    - `1` group with `has-high-score-disjoint-pairs`
  - artifacts at:
    - `reports/review-assist-entity-alias-batch-001.json`
    - `reports/review-assist-entity-alias-batch-001.md`
    - `reports/review-assist-entity-alias-batch-001-checklist.md`
    - `reports/review-assist-2026-03-25-entity-alias-batch-001.md`

## What Closed Since v7

- The operator no longer has to infer likely action from raw scores and labels alone.
- Selected batches now come with explicit review cues that separate probable rejects from cases needing contextual inspection.
- The batch workflow now has a dedicated checklist artifact suitable for manual review passes.

## New Frontier

The next leverage point is not more rendering. It is evidence-backed sampling: measure how accurate the `likely-reject` bucket actually is on live residue before designing any reject-assist workflow.

## Recommended Immediate Sequence

1. Sample multiple live `likely-reject` groups across several batches and record accept/reject precision.
2. Add a lightweight sample-report artifact so those measurements persist next to the checklist outputs.
3. If precision is strong, design a reversible reject-assist command that proposes decisions without mutating the queue by default.
4. If precision is weak, refine the bucket heuristics with more context-sensitive signals rather than automating.

## Guardrails

- Treat `likely-reject` as an operator aid, not a policy decision.
- Require measured sampling before any bulk or semi-bulk rejection workflow.
- Preserve artifact history for every review batch and sample session.
