# CCE Exhaustive Roadmap

**Date:** 2026-03-24
**Scope:** Micro → Macro — everything between "next line of code" and "system complete"
**Handoff target:** Codex

---

## Current State

- **Version:** 0.3.0 (10 commits this session)
- **Modules:** 32 (31 + __init__), 13,172 source lines
- **Tests:** 86 pass, 21/31 modules have test files (75% line coverage by module)
- **Corpora:** 5 live, all gates pass
- **Providers:** 8 wired (6 active, 2 awaiting data)
- **Review queue:** 1,649 open (from 3,854 — 57% auto-triaged)
- **Issues:** 0 open on GitHub
- **Distribution:** `pipx install git+https://...` works

---

## MICRO — Immediate Code Work

### M1. Test the untested (3,277 lines across 10 modules)

Priority by risk × size:

| Module | Lines | Risk | Why |
|--------|-------|------|-----|
| `federated_canon.py` | 1,056 | HIGH | Core federation logic — UnionFind, review queue, decision records. Zero tests. |
| `answering.py` | 1,287 | HIGH | Search engine, TF-IDF scoring, abstention logic. Only 3 tests (reranking). `build_documents`, `score_document`, `build_answer`, `determine_answer_state` untested. |
| `cli.py` | 822 | MEDIUM | Argument parsing + dispatch. Testable via subprocess or by calling `build_parser()` + `main()` with mock args. |
| `source_lifecycle.py` | 309 | MEDIUM | Hash-based freshness detection. Correctness matters for refresh workflows. |
| `provider_catalog.py` | 204 | LOW | Mostly config dict + path helpers. `provider_corpus_targets` has fallback logic worth testing. |
| `claude_local_session.py` | 324 | LOW | Platform-specific (macOS). Mock filesystem. |
| `import_claude_local_session_corpus.py` | 189 | LOW | Depends on local session reader. |
| `provider_exports.py` | 142 | LOW | Detection functions — `looks_like_X_export`. |
| `provider_discovery.py` | 110 | LOW | Inbox scanning. |
| `governance_policy.py` | 106 | LOW | Default thresholds + normalize. Simple. |
| `paths.py` | 15 | NONE | Trivial. |

**Order:** federated_canon → answering → source_lifecycle → cli → provider_catalog → rest

### M2. Review queue: resolve the remaining 1,649

| Type | Count | Strategy |
|------|-------|----------|
| entity-alias | 833 | Write semantic similarity policy — compare entity labels (not just IDs). Levenshtein or token overlap on canonical_label. Threshold ~0.85. Could resolve ~400. |
| family-merge | 344 | Title token overlap policy — if jaccard(title_tokens_a, title_tokens_b) > 0.8 across corpora, auto-accept. |
| unresolved-merge | 249 | Same pattern as action-merge — token overlap on canonical_question. |
| contradiction | 149 | Already deferred. These genuinely need human eyes or an LLM-assisted review pass. |
| action-merge | 74 | Token overlap on canonical_action text. Low volume, could be manual. |

**Target:** Get to <500 open with 2-3 more triage policies. The remainder is human review.

### M3. Re-import with enhanced adapter

The ChatGPT adapter now extracts code/execution/multimodal content, builds audit trails, and detects near-duplicates. Neither corpus has been re-imported:

- **ChatGPT:** Blocked — original `conversations.json` not on disk. User must re-export from ChatGPT (Settings → Data Controls → Export). Drop to `source-drop/chatgpt/inbox/`.
- **Claude export:** Source at `intake/ai-exports/source-drop/claude/inbox/data-2026-03-14-20-36-23-batch-0000`. Can re-import now but the Claude adapter (`import_claude_export_corpus.py`) wasn't enhanced with the same content-type handling. Enhance first, then re-import.
- **Claude local session:** VM-based desktop app, no accessible JSONL. Blocked until Anthropic exposes local session data.

**Order:** Enhance Claude adapter with content-type handling → re-import Claude export → request fresh ChatGPT export → re-import ChatGPT.

---

## MESO — Engine Completeness

### E1. Schema coverage for new artifacts

Two new artifact types have no schema:
- `import-audit.json` — per-thread audit records
- `near-duplicates.json` — sequence-similarity dedup candidates

Add schemas to `src/conversation_corpus_engine/schemas/`, register in `SCHEMA_CATALOG`, add validation.

### E2. Enhance Claude adapter to parity with ChatGPT

The ChatGPT adapter now has:
- Rich content-type extraction (code, execution, multimodal, tool)
- Per-thread audit trail
- Sequence-similarity dedup

The Claude adapter (`import_claude_export_corpus.py`) lacks all three. Cherry-pick the same patterns.

### E3. Provider readiness dashboard accuracy

`cce dashboard` shows "unknown" for all providers in the readiness section. The `build_provider_readiness` return format doesn't match what `render_dashboard_text` expects. Fix the field mapping.

### E4. Heuristic tagging system

Cherry-pick from genesis: 9 domain categories (systems-design, knowledge-architecture, research, github, automation, etc.) with 50+ regex rule patterns. Applies to all providers. Would enable corpus slicing by domain.

### E5. CI pipeline

No CI exists. Add:
- GitHub Actions workflow: `pytest`, `ruff check`, `ruff format --check`
- Run on push to main + PRs
- Badge in README

---

## MACRO — System Integration

### S1. Close the autopoietic loop

OM-MEM-001 says the system must ingest its own session transcripts. Currently blocked by:
- No transcript exporter for Claude Code sessions (`.specstory/history` is the closest)
- No adapter for SpecStory JSONL format

Build: `import_specstory_session_corpus.py` → reads `.specstory/history/*.json` → normalizes to corpus artifacts. This would make the CCE engine ingest its own creation story.

### S2. MCP server for live corpus access

The `mcp-context` payload is a static JSON export. For real-time access:
- Build a FastMCP server exposing `search_corpus`, `get_family`, `get_thread`, `review_queue_status` as MCP tools
- Register in Claude Desktop / Claude Code config
- Enables "ask the corpus" from any AI session

### S3. Companion indices (IRF-IDX-001/002/003)

Build the three classical indices in meta-organvm:
- **Index Locorum** — map of all locations (repos, paths, URLs, endpoints)
- **Index Nominum** — registry of all named entities (organs, repos, tools, personas)
- **Index Rerum** — ontological inventory (artifacts, their types, states, relationships)

CCE registration spec is written (GH#8 comment). Execute when indices exist.

### S4. Cross-provider conversation linking

Some conversations span multiple providers (started in ChatGPT, continued in Claude). The federation system detects these as entity-alias candidates but can't link them. Build:
- Cross-provider thread fingerprinting (topic + time window + entity overlap)
- Federated conversation chains (thread A in ChatGPT → thread B in Claude)
- Timeline view across providers

### S5. Omega criterion advancement

Current omega state: 8/19 criteria met. CCE directly advances:
- **OM-MEM-001** (proposed, not ratified): Autopoietic memory lifecycle
- **#9** (stranger test): Documentation review needed
- **#16** (self-documentation): CCE has CLAUDE.md + seed.yaml + comprehensive test suite

Route OM-MEM-001 through formal amendment. Audit #9 and #16 evidence.

---

## Dependency Graph

```
M1 (tests) ─────────────────────┐
M2 (triage policies) ───────────┤
M3 (re-import) ─── E2 (claude) ─┤
                                 ├── E5 (CI) ── S5 (omega)
E1 (schemas) ───────────────────┤
E3 (dashboard fix) ─────────────┤
E4 (heuristic tags) ────────────┘

S1 (autopoietic loop) ── S2 (MCP server)
S3 (companion indices) ── S4 (cross-provider linking)
```

M1-M3 are parallelizable. E1-E5 depend on M-layer. S-layer depends on E-layer.

---

## For Codex

**Entry point:** `CLAUDE.md` in repo root has commands, architecture, conventions.

**Test command:** `python -m pytest tests/ -v`

**Lint command:** `pipx run ruff check src/ tests/ && pipx run ruff format --check src/ tests/`

**Key constraint:** Zero runtime dependencies beyond stdlib. `pytest` and `ruff` are dev-only.

**Deployment site:** `../conversation-corpus-site/` (set `CCE_PROJECT_ROOT` to point there for live operations).

**Start with:** M1 (test `federated_canon.py`) — highest risk, highest value, no external dependencies.
