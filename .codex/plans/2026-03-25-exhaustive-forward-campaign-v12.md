# Exhaustive Forward Campaign v12

**Date:** 2026-03-25
**Repository:** `conversation-corpus-engine`
**Intent:** replace incremental local motion with a few large, defensible workstreams that materially change the system

## Current Baseline

- Test suite is green at `204 passed`.
- Direct module-level test coverage is already broad across `src/conversation_corpus_engine/`.
- The federated review queue is down to a human-boundary residue:
  - `406` open items
  - effectively all remaining work is `entity-alias`
- The review workflow stack now exists end to end:
  - queue grouping and batching
  - batch guidance and checklist export
  - cross-batch sampling
  - sample precision summarization
  - assistant proposal sidecar generation
- The live sample packet is still unadjudicated:
  - `12` sampled groups
  - `12` pending manual outcomes
- The live assistant proposal sidecar currently says:
  - `reject=12`
  - `high=12`
- No evidence yet exists that those proposals are actually correct at scale.

## Campaign Shape

This should not proceed as another string of local conveniences. The next meaningful body of work is five large swathes:

1. **Human-Adjudicated Evidence Campaign**
2. **Proposal-vs-Human Measurement and Calibration**
3. **Safe Queue-Application Engine**
4. **Queue Liquidation Program**
5. **Release, Policy, and Operational Hardening**

Each swathe has a hard gate. No later swathe should be treated as live policy until the previous one is empirically justified.

---

## Swathe I: Human-Adjudicated Evidence Campaign

### Objective

Turn the current review sample machinery into actual evidence by completing enough manual adjudication to say something true about the `likely-reject` residue.

### Deliverables

- Complete manual outcomes for the existing `12`-group sample packet.
- Generate multiple additional sample packets covering different queue regions:
  - first-window batches
  - mid-queue batches
  - late-queue batches
  - any `needs-context` residue
- Establish a stable adjudication corpus of completed sample packets.

### Required Work

- Fill the current packet by hand.
- Generate at least three more timestamped sample sessions, not just one.
- Ensure each completed sample packet is followed immediately by a summary run.
- Preserve all packet history; never overwrite a sample session after adjudication.

### Exit Criteria

- At least `40-60` groups manually adjudicated.
- Precision summaries exist for each completed sample session.
- The repository has enough completed evidence to compare buckets, not just one anecdotal packet.

### Why This Matters

Without this swathe, everything else is theater. The queue may look machine-solvable, but until manual adjudication exists, no proposal, no assist command, and no policy can claim legitimacy.

---

## Swathe II: Proposal-vs-Human Measurement and Calibration

### Objective

Measure whether the assistant proposal sidecar is actually useful, and if so, where it is useful and where it is wrong.

### Deliverables

- A comparison summarizer between:
  - completed sample packets
  - assistant proposal packets
- Metrics that matter:
  - proposal reject precision
  - disagreement rate
  - false-positive rate
  - bucket-specific precision
  - confidence-specific precision
- Calibration output showing whether `high` confidence is deserved.

### Required Work

- Build a comparer that joins manual outcomes with assistant outcomes by sampled anchor/review IDs.
- Split results by:
  - `likely-reject`
  - `needs-context`
  - label-signal presence
  - confidence band
- Surface disagreement examples directly in the output artifact, not only aggregate counts.

### Exit Criteria

- Measured precision for assistant proposals exists across a nontrivial adjudicated sample set.
- We know whether `assistant=reject/high` is real signal or optimism.
- We have explicit examples of failure modes, not just percentages.

### Why This Matters

This swathe answers the only question that matters before automation: “When the assistant says reject, how often is it right, and what kind of wrong is it?”

---

## Swathe III: Safe Queue-Application Engine

### Objective

Build the machinery that could apply decisions at scale, but keep it reversible, inspectable, and non-default until evidence warrants activation.

### Deliverables

- A proposal-to-queue bridge that can convert reviewed sample/proposal material into candidate queue actions.
- A non-mutating “stage queue actions” flow that produces:
  - proposed decisions
  - candidate affected `review_id`s
  - rationale bundle
  - rollback metadata
- A dry-run artifact for bulk review operations.

### Required Work

- Define an action manifest format for queue proposals.
- Add a staging command that reads approved decisions and produces a candidate action set.
- Add replay/rollback semantics before any live mutation command exists.
- Require explicit operator approval before queue writes.

### Exit Criteria

- We can stage queue decisions in bulk without mutating the queue.
- Every staged action is traceable back to:
  - source sample packet
  - summary/comparison metrics
  - explicit rationale
- Reversibility is designed before any “apply” path is exposed.

### Why This Matters

The project does not need another smart report. It needs a trustworthy transition from evidence to action. This swathe creates that bridge.

---

## Swathe IV: Queue Liquidation Program

### Objective

Use the evidence and safe action machinery to collapse the remaining review residue in large, policy-backed waves rather than by hand one item at a time.

### Deliverables

- A queue campaign plan split by bucket/class:
  - `likely-reject`
  - `needs-context`
  - any residual non-entity cases that reappear
- Approved bulk-decision waves for the safe cases.
- A sharply reduced queue with the true hard cases isolated.

### Required Work

- Run the calibrated proposal engine against the entire residue.
- Stage decisions for the high-confidence reject slice only if the measured precision justifies it.
- Keep `needs-context` as manual unless evidence shows otherwise.
- Rebuild federation after each approved decision wave and confirm no regressions in review-state artifacts.

### Exit Criteria

- The queue is reduced from “large residue” to “small explicitly hard residue.”
- High-confidence repetitive rejects are no longer clogging operator attention.
- Remaining items are the ones that genuinely need thought.

### Why This Matters

This is the swathe that actually moves the product from “well-instrumented review system” to “review burden materially removed.”

---

## Swathe V: Release, Policy, and Operational Hardening

### Objective

Turn the new review machinery into a stable, documented, operable subsystem rather than a clever internal toolchain.

### Deliverables

- CI and quality closure:
  - restore `ruff` in the environment or document an equivalent enforced lint path
  - keep `pytest` green through the whole review campaign
- Operator documentation for:
  - sample generation
  - manual adjudication
  - summary/comparison reading
  - proposal staging
  - rollback expectations
- Policy documentation describing:
  - what qualifies for reject-assist
  - what stays manual
  - what evidence threshold is required before enabling automation
- End-to-end smoke flow in docs:
  - generate sample
  - fill packet
  - summarize
  - compare
  - stage proposed actions

### Required Work

- Write durable command docs, not ephemeral chat knowledge.
- Add fixture-backed smoke tests where possible for the multi-command workflow.
- Make the reporting artifacts consistent enough that outside operators can use them.

### Exit Criteria

- The review subsystem can be run by someone who did not build it.
- Policy boundaries are written down, not remembered informally.
- The system is ready for repeated future campaigns, not just this one residue.

### Why This Matters

Without this swathe, the repository risks becoming a one-off heroic intervention rather than a reusable engine.

---

## Ordered Program

If this campaign is executed correctly, the order should be:

1. Finish Swathe I completely enough to generate real adjudication evidence.
2. Execute Swathe II to learn whether assistant proposals deserve trust.
3. Build Swathe III so trust can become staged action rather than free-floating confidence.
4. Use Swathe IV to liquidate the queue in policy-backed waves.
5. Finish Swathe V so the system survives beyond the current operator context.

## Hard Gates

- **Gate A:** no queue automation before adjudicated sample evidence exists.
- **Gate B:** no reject-assist application before proposal-vs-human precision is measured.
- **Gate C:** no live bulk queue mutation before staging + rollback are implemented.
- **Gate D:** no policy claim without persisted artifacts proving the claim.

## Concrete Success Condition

This campaign is successful only if it produces all of the following:

- a materially smaller live queue
- a measured and defensible reject-assist policy
- a reversible application path
- a documented operator workflow
- a stable subsystem that can be rerun on future corpus residues

## Immediate Next Action

The next action is not more code invention in the abstract. It is to complete Swathe I:

- adjudicate the current `12`-group packet
- generate additional sample packets
- summarize each packet
- only then begin the proposal-vs-human comparison machinery in earnest

That is the first large swathe of color. The rest of the campaign depends on it.
