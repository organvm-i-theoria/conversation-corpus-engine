# Playbook: Review-Assist Campaign Workflow

**Archetype:** THE FEDERATOR (lead), THE OPERATOR (CLI surface)

## Prerequisites

- At least 2 corpora imported and registered
- Federation indices materialized: `cce federation build --project-root <root>`
- Review queue populated (happens automatically during federation)

## Workflow

### 1. Check Queue State

```bash
cce review queue --project-root <root> --json
```

Shows pending review items by type:
- `entity-alias` — same entity with different names across corpora
- `family-merge` — overlapping conversation families
- `action-merge` — duplicate action items
- `unresolved-merge` — items that couldn't be auto-resolved
- `contradiction` — conflicting information across corpora

### 2. Run Triage (Auto-Resolution)

```bash
cce review triage --project-root <root> --json
```

Policy-driven auto-resolution. Items matching triage rules are resolved
automatically. Check the triage plan output for what was resolved and why.

### 3. Launch Review-Assist Campaign

```bash
cce review campaign --project-root <root> --json
```

Generates grouped assist reports for remaining items. Each group has:
- A batch file with the items
- A checklist for manual review
- Sample proposals with confidence scores

### 4. Build Campaign Index

```bash
cce review campaign-index --project-root <root> --json
```

Creates a navigable index of all campaign batches.

### 5. Sample and Propose

```bash
# Generate sample summary
cce review sample-summary --project-root <root> --json

# Generate proposals for a batch
cce review sample-propose --batch-id <id> --project-root <root> --json

# Compare proposals against manual decisions
cce review sample-compare --batch-id <id> --project-root <root> --json
```

### 6. Apply Decisions

```bash
# Stage decisions from a batch
cce review resolve --batch-id <id> --accept <ids> --reject <ids> \
  --project-root <root> --json

# View history
cce review history --project-root <root> --json
```

### 7. Campaign Rollup & Scoreboard

```bash
# Aggregate campaign results
cce review campaign-rollup --project-root <root> --json

# View scoreboard
cce review campaign-scoreboard --project-root <root> --json
```

## Verification

- `cce review queue --json` shows reduced pending count
- `cce dashboard` reflects updated federation stats
- No orphaned review items (all items either resolved or pending)
