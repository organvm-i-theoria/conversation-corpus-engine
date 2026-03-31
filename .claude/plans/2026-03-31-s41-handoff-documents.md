# Plan: Devise Handoff Documents for 6 Open GH Issues

## Context

S40 audit confirmed 6 open GitHub issues — no orphaned work. Each issue is blocked
by a different constraint (external auth, tooling availability, specification work,
or dependency chains). The user wants structured handoff documents so any future
session can pick up any issue independently, without re-exploration.

**Cross-agent-handoff skill** loaded — documents will follow its structure:
Current State, Completed Work, Key Decisions, Critical Context, Next Actions,
Risks & Warnings.

## Approach

Create one handoff document per issue in `playbooks/handoffs/`. Each document is
self-contained: a future session reads only that file + the code paths it references.
No inter-handoff dependencies.

### Files to create

```
playbooks/handoffs/
  gh-11-s33-testament-recording.md
  gh-12-s37-testament-recording.md
  gh-13-review-id-migration.md
  gh-14-omega-ratification.md
  gh-15-chatgpt-scope-degradation.md
  gh-16-chatgpt-projects-endpoint.md
```

### Issue-by-Issue Analysis

---

#### GH#11 + GH#12: S33/S37 Testament Recording (THE OPERATOR)

**What exists:**
- `state/testaments/s33-testament.json` — staged, schema-conformant (`testament-event-v1`)
- `state/testaments/s37-testament.json` — staged, schema-conformant
- Both follow the same structure: session metadata, commits, test delta, capabilities, issues, cross-repo propagation
- Schema at `schemas/testament-event.json`

**What "recording" means:**
- Commit the testament files (they're `git add`ed but not committed)
- Register the testament events in the meta-organvm testament system (`organvm session export`)
- Close the GitHub issues

**Blocker stated:** "testament tooling" — but testament files are already authored
and the `organvm session` CLI exists. The actual blocker is likely that `organvm`
CLI commands may not be installed/configured in the current environment.

**Handoff action:** Commit testaments, verify `organvm session export` is available,
register, close issues. If `organvm` CLI unavailable, manual registration in
`organvm-corpvs-testamentvm` is the fallback.

---

#### GH#13: Historical Review-ID Migration (THE FEDERATOR)

**What exists:**
- Migration code complete: `federated_canon.py:1085-1180`
  - `_migrate_item_id()` — computes new fingerprinted ID from old
  - `migrate_review_ids()` — migrates queue, history, decisions; writes audit trail
  - `build_review_id_legacy()` — preserves old format for mapping
- CLI wired: `cce migration review-ids [--dry-run] [--json]` (cli.py:156-163, 730-740)
- Tests exist (verified in test_federated_canon.py)

**ID format change:**
- Old: `federated-{review_type}-{slugify(subjects, limit=80)}`
- New: `federated-{review_type}-{slugify(subjects, limit=80)}-{sha1(subject_key)[:8]}`
- Collision rate was 40% of review items (S37 finding)

**What needs to happen:**
1. Run `cce migration review-ids --dry-run --json` against production site
   (`CCE_PROJECT_ROOT=../conversation-corpus-site/`)
2. Review the mapping output for sanity
3. Run without `--dry-run` to apply
4. Verify queue/history/decisions integrity post-migration
5. Run `cce federation build` to regenerate indices with new IDs
6. Close GH#13

**Critical files (production):**
- `../conversation-corpus-site/state/federated-review-queue.json`
- `../conversation-corpus-site/state/federated-review-history.json`
- `../conversation-corpus-site/state/federated-canonical-decisions.json`
- Output: `../conversation-corpus-site/state/review-id-mapping.json`

---

#### GH#14: OM-MEM-001 Omega Ratification (THE GOVERNOR)

**What exists:**
- Roadmap reference: `.claude/plans/2026-03-24-cce-exhaustive-roadmap.md:108-144`
- OM-MEM-001 definition: "the system must ingest its own session transcripts"
- Currently proposed, not ratified
- S5 in roadmap: "Route OM-MEM-001 through formal amendment"

**What "ratification" means:**
1. Write the complete OM-MEM-001 criterion specification as a GH#14 comment
   - Criterion statement (what must be true)
   - Evidence requirements (what demonstrates compliance)
   - Measurement method (how to verify)
2. The specification must be precise enough to pass/fail objectively
3. Evidence already partially exists: testament files, session review protocol,
   SpecStory history integration path

**Blocker:** Criterion authoring — needs formal specification language consistent
with existing omega criteria in `organvm-corpvs-testamentvm`.

**Handoff action:** Read existing omega criteria format from meta-organvm, draft
OM-MEM-001 spec, post as GH#14 comment, update IRF.

---

#### GH#15: ChatGPT API Scope Degradation (THE ACQUISITOR)

**What exists:**
- `scope_preflight_check()` at `chatgpt_local_session.py:462-499`
  - Threshold: `SCOPE_DEGRADATION_THRESHOLD = 0.5` (50% floor)
  - Compares current conversation_count against prior acquisition state
  - Raises `ChatGPTLocalSessionError` when below threshold
- S39 observed: 633 conversations → 4 (0.6% remaining)
- The session was authenticated (access token valid) but API returned truncated results
- `discover_chatgpt_local_session()` uses `backend-api/conversations?offset=0&limit=1`
  to get total count

**Root cause (per feedback memory `feedback_api_session_fragility.md`):**
ChatGPT sessions degrade silently — `session_state: "ready"` does not mean full
scope. The access token can be valid while the account scope is restricted.

**What needs to happen:**
1. Re-launch ChatGPT desktop app and sign in fresh
2. Run `cce provider discover` to verify conversation count recovers
3. Run `cce provider import --provider chatgpt --mode local-session` to verify full import
4. If scope still degraded: try Chrome cookie fallback path
5. Document the re-auth playbook

**Blocker:** External — requires human action (re-sign-in to ChatGPT desktop app).
No code changes needed unless the auth flow itself needs modification.

---

#### GH#16: Wrong Projects API Endpoint (THE ACQUISITOR)

**What exists:**
- `discover_chatgpt_projects()` at `chatgpt_local_session.py:877-917`
- Currently uses: `backend-api/gizmos/discovery/mine` with pagination
  - Comment on line 884: "ChatGPT gizmos API returns projects as gizmo entries"
- This is the GPT Store discovery endpoint, not the Projects API
- ChatGPT Projects (launched 2024) are distinct from GPTs/Gizmos
- The function filters by structure but the endpoint may not return Projects at all

**What needs to happen:**
1. Requires a working ChatGPT session (blocked by #15)
2. Investigate the correct Projects API endpoint:
   - Likely candidates: `backend-api/projects`, `backend-api/me/projects`
   - Use browser DevTools Network tab while navigating ChatGPT Projects UI
3. Update `discover_chatgpt_projects()` with correct endpoint
4. Update `fetch_chatgpt_project()` if project detail endpoint also differs
5. Test project discovery + extraction pipeline end-to-end

**Dependency:** Blocked by #15 — cannot test API endpoints without valid session.

---

## Verification

After creating all 6 handoff documents:
1. Each document can be read in isolation by a cold-start agent
2. Each lists exact file paths, line numbers, and CLI commands
3. Each identifies its blocker and what unblocks it
4. No handoff references another handoff

## Output

6 markdown files in `playbooks/handoffs/`, one per issue.
