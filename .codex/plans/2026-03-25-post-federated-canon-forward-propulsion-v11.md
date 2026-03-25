# Post-Federated-Canon Forward Propulsion v11

**Date:** 2026-03-25
**Repository:** `conversation-corpus-engine`
**Basis:** assistant proposal sidecar for review sample packets

## Verified Current State

- `python3 -m pytest -q` passes at `204 passed`.
- `review sample-propose` now supports:
  - parsing an existing sample markdown packet
  - assigning assistant outcome/confidence/rationale per sampled group
  - writing separate proposal artifacts without mutating the original sample packet
- Live proposal run against `reports/review-assist-sample-latest.md`:
  - `12` total samples
  - assistant outcomes:
    - `reject=12`
  - assistant confidence:
    - `high=12`
  - artifacts at:
    - `reports/review-assist-sample-proposal-latest.json`
    - `reports/review-assist-sample-proposal-latest.md`
    - `reports/review-assist-sample-proposal-2026-03-25-110903.json`
    - `reports/review-assist-sample-proposal-2026-03-25-110903.md`
- The original sample packet and summary packet remain untouched:
  - manual outcomes are still blank in `reports/review-assist-sample-latest.md`
  - precision remains uncomputed in `reports/review-assist-sample-summary-latest.md`

## What Closed Since v10

- The repository now has a three-layer review loop:
  - sample packet for human adjudication
  - summary packet for measured precision
  - assistant proposal sidecar for faster operator review
- This gives a way to compare assistant recommendations against later manual outcomes without overwriting the adjudication source artifact.

## New Frontier

The next leverage point is comparison, not more proposal generation: once manual outcomes are filled in, compare them against the assistant proposal sidecar and measure assistant reject precision / disagreement rate.

## Recommended Immediate Sequence

1. Fill manual outcomes in the current `12`-group sample packet.
2. Re-run `review sample-summary` to compute actual reject precision.
3. Add a comparison summarizer between:
   - sample packet manual outcomes
   - assistant proposal packet outcomes
4. Use that disagreement data to decide whether a non-mutating reject-assist proposal command is warranted for the main queue.

## Guardrails

- Keep assistant proposals sidecar-only; do not overwrite manual adjudication fields.
- Do not infer queue policy from proposal counts alone.
- Treat assistant proposal precision as an empirical question to be measured against completed sample packets.
