# Post-Federated-Canon Forward Propulsion v2

**Date:** 2026-03-25
**Repository:** `conversation-corpus-engine`
**Basis:** post-triage queue collapse, Claude adapter parity landing, and contract-catalog expansion

## Verified Current State

- `pytest -q` passes at `130 passed`.
- The federated review queue has been collapsed from `4272` open items to `406`, and the remaining open items are all `entity-alias`.
- `import_claude_export_corpus.py` now has parity-grade support for richer content extraction, per-thread import audit output, and near-duplicate prompt detection.
- The schema catalog now includes `import-audit` and `near-duplicates`, with real generated artifacts validated in tests.
- Dedicated direct tests now exist for `federated_canon.py`, `source_lifecycle.py`, `cli.py`, and expanded `answering.py`, `triage.py`, and Claude importer coverage.
- The remaining modules without dedicated `tests/test_<module>.py` files are:
  - `claude_local_session.py`
  - `governance_policy.py`
  - `import_claude_local_session_corpus.py`
  - `paths.py`
  - `provider_catalog.py`
  - `provider_discovery.py`
  - `provider_exports.py`

## What Closed Since v1

- Wave 0 closed: dashboard collection failure fixed and full suite collection restored.
- Wave 1 core confidence closed enough for now: `answering.py`, `source_lifecycle.py`, and `cli.py` all received direct coverage.
- Wave 2 largely closed on the obvious machine-detectable side: triage heuristics now collapse the queue down to the human-boundary `entity-alias` residue.
- Wave 3 closed: Claude export adapter parity is now materially aligned with the richer ChatGPT import path.
- Wave 4 partially closed: `import-audit.json` and `near-duplicates.json` now have published schemas and real validation coverage.

## Remaining Objective

Convert the now-proven engine core into operational durability: CI enforcement, final contract hygiene, and deliberate handling of the remaining `entity-alias` review boundary.

## Recommended Immediate Sequence

1. Add CI under `.github/workflows/` for editable install plus `pytest`, `ruff check`, and `ruff format --check`.
2. Finish direct test coverage for the remaining utility modules, starting with `provider_exports.py`, `provider_discovery.py`, and `provider_catalog.py`.
3. Add focused direct coverage for `governance_policy.py` and `paths.py` to tighten policy and filesystem invariants.
4. Decide whether the remaining `406` `entity-alias` items should stay explicitly human-reviewed or get a new semantically conservative assist layer.
5. Only after that, resume the longer-horizon local-session and transcript ingest path through `claude_local_session.py` and `import_claude_local_session_corpus.py`.

## Guardrails

- Do not burn down the remaining `entity-alias` queue with aggressive auto-merge heuristics unless they ship with explicit human-boundary regression tests.
- Do not add CI that assumes workstation-only tools; the workflow should provision its own lint/test dependencies.
- Keep contract additions paired with validation tests the same turn they are introduced.
- Preserve plan history by appending new dated versions instead of mutating prior plan files.
