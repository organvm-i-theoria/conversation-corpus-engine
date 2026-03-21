from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversation_corpus_engine.provider_catalog import provider_corpus_targets
from conversation_corpus_engine.source_policy import (
    load_source_policy,
    set_source_policy,
    source_policy_history_path,
)


class SourcePolicyTests(unittest.TestCase):
    def test_set_source_policy_updates_provider_targets_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            project_root = workspace_root / "project"
            source_drop_root = workspace_root / "source-drop"
            primary_root = workspace_root / "gemini-history-memory"
            fallback_root = workspace_root / "gemini-archive-memory"
            primary_root.mkdir(parents=True, exist_ok=True)
            fallback_root.mkdir(parents=True, exist_ok=True)

            payload = set_source_policy(
                project_root,
                "gemini",
                primary_root=primary_root,
                primary_corpus_id="gemini-history-memory",
                fallback_root=fallback_root,
                fallback_corpus_id="gemini-archive-memory",
                decision="manual-override",
                note="Prefer the curated history corpus for federation.",
            )
            policy = load_source_policy(project_root, "gemini")
            history = json.loads(
                source_policy_history_path(project_root).read_text(encoding="utf-8")
            )
            targets = provider_corpus_targets(project_root, "gemini", source_drop_root)

            self.assertEqual(payload["decision"], "manual-override")
            self.assertEqual(policy["primary_corpus_id"], "gemini-history-memory")
            self.assertEqual(policy["fallback_corpus_id"], "gemini-archive-memory")
            self.assertEqual(history["count"], 1)
            self.assertEqual(history["latest"]["provider"], "gemini")
            self.assertEqual(len(targets), 2)
            self.assertEqual(targets[0]["role"], "primary")
            self.assertEqual(targets[0]["root"], str(primary_root.resolve()))
            self.assertEqual(targets[1]["role"], "fallback")
            self.assertEqual(targets[1]["root"], str(fallback_root.resolve()))


if __name__ == "__main__":
    unittest.main()
