from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversation_corpus_engine import import_claude_local_session_corpus as module  # noqa: E402


def seed_corpus_scaffold(root: Path) -> None:
    corpus_dir = root / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    (corpus_dir / "contract.json").write_text(
        json.dumps(
            {
                "contract_name": "conversation-corpus-engine-v1",
                "contract_version": 1,
                "adapter_type": "claude-export",
                "corpus_id": "claude-local-session-memory",
                "name": "Claude Local Session Memory",
            }
        ),
        encoding="utf-8",
    )
    (corpus_dir / "evaluation-summary.json").write_text(
        json.dumps({"notes": ["placeholder"]}),
        encoding="utf-8",
    )
    (corpus_dir / "regression-gates.json").write_text(
        json.dumps({"source_notes": ["placeholder"]}),
        encoding="utf-8",
    )


def test_write_local_session_bundle_writes_expected_files(tmp_path: Path) -> None:
    bundle_root = tmp_path / "bundle"
    module.write_local_session_bundle(
        bundle_root,
        {
            "bootstrap": {"ok": True},
            "organizations": [{"uuid": "org-1"}],
            "projects": [{"uuid": "project-1"}],
            "memories": [],
            "users": [{"uuid": "user-1"}],
            "conversation_summaries": [{"uuid": "conv-1"}],
            "conversation_detail_failures": [{"uuid": "conv-2", "error": "boom"}],
            "conversations": [{"uuid": "conv-1", "chat_messages": []}, {"title": "skip"}],
        },
    )

    assert json.loads((bundle_root / "bootstrap.json").read_text(encoding="utf-8")) == {"ok": True}
    assert json.loads((bundle_root / "organizations.json").read_text(encoding="utf-8")) == [
        {"uuid": "org-1"}
    ]
    assert json.loads(
        (bundle_root / "conversation-detail-failures.json").read_text(encoding="utf-8")
    ) == [{"uuid": "conv-2", "error": "boom"}]
    assert json.loads(
        (bundle_root / "conversation-details" / "conv-1.json").read_text(encoding="utf-8")
    ) == {"uuid": "conv-1", "chat_messages": []}
    assert not (bundle_root / "conversation-details" / "None.json").exists()


def test_patch_contract_for_local_session_updates_contract_and_notes(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    local_root = tmp_path / "claude-local"
    local_root.mkdir()
    (local_root / "Cookies").write_text("cookies", encoding="utf-8")
    (local_root / "config.json").write_text("{}", encoding="utf-8")
    seed_corpus_scaffold(output_root)

    module.patch_contract_for_local_session(
        output_root,
        local_root=local_root,
        discovery={
            "generated_at": "2026-03-25T00:00:00+00:00",
            "safe_storage_service": "Claude Safe Storage",
            "active_org_uuid": "org-1",
            "account_uuid": "acct-1",
            "account_email": "user@example.com",
            "conversation_count": 2,
            "project_count": 1,
        },
    )

    contract = json.loads((output_root / "corpus" / "contract.json").read_text(encoding="utf-8"))
    snapshot = json.loads(
        (output_root / "corpus" / "source-snapshot.json").read_text(encoding="utf-8")
    )
    evaluation_summary = json.loads(
        (output_root / "corpus" / "evaluation-summary.json").read_text(encoding="utf-8")
    )
    regression_gates = json.loads(
        (output_root / "corpus" / "regression-gates.json").read_text(encoding="utf-8")
    )

    assert contract["adapter_type"] == "claude-local-session"
    assert contract["collection_scope"] == "local-session"
    assert contract["local_session"]["active_org_uuid"] == "org-1"
    assert snapshot["adapter_type"] == "claude-local-session"
    assert snapshot["file_count"] == 2
    assert evaluation_summary["notes"] == [
        "Imported Claude local-session corpus has not been manually evaluated."
    ]
    assert regression_gates["source_notes"] == [
        "Imported Claude local-session corpus has not been manually evaluated."
    ]


def test_rewrite_readme_for_local_session_includes_bundle_summary(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()

    module.rewrite_readme_for_local_session(
        output_root,
        local_root=tmp_path / "claude-local",
        bundle={
            "active_org_uuid": "org-1",
            "conversations": [{"uuid": "conv-1"}, {"uuid": "conv-2"}],
            "conversation_detail_failures": [{"uuid": "conv-3", "error": "boom"}],
            "projects": [{"uuid": "project-1"}],
            "users": [{"uuid": "user-1"}],
        },
    )

    readme = (output_root / "README.md").read_text(encoding="utf-8")
    assert "- Adapter type: claude-local-session" in readme
    assert "- Imported conversations: 2" in readme
    assert "- Detail fetch failures: 1" in readme


def test_import_claude_local_session_corpus_writes_metadata_and_returns_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local_root = tmp_path / "claude-local"
    output_root = tmp_path / "output"
    local_root.mkdir()
    (local_root / "Cookies").write_text("cookies", encoding="utf-8")
    (local_root / "config.json").write_text("{}", encoding="utf-8")

    discovery = {
        "generated_at": "2026-03-25T00:00:00+00:00",
        "safe_storage_service": "Claude Safe Storage",
        "active_org_uuid": "org-1",
        "account_uuid": "acct-1",
        "account_email": "user@example.com",
        "conversation_count": 1,
        "project_count": 1,
    }
    bundle = {
        "generated_at": "2026-03-25T00:01:00+00:00",
        "active_org_uuid": "org-1",
        "safe_storage_service": "Claude Safe Storage",
        "cookie_names": ["sessionKey", "lastActiveOrg"],
        "bootstrap": {"account": {"uuid": "acct-1"}},
        "organizations": [{"uuid": "org-1"}],
        "projects": [{"uuid": "project-1"}],
        "memories": [],
        "users": [{"uuid": "acct-1"}],
        "conversation_summaries": [{"uuid": "conv-1"}],
        "conversation_detail_failures": [{"uuid": "conv-2", "error": "boom"}],
        "conversations": [
            {
                "uuid": "conv-1",
                "name": "Claude Local Session Thread",
                "created_at": "2026-03-25T00:00:00Z",
                "updated_at": "2026-03-25T00:05:00Z",
                "chat_messages": [
                    {
                        "uuid": "msg-1",
                        "sender": "human",
                        "created_at": "2026-03-25T00:00:00Z",
                        "updated_at": "2026-03-25T00:00:00Z",
                        "text": "Summarize the local session import.",
                        "content": [{"type": "text", "text": "Summarize the local session import."}],
                        "attachments": [],
                        "files": [],
                    },
                    {
                        "uuid": "msg-2",
                        "sender": "assistant",
                        "created_at": "2026-03-25T00:01:00Z",
                        "updated_at": "2026-03-25T00:01:00Z",
                        "text": "The local session import is calibrated and ready.",
                        "content": [
                            {
                                "type": "text",
                                "text": "The local session import is calibrated and ready.",
                            }
                        ],
                        "attachments": [],
                        "files": [],
                    },
                ],
            }
        ],
    }
    monkeypatch.setattr(module, "discover_claude_local_session", lambda root: discovery)
    monkeypatch.setattr(module, "fetch_claude_local_session_bundle", lambda root: bundle)

    result = module.import_claude_local_session_corpus(local_root, output_root)

    contract = json.loads((output_root / "corpus" / "contract.json").read_text(encoding="utf-8"))
    discovery_file = json.loads(
        (output_root / "source" / "local-session-discovery.json").read_text(encoding="utf-8")
    )
    metadata_file = json.loads(
        (output_root / "source" / "local-session-metadata.json").read_text(encoding="utf-8")
    )
    readme = (output_root / "README.md").read_text(encoding="utf-8")

    assert result["source_type"] == "claude-local-session"
    assert result["local_root"] == str(local_root.resolve())
    assert result["detail_failure_count"] == 1
    assert contract["adapter_type"] == "claude-local-session"
    assert discovery_file["active_org_uuid"] == "org-1"
    assert metadata_file["cookie_names"] == ["sessionKey", "lastActiveOrg"]
    assert metadata_file["detail_failure_count"] == 1
    assert "Claude Local Session Memory Corpus" in readme
