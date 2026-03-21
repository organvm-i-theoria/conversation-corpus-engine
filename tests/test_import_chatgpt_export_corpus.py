from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversation_corpus_engine.import_chatgpt_export_corpus import (  # noqa: E402
    import_chatgpt_export_corpus,
)
from conversation_corpus_engine.provider_exports import looks_like_chatgpt_export  # noqa: E402

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "chatgpt-export"


class ChatGPTDetectionTests(unittest.TestCase):
    def test_looks_like_chatgpt_export_identifies_fixture(self) -> None:
        self.assertTrue(looks_like_chatgpt_export(FIXTURE_ROOT))

    def test_looks_like_chatgpt_export_rejects_empty_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertFalse(looks_like_chatgpt_export(Path(tmpdir)))

    def test_looks_like_chatgpt_export_rejects_claude_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "conversations.json").write_text("[]", encoding="utf-8")
            (root / "users.json").write_text("[]", encoding="utf-8")
            # Claude bundles have users.json (plural), ChatGPT has user.json (singular)
            self.assertFalse(looks_like_chatgpt_export(root))


class ImportChatGPTExportCorpusTests(unittest.TestCase):
    def test_import_chatgpt_export_builds_federation_surface(self) -> None:
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
                (output_root / "corpus" / "contract.json").read_text(
                    encoding="utf-8"
                ),
            )
            self.assertEqual(contract["adapter_type"], "chatgpt-export")
            self.assertEqual(
                contract["contract_name"], "conversation-corpus-engine-v1"
            )

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
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir) / "chatgpt-memory"
            import_chatgpt_export_corpus(
                FIXTURE_ROOT,
                output_root,
                corpus_id="chatgpt-memory",
                name="ChatGPT Memory",
            )
            threads = json.loads(
                (output_root / "corpus" / "threads-index.json").read_text(
                    encoding="utf-8"
                ),
            )
            # At least one thread should exist even from the null-title conversation
            titles = [t["title_normalized"] for t in threads]
            # The null-title conversation should have an inferred title
            self.assertTrue(
                all(isinstance(t, str) and len(t) > 0 for t in titles)
            )


if __name__ == "__main__":
    unittest.main()
