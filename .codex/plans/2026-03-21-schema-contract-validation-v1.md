# Schema Contract Validation Plan

## Goal
Extract publishable JSON-schema contracts and a repo-native validation surface so corpus, policy, candidate, and refresh artifacts can be checked before Meta integration.

## Steps
1. Wire a `cce schema` CLI for catalog listing, schema inspection, and file validation.
2. Package `src/conversation_corpus_engine/schemas/*.json` as installable data.
3. Add regression tests that validate real generated artifacts against the published schemas.
4. Update contributor/public docs so the new contract surface is discoverable.
5. Re-run lint, tests, and a CLI smoke check.

## Expected Outputs
- Installable schema catalog under `src/conversation_corpus_engine/schemas/`
- `schema_validation.py` as the lightweight built-in validator
- `cce schema list|show|validate`
- Regression coverage for contract, source policy, promotion policy, corpus candidate, and provider refresh payloads
