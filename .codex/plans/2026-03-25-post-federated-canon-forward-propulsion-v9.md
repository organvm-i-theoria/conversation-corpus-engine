# Post-Federated-Canon Forward Propulsion v9

**Date:** 2026-03-25
**Repository:** `conversation-corpus-engine`
**Basis:** live cross-batch sampling workflow for `likely-reject` review groups

## Verified Current State

- `python3 -m pytest -q` passes at `193 passed`.
- `review assist` now supports:
  - relation filters
  - source-pair filter
  - anchor substring filter
  - batch selection
  - review-bucket filtering
  - cross-batch sampling
  - timestamped sample-session artifacts
- Live sample run with:
  - `review assist --relation disjoint --bucket likely-reject --sample-groups 12 --sample-batches 5 --write --json`
  produced:
  - `12` sampled groups
  - `40` items within the sampled groups
  - from `36` candidate `likely-reject` groups
  - across `5` candidate batches
  - from `400` filtered disjoint items
  - from `406` open entity-alias items
  - artifacts at:
    - `reports/review-assist-sample-latest.json`
    - `reports/review-assist-sample-latest.md`
    - `reports/review-assist-sample-2026-03-25-105452.json`
    - `reports/review-assist-sample-2026-03-25-105452.md`

## What Closed Since v8

- The repository now has an actual live sampling workflow, not just bucket labels.
- Operators can generate timestamped review packets that span several batches while preserving session history.
- The sample artifacts now contain explicit proposed outcome placeholders, manual outcome fields, and per-group review checklists.

## New Frontier

The next leverage point is no longer tooling. It is adjudication and measurement: take one or more generated sample packets, record manual outcomes, and calculate whether `likely-reject` is precise enough to justify a reversible reject-assist workflow.

## Recommended Immediate Sequence

1. Review the current sample packet and record manual outcomes for all `12` sampled groups.
2. Add a lightweight precision summarizer that reads a completed sample packet and reports reject precision / false-positive rate.
3. Only if that precision is convincingly high, design a non-mutating reject-assist command that proposes queue decisions for operator approval.
4. If precision is weak, refine the bucket heuristics and resample rather than automating.

## Guardrails

- Do not mutate the queue from the sampling workflow.
- Treat `likely-reject` as a hypothesis until manual adjudication confirms it.
- Preserve timestamped sample-session artifacts so measurement history remains auditable.
