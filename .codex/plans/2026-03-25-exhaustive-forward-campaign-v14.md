# Exhaustive Forward Campaign v14

Date: 2026-03-25
Project: `/Users/4jp/Workspace/organvm-i-theoria/conversation-corpus-engine`

## Completed in v14

- Codified the standard multi-window entity-alias evidence program into a first-class workflow.
- Added reusable campaign build/render/write logic in `src/conversation_corpus_engine/triage.py`.
- Added `cce review campaign` in `src/conversation_corpus_engine/cli.py`.
- Added campaign regression coverage in `tests/test_triage.py` and `tests/test_cli.py`.
- Verified focused coverage at `77 passed`.
- Verified full suite at `217 passed`.
- Ran the live campaign end to end and wrote campaign + per-scenario artifacts under `reports/`.

## Live Campaign Snapshot

- Scenarios: `likely_front`, `likely_mid`, `likely_late`, `needs_context`
- Sampled groups: `44`
- Sampled items: `94`
- Assistant outcomes: `reject=36`, `needs-context=8`
- Adjudicated manual outcomes: `0`
- Proposal reject precision: `n/a` until manual packet completion exists

## New Operational Surface

- `cce review campaign --project-root <root> --write`
- Optional narrowing: `--scenario likely_front` (repeatable)
- Output now includes:
  - aggregate campaign manifest
  - per-scenario sample artifacts
  - per-scenario summary artifacts
  - per-scenario proposal artifacts
  - per-scenario comparison artifacts

## Current Gate

The technical orchestration gate is now closed. The blocking gate is evidence, not machinery:

1. Fill manual outcomes in one or more campaign sample packets.
2. Rerun `cce review sample-summary` and `cce review sample-compare` on adjudicated packets.
3. Measure proposal precision and disagreement rates from real outcomes.
4. Only then design a reversible reject-assist staging/apply path.

## Logical Next Swathe

If continuing autonomously before manual adjudication lands:

1. Add a packet-index/ledger surface that inventories all generated sample/proposal/compare artifacts and their adjudication status.
2. Add a comparison rollup command that aggregates multiple completed campaign packets instead of one packet at a time.
3. Add a reversible staging format for candidate reject actions, but keep it non-applying until human precision thresholds are satisfied.

If manual adjudication lands first:

1. Recompute comparison metrics across the adjudicated campaign windows.
2. Derive a conservative precision threshold for reject-assist.
3. Build a proposal-to-staging bridge with rollback semantics.
