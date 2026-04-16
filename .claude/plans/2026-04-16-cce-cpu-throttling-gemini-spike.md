# Gemini Local-Session Provider Adapter for CCE

## Context

The Gemini macOS app (`com.google.GeminiMacOS`) was recently released. It stores conversation data locally in a Core Data SQLite cache at `~/Library/Caches/com.google.GeminiMacOS/Gemini/user1/ChatInfo2.store`. The CCE already has `gemini` in its `PROVIDER_CONFIG` but with `local_session_supported: False` and `discovery_mode: document-export`. This plan adds a local-session adapter following the ChatGPT/Claude pattern.

## What We Found

### Local Storage Structure

| Path | Format | Content |
|------|--------|---------|
| `~/Library/Application Support/com.google.GeminiMacOS/Data/user1/auth` | Binary (encrypted) | OAuth2 credentials |
| `~/Library/Caches/com.google.GeminiMacOS/Gemini/user1/ChatInfo2.store` | Core Data SQLite | **51 conversations** |
| `~/Library/HTTPStorages/com.google.GeminiMacOS/httpstorages.sqlite` | SQLite | HSTS/alt-svc only (not cookies) |

### ChatInfo2.store Schema

```sql
ZCHATINFOSTOREDMODEL (
  ZCHATUUID VARCHAR,              -- e.g. "c_621ebc9a3e48da2e"
  ZROBINCONVERSATIONID VARCHAR,   -- server-side ID (matches ZCHATUUID for synced)
  ZLASTUPDATEDTIME TIMESTAMP,     -- Core Data epoch (2001-01-01 base)
  ZENCRYPTEDPROTOBYTES BLOB       -- encrypted protobuf conversation data
)

ZCHATMESSAGESTOREDMODEL (
  ZCHATUUID VARCHAR,              -- FK to conversation
  ZMESSAGEUUID VARCHAR,
  ZMESSAGEINDEX INTEGER,
  ZHASTASKARTIFACTS INTEGER,
  ZCREATEDTIME TIMESTAMP,
  ZENCRYPTEDPROTOBYTES BLOB       -- encrypted protobuf message data
)
```

### Encryption

- Magic header: `2EBAFECA 2EBAFECA` (8 bytes) + 4-byte length prefix
- After header: protobuf wire format, partially readable (fields 1-5 = metadata), then encrypted payload
- Decryption key: macOS keychain → service: `"Gemini Safe Storage"`, account: `"Gemini Keys"`
- Likely AES-128-CBC with PBKDF2 derivation (same pattern as Chrome/Claude Safe Storage)

### API Architecture

- **Native Swift app** — not Electron/Chromium
- Uses **gRPC/protobuf** internally (`google.ai.generativelanguage.v1main`)
- Internal codename: "Robin" (`assistant_mobile_robin_proto`)
- Auth: Google OAuth2 via `accounts.google.com/o/oauth2/auth`
- Protobuf messages: `ConversationTurn`, `Session_UserMessage`, `Session_ModelMessage`

## Problem: Two Unknowns

Before building the full adapter, two things need empirical validation:

1. **Can we decrypt the protobytes?** — We know the keychain service/account names. We need to confirm the derivation scheme (PBKDF2 params, IV extraction) and AES variant.

2. **Can we decode the protobuf without `.proto` files?** — Raw protobuf wire format is decodable field-by-field, but we need to map field numbers to semantic meaning (title, user text, model text, timestamps). This requires decrypting a few conversations and manually inspecting the decoded fields.

## Plan — Two Phases

### Phase 1: Spike — Decrypt + Decode (investigative, this session)

Build a standalone investigation script that:

1. Reads the `"Gemini Safe Storage"` password from keychain via `security find-generic-password`
2. Derives the AES key via PBKDF2 (try Chrome-style params: SHA1, salt `"saltysalt"`, 1003 iterations, 16-byte key)
3. Reads `ChatInfo2.store`, extracts `ZENCRYPTEDPROTOBYTES` for a known conversation
4. Strips the 8-byte magic + 4-byte length header
5. Attempts AES-128-CBC decryption of the encrypted portion (after the metadata proto fields)
6. Decodes the resulting protobuf wire format field-by-field
7. Reports what fields contain: titles, message text, timestamps, roles

**Success criteria:** We can extract human-readable conversation text (user prompts + model responses) from at least one conversation.

**If decryption fails:** Fall back to **web API approach** — extract Google session cookies from Chrome (we already read Chrome cookies for ChatGPT fallback) and hit `gemini.google.com` web endpoints.

### Phase 2: Full Adapter (build, next session after spike confirms)

Following the ChatGPT/Claude pattern exactly:

**New files:**
- `src/conversation_corpus_engine/gemini_local_session.py` — session discovery, cache reading, decryption, protobuf decoding, bundle assembly
- `src/conversation_corpus_engine/import_gemini_local_session_corpus.py` — bundle → corpus transformation (delegates to document-export or custom adapter)
- `tests/test_gemini_local_session.py` — unit tests with synthetic fixtures

**Modified files:**
- `provider_catalog.py` — update gemini config: `local_session_supported: True`, add `local_source_root`, `default_corpus_id` for local-session
- `provider_import.py` — add gemini local-session routing branch
- `provider_exports.py` — add `looks_like_gemini_local_session` detection
- `provider_discovery.py` — add gemini local-session to `summarize_provider()`
- `cli.py` — gemini already in provider choices; ensure `--mode local-session` works
- `scripts/refresh_local_sessions.sh` — add gemini as third provider in the refresh loop

**Existing utilities to reuse:**
- `claude_local_session.py:find_safe_storage_password()` — same keychain pattern, adapt service name
- `claude_local_session.py:decrypt_chromium_cookie()` — same AES decryption pattern if PBKDF2 params match
- `chatgpt_local_session.py:load_prior_acquisition()` / `save_acquisition_state()` — delta-sync pattern
- `import_chatgpt_export_corpus.py:detect_near_duplicates()` — now with trigram pre-filter
- `answering.py:tokenize()`, `slugify()`, `write_json()`, `write_markdown()`

**Key design decisions:**
- Protobuf decoding: stdlib-only raw wire format parser (no `protobuf` pip dependency)
- Conversation text extraction: map wire format fields to roles/content empirically
- Delta-sync: use `ZLASTUPDATEDTIME` from SQLite as the change-detection signal
- Cache reading is **offline** — no network required (unlike ChatGPT/Claude which fetch from APIs)

## Verification

### Phase 1 (spike)
- Script successfully decrypts and decodes at least 3 conversations
- Extracted text matches what's visible in the Gemini app
- Document the field mapping (field N = title, field M = user text, etc.)

### Phase 2 (adapter)
- `python -m pytest tests/ -v` — all tests pass
- `cce provider discover --provider gemini` reports local-session available
- `cce provider refresh --provider gemini --mode local-session --project-root ... --no-eval` completes without error
- Output corpus has `threads-index.json`, `pairs-index.json`, `near-duplicates.json` consistent with other providers

## Critical Files

| File | Purpose |
|------|---------|
| `~/Library/Caches/com.google.GeminiMacOS/Gemini/user1/ChatInfo2.store` | Local conversation cache (SQLite) |
| `src/conversation_corpus_engine/claude_local_session.py` | Template for keychain + decryption pattern |
| `src/conversation_corpus_engine/chatgpt_local_session.py` | Template for bundle fetch + delta-sync |
| `src/conversation_corpus_engine/import_chatgpt_local_session_corpus.py` | Template for local-session → corpus pipeline |
| `src/conversation_corpus_engine/provider_catalog.py` | Provider config registry |
| `src/conversation_corpus_engine/provider_import.py` | Import routing |
