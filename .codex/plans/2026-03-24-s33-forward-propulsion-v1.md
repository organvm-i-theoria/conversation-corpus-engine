# S33 Forward Propulsion

**Date:** 2026-03-24
**Repository:** `conversation-corpus-engine`
**Basis:** Verified post-S33 state, persisted roadmap, and transcript-reconciled closure audit

## Objective

Convert S33 from a successful sweep into compounding leverage. The next wave should reduce structural risk in the engine, shrink the human review burden again, and tighten the loop between source ingest, federation, governance, and live consumption.

## Phase 1: Prove The Highest-Risk Core

1. Write the first real test suite for `federated_canon.py`.
2. Deepen `answering.py` coverage around document building, scoring, answer-state resolution, and citation behavior.
3. Add focused tests for `source_lifecycle.py` and then `cli.py`.

**Exit condition:** the core engine stops relying on a small perimeter of tests while its two most central modules remain under-proven.

## Phase 2: Spend The Review Queue

1. Add semantic-similarity triage for `entity-alias` items using label-level comparison, not ID-level shortcuts.
2. Add title-token overlap for `family-merge`.
3. Add canonical-question overlap for `unresolved-merge` and canonical-action overlap for `action-merge`.
4. Re-run triage against the deployment site and measure the new open count.

**Exit condition:** the queue drops well below the current `1,649` open items and the remaining work is increasingly human-semantic rather than machine-structural.

## Phase 3: Restore Adapter Symmetry

1. Port ChatGPT-side rich content extraction patterns into `import_claude_export_corpus.py`.
2. Add tests that prove parity on code, execution output, multimodal content, audit records, and near-duplicate detection.
3. Re-import the Claude export corpus from the existing inbox source.
4. Only after that, request a fresh ChatGPT export and repeat the upgraded import path.

**Exit condition:** Claude and ChatGPT are no longer asymmetrical in the richest part of the import pipeline.

## Phase 4: Tighten Operational Completeness

1. Add schemas for `import-audit.json` and `near-duplicates.json`.
2. Fix provider-readiness field mapping in the dashboard.
3. Add CI for `pytest`, `ruff check`, and `ruff format --check`.
4. Rebuild the surfaces and validate that the new artifacts stay contract-clean.

**Exit condition:** S33 capability additions are no longer partially outside the formal contract system.

## Phase 5: Close The Autopoietic Loop

1. Treat session transcripts as first-class corpus source.
2. Design or implement a SpecStory/session adapter path.
3. Build toward live corpus access through MCP once the transcript-ingest path is stable.

**Exit condition:** the engine can remember more of the conversations that created it and can expose that memory without static-export indirection.

## Non-Negotiable Rules

- Every “N/A” is a vacuum until proven otherwise.
- Every closure claim must be backed by scoped commands and files on disk.
- Every newly added automation policy must either encode its human boundary or defer explicitly.
- Every core feature that becomes governance evidence must also become test evidence.

## Immediate Starting Point

Start with `tests` for `src/conversation_corpus_engine/federated_canon.py`. It is still the highest-risk blind spot with the best leverage-to-effort ratio.
