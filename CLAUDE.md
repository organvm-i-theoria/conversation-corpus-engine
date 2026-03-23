# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Canonical ENGINE for multi-provider AI conversation memory. Functional class: ENGINE. Formation type: GENERATOR. Signal signature: `(Σ,Π,Θ) → (Σ,Π,Ω,Δ)`. Zero runtime dependencies beyond stdlib.

Owns: provider import, corpus validation, evaluation, federation, governance policy, Meta/MCP surface exports.

Sibling deployment site: `../conversation-corpus-site/` (RESERVOIR, FORM-RES-001, not git). 5 live corpora, 744 federated families, 3,542 actions. ChatGPT is the genesis provider (55-thread corpus with manual gold fixtures, all gates pass).

## Constitutional Context

This repo exists within a system transitioning from numbered organs to named functions (SPEC-019). The current state:

- **Placement:** Theoria (knowledge AND memory). META is genome (law only). Proof: `post-flood/specs/PROOF-reservoir-placement.md`
- **Direction:** SPEC-019 System Manifestation defines the liquid model — formations declare function participation (`participates_in`) rather than organ ownership. Signal composability via set intersection. Mneme (memory) is the 8th physiological function.
- **Signal vocabulary:** 14 post-flood classes per Formation Protocol §8.1. Greek letter variables: Σ=ANNOTATED_CORPUS, Π=ARCHIVE_PACKET, Θ=EXECUTION_TRACE, Ω=VALIDATION_RECORD, Δ=STATE_MODEL, Λ=RULE_PROPOSAL, Ι=INTERFACE_CONTRACT. See `seed.yaml` for this repo's full signal I/O.
- **Reservoir Law:** RESERVOIR formations cannot emit ONT_FRAGMENT (Φ) or RULE_PROPOSAL (Λ). The site obeys this; the engine enforces it.
- **Functional class is orthogonal to organ.** Do not use the dependency DAG (I→II→III) to decide where knowledge lives — use the information graph (E^info), which is constitutionally cyclic.

## Commands

```bash
pip install -e ".[dev]"

# Tests
python -m pytest tests/ -v
python -m pytest tests/test_file.py::ClassName::test_name -v   # single test

# Lint + format (both required — CI runs both)
pipx run ruff check src/ tests/
pipx run ruff format --check src/ tests/

# Operate against the deployment site
export $(cat ../conversation-corpus-site/.cce-env | grep -v '^#' | xargs)
cce corpus list
cce provider readiness --write
cce surface bundle
cce evaluation run --root /path/to/corpus --seed --json
```

## Architecture

29 modules in `src/conversation_corpus_engine/`, flat structure. No subpackages. 8 JSON schemas in `schemas/`.

### Module Relationships

`answering.py` is the shared utility layer — `load_json`, `write_json`, `write_markdown`, `slugify`, `tokenize`, `search_documents_v4`, `build_answer`. Nearly every other module imports from it.

`provider_catalog.py` defines `PROVIDER_CONFIG` (6 providers). `provider_discovery.py` scans source-drop inboxes using detection functions from `provider_exports.py`. `provider_import.py` routes each provider to its adapter and orchestrates import → bootstrap eval → register → federation build.

Import adapters produce identical corpus artifact sets (threads-index, pairs-index, doctrine-briefs, canonical-families, etc.):
- `import_chatgpt_export_corpus.py` — walks ChatGPT `mapping` tree (parent/children pointers), linearizes by `create_time`
- `import_claude_export_corpus.py` — parses Claude `conversations.json` + `users.json` bundle
- `import_claude_local_session_corpus.py` — reads from `~/Library/Application Support/Claude`
- `import_document_export_corpus.py` — generic multi-format (md/html/json/csv/zip) → normalizes to markdown → delegates to `import_markdown_document_corpus.py`

`evaluation.py` runs seeded/manual gold fixtures through regression gates (8 metric thresholds). `federation.py` materializes cross-corpus federated indices. `surface_exports.py` assembles everything into META-facing manifests validated against the bundled schemas.

`corpus_candidates.py` and `governance_candidates.py` implement parallel stage→review→promote→rollback workflows for corpus data and policy thresholds respectively.

### Adding a Provider

1. Add entry to `PROVIDER_CONFIG` in `provider_catalog.py`
2. Add detection function in `provider_exports.py` (e.g., `looks_like_X_export`)
3. Wire detection mode in `provider_discovery.py:summarize_provider()`
4. Create `import_X_export_corpus.py` (follow `import_chatgpt_export_corpus.py` pattern)
5. Add routing in `provider_import.py` (module-level import, branch in `resolve_provider_import_source` and `import_provider_corpus`)
6. Add to all `choices=[...]` in `cli.py` (6 occurrences)

### Pre-commit Hook

A gitleaks secret scanner runs on commit. Dict comprehensions with `token:` keys trigger false positives. Place `# allow-secret` on the line containing `token:`, not on the `for` clause — ruff format moves comments to the `for` line but the scanner checks the `token:` line.

## Environment Variables

- `CCE_PROJECT_ROOT` — project root (default: repo root; production: `../conversation-corpus-site/`)
- `CCE_SOURCE_DROP_ROOT` — source-drop inbox location

## Conventions

- Conventional Commits with imperative mood
- stdlib only for runtime — `pytest` and `ruff` are dev-only
- `COM812` is ignored in ruff lint (conflicts with ruff formatter)
- Tests use `unittest.TestCase` + `tempfile.TemporaryDirectory`; shared helpers in `tests/conftest.py`
- ChatGPT is the genesis provider — adapter type `chatgpt-history` aliased to `chatgpt-export` for backward compat
- Signal vocabulary: 14 post-flood classes (see `seed.yaml` for this repo's signal I/O)
- The system is transitioning to one-org flat hierarchy with `--` naming (identity--role). This repo's future name: `conversation-corpus--engine`
