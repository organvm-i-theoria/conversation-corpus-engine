# Plan: The Post Office — ChatGPT Project Extraction Registry

## Context

63 ChatGPT projects exist in the account. Each one is either a seed or a missing flower on a grown plant. Three have been extracted (content-multiplex, machina-mundi-canonici, DSP-alternative partial). 60 remain undiscovered by the system. There is no tracking, no routing, no visibility into what's been extracted, where it went, or what's missing.

The system needs a mailroom — a registry that tracks each project through its lifecycle: discovered → queued → extracting → extracted → routed → delivered. So we know when a package arrives safely or mis-arrives haphazardly.

## Architecture

### Project Registry

A persistent JSON file at `state/chatgpt-project-registry.json` (under the corpus site) that inventories every discovered project:

```json
{
  "generated_at": "...",
  "account_id": "...",
  "project_count": 63,
  "projects": {
    "g-p-69c3250247688191b6cd2ad8a54f68d9": {
      "name": "content-multiplex",
      "interactions": 32,
      "file_count": 39,
      "discovered_at": "...",
      "extraction_state": "delivered",
      "extracted_at": "...",
      "extraction_manifest": {
        "files_extracted": 39,
        "conversations_extracted": 18,
        "output_root": "/Users/4jp/Workspace/organvm-iii-ergon/content-engine--asset-amplifier/docs/genesis-project"
      },
      "route": {
        "destination": "/Users/4jp/Workspace/organvm-iii-ergon/content-engine--asset-amplifier/docs/genesis-project",
        "organ": "ORGAN-III",
        "repo": "content-engine--asset-amplifier",
        "routed_at": "..."
      }
    },
    "g-p-67a0c90e58348191a374880d50f20b8e": {
      "name": "pedagogy",
      "interactions": 1002,
      "file_count": 0,
      "discovered_at": "...",
      "extraction_state": "discovered",
      "extracted_at": null,
      "extraction_manifest": null,
      "route": null
    }
  }
}
```

### Extraction states

```
discovered → queued → extracting → extracted → routed → delivered
                                  ↘ partial (rate limited, some files missing)
                                  ↘ failed (API error, session expired)
```

### CLI commands

```
cce project discover                    # scan all projects, update registry
cce project status                      # show extraction state for all projects
cce project extract --project-id <id> --output <path>  # extract one project (exists)
cce project route --project-id <id> --destination <path>  # set where a project should go
cce project sync                        # extract all queued/stale projects to their routes
cce project sync --batch-size 5         # extract N projects per run (rate limit awareness)
```

### Where it lives

**Registry + state:** `conversation-corpus-site/state/chatgpt-project-registry.json`
**Code:** `src/conversation_corpus_engine/chatgpt_local_session.py` (extend with registry functions)
**CLI:** `src/conversation_corpus_engine/cli.py` (extend `project` command group)

## Implementation

### Phase 1: Registry builder (`project discover`)

Add to `chatgpt_local_session.py`:

- `discover_chatgpt_projects(cookie_jar)` — fetch all project metadata via API, return registry payload
- `load_project_registry(project_root)` — read existing registry
- `save_project_registry(project_root, registry)` — write registry
- `merge_project_discovery(existing, discovered)` — merge new discovery into existing registry without losing extraction/route state

Wire `cce project discover --project-root <root> --json`.

### Phase 2: Status display (`project status`)

Add to `chatgpt_local_session.py`:

- `render_project_status(registry)` — text summary: total/extracted/partial/queued/unrouted counts + per-project table

Wire `cce project status --project-root <root> --json`.

### Phase 3: Route assignment (`project route`)

Add to `chatgpt_local_session.py`:

- `set_project_route(project_root, project_id, destination, organ=None, repo=None)` — update a project's route in the registry

Wire `cce project route --project-id <id> --destination <path>`.

### Phase 4: Extraction with registry tracking

Modify existing `fetch_chatgpt_project()` to:
- Update registry state to `extracting` before fetch
- Update to `extracted` or `partial` after fetch
- Write extraction manifest into the registry entry
- If a route exists and output matches route destination, mark as `delivered`

### Phase 5: Batch sync (`project sync`)

Add to `chatgpt_local_session.py`:

- `sync_chatgpt_projects(project_root, batch_size=5)` — iterate queued/stale projects, extract each to its routed destination, update registry, respect rate limits with configurable batch size

Wire `cce project sync --project-root <root> --batch-size 5 --json`.

### Phase 6: Pre-populate registry with known extractions

On first `discover`, the registry should recognize the three already-extracted projects and mark them correctly:
- content-multiplex → delivered to `organvm-iii-ergon/content-engine--asset-amplifier/docs/genesis-project`
- machina-mundi-canonici → delivered to `intake/machina-mundi-canonici`
- DSP-alternative → partial at `intake/dsp-alternative`

## Critical files

| File | Action |
|------|--------|
| `src/.../chatgpt_local_session.py` | Add registry functions: discover, load, save, merge, route, sync |
| `src/.../cli.py` | Extend `project` group with discover, status, route, sync |
| `tests/test_chatgpt_local_session.py` | Add registry/routing/sync tests |
| `conversation-corpus-site/state/chatgpt-project-registry.json` | Created by first `discover` |

## Verification

1. `python3 -m pytest -q` — suite green
2. `cce project discover` — scans all 63 projects, writes registry
3. `cce project status` — shows extraction state for each project
4. `cce project route --project-id <id> --destination <path>` — sets a route
5. `cce project extract --project-id <id> --output <path>` — extracts and updates registry
6. `cce project sync --batch-size 3` — extracts 3 queued projects to their routes
7. Registry correctly shows discovered/extracted/partial/delivered states
