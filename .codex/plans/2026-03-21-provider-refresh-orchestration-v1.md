# Provider Refresh Orchestration Plan

Date: 2026-03-21
Repo: `/Users/4jp/Workspace/organvm-i-theoria/conversation-corpus-engine`

## Goal

Add one canonical command that resolves provider authority, imports a fresh candidate corpus, evaluates it, stages the live-vs-candidate diff, and optionally promotes it.

## Scope

1. Add a `provider_refresh.py` orchestration layer.
2. Resolve the live provider lane using:
   - explicit `live_corpus_id`, or
   - provider source policy / registry defaults
3. Import the fresh source into a run-scoped candidate root under ignored runtime state.
4. Run seeded corpus evaluation after import.
5. Stage a corpus candidate automatically.
6. Optionally auto-approve and promote on explicit request.
7. Persist refresh reports and history.
8. Add a CLI surface under `cce provider refresh ...`.

## Non-Goals

- Auto-promote without explicit operator intent.
- Add queue UIs or precedent learning.
- Replace provider import or corpus candidate commands; this wraps them.

## Design

- `provider_refresh.py` will compose:
  - `import_provider_corpus`
  - `run_corpus_evaluation`
  - `stage_corpus_candidate`
  - `review_corpus_candidate`
  - `promote_corpus_candidate`
- Output roots will live under `state/provider-refresh/<provider>/<run-id>/candidate-corpus`.
- Refresh history and latest markdown/json reports will be written under ignored runtime paths.
- `provider_readiness` should recommend `cce provider refresh ...` when a provider is already healthy and a new inbox payload is waiting.

## Verification

- `python3 -m ruff check src tests`
- `python3 -m pytest -q`
- smoke test `cce provider refresh --provider perplexity --project-root ... --source-drop-root ...`
- smoke test `cce provider refresh --provider claude --project-root ... --candidate-root ... --promote`
