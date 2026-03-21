from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversation_corpus_engine.federation import list_registered_corpora
from conversation_corpus_engine.migration import seed_registry_from_staging


def seed_valid_corpus(root: Path, *, contract_name: str = "conversation-corpus-engine-v1") -> None:
    corpus_dir = root / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    for rel in (
        "threads-index.json",
        "semantic-v3-index.json",
        "pairs-index.json",
        "doctrine-briefs.json",
        "family-dossiers.json",
    ):
        (corpus_dir / rel).write_text(
            "[]" if rel != "semantic-v3-index.json" else '{"threads":[]}', encoding="utf-8"
        )
    (corpus_dir / "canonical-families.json").write_text("[]", encoding="utf-8")
    (corpus_dir / "action-ledger.json").write_text("[]", encoding="utf-8")
    (corpus_dir / "unresolved-ledger.json").write_text("[]", encoding="utf-8")
    (corpus_dir / "canonical-entities.json").write_text("[]", encoding="utf-8")
    (corpus_dir / "evaluation-summary.json").write_text("{}", encoding="utf-8")
    (corpus_dir / "regression-gates.json").write_text("{}", encoding="utf-8")
    (corpus_dir / "contract.json").write_text(
        json.dumps(
            {
                "contract_name": contract_name,
                "contract_version": 1,
                "adapter_type": "markdown-document",
            }
        ),
        encoding="utf-8",
    )


class MigrationTests(unittest.TestCase):
    def test_seed_registry_from_staging_registers_valid_corpora(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            staging_root = Path(tmpdir) / "staging"
            seed_valid_corpus(staging_root / "chatgpt-history")
            seed_valid_corpus(staging_root / "notes-memory")
            (staging_root / "ignored-dir").mkdir(parents=True, exist_ok=True)

            result = seed_registry_from_staging(project_root, staging_root)
            corpora = list_registered_corpora(project_root)

            self.assertEqual(result["registered_count"], 2)
            self.assertEqual(len(corpora), 2)
            self.assertEqual(corpora[0]["corpus_id"], "chatgpt-history")
            self.assertTrue(any(entry["default"] for entry in corpora))


if __name__ == "__main__":
    unittest.main()
