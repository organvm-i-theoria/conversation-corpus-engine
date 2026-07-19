# Conversation Corpus Engine

[![CI](https://github.com/organvm-i-theoria/conversation-corpus-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/organvm-i-theoria/conversation-corpus-engine/actions/workflows/ci.yml)

`conversation-corpus-engine` is the canonical Organ I implementation of the AI conversation corpus system extracted from the staging workspace at `Workspace/intake/ai-exports`.

It owns:

- provider/source registration
- provider-neutral redacted-bundle normalization and authority projection
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
- commercial-awareness metadata for pipeline and surface consumers

It does not own raw intake routing or system-wide discovery contracts. Those belong in Meta integrations such as `alchemia-ingestvm`, `schema-definitions`, `organvm-engine`, and `organvm-mcp-server`.

## Commercial Strategy Linkage

CCE is the institutional memory and product-scale side of the ORGANVM income surface. Its commercial architecture is tracked in [`docs/superpowers/specs/2026-03-31-cce-commercial-architecture-design.md`](docs/superpowers/specs/2026-03-31-cce-commercial-architecture-design.md) and [`docs/superpowers/specs/2026-03-31-cce-commercial-architecture-expansion.md`](docs/superpowers/specs/2026-03-31-cce-commercial-architecture-expansion.md).

The personal-capacity counterpart is [`4444J99/application-pipeline`](https://github.com/4444J99/application-pipeline), whose jobs, grants/residencies, and consulting tracks supply near-term income, market feedback, and enterprise-service leads for CCE Ring 4. This backlink closes `IRF-CCE-038` on the CCE side: the two repos should stay commercially aware of one another rather than treating pipeline revenue and CCE product revenue as separate strategies.

## Install

```bash
pip install -e ".[dev]"
```

For tool-host integration:

```bash
pipx install "conversation-corpus-engine[mcp]"
cce-mcp --project-root /path/to/project
```

The `mcp` extra is dependency-free today; it enables the install target and exposes
the stdio MCP entry point. A Claude Desktop-style server entry can point directly at
the command:

```json
{
  "mcpServers": {
    "conversation-corpus-engine": {
      "command": "cce-mcp",
      "args": ["--project-root", "/path/to/project"]
    }
  }
}
```

## License

MIT

## CLI

```bash
cce corpus list --project-root /path/to/project
cce corpus register /path/to/corpus --project-root /path/to/project --name "Notes Memory"
cce federation build --project-root /path/to/project
cce provider discover --project-root /path/to/project --source-drop-root /path/to/source-drop
cce provider authority-ingest --source-root /path/to/redacted-bundle --source-census /path/to/source-census.v1.json --provider-manifest /path/to/provider-manifest.json --output-root /path/to/output --snapshot-id frozen-snapshot --captured-at 2026-07-16T16:00:00Z --custody-pointer custody:frozen-snapshot
cce provider import --provider chatgpt --source-drop-root /path/to/source-drop --register --build
cce provider import --provider gemini --source-drop-root /path/to/source-drop --register --build
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
cce-mcp --project-root /path/to/project
```

### Provider-neutral authority ingest

`provider authority-ingest` is the default path for new source acquisition. It reads only a
frozen, redacted `session-meta` atom bundle. It never opens browser profiles, cookies, tokens,
OAuth material, or provider application stores. The runtime provider manifest separates source
families, aliases, adapter IDs, custody root environment keys, authority policy, and owner
blockers. Adding or renaming a provider is a manifest-only change when an existing format adapter
applies.

The bundled `provider-manifest.organvm.v1.json` is explicitly instance configuration. The
`provider-manifest.example.v1.json` reusable template contains only generic placeholders. Set
`CCE_PROVIDER_MANIFEST` or pass `--provider-manifest` to select another runtime manifest.
Supplying `--source-census` binds normalization to session-meta's exact frozen denominator;
the census is rejected on schema-shape, snapshot, or RFC 8785 digest mismatch. Contract digests
use the pinned `rfc8785` dependency and exclude JSONL record delimiters. Exact ingest also
requires each atom's `meta.raw_unit_content_hashes` to match the census. That immutable
raw-unit content identity is promoted into every source envelope and normalized event and
repeated in the complete parity crosswalk; a changed-and-resealed census fails before
projection.

Each frozen run writes deterministic, body-free public projections:

- `source-envelope.v1.jsonl`
- `normalized-events.v1.jsonl`
- `quarantine.jsonl`
- `owner-blockers.jsonl`
- `coverage-receipt.v1.json`
- `normalization-parity-receipt.v1.json`

Malformed rows quarantine without stopping valid siblings. Unknown families and missing roots
remain explicit owner blockers. `exact_all` means every discovered unit was classified exactly
once; `ready` additionally requires every unit to be parsed with no residual debt. Per-record
adapter failures remain explicit parity quarantine debt even when valid siblings from the same raw
unit normalize. Existing export importers remain compatibility paths until a frozen run reports
both exact parity and readiness.

### Governance cadence parse/classify owners

CCE exposes separate owner commands for Limen's bounded `parse` and `classify`
stages. `authority-parse-cadence` performs the existing authority ingest exactly
once. `authority-classify-cadence` does not reprocess the source: it independently
checks the parse projection, copies the six governed artifacts byte-for-byte, and
binds their digests in a typed classify projection.

```bash
cce provider authority-parse-cadence \
  --source-root "$CCE_REDACTED_SNAPSHOT" \
  --source-census "$CCE_SOURCE_CENSUS" \
  --provider-manifest "$CCE_PROVIDER_MANIFEST" \
  --output-root "$LIMEN_GOV_RUN_ROOT/parse" \
  --snapshot-id "$LIMEN_GOV_SNAPSHOT_ID" \
  --captured-at "$LIMEN_GOV_SNAPSHOT_AT" \
  --custody-pointer "$CCE_CUSTODY_POINTER"

cce provider authority-classify-cadence \
  --input-root "$LIMEN_GOV_RUN_ROOT/parse" \
  --output-root "$LIMEN_GOV_RUN_ROOT/classify" \
  --snapshot-id "$LIMEN_GOV_SNAPSHOT_ID"
```

The commands consume Limen's injected `LIMEN_GOV_*` execution variables and
write one bounded transaction child to `LIMEN_GOV_STAGE_METRICS_OUT`.
`LIMEN_GOV_MAX_ITEMS` bounds the census raw-unit or promotion denominator.
On proof traversals, the parse owner reruns the exact ingest in a temporary
directory and requires every governed artifact and projection to be
byte-identical; the classify owner revalidates its byte projection. Neither
owner rewrites governed outputs. Both emit a `skipped_completed` child bound to
the exact prior child receipt and report zero new events. The independent
predicate commands are:

```bash
cce provider authority-parse-predicate \
  --source-root "$CCE_REDACTED_SNAPSHOT" \
  --source-census "$CCE_SOURCE_CENSUS" \
  --provider-manifest "$CCE_PROVIDER_MANIFEST" \
  --output-root "$LIMEN_GOV_RUN_ROOT/parse" \
  --snapshot-id "$LIMEN_GOV_SNAPSHOT_ID" \
  --captured-at "$LIMEN_GOV_SNAPSHOT_AT" \
  --custody-pointer "$CCE_CUSTODY_POINTER"

cce provider authority-classify-predicate \
  --input-root "$LIMEN_GOV_RUN_ROOT/parse" \
  --output-root "$LIMEN_GOV_RUN_ROOT/classify" \
  --snapshot-id "$LIMEN_GOV_SNAPSHOT_ID" \
  --captured-at "$LIMEN_GOV_SNAPSHOT_AT"
```

Both projections preserve the owner's distinction between classification and
readiness: a complete parity crosswalk can remain `exact_all: true` while
blockers or quarantines keep `ready: false`.

## MCP Tools

`cce-mcp` serves MCP over stdio and never writes non-protocol output to stdout. It
currently exposes:

- `cce_search`: search a registered or direct corpus root and return a grounded
  answer, citations, and structured top-hit metadata.
- `cce_list_corpora`: list registered project corpora.
- `cce_surface_context`: build the MCP-facing project context payload.

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
- `src/conversation_corpus_engine/source_adapter_registry.py` — provider-neutral redacted-bundle adapter registry
- `src/conversation_corpus_engine/authority_projection.py` — role-aware authority and lane projection
- `src/conversation_corpus_engine/authority_ingest.py` — deterministic envelope, event, quarantine, coverage, and parity generation
- `src/conversation_corpus_engine/authority_cadence.py` — bounded parse/classify owner projections and proof metrics
- `src/conversation_corpus_engine/authority_cadence_predicate.py` — independent parse/classify predicates
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
