# Post-Federated-Canon Forward Propulsion

**Date:** 2026-03-25
**Repository:** `conversation-corpus-engine`
**Basis:** direct module/test map after adding `tests/test_federated_canon.py`, persisted S33 forward plan, and current suite collection behavior

## Verified Current State

- `federated_canon.py` now has a dedicated direct regression suite.
- `pytest -q tests/test_federated_canon.py tests/test_federation.py` passes.
- The current highest-risk core blind spot is still `answering.py` (`1287` lines) because it owns document building, scoring, reranking, evidence selection, answer-state resolution, rendering, and dossier persistence.
- `source_lifecycle.py` (`309` lines) and `cli.py` (`822` lines) still have no dedicated direct test modules.
- `pytest --collect-only -q` currently fails at `tests/test_dashboard.py` because it imports `tests.conftest` as if `tests/` were a package.
- The following modules still have no dedicated `tests/test_<module>.py` file: `claude_local_session.py`, `cli.py`, `governance_policy.py`, `import_claude_local_session_corpus.py`, `paths.py`, `provider_catalog.py`, `provider_discovery.py`, `provider_exports.py`, `source_lifecycle.py`.

## Objective

Convert the new `federated_canon` coverage into broader engine confidence by proving the remaining core execution path end to end, then tighten contract completeness, adapter symmetry, and operational reliability in that order.

## Ordering Principle

1. Unblock cheap confidence first.
2. Prove the execution core before broadening the periphery.
3. Close test gaps in the same order users would feel breakage: answer quality, refresh correctness, command dispatch, import symmetry, contracts, then secondary utilities.
4. Prefer work that compounds across federation, provider refresh, evaluation, and live operator usage.

## Wave 0: Remove Friction From Validation

### Immediate target

Fix the `tests/test_dashboard.py` import pattern so `pytest --collect-only -q` and then `pytest -q` can run without a collection-time failure.

### Preferred approach

- Move reusable test helpers out of `conftest.py` into a normal helper module such as `tests/helpers.py`, or
- change the dashboard test to avoid importing `tests.conftest` as a package-level module.

### Exit condition

- Full suite collects cleanly.

## Wave 1: Finish Phase 1 Of The S33 Plan

### 1. `answering.py` direct tests

This is the next highest-leverage target.

#### Cover these functions directly

- `build_documents`
- `expand_query_tokens`
- `score_document`
- `rank_documents`
- `matched_family_ids_for_query`
- `rerank_thread_hits`
- `rerank_family_hits`
- `rerank_pair_hits`
- `merge_rankings`
- `search_documents_v4`
- `select_primary_evidence`
- `determine_answer_state`
- `build_answer`
- `render_answer_text`
- `render_answer_markdown`
- `save_answer_dossier`

#### Minimum test matrix

- canonical-thread bonuses versus non-canonical hits
- family/title exact-match reranking versus weaker lexical matches
- pair-focused search behavior
- citation materialization and evidence ordering
- grounded versus partial versus speculative answer-state resolution
- answer rendering with and without canon/federation evidence
- dossier write paths and expected artifact names

### 2. `source_lifecycle.py` direct tests

This module governs refresh correctness and is important for provider readiness, refresh, and dashboard truthfulness.

#### Cover these branches

- unsupported adapter type
- missing source input
- markdown top-level versus recursive collection
- transcript attachment discovery
- claude local session tracked-path collection
- supported export adapter collection through `provider_exports`
- `missing_snapshot`, `fresh`, `stale`, and `missing_source` freshness states
- fingerprint changes on metadata-only versus content changes where relevant

### 3. `cli.py` direct tests

The CLI is the operational front door and is too large to remain unproven.

#### Cover these behaviors

- threshold override parsing
- parser shape for core command groups
- `main()` dispatch for federation, provider, schema, surface, policy, candidate, review, dashboard, and evaluation commands
- argument-to-function wiring with monkeypatched handlers
- success-path stdout assertions where the CLI emits user-facing reports
- error-path assertions for missing required arguments or malformed overrides

### Exit condition

- The execution core no longer depends on indirect coverage alone.
- The suite can prove answer construction, refresh-state reasoning, and command dispatch directly.

## Wave 2: Shrink Human Review Load Again

Resume Phase 2 from the S33 plan after Wave 1 is green.

### Deliverables

- semantic-similarity triage for `entity-alias` using label-level comparison
- title-token overlap for `family-merge`
- canonical-question overlap for `unresolved-merge`
- canonical-action overlap for `action-merge`
- post-change queue measurement against the deployment dataset

### Exit condition

- The open review queue drops materially below `1,649`.
- Remaining queue items skew toward genuinely semantic human judgment rather than obvious machine-detectable overlap.

## Wave 3: Restore Adapter Symmetry

Resume the stored Claude parity work.

### Deliverables

- port ChatGPT rich-content extraction patterns into `import_claude_export_corpus.py`
- parity tests for code blocks, execution output, multimodal content, audit generation, and near-duplicate handling
- re-import the existing Claude export corpus through the upgraded path
- only after parity is proven, refresh the ChatGPT import path against a fresh export

### Exit condition

- Claude and ChatGPT ingest paths stop diverging in the highest-value content extraction behavior.

## Wave 4: Finish Contract And Ops Completeness

### Deliverables

- add schemas for `import-audit.json` and `near-duplicates.json`
- validate new provider import artifacts against those schemas
- fix provider-readiness field mapping in the dashboard if still present after Wave 0
- add CI for `pytest`, `ruff check`, and `ruff format --check`

### Exit condition

- Runtime artifacts that now matter to governance and review are no longer outside the formal contract system.

## Wave 5: Close The Utility Test Gaps

After the core is proven, add focused direct tests for the remaining modules without dedicated coverage:

- `provider_exports.py`
- `provider_catalog.py`
- `provider_discovery.py`
- `governance_policy.py`
- `paths.py`
- `claude_local_session.py`
- `import_claude_local_session_corpus.py`

These are lower priority than Waves 0 through 4 because they are either smaller, more static, or already exercised indirectly.

## Wave 6: Resume The Autopoietic Loop

Only after the engine is operationally tight:

- treat session transcripts as first-class source input
- design or implement the SpecStory/session adapter path
- expose live corpus memory through MCP once transcript ingest is stable

## Recommended Immediate Sequence

1. Fix the `test_dashboard.py` collection bug.
2. Add the first `answering.py` direct test tranche around document building, scoring, answer-state resolution, and citations.
3. Add a `source_lifecycle.py` state-matrix suite.
4. Add CLI parser/dispatch tests.
5. Run the full suite and then begin Wave 2 queue-reduction work.

## Non-Negotiable Rules

- Do not widen scope before the full suite collects cleanly.
- Do not call a module “covered” because another module happens to traverse it indirectly.
- Any new artifact that becomes review evidence should either get a schema or be explicitly marked provisional.
- Any queue-reduction heuristic should include a human-boundary test so automation does not silently over-merge memory.
