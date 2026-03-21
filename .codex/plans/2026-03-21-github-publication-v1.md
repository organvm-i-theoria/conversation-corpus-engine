# GitHub Publication V1

Date: 2026-03-21
Project: organvm-i-theoria/conversation-corpus-engine

## Goal

Promote the canonical conversation corpus engine from a local extraction into a real GitHub-published Organ I repository.

## Scope

1. Audit the repo for publishable contents versus ignored runtime state.
2. Add any missing repo-level publication essentials.
3. Re-run lint and tests against the canonical codebase.
4. Create the initial commit history for the local git repository.
5. Create the GitHub remote in the correct Organ I namespace.
6. Push `main` so the canonical implementation is no longer local-only.

## Constraints

- Do not commit raw provider exports, state snapshots, federation artifacts, or reports.
- Keep the repo community-shareable.
- Preserve the existing extraction history in `.codex/plans/`.

## Verification

- `ruff check src tests`
- `pytest -q`
- confirm `origin` exists and `main` is pushed
