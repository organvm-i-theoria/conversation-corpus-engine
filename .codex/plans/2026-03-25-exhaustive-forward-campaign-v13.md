# Exhaustive Forward Campaign v13

**Date:** 2026-03-25
**Repository:** `conversation-corpus-engine`
**Basis:** multi-window evidence campaign plus proposal-vs-manual comparison machinery

## Verified Current State

- `python3 -m pytest -q` passes at `212 passed`.
- The review subsystem now has five linked layers:
  - grouped queue assist
  - batch guidance/checklists
  - cross-batch sampling
  - sample summaries
  - assistant proposal sidecars
  - proposal-vs-manual comparison summaries
- Session artifact naming now has microsecond precision, so rapid successive runs no longer overwrite each other.

## What Closed In This Pass

### 1. Evidence Campaign Widening

Sampling is no longer limited to the front of the queue. The system now supports `--batch-offset`, which made it possible to generate distinct windows across the remaining residue.

### 2. Comparison Machinery

The repository now has a `review sample-compare` flow that compares:

- manual outcomes from a sample markdown packet
- assistant outcomes from a proposal JSON sidecar

and computes:

- matched sample count
- adjudicated count
- agreement / disagreement
- proposal reject precision
- confidence-sliced precision
- disagreement examples

### 3. Collision Fix

Session artifact timestamps now include subsecond precision, which fixed real overwrite collisions during rapid campaign generation.

### 4. Precision Nullability Fix

Comparison precision no longer reports `0.0` when there are no adjudicated decisions. It now correctly reports `null` / `n/a` until evidence exists.

## Campaign Artifacts Generated

### Likely-Reject Front Window

- Sample packet:
  - `reports/review-assist-sample-2026-03-25-113955-087698.md`
- Proposal packet:
  - `reports/review-assist-sample-proposal-2026-03-25-113955-153880.json`
- Comparison packet:
  - `reports/review-assist-sample-compare-2026-03-25-113955-214366.md`
- Shape:
  - `12` groups
  - `40` items
  - first `5` matching batches

### Likely-Reject Mid Window

- Sample packet:
  - `reports/review-assist-sample-2026-03-25-113955-292340.md`
- Proposal packet:
  - `reports/review-assist-sample-proposal-2026-03-25-113955-359652.json`
- Comparison packet:
  - `reports/review-assist-sample-compare-2026-03-25-113955-431196.md`
- Shape:
  - `12` groups
  - `24` items
  - batch offset `5`

### Likely-Reject Late Window

- Sample packet:
  - `reports/review-assist-sample-2026-03-25-113955-509034.md`
- Proposal packet:
  - `reports/review-assist-sample-proposal-2026-03-25-113955-569999.json`
- Comparison packet:
  - `reports/review-assist-sample-compare-2026-03-25-113955-632589.md`
- Shape:
  - `12` groups
  - `12` items
  - batch offset `10`

### Needs-Context Window

- Sample packet:
  - `reports/review-assist-sample-2026-03-25-113955-712523.md`
- Proposal packet:
  - `reports/review-assist-sample-proposal-2026-03-25-113955-776476.json`
- Comparison packet:
  - `reports/review-assist-sample-compare-2026-03-25-113955-906094.md`
- Shape:
  - `8` groups
  - `18` items
  - first `10` matching batches

## True State Of The Evidence

The campaign infrastructure is now broad enough. The missing ingredient is still the same one:

- all comparison packets currently show `0` adjudicated
- proposal precision remains `null`
- no empirical permission exists yet to automate queue decisions

That is not a tooling limitation anymore. It is an adjudication limitation.

## Updated Large-Scale Order

### Swathe I: Human-Adjudicated Evidence Campaign

Now ready in full. The repository has multiple sample windows across the queue, including both `likely-reject` and `needs-context`.

### Swathe II: Proposal-vs-Human Calibration

Now mechanically ready. The comparison engine exists and will produce real precision once the sample packets are filled.

### Swathe III: Safe Queue-Application Engine

Still blocked on actual calibration evidence. The bridge to queue mutation should not be built as live policy yet.

### Swathe IV: Queue Liquidation Program

Not yet justified. It remains downstream of measured precision.

### Swathe V: Release / Policy / Operations

Still necessary, but it would be premature to freeze policy before adjudication data exists.

## Immediate Next Action

The next action is no longer code invention. It is to adjudicate the generated packets:

1. Fill manual outcomes in the front, mid, late, and `needs-context` sample markdown files.
2. Re-run `review sample-summary` on each.
3. Re-run `review sample-compare` on each.
4. Then aggregate whether:
   - `likely-reject` proposals are truly precise
   - `needs-context` proposals are appropriately conservative

Only after that does it become rational to build the safe queue-application engine as the next dominant swathe.
