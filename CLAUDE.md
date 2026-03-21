# CLAUDE.md

Project-specific guidance for Claude Code in this repository.

## What This Is

**conversation-corpus-engine** is the canonical Organ I implementation of the AI conversation corpus system. It owns provider import, corpus validation, evaluation, federation, governance policy, and Meta/MCP surface exports.

- GitHub: `organvm-i-theoria/conversation-corpus-engine`
- Organ: ORGAN-I (Theory)
- Tier: standard
- Promotion status: GRADUATED

## Commands

```bash
# Install
pip install -e ".[dev]"

# Test
python -m pytest tests/ -v
python -m pytest tests/test_specific.py::ClassName::test_name -v  # single test

# Lint
pipx run ruff check src/ tests/
pipx run ruff format --check src/ tests/

# CLI
cce corpus list
cce provider discover
cce provider readiness --write
cce schema list
cce schema validate corpus-contract --path /path/to/contract.json
cce surface bundle
```

## Architecture

- `src/conversation_corpus_engine/` — all source code, flat module structure
- `src/conversation_corpus_engine/schemas/` — JSON Schema contracts (bundled with package)
- `tests/` — unittest-based test suite (all tests use `tempfile.TemporaryDirectory`)
- `federation/`, `reports/`, `state/` — runtime output dirs (gitignored)

### Provider Adapter Pattern

Each provider has:
1. An entry in `provider_catalog.py` `PROVIDER_CONFIG` dict
2. A detection function in `provider_exports.py`
3. An import module (`import_*_corpus.py`) that produces federation-compatible corpus artifacts
4. Wiring in `provider_import.py` to route the provider to its adapter
5. CLI choices in `cli.py`

Non-Claude providers route through `import_document_export_corpus.py` (generic multi-format).
Claude has two dedicated adapters: `import_claude_export_corpus.py` (JSON bundle) and `import_claude_local_session_corpus.py` (Application Support).
ChatGPT has a dedicated adapter: `import_chatgpt_export_corpus.py` (conversations.json with mapping tree).

### Test Pattern

Tests use `unittest.TestCase` with `tempfile.TemporaryDirectory`. Each test scaffolds its own isolated filesystem. Shared helpers in `tests/conftest.py` provide pytest fixtures for common corpus seeding.

## Runtime Outputs

`federation/`, `reports/`, `state/`, and `source-drop/` are gitignored. The repo tracks only code, schemas, tests, and documentation.

## Environment Variables

- `CCE_PROJECT_ROOT` — override the default project root (defaults to repo root)
- `CCE_SOURCE_DROP_ROOT` — override the source-drop inbox location

## Conventions

- Conventional Commits: `feat:`, `fix:`, `docs:`, `chore:`, `ci:`, `test:`
- Python: PEP 8, type hints, ruff linting, unittest + pytest
- No external runtime dependencies (stdlib only for core engine)
