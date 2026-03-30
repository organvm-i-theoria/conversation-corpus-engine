#!/usr/bin/env bash
set -euo pipefail

# ChatGPT local-session refresh — ongoing incremental sync
# Runs via LaunchAgent or manually. Reads cookies from the ChatGPT desktop app
# (or Chrome fallback), fetches new/updated conversations, caches payloads,
# and imports through the CCE pipeline.

export CCE_PROJECT_ROOT="${CCE_PROJECT_ROOT:-/Users/4jp/Workspace/organvm-i-theoria/conversation-corpus-site}"

LOGDIR="${CCE_PROJECT_ROOT}/reports"
mkdir -p "$LOGDIR"

exec >> "${LOGDIR}/chatgpt-local-session-refresh.log" 2>&1

echo "=== ChatGPT local-session refresh: $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

python3 -m conversation_corpus_engine.cli provider refresh \
  --provider chatgpt \
  --mode local-session \
  --project-root "$CCE_PROJECT_ROOT" \
  --approve --promote

echo "=== Done: $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
