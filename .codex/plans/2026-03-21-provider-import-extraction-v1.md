# Provider Import Extraction Plan

Date: 2026-03-21
Repo: `/Users/4jp/Workspace/organvm-i-theoria/conversation-corpus-engine`

## Goal

Move raw provider corpus materialization out of the staging workspace and into the canonical Organ I repo.

## Scope

1. Extract the reusable importer core needed to build corpora from:
   - Claude export bundles
   - Claude local desktop sessions
   - document-style export bundles used by Gemini, Grok, Perplexity, and Copilot
2. Add canonical CLI commands so `cce` can:
   - resolve a provider source from `source-drop`
   - materialize a corpus
   - optionally register it into federation
   - optionally rebuild federation
3. Ensure imported corpora include a manual review guide so readiness can advance beyond `imported-needs-bootstrap`.
4. Add regression tests for at least one document-export provider path and one Claude path or unit-equivalent.

## Non-Goals

- Port every staging helper verbatim.
- Port the full seeded evaluation curriculum in this pass.
- Port all refresh/replay/policy operations in this pass.

## Design

- Keep provider discovery/readiness modules as the public surface.
- Add importer modules under `src/conversation_corpus_engine/`.
- Add a thin orchestration module that maps provider + source mode to the correct importer.
- Default output roots should remain adjacent to the selected `source-drop` root, not inside the canonical repo.
- Keep runtime artifacts outside versioned source; `.gitignore` already covers generated state.

## Verification

- `python3 -m pytest -q`
- `python3 -m ruff check src tests`
- smoke test `cce provider import ... --register --build --json` against the real `source-drop` workspace
