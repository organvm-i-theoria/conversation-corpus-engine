# Evaluation Extraction Plan

Date: 2026-03-21
Repo: `/Users/4jp/Workspace/organvm-i-theoria/conversation-corpus-engine`

## Goal

Move the seeded evaluation and bootstrap workflow out of staging and into the canonical Organ I repo so imported corpora can advance from scaffolding to reproducible scorecards and gates.

## Scope

1. Extract the seeded evaluation core:
   - seeded/manual fixture resolution
   - retrieval and answer evaluation
   - regression gate computation
   - report rendering and output path generation
2. Extract provider-aware evaluation bootstrap:
   - resolve provider target roots
   - seed gold/manual templates
   - write manual review guidance
   - optionally run full evaluation and persist outputs
3. Wire canonical CLI commands so `cce` can:
   - run evaluation for a corpus root
   - bootstrap provider evaluation with optional full eval
4. Update provider import/bootstrap flows to use the canonical evaluation bootstrap instead of empty placeholder files.
5. Add regression tests for seeded evaluation and provider bootstrap.

## Non-Goals

- Port the full policy candidate, shadow policy, or replay governance stack in this pass.
- Port every historical report artifact shape from staging.
- Redesign evaluation semantics; extraction should stay behaviorally close to staging.

## Design

- Add `evaluation.py` for reusable scoring and fixture logic.
- Add `evaluation_bootstrap.py` for provider-target resolution and report generation.
- Keep provider-specific entrypoints thin and route them through the bootstrap module.
- Preserve runtime outputs under corpus-local `eval/` and `reports/`, which remain ignored.
- Prefer canonical command surfaces over staging script names.

## Verification

- `python3 -m ruff check src tests`
- `python3 -m pytest -q`
- smoke test `cce evaluation run --root ... --seed --json`
- smoke test `cce provider bootstrap-eval --provider ... --target-root ... --full-eval --json`
