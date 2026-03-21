from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversation_corpus_engine.import_claude_export_corpus import import_claude_export_corpus


class ImportClaudeExportCorpusTests(unittest.TestCase):
    def test_import_claude_export_corpus_builds_federation_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle = Path(tmpdir) / "claude-bundle"
            output_root = Path(tmpdir) / "claude-history-memory"
            bundle.mkdir(parents=True, exist_ok=True)
            (bundle / "users.json").write_text(
                json.dumps([{"uuid": "user-1", "full_name": "Test User"}]),
                encoding="utf-8",
            )
            (bundle / "projects.json").write_text("[]", encoding="utf-8")
            (bundle / "memories.json").write_text("[]", encoding="utf-8")
            (bundle / "conversations.json").write_text(
                json.dumps(
                    [
                        {
                            "uuid": "conv-1",
                            "name": "Claude Test Thread",
                            "summary": "",
                            "created_at": "2026-03-14T10:00:00Z",
                            "updated_at": "2026-03-14T10:05:00Z",
                            "chat_messages": [
                                {
                                    "uuid": "msg-1",
                                    "sender": "human",
                                    "created_at": "2026-03-14T10:00:00Z",
                                    "updated_at": "2026-03-14T10:00:00Z",
                                    "text": "Build the adapter for Claude exports.",
                                    "content": [{"type": "text", "text": "Build the adapter for Claude exports."}],
                                    "attachments": [],
                                    "files": [],
                                },
                                {
                                    "uuid": "msg-2",
                                    "sender": "assistant",
                                    "created_at": "2026-03-14T10:01:00Z",
                                    "updated_at": "2026-03-14T10:01:00Z",
                                    "text": "I will implement a Claude export adapter and keep it in calibration.",
                                    "content": [
                                        {"type": "text", "text": "I will implement a Claude export adapter and keep it in calibration."},
                                        {"type": "tool_use", "name": "artifacts", "input": {"title": "Claude Adapter Plan"}},
                                    ],
                                    "attachments": [],
                                    "files": [],
                                },
                            ],
                        },
                    ],
                ),
                encoding="utf-8",
            )

            result = import_claude_export_corpus(
                bundle,
                output_root,
                corpus_id="claude-history-memory",
                name="Claude History Memory",
            )

            self.assertEqual(result["corpus_id"], "claude-history-memory")
            self.assertEqual(result["thread_count"], 1)
            self.assertGreaterEqual(result["pair_count"], 1)
            contract = json.loads((output_root / "corpus" / "contract.json").read_text(encoding="utf-8"))
            self.assertEqual(contract["adapter_type"], "claude-export")
            self.assertEqual(contract["counts"]["threads"], 1)
            self.assertTrue((output_root / "corpus" / "source-snapshot.json").exists())
            threads = json.loads((output_root / "corpus" / "threads-index.json").read_text(encoding="utf-8"))
            self.assertEqual(threads[0]["title_normalized"], "Claude Test Thread")
            self.assertIn("claude-export", threads[0]["tags"])
            readme = (output_root / "README.md").read_text(encoding="utf-8")
            self.assertIn("Imported conversations: 1", readme)


if __name__ == "__main__":
    unittest.main()
