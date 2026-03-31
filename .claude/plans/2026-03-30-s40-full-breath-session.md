# S40 Plan: Full-Breath Session — Ops Recovery, Code, Archetypes, Resources

## Context

Session S40 picks up from the S39 Tribunal judgment. The ChatGPT API degraded silently (633→4 conversations), the LaunchAgent exists in domus but was never deployed, the source-drop inbox is empty (no official export arrived), and 6 GH issues remain open. The user wants a comprehensive session: operational recovery, code work, housekeeping, plus establishing owner archetypes, strict module boundaries, skills integration, and resource directories.

**Critical constraint:** The ChatGPT cookie jar was updated today (Mar 30, 18:04) but scope is unknown. Per feedback memory: check `conversation_count` before any bulk operation.

---

## Phase 0 — Operational Triage (parallel, read-only)

### 0A: Test ChatGPT session scope
Run `cce provider discover --provider chatgpt --mode local-session --json` and check `conversation_count`. If ≥600: session restored. If <100: still degraded — defer #15/#16 and all ChatGPT API work.

### 0B: Deploy LaunchAgent
Template exists at `~/Workspace/4444J99/domus-semper-palingenesis/private_Library/LaunchAgents/com.4jp.cce-refresh.plist.tmpl`. Deploy:
```bash
chezmoi apply ~/Library/LaunchAgents/com.4jp.cce-refresh.plist
launchctl load ~/Library/LaunchAgents/com.4jp.cce-refresh.plist
```
Verify: `launchctl list | grep cce-refresh`

### 0C: Confirm no export in inbox
Already confirmed: `source-drop/chatgpt/inbox/` is empty. Note in session record.

---

## Phase 1 — Owner Archetypes & Module Boundaries

Define 5 archetypes that own the 33 modules. Create `OWNERS.md` at repo root.

| Archetype | Domain | Modules (count) |
|-----------|--------|-----------------|
| **THE ACQUISITOR** | Provider intake, session adapters, import pipelines | `chatgpt_local_session`, `claude_local_session`, `import_chatgpt_export_corpus`, `import_chatgpt_local_session_corpus`, `import_claude_export_corpus`, `import_claude_local_session_corpus`, `import_document_export_corpus`, `import_markdown_document_corpus`, `provider_catalog`, `provider_discovery`, `provider_exports`, `provider_import`, `provider_readiness`, `provider_refresh`, `source_policy`, `source_lifecycle` (16) |
| **THE EVALUATOR** | Quality gates, regression, schema contracts | `evaluation`, `evaluation_bootstrap`, `schema_validation` (3) |
| **THE FEDERATOR** | Cross-corpus federation, review queue, triage | `federation`, `federated_canon`, `triage` (3) |
| **THE GOVERNOR** | Promotion policy, corpus lifecycle, governance | `governance_policy`, `governance_replay`, `governance_candidates`, `corpus_candidates`, `corpus_diff` (5) |
| **THE OPERATOR** | CLI, dashboard, surface exports, infrastructure | `cli`, `dashboard`, `surface_exports`, `answering`, `paths`, `migration` (6) |

### Boundary Rules
- Each module belongs to exactly ONE archetype
- Cross-archetype imports are permitted (flat module structure) but edge direction matters
- THE EVALUATOR must be independent of THE GOVERNOR — evaluation cannot be influenced by promotion desire
- THE ACQUISITOR never writes to federation state
- THE FEDERATOR reads from all corpora but writes only to `state/` and `federation/`

### Issue Ownership
| Issue | Archetype |
|-------|-----------|
| #11, #12 (testament) | THE OPERATOR |
| #13 (review-ID migration) | THE FEDERATOR |
| #14 (omega ratification) | THE GOVERNOR |
| #15 (API scope degradation) | THE ACQUISITOR |
| #16 (wrong Projects endpoint) | THE ACQUISITOR |

---

## Phase 2 — Resource Directories

Add two new directories:

### `playbooks/`
Operational runbooks for recurring procedures:
- `scope-recovery.md` — ChatGPT session re-auth checklist (from S39 Tribunal + feedback memory)
- `new-provider-onboarding.md` — 6-step provider addition checklist (from CLAUDE.md)
- `review-campaign-workflow.md` — running a review-assist campaign end-to-end

### `templates/`
Reusable document templates:
- `testament-event.json` — testament event schema for #11/#12
- `session-canon.md` — session closure document template (from docs/2026-03-24-s33-closure-session-canon.md pattern)

**NOT adding:** `campaigns/` (premature — reports/ handles this), `config/` (promotion-policy.json at root is fine), `governance/` (governance is code, not docs).

---

## Phase 3 — Code Work

### 3A: Scope Pre-flight Check (THE ACQUISITOR)
**File:** `chatgpt_local_session.py`
**What:** Add `scope_preflight_check(conversation_count: int, output_root: Path) -> dict` that:
1. Loads prior acquisition state via `load_prior_acquisition(output_root)`
2. Compares current `conversation_count` against prior known count
3. Returns `{"status": "ok"|"degraded"|"unknown", "current": N, "prior": M, "delta_pct": float}`
4. If degraded (>50% drop): raises `ChatGPTLocalSessionError` with actionable message

**Wire into:** `import_chatgpt_local_session_corpus.py` calls pre-flight before fetching. `provider_refresh.py` surfaces the result in refresh output.

**Tests:** `test_chatgpt_local_session.py` — test ok/degraded/unknown/no-prior-state cases.

### 3B: Projects API Endpoint (THE ACQUISITOR) — CONDITIONAL on Phase 0A
**File:** `chatgpt_local_session.py:834-874`
**What:** If ChatGPT session is restored, use browser devtools to discover the real Projects (folder) API endpoint. Replace `gizmos/discovery/mine` with the correct endpoint.
**If session still degraded:** Document the blocking dependency in #16 and defer.

### 3C: Review-ID Migration (THE FEDERATOR)
**File:** `federated_canon.py`
**What:** The current `build_review_id()` at line 471 truncates via `slugify(..., limit=80)` causing collisions. `stabilize_review_ids()` at line 475 already patches collisions with sha1 fingerprints at generation time. The migration path:
1. Add `migrate_review_ids(queue_path, history_path, decisions_path)` function
2. Scan all review items, recompute IDs with always-present fingerprint suffix
3. Build a `review-id-mapping.json` in `state/` mapping old→new IDs
4. Update queue, history, and decisions files in-place
5. Validate no orphaned references remain

**Tests:** Test migration on synthetic queue/history data with known collisions.

---

## Phase 4 — Housekeeping

### 4A: Testament Events (#11, #12) — THE OPERATOR
**What:** The testament cascade tooling doesn't exist yet. Build minimal testament event files:
1. Create `templates/testament-event.json` with the schema
2. Write `state/testaments/s33-testament.json` and `state/testaments/s37-testament.json` with the key facts (modules added, capabilities shipped, test counts)
3. Comment on #11 and #12 with the testament event data and close as "completed (manual recording)"

### 4B: Omega Ratification (#14) — THE GOVERNOR
**What:** Can't author the criterion in meta-organvm from here. Instead:
1. Write the complete `OM-MEM-001` criterion specification in a comment on #14
2. Include: criterion name, description, evidence requirements, pass/fail conditions
3. Leave issue open — blocked on meta-organvm criterion authoring tooling

---

## Phase 5 — Skills Integration

Map relevant skills from the 143 available to each archetype:

| Archetype | Tier-1 Skills (daily use) | Tier-2 Skills (per-session) |
|-----------|--------------------------|----------------------------|
| ACQUISITOR | `data-ingestion-pipeline`, `data-pipeline-architect` | `session-lifecycle-patterns`, `data-backup-patterns` |
| EVALUATOR | `testing-patterns`, `tdd-workflow` | `verification-loop`, `coding-standards-enforcer` |
| FEDERATOR | `knowledge-graph-builder`, `research-synthesis-workflow` | `knowledge-architecture` |
| GOVERNOR | `continuous-learning-agent` | `configuration-management`, `repo-onboarding-flow` |
| OPERATOR | `cli-tool-design`, `api-design-patterns` | `cross-agent-handoff`, `agent-swarm-orchestrator` |

Document this mapping in `OWNERS.md` alongside the module assignments.

---

## Phase 6 — Verification & Closure

1. `python -m pytest tests/ -v` — all 267+ tests pass
2. `pipx run ruff check src/ tests/` — lint clean
3. `pipx run ruff format --check src/ tests/` — format clean
4. Verify new files: `OWNERS.md`, `playbooks/*.md`, `templates/*`, `state/testaments/*`
5. Verify LaunchAgent is loaded: `launchctl list | grep cce-refresh`
6. Update GH issues: close #11, #12; comment on #13 (if migration merged), #14, #15, #16
7. Single commit or logical commit series

---

## Critical Files

| File | Phase | Change Type |
|------|-------|-------------|
| `src/.../chatgpt_local_session.py` | 3A, 3B | Add scope_preflight_check, fix projects API |
| `src/.../import_chatgpt_local_session_corpus.py` | 3A | Wire pre-flight check |
| `src/.../provider_refresh.py` | 3A | Surface pre-flight result |
| `src/.../federated_canon.py` | 3C | Add migrate_review_ids |
| `tests/test_chatgpt_local_session.py` | 3A | Pre-flight test cases |
| `tests/test_federated_canon.py` | 3C | Migration test cases |
| `OWNERS.md` (new) | 1, 5 | Archetype definitions + skills |
| `playbooks/*.md` (new) | 2 | 3 operational runbooks |
| `templates/*.json, *.md` (new) | 2, 4A | Templates + testament events |
| `state/testaments/*.json` (new) | 4A | S33/S37 testament records |

## Deferral Policy

If the session runs long, defer in this order (last = first to drop):
1. Phase 5 (skills mapping) — document later
2. Phase 3B (Projects API) — blocked if session degraded anyway
3. Phase 4B (omega spec) — comment only, no code
4. Phase 4A (testaments) — minimal data entry
5. **Never defer:** Phase 0 (ops triage), Phase 1 (archetypes), Phase 3A (pre-flight), Phase 3C (review-ID migration)
