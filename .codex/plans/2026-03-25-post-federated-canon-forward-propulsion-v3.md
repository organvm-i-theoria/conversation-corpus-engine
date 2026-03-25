# Post-Federated-Canon Forward Propulsion v3

**Date:** 2026-03-25
**Repository:** `conversation-corpus-engine`
**Basis:** post-Claude parity, post-audit schema catalog expansion, post-provider utility test extraction

## Verified Current State

- `pytest -q` passes at `148 passed`.
- The federated review queue remains reduced to `406` open items, all in the `entity-alias` category.
- Claude import parity is landed: richer message extraction, `import-audit.json`, near-duplicate prompt detection, and matching contract/result counts.
- The schema catalog now publishes `import-audit` and `near-duplicates`, and real generated artifacts validate against them.
- A real discovery bug in nested document-export inboxes was fixed: multiple child candidates no longer collapse into a false `ready` state at the inbox root.
- Dedicated direct test files now exist for:
  - `federated_canon.py`
  - `source_lifecycle.py`
  - `cli.py`
  - `provider_exports.py`
  - `provider_discovery.py`
  - `provider_catalog.py`

## Remaining Modules Without Dedicated Direct Tests

- `claude_local_session.py`
- `governance_policy.py`
- `import_claude_local_session_corpus.py`
- `paths.py`

## Immediate Objective

Finish shrinking the remaining direct-coverage blind spots while keeping the human-boundary review queue intentionally conservative.

## Recommended Immediate Sequence

1. Add direct tests for `paths.py` and `governance_policy.py`.
2. Add a contained test tranche for `claude_local_session.py` that avoids workstation-coupled assumptions and focuses on pure helpers or mocked boundaries.
3. Add direct tests for `import_claude_local_session_corpus.py` once the local-session helper seams are proven.
4. Reassess whether the remaining `entity-alias` queue should stay manual or receive a new, explicitly conservative assist layer.

## Guardrails

- Keep `entity-alias` automation conservative; do not spend the remaining human-boundary residue by over-merging.
- Prefer pure/helper-level tests for workstation-sensitive modules before attempting broader integration coverage.
- Persist every roadmap revision as a new plan file; do not mutate v1 or v2.
