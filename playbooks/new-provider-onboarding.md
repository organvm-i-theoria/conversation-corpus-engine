# Playbook: New Provider Onboarding

**Archetype:** THE ACQUISITOR (lead), THE EVALUATOR (gates), THE OPERATOR (CLI)

## Steps

### 1. Register in Provider Catalog

**File:** `src/conversation_corpus_engine/provider_catalog.py`

Add entry to `PROVIDER_CONFIG`:
```python
"newprovider": {
    "adapter_type": "newprovider-export",  # or "newprovider-local-session"
    "inbox_subdir": "newprovider/inbox",
    "corpus_id_prefix": "newprovider-export-",
    "display_name": "NewProvider",
},
```

### 2. Add Export Detection

**File:** `src/conversation_corpus_engine/provider_exports.py`

Create `looks_like_newprovider_export(path: Path) -> bool`. Signature detection
should identify the provider's export format (ZIP structure, JSON shape, etc.).

### 3. Wire Discovery

**File:** `src/conversation_corpus_engine/provider_discovery.py`

Add the detection mode call in `summarize_provider()` for the new provider.

### 4. Create Import Adapter

**File:** `src/conversation_corpus_engine/import_newprovider_export_corpus.py`

Follow the `import_chatgpt_export_corpus.py` pattern. Must produce:
- `threads-index.json` — conversation thread metadata
- `pairs-index.json` — question/answer pair index
- `doctrine-briefs.json` — topic/doctrine summaries
- `canonical-families.json` — entity family groupings

### 5. Wire Import Routing

**File:** `src/conversation_corpus_engine/provider_import.py`

- Add module-level import
- Add branch in `resolve_provider_import_source()`
- Add branch in `import_provider_corpus()`

### 6. Update CLI Choices

**File:** `src/conversation_corpus_engine/cli.py`

Add `"newprovider"` to all `choices=[...]` lists (6 occurrences).

### 7. Bootstrap Evaluation

```bash
cce provider bootstrap-eval --provider newprovider --project-root <root>
```

This scaffolds gold fixture files. Edit them with known-good answers.

### 8. Run Full Refresh

```bash
cce provider refresh --provider newprovider --mode upload \
  --project-root <root> --approve --promote --json
```

### 9. Write Tests

Create `tests/test_import_newprovider_export_corpus.py` with:
- Minimal fixture import test
- Edge cases (empty export, malformed data, missing fields)
- Thread linearization verification

## Verification

- All 8 evaluation gates pass for the new provider
- `cce provider readiness --json` shows the provider as "ready"
- `cce dashboard` includes the provider in the health summary
