# Post-Federated-Canon Forward Propulsion v4

**Date:** 2026-03-25
**Repository:** `conversation-corpus-engine`
**Basis:** post-direct-coverage completion across the full package

## Verified Current State

- `pytest -q` passes at `174 passed`.
- Every module under `src/conversation_corpus_engine/` now has a dedicated `tests/test_<module>.py` file.
- Claude export parity is landed and schema-backed.
- Provider discovery/export/catalog utilities have dedicated direct tests and a real nested document-export detection bug has been fixed.
- Local-session discovery/import helpers now have mocked direct coverage without depending on a real workstation session.
- The federated review queue still sits at `406` open items, all `entity-alias`.

## What Closed Since v3

- `paths.py` now has dedicated direct coverage.
- `governance_policy.py` now has dedicated direct coverage.
- `claude_local_session.py` now has dedicated direct coverage for root resolution, safe-storage selection, cookie loading/decryption seams, HTTP fetching, discovery summary assembly, bundle fetching, and rendering.
- `import_claude_local_session_corpus.py` now has dedicated direct coverage for bundle writing, contract patching, README rewriting, and end-to-end local-session import with mocked discovery/bundle acquisition.

## New Frontier

The bottleneck is no longer module-level blind spots. The next leverage point is live decision quality and operator workflow over already-proven mechanics.

## Recommended Immediate Sequence

1. Build a conservative review-assist layer for the remaining `entity-alias` queue without auto-merging by default.
2. Improve operator ergonomics around the review residue:
   - grouped/entity-centric review views
   - stable ordering and batching
   - review rationale surfaces based on existing semantic signals
3. Expand evaluation assets for high-value live behaviors rather than raw code coverage:
   - federation search/ranking regressions grounded in realistic corpus mixtures
   - provider refresh and candidate promotion scenario matrices
   - review-queue boundary tests that prove what must remain human-reviewed
4. Only after the review boundary is better supported, consider a narrowly scoped semantic assist pass for `entity-alias`.

## Guardrails

- Do not auto-consume the remaining `entity-alias` queue with aggressive heuristics.
- Prefer assistive review tooling and explicit rationale over silent acceptance/rejection.
- Keep future work focused on live correctness and operator leverage, not just increasing test count.
