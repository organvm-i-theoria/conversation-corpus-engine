# Conversation Corpus Engine

[![CI](https://github.com/organvm-i-theoria/conversation-corpus-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/organvm-i-theoria/conversation-corpus-engine/actions/workflows/ci.yml)

`conversation-corpus-engine` is the canonical Organ I implementation of the AI conversation corpus system extracted from the staging workspace at `Workspace/intake/ai-exports`.

It owns:

- provider/source registration
- provider inbox discovery and readiness reporting
- corpus validation
- source freshness and snapshot logic
- federation across corpora
- federated canon materialization
- answering and retrieval primitives
- source authority policy per provider
- promotion policy replay, staging, review, apply, and rollback
- corpus candidate diffing, review, promotion, and rollback
- provider refresh orchestration across import, evaluation, candidate staging, and optional promotion
- publishable JSON schemas and repo-native artifact validation
- Meta/MCP-facing surface manifests and export bundles

It does not own raw intake routing or system-wide discovery contracts. Those belong in Meta integrations such as `alchemia-ingestvm`, `schema-definitions`, `organvm-engine`, and `organvm-mcp-server`.

## Install

```bash
pip install -e ".[dev]"
```

## License

MIT

## CLI

```bash
cce corpus list --project-root /path/to/project
cce corpus register /path/to/corpus --project-root /path/to/project --name "Notes Memory"
cce federation build --project-root /path/to/project
cce provider discover --project-root /path/to/project --source-drop-root /path/to/source-drop
cce provider import --provider chatgpt --source-drop-root /path/to/source-drop --register --build
cce provider import --provider gemini --source-drop-root /path/to/source-drop --register --build
cce provider import --provider claude --mode local-session --local-root "/Users/you/Library/Application Support/Claude"
cce provider bootstrap-eval --provider claude --project-root /path/to/project --full-eval
cce provider readiness --project-root /path/to/project --source-drop-root /path/to/source-drop --write
cce provider refresh --provider chatgpt --project-root /path/to/project --source-drop-root /path/to/source-drop
cce provider refresh --provider perplexity --project-root /path/to/project --source-drop-root /path/to/source-drop
cce provider refresh --provider claude --project-root /path/to/project --promote --note "refresh and replace live corpus"
cce schema list
cce schema show corpus-contract
cce schema validate corpus-contract --path /path/to/corpus/contract.json
cce surface manifest --project-root /path/to/project --source-drop-root /path/to/source-drop
cce surface context --project-root /path/to/project --source-drop-root /path/to/source-drop
cce surface bundle --project-root /path/to/project --source-drop-root /path/to/source-drop
cce source-policy set --project-root /path/to/project --provider claude --primary-root /path/to/corpus --primary-corpus-id claude-local-session-memory
cce policy replay --project-root /path/to/project --set-threshold max_stale_corpora=1 --write
cce policy stage --project-root /path/to/project --set-threshold max_stale_corpora=1 --note "allow one stale corpus during migration"
cce policy apply --project-root /path/to/project --candidate-id latest --note "promote reviewed threshold"
cce candidate stage --project-root /path/to/project --candidate-root /path/to/candidate-corpus --provider claude --note "stage refreshed corpus"
cce candidate review --project-root /path/to/project --candidate-id latest --decision approve --note "promote candidate"
cce candidate promote --project-root /path/to/project --candidate-id latest --note "replace live corpus"
cce candidate rollback --project-root /path/to/project --target previous --note "restore previous live corpus"
cce evaluation run --root /path/to/corpus --seed --json
cce review queue --project-root /path/to/project
cce review resolve federated-family-merge-... --decision accepted --note "same family"
cce source freshness /path/to/corpus
```

## Layout

- `src/conversation_corpus_engine/answering.py` — retrieval and answer-building primitives
- `src/conversation_corpus_engine/source_lifecycle.py` — source snapshot and freshness checks
- `src/conversation_corpus_engine/federated_canon.py` — federated review state and canon builders
- `src/conversation_corpus_engine/federation.py` — corpus registry and federation build/query logic
- `src/conversation_corpus_engine/import_markdown_document_corpus.py` — generic markdown corpus materialization
- `src/conversation_corpus_engine/import_document_export_corpus.py` — document-style provider export import
- `src/conversation_corpus_engine/import_claude_export_corpus.py` — Claude bundle import
- `src/conversation_corpus_engine/import_claude_local_session_corpus.py` — Claude local-session import
- `src/conversation_corpus_engine/import_chatgpt_export_corpus.py` — ChatGPT conversations.json export import
- `src/conversation_corpus_engine/provider_discovery.py` — source-drop inbox discovery
- `src/conversation_corpus_engine/provider_import.py` — provider import/onboarding orchestration
- `src/conversation_corpus_engine/provider_refresh.py` — provider refresh orchestration over import, evaluation, and corpus promotion
- `src/conversation_corpus_engine/provider_readiness.py` — provider lane readiness and report writing
- `src/conversation_corpus_engine/schema_validation.py` — published schema catalog and lightweight JSON validation
- `src/conversation_corpus_engine/surface_exports.py` — Meta/MCP-facing manifest and context export layer
- `src/conversation_corpus_engine/schemas/` — installable JSON-schema contracts for canonical artifacts
- `src/conversation_corpus_engine/evaluation.py` — seeded/manual evaluation, scorecards, and regression gates
- `src/conversation_corpus_engine/evaluation_bootstrap.py` — provider-aware evaluation bootstrap and report generation
- `src/conversation_corpus_engine/source_policy.py` — per-provider source authority records and reports
- `src/conversation_corpus_engine/governance_policy.py` — live promotion-policy defaults and calibration
- `src/conversation_corpus_engine/governance_replay.py` — replay current corpora against promotion thresholds
- `src/conversation_corpus_engine/governance_candidates.py` — candidate stage/review/apply/rollback workflow
- `src/conversation_corpus_engine/corpus_diff.py` — live-vs-candidate structural and retrieval diffing
- `src/conversation_corpus_engine/corpus_candidates.py` — corpus candidate stage/review/promote/rollback workflow
- `tests/` — extraction-safe regression tests

## Runtime Outputs

Runtime state is written to `state/`, `federation/`, and `reports/`. Those directories are intentionally ignored so the repo stays focused on canonical code, contracts, tests, and public documentation.

## Status

This repo now serves as the canonical Organ I home of the conversation corpus system. The adjacent Meta consumer path is also live: `schema-definitions` canonizes the outward contracts, `organvm-engine` discovers and validates emitted surface bundles, and `organvm-mcp-server` exposes them to agent sessions. Operational hardening is underway: CI gates all pushes, ChatGPT is a first-class provider alongside Claude/Gemini/Grok/Perplexity/Copilot, and sanitized test fixtures document the expected export formats. The next frontier is downstream dashboard consumption and additional provider adapters.
