# Governance And Promotion Extraction Plan

Date: 2026-03-21
Repo: `/Users/4jp/Workspace/organvm-i-theoria/conversation-corpus-engine`

## Goal

Add the canonical governance layer so the repo can decide, review, and promote changes instead of only importing and evaluating corpora in isolation.

## Scope

1. Generalize provider source authority into a repo-native source-policy system for all providers.
2. Add a live promotion policy with persisted thresholds and simple calibration metadata.
3. Add replay over the current registered corpus set using evaluation summaries and source freshness.
4. Add a policy-candidate lifecycle:
   - stage threshold overrides
   - review approve/reject
   - apply to the live policy
   - rollback to the previous live policy
5. Write diff, replay, application, and history artifacts under ignored runtime paths.
6. Add canonical CLI commands and regression tests.

## Non-Goals

- Port the entire staging precedent engine, synthetic scenario curriculum, or policy shadow experimentation framework.
- Recreate every historical report shape from staging.
- Govern arbitrary candidate-build manifests in this pass.

## Design

- `source_policy.py` will own provider primary/fallback authority decisions and histories.
- `governance_policy.py` will own the live promotion policy and calibration file.
- `governance_replay.py` will replay the live or overridden policy against registered corpora.
- `governance_candidates.py` will own stage/review/apply/rollback plus reports and histories.
- Replay will key off existing corpus summaries, evaluation gates, and freshness state rather than staging-only candidate-build artifacts.
- Provider readiness and provider target selection will consume the new source-policy layer.

## Verification

- `python3 -m ruff check src tests`
- `python3 -m pytest -q`
- smoke test `cce policy replay --project-root ... --json`
- smoke test `cce policy stage --project-root ... --set-threshold key=value --json`
- smoke test `cce policy apply --project-root ... --candidate-id ... --json`
