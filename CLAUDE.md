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

### CLI Command Tree

The `cce` entrypoint has 11 command groups. All accept `--project-root` (default: `CCE_PROJECT_ROOT` or repo root) and most accept `--json` for machine output.

```
cce corpus      list | register           # manage corpus registry
cce federation  build                      # materialize cross-corpus indices
cce migration   seed-from-staging          # bootstrap registry from legacy staging root
cce provider    discover | readiness | import | bootstrap-eval | refresh
cce schema      list | show | validate     # inspect/validate the 8 JSON schema contracts
cce surface     manifest | context | bundle # Meta/MCP-facing surface exports
cce source-policy  show | set | history    # per-provider source authority
cce policy      show | replay | stage | review | apply | rollback  # promotion thresholds
cce candidate   show | history | stage | review | promote | rollback  # corpus candidates
cce evaluation  run                        # regression gate evaluation
cce review      queue | history | resolve  # federated human-review queue
cce source      freshness                  # source staleness check
```

**`provider refresh`** is the primary operational workflow — orchestrates import → bootstrap eval → run eval → stage candidate → (optionally) review → promote in a single command. Use `--approve --promote` for end-to-end auto-promote.

Providers: `chatgpt`, `claude`, `gemini`, `grok`, `perplexity`, `copilot`. Claude also supports `--mode local-session` (reads from `~/Library/Application Support/Claude`).

## Architecture

30 modules in `src/conversation_corpus_engine/`, flat structure. No subpackages. 8 JSON schemas bundled as package data in `src/conversation_corpus_engine/schemas/`.

### Project Root Directories

- `state/` — mutable operational state: federation registry, federated review queue, canonical decisions
- `reports/` — generated readiness reports, `surfaces/` subdirectory for Meta/MCP exports
- `federation/` — materialized cross-corpus federated indices (families, entities, actions, doctrine briefs, conflict reports, lineage maps)
- `promotion-policy.json` — live promotion threshold config at repo root

### Module Relationships

`answering.py` is the shared utility layer — `load_json`, `write_json`, `write_markdown`, `slugify`, `tokenize`, `search_documents_v4`, `build_answer`. Nearly every other module imports from it. `paths.py` provides `default_project_root()` and path constants (`REPO_ROOT`, `PACKAGE_ROOT`).

**Provider pipeline:** `provider_catalog.py` defines `PROVIDER_CONFIG` (6 providers with adapter types, inbox paths, corpus ID conventions). `provider_discovery.py` scans source-drop inboxes using detection functions from `provider_exports.py`. `provider_import.py` routes each provider to its adapter. `provider_readiness.py` aggregates status across all providers. `provider_refresh.py` orchestrates the full import→eval→stage→promote lifecycle.

**Import adapters** produce identical corpus artifact sets (threads-index, pairs-index, doctrine-briefs, canonical-families, etc.):
- `import_chatgpt_export_corpus.py` — walks ChatGPT `mapping` tree (parent/children pointers), linearizes by `create_time`
- `import_claude_export_corpus.py` — parses Claude `conversations.json` + `users.json` bundle
- `import_claude_local_session_corpus.py` — reads from `~/Library/Application Support/Claude` via `claude_local_session.py`
- `import_document_export_corpus.py` — generic multi-format (md/html/json/csv/zip) → normalizes to markdown → delegates to `import_markdown_document_corpus.py`

**Evaluation:** `evaluation.py` runs seeded/manual gold fixtures through 8 regression gates. `evaluation_bootstrap.py` scaffolds initial gold fixtures for new providers.

**Governance layer:** `governance_policy.py` manages promotion thresholds (defaults: zero tolerance for failures). `governance_replay.py` enables what-if threshold testing against active corpora. `governance_candidates.py` implements the stage→review→apply→rollback workflow for policy changes.

**Corpus lifecycle:** `corpus_candidates.py` implements stage→review→promote→rollback for corpus data. `corpus_diff.py` computes diffs between candidate and baseline. Both candidate workflows (corpus and policy) share the same 4-phase pattern.

**Source management:** `source_policy.py` tracks per-provider source authority (primary/fallback roots, manual vs auto decisions). `source_lifecycle.py` computes source freshness via hash-based change detection.

**Federation:** `federation.py` materializes cross-corpus indices. `federated_canon.py` manages the human review queue (5 review types: entity-alias, family-merge, action-merge, unresolved-merge, contradiction).

**Schema validation:** `schema_validation.py` implements a stdlib-only JSON Schema validator (no `jsonschema` dependency) supporting type checks, required properties, const/enum, nested objects, and arrays. `surface_exports.py` assembles META-facing manifests validated against these schemas.

### Evaluation Gates

8 regression gates with pass/warn thresholds (`evaluation.py:GATE_THRESHOLDS`):

| Gate | Direction | Pass | Warn |
|------|-----------|------|------|
| `family_stability.exact_member_match_rate` | min | 1.0 | 0.9 |
| `retrieval_metrics.family_hit_at_1` | min | 0.9 | 0.75 |
| `retrieval_metrics.thread_hit_at_1` | min | 0.5 | 0.3 |
| `retrieval_metrics.pair_hit_at_3` | min | 0.5 | 0.25 |
| `answer_metrics.state_match_rate` | min | 0.9 | 0.75 |
| `answer_metrics.required_citation_coverage_avg` | min | 0.9 | 0.75 |
| `answer_metrics.forbidden_citation_violation_rate` | max | 0.0 | 0.1 |
| `answer_metrics.abstention_match_rate` | min | 0.9 | 0.75 |

### Adding a Provider

1. Add entry to `PROVIDER_CONFIG` in `provider_catalog.py`
2. Add detection function in `provider_exports.py` (e.g., `looks_like_X_export`)
3. Wire detection mode in `provider_discovery.py:summarize_provider()`
4. Create `import_X_export_corpus.py` (follow `import_chatgpt_export_corpus.py` pattern)
5. Add routing in `provider_import.py` (module-level import, branch in `resolve_provider_import_source` and `import_provider_corpus`)
6. Add to all `choices=[...]` in `cli.py` (6 occurrences)

### Pre-commit Hook

A gitleaks secret scanner runs on commit. Dict comprehensions with `token:` keys trigger false positives. Place `# allow-secret` on the line containing `token:`, not on the `for` clause — ruff format moves comments to the `for` line but the scanner checks the `token:` line.

## Testing

Tests use pytest with shared fixtures in `tests/conftest.py`:

- **Fixtures:** `workspace` (isolated tmp_path with project/ + source-drop/), `project_root`, `source_drop_root`
- **Helpers:** `seed_minimal_corpus(root, corpus_id=, gate_state=, thread_count=)` — creates a valid corpus tree with configurable evaluation gates. `seed_provider_inbox(source_drop_root, provider, files)` — populates a provider inbox. `write_markdown_sources(root, files)` — writes markdown files for import testing.

All tests use `tmp_path` — never touch production data directories.

## Environment Variables

- `CCE_PROJECT_ROOT` — project root (default: repo root; production: `../conversation-corpus-site/`)
- `CCE_SOURCE_DROP_ROOT` — source-drop inbox location

## Conventions

- Conventional Commits with imperative mood
- stdlib only for runtime — `pytest` and `ruff` are dev-only
- Ruff config: line-length 100, target py311, selects E/F/W/I/B/PTH/RET/SIM/COM/PL. Ignores COM812 (conflicts with formatter), E501 (formatter handles length), and PLR complexity limits (0911/0912/0913/0915/2004)
- ChatGPT is the genesis provider — adapter type `chatgpt-history` aliased to `chatgpt-export` for backward compat
- Signal vocabulary: 14 post-flood classes (see `seed.yaml` for this repo's signal I/O)
- The system is transitioning to one-org flat hierarchy with `--` naming (identity--role). This repo's future name: `conversation-corpus--engine`
