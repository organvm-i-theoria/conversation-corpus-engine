# Agent Handoff: GH#13 — Historical Review-ID Migration

**From:** Session S41 | **Date:** 2026-03-31 | **Phase:** HANDOFF
**Archetype:** THE FEDERATOR | **IRF:** IRF-CCE-019

## Current State

Migration code is **complete and tested**. No code changes needed — this is a
data migration operation against the production site.

### Code (engine repo)

| File | Lines | Function |
|------|-------|----------|
| `federated_canon.py` | 471-472 | `_subject_fingerprint()` — SHA1 of subject key, first 8 hex chars |
| `federated_canon.py` | 475-477 | `build_review_id()` — new format with fingerprint suffix |
| `federated_canon.py` | 480-482 | `build_review_id_legacy()` — old format for mapping reference |
| `federated_canon.py` | 485-493 | `stabilize_review_ids()` — dedup during generation |
| `federated_canon.py` | 1090-1098 | `_migrate_item_id()` — per-item old→new ID computation |
| `federated_canon.py` | 1101-1180 | `migrate_review_ids()` — full migration with audit trail |
| `cli.py` | 156-163 | CLI parser: `cce migration review-ids [--dry-run] [--json]` |
| `cli.py` | 730-740 | CLI handler: routes to `migrate_review_ids()` |

### ID Format Change

```
OLD: federated-{review_type}-{slugify(subjects, limit=80)}
NEW: federated-{review_type}-{slugify(subjects, limit=80)}-{sha1(subject_key)[:8]}
```

The old format truncates subject IDs at 80 characters via `slugify()`. When two
different subject pairs produce the same truncated slug, their review IDs collide.
S37 found this affected **40% of review items**. The fingerprint suffix (8 hex chars
from SHA1 of the canonical subject key) guarantees uniqueness.

### Production Data (deployment site)

Target files at `CCE_PROJECT_ROOT=../conversation-corpus-site/`:

| File | Content |
|------|---------|
| `state/federated-review-queue.json` | Active review queue (~406 open items post-triage) |
| `state/federated-review-history.json` | Resolved review history |
| `state/federated-canonical-decisions.json` | Accept/reject decision records |

## Completed Work

- [x] `build_review_id()` with fingerprint suffix (S40)
- [x] `build_review_id_legacy()` for old→new mapping (S40)
- [x] `stabilize_review_ids()` for new-item collision prevention (S37)
- [x] `migrate_review_ids()` data migration function (S40)
- [x] CLI wiring: `cce migration review-ids` (S40)
- [x] Tests for review ID generation and migration (S40)
- [ ] Dry-run against production data
- [ ] Migration execution
- [ ] Post-migration verification
- [ ] GH#13 closed

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| SHA1 fingerprint, not UUID | Deterministic from subject IDs — same inputs always produce same ID |
| 8 hex chars (32 bits) | Collision probability negligible at queue scale (~10^3 items) |
| Audit trail in `review-id-mapping.json` | Enables rollback and cross-reference of old IDs in logs/comments |
| In-place migration, not rebuild | Preserves resolution timestamps, decision notes, and history ordering |

## Critical Context

- The migration touches **three state files** simultaneously. If any write fails
  mid-operation, the state files could be inconsistent. The `--dry-run` flag exists
  precisely for this — always dry-run first.
- Decision records in `federated-canonical-decisions.json` store `review_id` but
  some entries may lack `review_type` (older decisions). The migration code handles
  this: items without `review_type` or `subject_ids` are left unchanged (line 1095-1096).
- After migration, `cce federation build` must be re-run to regenerate federated
  indices with the new IDs. Without this, the queue and indices will reference
  different ID formats.
- The triage module (`triage.py`) references review IDs when building assist reports
  and campaign indices. These are generated fresh each time, so they will automatically
  use the new format post-migration.

## Next Actions

1. **Dry run:**
   ```bash
   export CCE_PROJECT_ROOT=../conversation-corpus-site
   cce migration review-ids --dry-run --json > /tmp/migration-preview.json
   ```
   Review the output: check `stats` for migration counts, spot-check `mapping` entries.

2. **Execute migration:**
   ```bash
   cce migration review-ids --json
   ```
   This writes to all three state files and creates `state/review-id-mapping.json`.

3. **Verify integrity:**
   ```bash
   cce review queue | head -20          # Verify IDs have fingerprint suffix
   cce review history | head -10        # Verify history IDs match
   cce federation build                  # Regenerate indices
   cce dashboard                         # Verify no gate failures
   ```

4. **Commit production state** (in conversation-corpus-site):
   ```bash
   cd ../conversation-corpus-site
   git add state/
   git commit -m "feat: migrate review IDs to fingerprinted format"
   ```

5. Close GH#13, update IRF-CCE-019.

## Risks & Warnings

- **Back up state files before migration.** The migration is not reversible from
  the mapping file alone — you'd need to restore from git.
  ```bash
  cp ../conversation-corpus-site/state/federated-review-queue.json /tmp/backup-queue.json
  cp ../conversation-corpus-site/state/federated-review-history.json /tmp/backup-history.json
  cp ../conversation-corpus-site/state/federated-canonical-decisions.json /tmp/backup-decisions.json
  ```
- Any external references to old review IDs (GH issue comments, campaign reports,
  manual notes) will become stale. The mapping file provides the translation.
- Do NOT run `cce federation build` before the migration — it would generate new
  items with fingerprinted IDs while the queue still has old-format IDs, creating
  a mixed-format state.
