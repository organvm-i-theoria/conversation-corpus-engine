# Operational Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the conversation-corpus-engine from a freshly-published single-commit repo into a CI-gated, governance-integrated, fixture-documented, ChatGPT-capable production system.

**Architecture:** Four parallel hardening fronts converging on a single repo: (1) GitHub Actions CI gates pytest + ruff on every push/PR, (2) seed.yaml + project CLAUDE.md integrate the repo into the ORGANVM governance ecosystem, (3) shared pytest fixtures + conftest replace inline tempdir scaffolding and provide sanitized demo data, (4) a ChatGPT/OpenAI provider adapter follows the existing `import_claude_export_corpus` pattern to parse ChatGPT's `conversations.json` export format and register as a first-class provider.

**Tech Stack:** Python 3.11+, pytest, ruff, GitHub Actions, JSON Schema, argparse CLI

**Baseline:** 41 tests passing in 0.4s, 0 ruff lint errors, single commit `c85f93b` on `main`.

---

## File Structure

### New Files
| Path | Responsibility |
|------|---------------|
| `.github/workflows/ci.yml` | GitHub Actions CI: pytest + ruff on push/PR |
| `seed.yaml` | ORGANVM governance contract |
| `CLAUDE.md` | Project-specific Claude Code instructions |
| `tests/conftest.py` | Shared pytest fixtures (project_root, source_drop_root, corpus seeding) |
| `tests/fixtures/chatgpt-export/conversations.json` | Sanitized minimal ChatGPT export (3 conversations) |
| `tests/fixtures/chatgpt-export/user.json` | Sanitized ChatGPT user metadata |
| `src/conversation_corpus_engine/import_chatgpt_export_corpus.py` | ChatGPT conversations.json → federation corpus |
| `tests/test_import_chatgpt_export_corpus.py` | Tests for ChatGPT import adapter |

### Modified Files
| Path | Change |
|------|--------|
| `src/conversation_corpus_engine/provider_catalog.py` | Add `chatgpt` entry to `PROVIDER_CONFIG` |
| `src/conversation_corpus_engine/provider_exports.py` | Add `looks_like_chatgpt_export()` + `resolve_chatgpt_source_path()` |
| `src/conversation_corpus_engine/provider_discovery.py` | Wire ChatGPT detection into `summarize_provider()` |
| `src/conversation_corpus_engine/provider_import.py` | Route `chatgpt` provider to dedicated adapter |
| `src/conversation_corpus_engine/cli.py` | Add `chatgpt` to provider choices |
| `pyproject.toml` | Version bump 0.1.0 → 0.2.0 |
| `src/conversation_corpus_engine/__init__.py` | Version bump |
| `README.md` | Add CI badge, ChatGPT provider, CLAUDE.md reference |

---

## Phase 1: CI Foundation

### Task 1: GitHub Actions CI Workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write the CI workflow**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - run: python -m pytest tests/ -v --tb=short
      - run: python -m ruff check src/ tests/
      - run: python -m ruff format --check src/ tests/

  schema-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: python -c "from conversation_corpus_engine.schema_validation import list_schemas, load_schema; [load_schema(s['name']) for s in list_schemas()]"
```

- [ ] **Step 2: Verify workflow YAML is valid**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" 2>&1 || echo "pyyaml not available, visual check only"`

- [ ] **Step 3: Run the test + lint suite locally to confirm it mirrors CI**

Run: `python -m pytest tests/ -v --tb=short && pipx run ruff check src/ tests/ && pipx run ruff format --check src/ tests/`
Expected: 41 tests PASS, 0 lint errors, 0 format diffs

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions workflow for pytest, ruff, and schema validation"
```

---

## Phase 2: Governance Integration

### Task 2: seed.yaml Contract

**Files:**
- Create: `seed.yaml`

- [ ] **Step 1: Write the seed.yaml governance contract**

```yaml
organ: ORGAN-I
org: organvm-i-theoria
repo: conversation-corpus-engine

metadata:
  tier: standard
  promotion_status: GRADUATED
  description: >-
    Canonical corpus and federation engine for multi-provider AI conversation memory.
    Owns provider import, evaluation, governance, federation, and Meta/MCP surface exports.
  language: python
  license: MIT

produces:
  - surface-manifest.json
  - mcp-context.json
  - surface-bundle.json
  - corpus-contract.schema.json
  - surface-manifest.schema.json
  - mcp-context.schema.json
  - surface-bundle.schema.json
  - promotion-policy.schema.json
  - provider-refresh.schema.json
  - source-policy.schema.json
  - corpus-candidate.schema.json

consumes:
  - provider-exports  # raw exports from claude, gemini, grok, perplexity, copilot, chatgpt

subscriptions:
  - governance.updated
  - schema.registry.sync
```

- [ ] **Step 2: Validate YAML is parseable**

Run: `python -c "import yaml; print(yaml.safe_load(open('seed.yaml'))['organ'])"` or `python -c "import json; exec(\"import pathlib, re\\ntext = pathlib.Path('seed.yaml').read_text()\\nprint('organ:' in text and 'ORGAN-I' in text)\")"`
Expected: Truthy output confirming organ = ORGAN-I

- [ ] **Step 3: Commit**

```bash
git add seed.yaml
git commit -m "chore: add seed.yaml governance contract"
```

### Task 3: Project CLAUDE.md

**Files:**
- Create: `CLAUDE.md`

- [ ] **Step 1: Write the project CLAUDE.md**

```markdown
# CLAUDE.md

Project-specific guidance for Claude Code in this repository.

## What This Is

**conversation-corpus-engine** is the canonical Organ I implementation of the AI conversation corpus system. It owns provider import, corpus validation, evaluation, federation, governance policy, and Meta/MCP surface exports.

- GitHub: `organvm-i-theoria/conversation-corpus-engine`
- Organ: ORGAN-I (Theory)
- Tier: standard
- Promotion status: GRADUATED

## Commands

```bash
# Install
pip install -e ".[dev]"

# Test
python -m pytest tests/ -v
python -m pytest tests/test_specific.py::ClassName::test_name -v  # single test

# Lint
pipx run ruff check src/ tests/
pipx run ruff format --check src/ tests/

# CLI
cce corpus list
cce provider discover
cce provider readiness --write
cce schema list
cce schema validate corpus-contract --path /path/to/contract.json
cce surface bundle
```

## Architecture

- `src/conversation_corpus_engine/` — all source code, flat module structure
- `src/conversation_corpus_engine/schemas/` — JSON Schema contracts (bundled with package)
- `tests/` — unittest-based test suite (all tests use `tempfile.TemporaryDirectory`)
- `federation/`, `reports/`, `state/` — runtime output dirs (gitignored)

### Provider Adapter Pattern

Each provider has:
1. An entry in `provider_catalog.py` `PROVIDER_CONFIG` dict
2. A detection function in `provider_exports.py`
3. An import module (`import_*_corpus.py`) that produces federation-compatible corpus artifacts
4. Wiring in `provider_import.py` to route the provider to its adapter
5. CLI choices in `cli.py`

Non-Claude providers route through `import_document_export_corpus.py` (generic multi-format).
Claude has two dedicated adapters: `import_claude_export_corpus.py` (JSON bundle) and `import_claude_local_session_corpus.py` (Application Support).
ChatGPT has a dedicated adapter: `import_chatgpt_export_corpus.py` (conversations.json with mapping tree).

### Test Pattern

Tests use `unittest.TestCase` with `tempfile.TemporaryDirectory`. Each test scaffolds its own isolated filesystem. Shared helpers in `tests/conftest.py` provide pytest fixtures for common corpus seeding.

## Runtime Outputs

`federation/`, `reports/`, `state/`, and `source-drop/` are gitignored. The repo tracks only code, schemas, tests, and documentation.

## Environment Variables

- `CCE_PROJECT_ROOT` — override the default project root (defaults to repo root)
- `CCE_SOURCE_DROP_ROOT` — override the source-drop inbox location

## Conventions

- Conventional Commits: `feat:`, `fix:`, `docs:`, `chore:`, `ci:`, `test:`
- Python: PEP 8, type hints, ruff linting, unittest + pytest
- No external runtime dependencies (stdlib only for core engine)
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add project CLAUDE.md with architecture and command reference"
```

---

## Phase 3: Shared Test Infrastructure

### Task 4: pytest conftest with Shared Fixtures

**Files:**
- Create: `tests/conftest.py`

- [ ] **Step 1: Write conftest.py with shared fixtures**

```python
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Isolated workspace root with project and source-drop subdirectories."""
    project_root = tmp_path / "project"
    source_drop_root = tmp_path / "source-drop"
    project_root.mkdir()
    source_drop_root.mkdir()
    return tmp_path


@pytest.fixture
def project_root(workspace: Path) -> Path:
    return workspace / "project"


@pytest.fixture
def source_drop_root(workspace: Path) -> Path:
    return workspace / "source-drop"


def seed_minimal_corpus(
    root: Path,
    *,
    corpus_id: str = "test-corpus",
    name: str = "Test Corpus",
    adapter_type: str = "test-adapter",
    gate_state: str = "pass",
    thread_count: int = 1,
) -> Path:
    """Seed a minimal valid corpus at `root` with configurable gate state."""
    corpus_dir = root / "corpus"
    eval_dir = root / "eval"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    eval_dir.mkdir(parents=True, exist_ok=True)

    threads = [
        {
            "thread_uid": f"thread-test-{i:03d}",
            "title_normalized": f"Test Thread {i}",
            "family_ids": [f"family-test-{i:03d}"],
        }
        for i in range(thread_count)
    ]
    families = [
        {
            "canonical_family_id": f"family-test-{i:03d}",
            "canonical_title": f"Test Family {i}",
            "canonical_thread_uid": f"thread-test-{i:03d}",
            "thread_uids": [f"thread-test-{i:03d}"],
        }
        for i in range(thread_count)
    ]
    doctrine_briefs = [
        {
            "family_id": f"family-test-{i:03d}",
            "canonical_title": f"Test Family {i}",
            "canonical_thread_uid": f"thread-test-{i:03d}",
            "stable_themes": ["test", "fixture"],
            "brief_text": f"Test brief {i}",
        }
        for i in range(thread_count)
    ]

    for rel, content in {
        "threads-index.json": threads,
        "pairs-index.json": [],
        "doctrine-briefs.json": doctrine_briefs,
        "family-dossiers.json": [],
        "canonical-families.json": families,
        "action-ledger.json": [],
        "unresolved-ledger.json": [],
        "canonical-entities.json": [],
    }.items():
        (corpus_dir / rel).write_text(json.dumps(content), encoding="utf-8")

    (corpus_dir / "semantic-v3-index.json").write_text(
        json.dumps({"threads": []}), encoding="utf-8",
    )
    (corpus_dir / "evaluation-summary.json").write_text(
        json.dumps({"regression_gates": {"overall_state": gate_state}}),
        encoding="utf-8",
    )
    (corpus_dir / "regression-gates.json").write_text(
        json.dumps({
            "overall_state": gate_state,
            "source_reliability_state": "pass",
        }),
        encoding="utf-8",
    )
    (corpus_dir / "contract.json").write_text(
        json.dumps({
            "contract_name": "conversation-corpus-engine-v1",
            "contract_version": 1,
            "adapter_type": adapter_type,
            "corpus_id": corpus_id,
            "name": name,
        }),
        encoding="utf-8",
    )
    (eval_dir / "manual-review-guide.md").write_text("# Manual Review\n", encoding="utf-8")
    return root


def write_markdown_sources(root: Path, files: dict[str, str]) -> None:
    """Write markdown files into a directory tree for import testing."""
    for relative_path, content in files.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def seed_provider_inbox(source_drop_root: Path, provider: str, files: dict[str, str]) -> Path:
    """Seed a provider inbox under source-drop with the given files."""
    inbox = source_drop_root / provider / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (inbox / name).write_text(content, encoding="utf-8")
    return inbox
```

- [ ] **Step 2: Run existing tests to confirm conftest doesn't break anything**

Run: `python -m pytest tests/ -v --tb=short`
Expected: 41 tests PASS (conftest is additive — existing tests don't use these fixtures yet)

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add shared pytest conftest with corpus seeding and inbox helpers"
```

### Task 5: Sanitized ChatGPT Export Fixture

**Files:**
- Create: `tests/fixtures/chatgpt-export/conversations.json`
- Create: `tests/fixtures/chatgpt-export/user.json`

- [ ] **Step 1: Write the sanitized ChatGPT export fixture**

The ChatGPT export format uses `conversations.json` with a `mapping` tree of message nodes. Each conversation has a `title`, `create_time`, `update_time`, and a `mapping` dict where keys are message UUIDs and values have `message` objects with `author.role` and `content.parts`.

`tests/fixtures/chatgpt-export/conversations.json`:
```json
[
  {
    "title": "Python Type Hints",
    "create_time": 1710000000.0,
    "update_time": 1710000300.0,
    "mapping": {
      "msg-system-001": {
        "id": "msg-system-001",
        "message": {
          "id": "msg-system-001",
          "author": {"role": "system"},
          "content": {"content_type": "text", "parts": ["You are ChatGPT."]},
          "create_time": 1710000000.0
        },
        "parent": null,
        "children": ["msg-user-001"]
      },
      "msg-user-001": {
        "id": "msg-user-001",
        "message": {
          "id": "msg-user-001",
          "author": {"role": "user"},
          "content": {"content_type": "text", "parts": ["Explain Python type hints for function signatures."]},
          "create_time": 1710000010.0
        },
        "parent": "msg-system-001",
        "children": ["msg-asst-001"]
      },
      "msg-asst-001": {
        "id": "msg-asst-001",
        "message": {
          "id": "msg-asst-001",
          "author": {"role": "assistant"},
          "content": {"content_type": "text", "parts": ["Type hints in Python let you annotate function parameters and return values. Use the typing module for complex types like Optional, Union, and generics."]},
          "create_time": 1710000020.0
        },
        "parent": "msg-user-001",
        "children": []
      }
    },
    "conversation_id": "conv-fixture-001"
  },
  {
    "title": "Git Rebase Strategy",
    "create_time": 1710100000.0,
    "update_time": 1710100600.0,
    "mapping": {
      "msg-system-002": {
        "id": "msg-system-002",
        "message": {
          "id": "msg-system-002",
          "author": {"role": "system"},
          "content": {"content_type": "text", "parts": ["You are ChatGPT."]},
          "create_time": 1710100000.0
        },
        "parent": null,
        "children": ["msg-user-002"]
      },
      "msg-user-002": {
        "id": "msg-user-002",
        "message": {
          "id": "msg-user-002",
          "author": {"role": "user"},
          "content": {"content_type": "text", "parts": ["When should I use git rebase instead of merge?"]},
          "create_time": 1710100010.0
        },
        "parent": "msg-system-002",
        "children": ["msg-asst-002"]
      },
      "msg-asst-002": {
        "id": "msg-asst-002",
        "message": {
          "id": "msg-asst-002",
          "author": {"role": "assistant"},
          "content": {"content_type": "text", "parts": ["Rebase is best for keeping a linear history on feature branches before merging. Use merge for shared branches where you need to preserve the full commit graph."]},
          "create_time": 1710100020.0
        },
        "parent": "msg-user-002",
        "children": ["msg-user-003"]
      },
      "msg-user-003": {
        "id": "msg-user-003",
        "message": {
          "id": "msg-user-003",
          "author": {"role": "user"},
          "content": {"content_type": "text", "parts": ["What about interactive rebase for squashing commits?"]},
          "create_time": 1710100030.0
        },
        "parent": "msg-asst-002",
        "children": ["msg-asst-003"]
      },
      "msg-asst-003": {
        "id": "msg-asst-003",
        "message": {
          "id": "msg-asst-003",
          "author": {"role": "assistant"},
          "content": {"content_type": "text", "parts": ["Interactive rebase with git rebase -i lets you squash, reorder, and edit commits. It is ideal for cleaning up a feature branch before a pull request."]},
          "create_time": 1710100040.0
        },
        "parent": "msg-user-003",
        "children": []
      }
    },
    "conversation_id": "conv-fixture-002"
  },
  {
    "title": null,
    "create_time": 1710200000.0,
    "update_time": 1710200000.0,
    "mapping": {
      "msg-system-003": {
        "id": "msg-system-003",
        "message": null,
        "parent": null,
        "children": ["msg-user-004"]
      },
      "msg-user-004": {
        "id": "msg-user-004",
        "message": {
          "id": "msg-user-004",
          "author": {"role": "user"},
          "content": {"content_type": "text", "parts": ["Hello"]},
          "create_time": 1710200010.0
        },
        "parent": "msg-system-003",
        "children": []
      }
    },
    "conversation_id": "conv-fixture-003"
  }
]
```

`tests/fixtures/chatgpt-export/user.json`:
```json
{
  "id": "user-fixture-001",
  "email": "fixture@example.com",
  "chatgpt_plus_user": false
}
```

Notes on fixture design:
- Conversation 1: single turn, titled, clean structure
- Conversation 2: multi-turn, titled, 2 user/assistant exchanges
- Conversation 3: null title, single user message (no assistant response), null message node — tests edge cases

- [ ] **Step 2: Validate fixture JSON is parseable**

Run: `python -c "import json, pathlib; data = json.loads(pathlib.Path('tests/fixtures/chatgpt-export/conversations.json').read_text()); print(f'{len(data)} conversations, titles: {[c.get(\"title\") for c in data]}')"`
Expected: `3 conversations, titles: ['Python Type Hints', 'Git Rebase Strategy', None]`

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/
git commit -m "test: add sanitized ChatGPT export fixtures for adapter testing"
```

---

## Phase 4: ChatGPT Provider Adapter

### Task 6: ChatGPT Detection in provider_exports.py

**Files:**
- Modify: `src/conversation_corpus_engine/provider_exports.py`

- [ ] **Step 1: Write a failing test for ChatGPT detection**

Create `tests/test_import_chatgpt_export_corpus.py` with the detection test:

```python
from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversation_corpus_engine.provider_exports import looks_like_chatgpt_export

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "chatgpt-export"


class ChatGPTDetectionTests(unittest.TestCase):
    def test_looks_like_chatgpt_export_identifies_fixture(self) -> None:
        self.assertTrue(looks_like_chatgpt_export(FIXTURE_ROOT))

    def test_looks_like_chatgpt_export_rejects_empty_dir(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertFalse(looks_like_chatgpt_export(Path(tmpdir)))

    def test_looks_like_chatgpt_export_rejects_claude_bundle(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "conversations.json").write_text("[]", encoding="utf-8")
            (root / "users.json").write_text("[]", encoding="utf-8")
            # Claude bundles have users.json (plural), ChatGPT has user.json (singular)
            self.assertFalse(looks_like_chatgpt_export(root))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_import_chatgpt_export_corpus.py::ChatGPTDetectionTests -v`
Expected: FAIL with `cannot import name 'looks_like_chatgpt_export'`

- [ ] **Step 3: Implement detection functions in provider_exports.py**

Add to `src/conversation_corpus_engine/provider_exports.py`:

```python
def looks_like_chatgpt_export(path: Path) -> bool:
    """Detect a ChatGPT export: has conversations.json + user.json (singular, not plural)."""
    if not path.is_dir():
        return False
    has_conversations = (path / "conversations.json").exists()
    has_user_singular = (path / "user.json").exists()
    has_users_plural = (path / "users.json").exists()
    # ChatGPT exports have user.json; Claude exports have users.json
    return has_conversations and has_user_singular and not has_users_plural


def resolve_chatgpt_source_path(upload_root: Path) -> Path:
    """Resolve a ChatGPT export source from an inbox directory."""
    upload_root = upload_root.resolve()
    if looks_like_chatgpt_export(upload_root):
        return upload_root
    entries = visible_entries(upload_root)
    if not entries:
        raise FileNotFoundError(
            f"No ChatGPT upload was found in {upload_root}. Put the raw ChatGPT export folder there first.",
        )
    export_dirs = [item.resolve() for item in entries if looks_like_chatgpt_export(item)]
    if len(export_dirs) == 1:
        return export_dirs[0]
    if len(export_dirs) > 1:
        raise FileNotFoundError(
            f"Multiple ChatGPT export bundles were found in {upload_root}. Leave only one at a time.",
        )
    if len(entries) == 1:
        return entries[0].resolve()
    raise FileNotFoundError(
        f"ChatGPT upload inbox {upload_root} contains multiple visible entries but no ChatGPT export could be selected.",
    )
```

- [ ] **Step 4: Run detection tests to verify they pass**

Run: `python -m pytest tests/test_import_chatgpt_export_corpus.py::ChatGPTDetectionTests -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/conversation_corpus_engine/provider_exports.py tests/test_import_chatgpt_export_corpus.py
git commit -m "feat: add ChatGPT export detection to provider_exports"
```

### Task 7: ChatGPT Import Adapter

**Files:**
- Create: `src/conversation_corpus_engine/import_chatgpt_export_corpus.py`
- Modify: `tests/test_import_chatgpt_export_corpus.py`

- [ ] **Step 1: Add import test to the test file**

Append to `tests/test_import_chatgpt_export_corpus.py`:

```python
from conversation_corpus_engine.import_chatgpt_export_corpus import import_chatgpt_export_corpus


class ImportChatGPTExportCorpusTests(unittest.TestCase):
    def test_import_chatgpt_export_builds_federation_surface(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir) / "chatgpt-history-memory"
            result = import_chatgpt_export_corpus(
                FIXTURE_ROOT,
                output_root,
                corpus_id="chatgpt-history-memory",
                name="ChatGPT History Memory",
            )

            self.assertEqual(result["corpus_id"], "chatgpt-history-memory")
            self.assertEqual(result["name"], "ChatGPT History Memory")
            # 3 conversations in fixture, but conv 3 has no assistant response
            # so it should still import (single user message is valid)
            self.assertGreaterEqual(result["thread_count"], 2)
            self.assertGreaterEqual(result["pair_count"], 1)

            # Verify contract.json was written
            contract = json.loads(
                (output_root / "corpus" / "contract.json").read_text(encoding="utf-8"),
            )
            self.assertEqual(contract["adapter_type"], "chatgpt-export")
            self.assertEqual(contract["contract_name"], "conversation-corpus-engine-v1")

            # Verify federation-required files exist
            corpus_dir = output_root / "corpus"
            for required in (
                "threads-index.json",
                "pairs-index.json",
                "doctrine-briefs.json",
                "canonical-families.json",
                "evaluation-summary.json",
                "regression-gates.json",
            ):
                self.assertTrue(
                    (corpus_dir / required).exists(),
                    f"Missing required corpus artifact: {required}",
                )

    def test_import_chatgpt_handles_null_title_and_null_message(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir) / "chatgpt-memory"
            result = import_chatgpt_export_corpus(
                FIXTURE_ROOT,
                output_root,
                corpus_id="chatgpt-memory",
                name="ChatGPT Memory",
            )
            threads = json.loads(
                (output_root / "corpus" / "threads-index.json").read_text(encoding="utf-8"),
            )
            # At least one thread should exist even from the null-title conversation
            titles = [t["title_normalized"] for t in threads]
            # The null-title conversation should have an inferred title
            self.assertTrue(all(isinstance(t, str) and len(t) > 0 for t in titles))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_import_chatgpt_export_corpus.py::ImportChatGPTExportCorpusTests -v`
Expected: FAIL with `No module named 'conversation_corpus_engine.import_chatgpt_export_corpus'`

- [ ] **Step 3: Write the ChatGPT import adapter**

Create `src/conversation_corpus_engine/import_chatgpt_export_corpus.py`:

```python
from __future__ import annotations

import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .answering import slugify, tokenize, write_json, write_markdown
from .source_lifecycle import build_source_snapshot

CONTRACT_NAME = "conversation-corpus-engine-v1"
CONTRACT_VERSION = 1
STOP_WORDS = {
    "a", "about", "all", "also", "an", "and", "any", "are", "as", "at",
    "be", "been", "being", "but", "by", "can", "could", "do", "for", "from",
    "get", "going", "have", "if", "in", "into", "is", "it", "just", "like",
    "make", "maybe", "more", "need", "not", "of", "on", "or", "our", "out",
    "say", "should", "so", "that", "the", "their", "them", "then", "there",
    "they", "this", "to", "want", "we", "what", "where", "will", "with",
    "you", "your",
}
ACTION_MARKERS = (
    "need to", "needs to", "should", "will", "want to",
    "implement", "add", "build", "develop", "next step", "recommend",
)
UNRESOLVED_MARKERS = (
    "maybe", "perhaps", "unclear", "unknown", "whether", "what if", "which option",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_whitespace(text: str) -> str:
    return " ".join(text.split()).strip()


def shorten(text: str, limit: int = 320) -> str:
    cleaned = normalize_whitespace(text)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 3)].rstrip() + "..."


def split_sentences(text: str) -> list[str]:
    rough = []
    for line in text.splitlines():
        stripped_line = line.strip()
        if not stripped_line:
            continue
        rough.extend(
            part.strip()
            for part in stripped_line.replace("?", "?\n").replace("!", "!\n").replace(".", ".\n").splitlines()
        )
    return [normalize_whitespace(item) for item in rough if normalize_whitespace(item)]


def top_keywords(text: str, *, limit: int = 12) -> list[str]:
    counts = Counter(
        token for token in tokenize(text)
        if token not in STOP_WORDS and len(token) > 2
    )
    return [token for token, _ in counts.most_common(limit)]


def vector_terms(text: str, *, limit: int = 18) -> dict[str, float]:
    counts = Counter(
        token for token in tokenize(text)
        if token not in STOP_WORDS and len(token) > 2
    )
    if not counts:
        return {}
    highest = max(counts.values())
    return {token: round(count / highest, 4) for token, count in counts.most_common(limit)}  # allow-secret


def dedupe_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        cleaned = normalize_whitespace(value)
        lowered = cleaned.lower()
        if not cleaned or lowered in seen:
            continue
        seen.add(lowered)
        ordered.append(cleaned)
    return ordered


def extract_actions(sentences: list[str]) -> list[str]:
    candidates = []
    for sentence in sentences:
        lowered = sentence.lower()
        if len(sentence) < 24 or len(sentence) > 220:
            continue
        if any(marker in lowered for marker in ACTION_MARKERS):
            candidates.append(shorten(sentence, 180))
    return dedupe_preserve(candidates)[:6]


def extract_unresolved(sentences: list[str]) -> list[str]:
    candidates = []
    for sentence in sentences:
        lowered = sentence.lower()
        if len(sentence) < 24 or len(sentence) > 220:
            continue
        if sentence.endswith("?") or any(marker in lowered for marker in UNRESOLVED_MARKERS):
            candidates.append(shorten(sentence, 180))
    return dedupe_preserve(candidates)[:5]


def linearize_mapping(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    """Walk the ChatGPT mapping tree and return messages in chronological order."""
    nodes = {}
    roots = []
    for node_id, node in mapping.items():
        nodes[node_id] = node
        if node.get("parent") is None:
            roots.append(node_id)

    messages: list[dict[str, Any]] = []
    visited: set[str] = set()

    def walk(node_id: str) -> None:
        if node_id in visited or node_id not in nodes:
            return
        visited.add(node_id)
        node = nodes[node_id]
        msg = node.get("message")
        if msg is not None:
            messages.append(msg)
        for child_id in node.get("children") or []:
            walk(child_id)

    for root_id in roots:
        walk(root_id)

    messages.sort(key=lambda m: m.get("create_time") or 0)
    return messages


def extract_message_text(message: dict[str, Any]) -> str:
    content = message.get("content") or {}
    parts = content.get("parts") or []
    segments = []
    for part in parts:
        if isinstance(part, str):
            cleaned = normalize_whitespace(part)
            if cleaned:
                segments.append(cleaned)
    return normalize_whitespace(" ".join(segments))


def build_pairs(
    messages: list[dict[str, Any]],
    thread_uid: str,
    family_id: str,
) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    current_prompt = ""
    current_response_parts: list[str] = []
    current_title = ""
    pair_index = 0

    for message in messages:
        role = (message.get("author") or {}).get("role", "")
        text = extract_message_text(message)
        if not text:
            continue
        if role == "system":
            continue
        if role == "user":
            if current_prompt or current_response_parts:
                pair_index += 1
                response_text = normalize_whitespace(" ".join(current_response_parts))
                summary = shorten(f"User: {current_prompt} Assistant: {response_text}", 240)
                pair_id = f"{thread_uid}-pair-{pair_index:03d}"
                pairs.append({
                    "pair_id": pair_id,
                    "thread_uid": thread_uid,
                    "title": current_title or shorten(current_prompt, 80) or f"ChatGPT Pair {pair_index:03d}",
                    "summary": summary,
                    "search_text": f"{pair_id} {current_prompt} {response_text}",
                    "themes": top_keywords(f"{current_prompt} {response_text}", limit=8),
                    "entities": [],
                    "family_ids": [family_id],
                    "vector_terms": vector_terms(f"{current_prompt} {response_text}"),
                })
            current_prompt = text
            current_title = shorten(text, 80)
            current_response_parts = []
        elif role == "assistant":
            if not current_prompt:
                current_prompt = "[assistant-led]"
                current_title = "Assistant-Led Turn"
            current_response_parts.append(text)

    if current_prompt or current_response_parts:
        pair_index += 1
        response_text = normalize_whitespace(" ".join(current_response_parts))
        summary = shorten(f"User: {current_prompt} Assistant: {response_text}", 240)
        pair_id = f"{thread_uid}-pair-{pair_index:03d}"
        pairs.append({
            "pair_id": pair_id,
            "thread_uid": thread_uid,
            "title": current_title or f"ChatGPT Pair {pair_index:03d}",
            "summary": summary,
            "search_text": f"{pair_id} {current_prompt} {response_text}",
            "themes": top_keywords(f"{current_prompt} {response_text}", limit=8),
            "entities": [],
            "family_ids": [family_id],
            "vector_terms": vector_terms(f"{current_prompt} {response_text}"),
        })
    return pairs


def build_entities(title: str, keywords: list[str]) -> list[dict[str, str]]:
    entities = [{"canonical_label": title, "entity_type": "conversation"}]
    for keyword in keywords[:3]:
        entities.append({
            "canonical_label": keyword.replace("-", " ").title(),
            "entity_type": "concept",
        })
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for entity in entities:
        label = normalize_whitespace(entity["canonical_label"])
        lowered = label.lower()
        if not label or lowered in seen:
            continue
        seen.add(lowered)
        result.append({"canonical_label": label, "entity_type": entity["entity_type"]})
    return result


def infer_title(conversation: dict[str, Any], fallback_index: int) -> str:
    title = conversation.get("title")
    if isinstance(title, str) and normalize_whitespace(title):
        return normalize_whitespace(title)
    mapping = conversation.get("mapping") or {}
    messages = linearize_mapping(mapping)
    for msg in messages:
        role = (msg.get("author") or {}).get("role", "")
        if role == "user":
            text = extract_message_text(msg)
            if text:
                return shorten(text, 120)
    return f"ChatGPT Conversation {fallback_index:04d}"


def copy_export_files(export_root: Path, output_root: Path) -> list[str]:
    copied: list[str] = []
    source_root = output_root / "source"
    source_root.mkdir(parents=True, exist_ok=True)
    for path in sorted(export_root.rglob("*.json")):
        relative = path.relative_to(export_root)
        destination = source_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        copied.append(str(destination))
    return copied


def import_chatgpt_export_corpus(
    input_path: Path,
    output_root: Path,
    *,
    corpus_id: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    input_path = input_path.resolve()
    conversations_path = input_path / "conversations.json"
    if not conversations_path.exists():
        raise FileNotFoundError(f"ChatGPT export at {input_path} is missing conversations.json")

    conversations = json.loads(conversations_path.read_text(encoding="utf-8"))

    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "corpus").mkdir(parents=True, exist_ok=True)

    copied_sources = copy_export_files(input_path, output_root)

    threads: list[dict[str, Any]] = []
    semantic_threads: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    doctrine_briefs: list[dict[str, Any]] = []
    family_dossiers: list[dict[str, Any]] = []
    canonical_families: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    import_manifest: list[dict[str, Any]] = []
    entity_map: dict[str, dict[str, Any]] = {}

    imported_count = 0
    empty_count = 0

    for index, conversation in enumerate(conversations, start=1):
        mapping = conversation.get("mapping") or {}
        messages = linearize_mapping(mapping)
        user_assistant_messages = [
            msg for msg in messages
            if (msg.get("author") or {}).get("role") in ("user", "assistant")
            and extract_message_text(msg)
        ]
        if not user_assistant_messages:
            empty_count += 1
            continue

        imported_count += 1
        title = infer_title(conversation, index)
        conv_id = conversation.get("conversation_id") or f"chatgpt-{index:04d}"
        slug = slugify(f"{title}-{conv_id[:8]}", limit=96)
        family_id = f"family-{slug}"
        thread_uid = f"thread-{slug}"
        combined_text = "\n".join(extract_message_text(msg) for msg in user_assistant_messages)
        sentences = split_sentences(combined_text)
        keywords = top_keywords(combined_text)
        vectors = vector_terms(combined_text)
        action_items_text = extract_actions(sentences)
        unresolved_items_text = extract_unresolved(sentences)
        summary = shorten(" ".join(sentences[:3]) or combined_text or title, 320)
        update_time = conversation.get("update_time")
        update_time_iso = (
            datetime.fromtimestamp(update_time, tz=timezone.utc).isoformat()
            if isinstance(update_time, (int, float))
            else now_iso()
        )
        key_entities = build_entities(title, keywords)
        semantic_entities = [e["canonical_label"] for e in key_entities]
        pair_items = build_pairs(user_assistant_messages, thread_uid, family_id)
        for pair in pair_items:
            pair["entities"] = semantic_entities
        pairs.extend(pair_items)

        action_items = [
            {
                "action_key": f"action-{slugify(action, limit=64)}",
                "canonical_action": action,
                "status": "open",
                "family_ids": [family_id],
                "thread_uids": [thread_uid],
                "occurrence_count": 1,
            }
            for action in action_items_text
        ]
        unresolved_items = [
            {
                "question_key": f"question-{slugify(q, limit=64)}",
                "canonical_question": q,
                "why_unresolved": "Imported ChatGPT conversation still implies an open question.",
                "family_ids": [family_id],
                "thread_uids": [thread_uid],
                "occurrence_count": 1,
            }
            for q in unresolved_items_text
        ]

        tags = dedupe_preserve(["chatgpt-export", "json-export", "calibration-import"])
        threads.append({
            "thread_uid": thread_uid,
            "conversation_id": conv_id,
            "title_normalized": title,
            "title_raw": title,
            "answer_state": "imported_chatgpt_export",
            "tags": tags,
            "semantic_tags": ["chatgpt-thread"],
            "keywords": keywords,
            "semantic_themes": keywords[:6],
            "semantic_v2_themes": keywords[:8],
            "semantic_v3_themes": keywords[:8],
            "semantic_v3_entities": semantic_entities,
            "semantic_summary": summary,
            "semantic_v2_summary": summary,
            "semantic_v3_summary": f"{title} imported ChatGPT conversation centered on {', '.join(keywords[:4])}.",
            "action_count": len(action_items),
            "unresolved_question_count": len(unresolved_items),
            "audit_flags": [],
            "thread_path": str(output_root / "source" / "conversations.json"),
            "family_ids": [family_id],
            "update_time_iso": update_time_iso,
        })
        semantic_threads.append({
            "thread_uid": thread_uid,
            "title": title,
            "summary": summary,
            "search_text": f"{title} {combined_text}",
            "family_ids": [family_id],
            "vector_terms": vectors,
        })
        doctrine_briefs.append({
            "family_id": family_id,
            "canonical_title": title,
            "canonical_thread_uid": thread_uid,
            "member_count": 1,
            "stable_themes": keywords[:8],
            "brief_text": f"{title} currently centers on {', '.join(keywords[:4])}. Imported from ChatGPT export.",
            "search_text": f"{title} {' '.join(keywords[:10])} {combined_text}",
            "vector_terms": vectors,
        })
        family_dossiers.append({
            "family_id": family_id,
            "canonical_title": title,
            "canonical_thread_uid": thread_uid,
            "member_count": 1,
            "stable_themes": keywords[:8],
            "doctrine_summary": f"{title} imported ChatGPT conversation summary: {summary}",
            "search_text": f"{title} doctrine {' '.join(keywords[:10])} {combined_text}",
            "actions": [
                {"action_key": a["action_key"], "canonical_action": a["canonical_action"]}
                for a in action_items
            ],
            "unresolved": [
                {"question_key": u["question_key"], "canonical_question": u["canonical_question"]}
                for u in unresolved_items
            ],
            "key_entities": key_entities,
            "vector_terms": vectors,
        })
        canonical_families.append({
            "canonical_family_id": family_id,
            "canonical_title": title,
            "canonical_thread_uid": thread_uid,
            "thread_uids": [thread_uid],
        })
        actions.extend(action_items)
        unresolved.extend(unresolved_items)
        for entity in key_entities:
            key = entity["canonical_label"].lower()
            existing = entity_map.setdefault(key, {
                "canonical_entity_id": f"entity-{slugify(entity['canonical_label'], limit=64)}",
                "canonical_label": entity["canonical_label"],
                "entity_type": entity["entity_type"],
                "aliases": [],
            })
            existing["aliases"] = dedupe_preserve(existing.get("aliases", []) + [title])
        import_manifest.append({
            "conversation_id": conv_id,
            "thread_uid": thread_uid,
            "family_id": family_id,
            "pair_count": len(pair_items),
            "title": title,
        })

    entities = list(entity_map.values())
    corpus_dir = output_root / "corpus"
    source_snapshot = build_source_snapshot(input_path, "chatgpt-export", "bundle-json")
    write_json(corpus_dir / "threads-index.json", threads)
    write_json(corpus_dir / "semantic-v3-index.json", {"threads": semantic_threads})
    write_json(corpus_dir / "pairs-index.json", pairs)
    write_json(corpus_dir / "doctrine-briefs.json", doctrine_briefs)
    write_json(corpus_dir / "family-dossiers.json", family_dossiers)
    write_json(corpus_dir / "canonical-families.json", canonical_families)
    write_json(corpus_dir / "action-ledger.json", actions)
    write_json(corpus_dir / "unresolved-ledger.json", unresolved)
    write_json(corpus_dir / "canonical-entities.json", entities)
    write_json(corpus_dir / "entity-aliases.json", [
        {"canonical_label": e["canonical_label"], "labels": e.get("aliases", [])}
        for e in entities if e.get("aliases")
    ])
    write_json(corpus_dir / "doctrine-timeline.json", [])
    write_json(corpus_dir / "source-snapshot.json", source_snapshot)
    write_json(corpus_dir / "contract.json", {
        "contract_name": CONTRACT_NAME,
        "contract_version": CONTRACT_VERSION,
        "adapter_type": "chatgpt-export",
        "corpus_id": slugify(corpus_id or output_root.name),
        "name": name or output_root.name,
        "generated_at": now_iso(),
        "required_files": [
            "corpus/threads-index.json",
            "corpus/semantic-v3-index.json",
            "corpus/pairs-index.json",
            "corpus/doctrine-briefs.json",
            "corpus/family-dossiers.json",
        ],
        "counts": {
            "threads": len(threads),
            "families": len(canonical_families),
            "pairs": len(pairs),
            "actions": len(actions),
            "unresolved": len(unresolved),
            "entities": len(entities),
            "empty_conversations": empty_count,
        },
        "source_input": str(input_path),
        "collection_scope": "bundle-json",
        "source_snapshot_path": "corpus/source-snapshot.json",
        "source_signature_fingerprint": source_snapshot.get("signature_fingerprint"),
        "source_content_fingerprint": source_snapshot.get("content_fingerprint"),
        "source_file_count": source_snapshot.get("file_count"),
        "source_total_bytes": source_snapshot.get("total_bytes"),
        "source_latest_mtime_ns": source_snapshot.get("latest_mtime_ns"),
    })
    write_json(corpus_dir / "evaluation-summary.json", {
        "generated_at": now_iso(),
        "fixture_sources": {"manual": {"source": "unavailable", "count": 0}},
        "regression_gates": {"overall_state": "warn", "source_reliability_state": "warn"},
        "notes": ["Imported ChatGPT export corpus has not been manually evaluated."],
    })
    write_json(corpus_dir / "regression-gates.json", {
        "generated_at": now_iso(),
        "overall_state": "warn",
        "source_reliability_state": "warn",
        "source_notes": ["Imported ChatGPT export corpus has not been manually evaluated."],
        "gates": [],
    })
    write_json(output_root / "import-manifest.json", import_manifest)
    write_markdown(output_root / "README.md", "\n".join([
        "# ChatGPT History Memory Corpus",
        "",
        f"- Generated: {now_iso()}",
        f"- Source input: {input_path}",
        f"- Imported conversations: {imported_count}",
        f"- Empty conversations skipped: {empty_count}",
        f"- Pair count: {len(pairs)}",
        f"- Action count: {len(actions)}",
        f"- Unresolved count: {len(unresolved)}",
        f"- Copied source files: {len(copied_sources)}",
        f"- Contract manifest: {corpus_dir / 'contract.json'}",
        "",
        "This corpus is federation-compatible but unevaluated.",
    ]))

    resolved_corpus_id = corpus_id or output_root.name
    return {
        "corpus_id": slugify(resolved_corpus_id),
        "name": name or output_root.name,
        "output_root": str(output_root),
        "thread_count": len(threads),
        "pair_count": len(pairs),
        "action_count": len(actions),
        "unresolved_count": len(unresolved),
        "empty_conversation_count": empty_count,
        "manifest_path": str(output_root / "import-manifest.json"),
        "readme_path": str(output_root / "README.md"),
    }
```

- [ ] **Step 4: Run import tests to verify they pass**

Run: `python -m pytest tests/test_import_chatgpt_export_corpus.py -v`
Expected: 5 PASS (3 detection + 2 import)

- [ ] **Step 5: Commit**

```bash
git add src/conversation_corpus_engine/import_chatgpt_export_corpus.py tests/test_import_chatgpt_export_corpus.py
git commit -m "feat: add ChatGPT export import adapter"
```

### Task 8: Wire ChatGPT into Provider Catalog and CLI

**Files:**
- Modify: `src/conversation_corpus_engine/provider_catalog.py`
- Modify: `src/conversation_corpus_engine/provider_discovery.py`
- Modify: `src/conversation_corpus_engine/provider_import.py`
- Modify: `src/conversation_corpus_engine/cli.py`

- [ ] **Step 1: Write a failing integration test**

Add to `tests/test_import_chatgpt_export_corpus.py`:

```python
from conversation_corpus_engine.provider_catalog import PROVIDER_CONFIG
from conversation_corpus_engine.provider_discovery import discover_provider_uploads
from conversation_corpus_engine.provider_import import import_provider_corpus


class ChatGPTProviderIntegrationTests(unittest.TestCase):
    def test_chatgpt_in_provider_config(self) -> None:
        self.assertIn("chatgpt", PROVIDER_CONFIG)
        self.assertEqual(PROVIDER_CONFIG["chatgpt"]["adapter_type"], "chatgpt-export")

    def test_discover_chatgpt_upload_in_inbox(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            source_drop_root = Path(tmpdir) / "source-drop"
            inbox = source_drop_root / "chatgpt" / "inbox"
            inbox.mkdir(parents=True, exist_ok=True)
            shutil.copy2(
                FIXTURE_ROOT / "conversations.json",
                inbox / "conversations.json",
            )
            shutil.copy2(
                FIXTURE_ROOT / "user.json",
                inbox / "user.json",
            )
            payload = discover_provider_uploads(project_root, source_drop_root)
            chatgpt = next(
                item for item in payload["providers"] if item["provider"] == "chatgpt"
            )
            self.assertEqual(chatgpt["upload_state"], "ready")

    def test_import_provider_corpus_routes_chatgpt(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            source_path = FIXTURE_ROOT
            output_root = Path(tmpdir) / "chatgpt-history-memory"
            result = import_provider_corpus(
                project_root=project_root,
                provider="chatgpt",
                source_path=source_path,
                output_root=output_root,
                bootstrap_eval=False,
            )
            self.assertEqual(result["provider"], "chatgpt")
            self.assertGreaterEqual(result["import_result"]["thread_count"], 2)
```

- [ ] **Step 2: Run integration test to verify it fails**

Run: `python -m pytest tests/test_import_chatgpt_export_corpus.py::ChatGPTProviderIntegrationTests -v`
Expected: FAIL (chatgpt not in PROVIDER_CONFIG)

- [ ] **Step 3: Add chatgpt to provider_catalog.py**

Add to `PROVIDER_CONFIG` dict in `src/conversation_corpus_engine/provider_catalog.py`:

```python
    "chatgpt": {
        "display_name": "ChatGPT",
        "adapter_state": "supported",
        "adapter_type": "chatgpt-export",
        "discovery_mode": "chatgpt-bundle",
        "inbox_rel": "chatgpt/inbox",
        "default_corpus_id": "chatgpt-history-memory",
        "default_corpus_name": "ChatGPT History Memory",
        "calibration_only": True,
    },
```

- [ ] **Step 4: Wire detection in provider_discovery.py**

In `summarize_provider()`, add the chatgpt-bundle detection mode. After the existing line:

```python
    detector = looks_like_claude_bundle if config["discovery_mode"] == "claude-bundle" else path_has_supported_export_content
```

Replace with:

```python
    if config["discovery_mode"] == "claude-bundle":
        detector = looks_like_claude_bundle
    elif config["discovery_mode"] == "chatgpt-bundle":
        detector = looks_like_chatgpt_export
    else:
        detector = path_has_supported_export_content
```

And add the import at the top of the file:

```python
from .provider_exports import (
    looks_like_chatgpt_export,
    looks_like_claude_bundle,
    path_has_supported_export_content,
    visible_entries,
)
```

- [ ] **Step 5: Wire routing in provider_import.py**

In `resolve_provider_import_source()`, add ChatGPT routing. After the Claude inbox resolution block, before the generic fallback, add:

```python
    if provider == "chatgpt":
        return resolve_chatgpt_source_path(inbox_root), {"resolution": "provider-inbox", "inbox_root": str(inbox_root)}
```

Add to the module-level imports at the top of `provider_import.py`:

```python
from .import_chatgpt_export_corpus import import_chatgpt_export_corpus
from .provider_exports import resolve_chatgpt_source_path, resolve_claude_source_path, resolve_document_export_source_path
```

(Replace the existing `from .provider_exports import resolve_claude_source_path, resolve_document_export_source_path` line with the expanded version above.)

In `import_provider_corpus()`, add the ChatGPT import branch. After the `elif provider == "claude":` block but before the `else:` block, add:

```python
    elif provider == "chatgpt":
        resolved_corpus_id = resolved_corpus_id or config["default_corpus_id"]
        resolved_name = resolved_name or config["default_corpus_name"]
        import_result = import_chatgpt_export_corpus(
            resolved_source_path,
            resolved_output_root,
            corpus_id=resolved_corpus_id,
            name=resolved_name,
        )
```

- [ ] **Step 6: Add chatgpt to CLI choices**

In `src/conversation_corpus_engine/cli.py`, find all `choices=["claude", "gemini", "grok", "perplexity", "copilot"]` and change to `choices=["chatgpt", "claude", "gemini", "grok", "perplexity", "copilot"]`.

There are 6 occurrences across: provider import, provider bootstrap-eval, provider refresh, source-policy show, source-policy set, candidate stage (provider arg).

- [ ] **Step 7: Run integration tests to verify they pass**

Run: `python -m pytest tests/test_import_chatgpt_export_corpus.py -v`
Expected: 8 PASS (3 detection + 2 import + 3 integration)

- [ ] **Step 8: Run full test suite to verify nothing is broken**

Run: `python -m pytest tests/ -v --tb=short`
Expected: 49+ tests PASS (41 original + 8 new)

- [ ] **Step 9: Run lint**

Run: `pipx run ruff check src/ tests/ && pipx run ruff format --check src/ tests/`
Expected: 0 errors

- [ ] **Step 10: Commit**

```bash
git add src/conversation_corpus_engine/provider_catalog.py src/conversation_corpus_engine/provider_discovery.py src/conversation_corpus_engine/provider_import.py src/conversation_corpus_engine/cli.py
git commit -m "feat: wire ChatGPT as first-class provider in catalog, discovery, import, and CLI"
```

---

## Phase 5: Version Bump and Documentation

### Task 9: Version Bump and README Update

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/conversation_corpus_engine/__init__.py`
- Modify: `README.md`

- [ ] **Step 1: Bump version to 0.2.0**

In `pyproject.toml`: change `version = "0.1.0"` to `version = "0.2.0"`
In `src/conversation_corpus_engine/__init__.py`: change `__version__ = "0.1.0"` to `__version__ = "0.2.0"`

- [ ] **Step 2: Update README.md**

Add after the first paragraph:

```markdown
[![CI](https://github.com/organvm-i-theoria/conversation-corpus-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/organvm-i-theoria/conversation-corpus-engine/actions/workflows/ci.yml)
```

Add ChatGPT to the CLI examples section:

```markdown
cce provider import --provider chatgpt --source-drop-root /path/to/source-drop --register --build
cce provider refresh --provider chatgpt --project-root /path/to/project --source-drop-root /path/to/source-drop
```

Add to the Layout section:

```markdown
- `src/conversation_corpus_engine/import_chatgpt_export_corpus.py` — ChatGPT conversations.json export import
```

- [ ] **Step 3: Run full test suite one final time**

Run: `python -m pytest tests/ -v --tb=short && pipx run ruff check src/ tests/`
Expected: All pass, 0 lint errors

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml src/conversation_corpus_engine/__init__.py README.md
git commit -m "chore: bump version to 0.2.0 with CI, ChatGPT adapter, and governance"
```

---

## Verification Checklist

After all tasks are complete, verify:

- [ ] `python -m pytest tests/ -v` — all tests pass
- [ ] `pipx run ruff check src/ tests/` — 0 lint errors
- [ ] `pipx run ruff format --check src/ tests/` — 0 format diffs
- [ ] `python -c "from conversation_corpus_engine import __version__; assert __version__ == '0.2.0'"` — version correct
- [ ] `python -c "from conversation_corpus_engine.provider_catalog import PROVIDER_CONFIG; assert 'chatgpt' in PROVIDER_CONFIG"` — ChatGPT wired
- [ ] `python -c "import yaml; assert yaml.safe_load(open('seed.yaml'))['organ'] == 'ORGAN-I'"` or `python -c "assert 'ORGAN-I' in open('seed.yaml').read()"` — seed.yaml valid
- [ ] `.github/workflows/ci.yml` exists and is valid YAML
- [ ] `CLAUDE.md` exists with architecture docs
- [ ] `tests/conftest.py` has shared fixtures
- [ ] `tests/fixtures/chatgpt-export/conversations.json` has 3 sanitized conversations
