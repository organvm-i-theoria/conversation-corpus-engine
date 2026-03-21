# Corpus Candidate Promotion Plan

Date: 2026-03-21
Repo: `/Users/4jp/Workspace/organvm-i-theoria/conversation-corpus-engine`

## Goal

Add the canonical workflow for staging a newly built corpus against the live baseline, reviewing the diff, promoting it into the registry, and rolling it back safely.

## Scope

1. Add a corpus diff engine that compares:
   - corpus summary/evaluation/freshness
   - family, action, unresolved, and entity deltas
   - representative retrieval/answer outputs across live vs candidate
2. Add a candidate lifecycle for corpora:
   - stage from an explicit candidate root
   - resolve the live baseline by corpus id, provider, or default registry entry
   - review approve/reject
   - promote into the registry
   - rollback to the previous live root
3. Sync provider source authority when a promoted corpus replaces the root for a provider-owned corpus id.
4. Add CLI commands, reports, histories, and regression tests.

## Non-Goals

- Port staging-era precedent learning, hold groups, or auto-promote policy heuristics.
- Build provider refresh orchestration in this pass.
- Rework importer output layouts.

## Design

- `corpus_diff.py` will own structural/query diffing between a live and candidate corpus root.
- `corpus_candidates.py` will own stage/show/review/promote/rollback plus histories and latest reports.
- Candidate staging will not mutate the registry or provider authority.
- Promotion will update the live registry entry, rebuild federation, and optionally sync provider source policy roots.
- Rollback will restore the previous registry entry and previous provider source policy payload when captured.

## Verification

- `python3 -m ruff check src tests`
- `python3 -m pytest -q`
- smoke test `cce candidate stage --project-root ... --candidate-root ... --live-corpus-id ...`
- smoke test `cce candidate review --project-root ... --candidate-id latest --decision approve`
- smoke test `cce candidate promote --project-root ... --candidate-id latest`
- smoke test `cce candidate rollback --project-root ... --target previous`
