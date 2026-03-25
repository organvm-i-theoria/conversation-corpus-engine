# Session Closeout Audit v17

Date: 2026-03-25
Repo: `/Users/4jp/Workspace/organvm-i-theoria/conversation-corpus-engine`

## Goal

Close the current CCE session without losing work, while reconciling code, registry state, metadata, and external indices.

## Steps

1. Re-read governing instructions and inspect repo, CLAUDE, seed, IRF, GitHub issue state.
2. Verify the session work is saved locally and identify whether remote persistence is still missing.
3. Audit live runtime artifacts for closure blockers instead of assuming passing tests are sufficient.
4. Fix any concrete defect uncovered by the audit before closeout.
5. Refresh stale repo metadata (`CLAUDE.md`, `seed.yaml`) to match the current command surface and capabilities.
6. Update the universal IRF for completed and newly discovered CCE items.
7. Propagate remaining open CCE work into GitHub issues where applicable.
8. Run validation, commit the repo, push origin, then commit and push any IRF/meta changes.
9. Answer whether the session is safe to close with explicit evidence and residual risks.
