# CLAUDE.md

Project-specific guidance for Claude Code in this repository.

## What This Is

**conversation-corpus-engine** is the canonical ORGAN-I ENGINE for multi-provider AI conversation memory. It owns provider import, corpus validation, evaluation, federation, governance policy, and Meta/MCP surface exports.

- GitHub: `organvm-i-theoria/conversation-corpus-engine`
- Organ: ORGAN-I (Theoria)
- Functional class: ENGINE
- Tier: standard
- Promotion status: GRADUATED

## Deployment Site

The engine operates on a deployment site that lives alongside it:

```
organvm-i-theoria/
├── conversation-corpus-engine/     ← THIS REPO (code)
└── conversation-corpus-site/       ← DEPLOYMENT SITE (data, not git)
    ├── .cce-env                    ← sets CCE_PROJECT_ROOT + CCE_SOURCE_DROP_ROOT
    ├── formation.yaml              ← FORM-RES-001, type RESERVOIR, host ORGAN-I
    ├── state/                      ← registry, policies, federation state
    ├── federation/                 ← federated outputs
    ├── reports/                    ← surfaces, readiness
    ├── source-drop/                ← provider inboxes
    ├── chatgpt-history/            ← corpus (genesis, 55 threads, 9 families)
    ├── claude-local-session-memory/ ← corpus (351 threads)
    ├── claude-history-memory/       ← corpus (351 threads)
    ├── brainstorm-transcript-memory/ ← corpus
    ├── ai-exports-markdown-memory/  ← corpus
    └── archive/legacy-scripts/     ← 84 retired scripts from staging ancestor
```

To operate: `export $(cat ../conversation-corpus-site/.cce-env | grep -v '^#' | xargs)`

## Constitutional Placement

Per the Post-Flood Constitutional Order (2026-03-21):
- **META is genome (law), Theoria is knowledge AND memory**
- Placement is by physiological role (Formation Charter §7.2), not dependency rank
- The engine is an ENGINE in ORGAN-I; the site is a RESERVOIR in ORGAN-I
- Proof: `post-flood/specs/PROOF-reservoir-placement.md`

## Commands

```bash
# Install
pip install -e ".[dev]"

# Test
python -m pytest tests/ -v
python -m pytest tests/test_specific.py::ClassName::test_name -v

# Lint
pipx run ruff check src/ tests/
pipx run ruff format --check src/ tests/

# CLI (with site env loaded)
cce corpus list
cce provider discover
cce provider readiness --write
cce provider import --provider chatgpt --source-path /path/to/export
cce provider refresh --provider claude --promote
cce schema list
cce schema validate corpus-contract --path /path/to/contract.json
cce surface bundle
cce evaluation run --root /path/to/corpus --seed --json
cce review queue
```

## Architecture

- `src/conversation_corpus_engine/` — 29 modules, flat structure
- `src/conversation_corpus_engine/schemas/` — 8 JSON Schema contracts (bundled with package)
- `tests/` — 49 tests, unittest + pytest, `tempfile.TemporaryDirectory` isolation
- `tests/fixtures/` — sanitized export fixtures (ChatGPT)
- `tests/conftest.py` — shared corpus seeding and inbox helpers

### Provider Adapter Pattern

6 providers: ChatGPT, Claude, Gemini, Grok, Perplexity, Copilot.

Each provider has:
1. An entry in `provider_catalog.py` `PROVIDER_CONFIG` dict
2. A detection function in `provider_exports.py`
3. An import module (`import_*_corpus.py`) producing federation-compatible corpus artifacts
4. Wiring in `provider_import.py` to route the provider to its adapter
5. CLI choices in `cli.py`

Adapter routing:
- ChatGPT → `import_chatgpt_export_corpus.py` (conversations.json mapping tree)
- Claude upload → `import_claude_export_corpus.py` (conversations.json + users.json bundle)
- Claude local → `import_claude_local_session_corpus.py` (Application Support)
- All others → `import_document_export_corpus.py` (generic multi-format: md/html/json/csv/zip)

ChatGPT is the genesis provider. The adapter type `chatgpt-history` is recognized as an alias for `chatgpt-export` (backward compat with the 55-thread live corpus).

### Signal Flow

```
Provider exports → source-drop inboxes → cce provider import → corpus artifacts
→ cce evaluation run → regression gates → cce federation build → federated index
→ cce surface bundle → surface-manifest.json + mcp-context.json
→ META consumers: schema-definitions → organvm-engine → organvm-mcp-server → agents
```

## Environment Variables

- `CCE_PROJECT_ROOT` — project root (default: repo root; production: ../conversation-corpus-site/)
- `CCE_SOURCE_DROP_ROOT` — source-drop inbox location

## Conventions

- Conventional Commits: `feat:`, `fix:`, `docs:`, `chore:`, `ci:`, `test:`
- Python: PEP 8, type hints, ruff linting, unittest + pytest
- No external runtime dependencies (stdlib only for core engine)
- Signal vocabulary: 14 post-flood classes per Formation Protocol §8.1
