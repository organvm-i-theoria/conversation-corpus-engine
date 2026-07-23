from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversation_corpus_engine.corpus_store import CorpusStoreError, register_corpus_store
from conversation_corpus_engine.federation import list_registered_corpora
from conversation_corpus_engine.provider_import import import_provider_corpus
from conversation_corpus_engine.provider_readiness import build_provider_readiness


class ProviderImportTests(unittest.TestCase):
    def test_import_provider_corpus_registers_and_builds_federation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            project_root = workspace_root / "project"
            project_root.mkdir()
            corpus_store_root = workspace_root / "corpus-store"
            corpus_store_root.mkdir()
            register_corpus_store(project_root, corpus_store_root)
            source_drop_root = workspace_root / "source-drop"
            inbox = source_drop_root / "perplexity" / "inbox"
            inbox.mkdir(parents=True, exist_ok=True)
            (inbox / "export.md").write_text(
                "# Routing Notes\n\nWe should build the provider import command next.\n",
                encoding="utf-8",
            )

            result = import_provider_corpus(
                project_root=project_root,
                provider="perplexity",
                source_drop_root=source_drop_root,
                corpus_store_root=corpus_store_root,
                register=True,
                build=True,
            )

            registry = list_registered_corpora(project_root)
            readiness = build_provider_readiness(project_root, source_drop_root)
            perplexity = next(
                item for item in readiness["providers"] if item["provider"] == "perplexity"
            )
            contract = json.loads(
                (Path(result["output_root"]) / "corpus" / "contract.json").read_text(
                    encoding="utf-8"
                ),
            )

            self.assertEqual(result["corpus_id"], "perplexity-history-memory")
            self.assertEqual(
                Path(result["output_root"]).resolve(),
                (corpus_store_root / "perplexity-history-memory").resolve(),
            )
            self.assertEqual(contract["adapter_type"], "perplexity-export")
            self.assertEqual(len(registry), 1)
            self.assertEqual(registry[0]["corpus_id"], "perplexity-history-memory")
            self.assertTrue((project_root / "federation" / "federation-summary.md").exists())
            self.assertTrue(Path(result["bootstrap_result"]["manual_guide_path"]).exists())
            self.assertTrue(Path(result["bootstrap_result"]["seeded_paths"]["answers"]).exists())
            self.assertEqual(perplexity["overall_state"], "manual-eval-pending")
            self.assertIn("cce evaluation run --root", perplexity["next_command"])

    def test_import_denial_creates_no_destination_or_control_plane_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            project_root = workspace_root / "project"
            project_root.mkdir()
            corpus_store_root = workspace_root / "corpus-store"
            corpus_store_root.mkdir()
            register_corpus_store(project_root, corpus_store_root)
            source_drop_root = workspace_root / "source-drop"
            inbox = source_drop_root / "perplexity" / "inbox"
            inbox.mkdir(parents=True)
            (inbox / "export.md").write_text("# Export\n\nPrivate custody required.\n")
            outside_destination = workspace_root / "visible-output"
            registry_path = project_root / "state" / "federation-registry.json"
            registry_before = registry_path.read_bytes()

            with self.assertRaises(CorpusStoreError):
                import_provider_corpus(
                    project_root=project_root,
                    provider="perplexity",
                    source_drop_root=source_drop_root,
                    corpus_store_root=corpus_store_root,
                    output_root=outside_destination,
                )

            self.assertFalse(outside_destination.exists())
            self.assertEqual(registry_path.read_bytes(), registry_before)
            self.assertFalse((project_root / "reports").exists())


if __name__ == "__main__":
    unittest.main()
