from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversation_corpus_engine.provider_exports import looks_like_chatgpt_export

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


if __name__ == "__main__":
    unittest.main()
