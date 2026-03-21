from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversation_corpus_engine.corpus_candidates import stage_corpus_candidate
from conversation_corpus_engine.federation import build_federation, upsert_corpus
from conversation_corpus_engine.governance_candidates import stage_policy_candidate
from conversation_corpus_engine.governance_replay import (
    build_policy_replay_payload,
    write_policy_replay_artifacts,
)
from conversation_corpus_engine.import_markdown_document_corpus import (
    import_markdown_document_corpus,
)
from conversation_corpus_engine.schema_validation import validate_json_file
from conversation_corpus_engine.source_policy import set_source_policy
from conversation_corpus_engine.surface_exports import (
    build_mcp_context_payload,
    build_surface_manifest,
    export_surface_bundle,
    mcp_context_json_path,
    surface_bundle_json_path,
    surface_manifest_json_path,
)


def write_markdown_sources(root: Path, files: dict[str, str]) -> None:
    for relative_path, content in files.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def seed_surface_project(project_root: Path, source_drop_root: Path) -> None:
    workspace_root = project_root.parent
    live_source = workspace_root / "perplexity-live-source"
    candidate_source = workspace_root / "perplexity-candidate-source"
    live_root = workspace_root / "perplexity-history-memory"
    candidate_root = workspace_root / "perplexity-history-memory-candidate"

    write_markdown_sources(
        live_source,
        {
            "baseline.md": "# Perplexity Baseline\n\nNeed to preserve the live corpus contract.\n\nMaybe keep source authority on the reviewed baseline until promotion.\n",
        },
    )
    write_markdown_sources(
        candidate_source,
        {
            "candidate.md": "# Perplexity Candidate\n\nNeed to expose Meta-facing surfaces from the governed corpus engine.\n\nMaybe promote the refreshed candidate after review.\n",
        },
    )
    write_markdown_sources(
        source_drop_root / "perplexity" / "inbox",
        {
            "export.md": "# Refreshed Export\n\nNeed to import a fresh Perplexity export.\n\nMaybe stage it through provider refresh.\n",
        },
    )

    import_markdown_document_corpus(
        live_source,
        live_root,
        corpus_id="perplexity-history-memory",
        name="Perplexity History Memory",
    )
    import_markdown_document_corpus(
        candidate_source,
        candidate_root,
        corpus_id="perplexity-history-memory",
        name="Perplexity History Memory",
    )
    upsert_corpus(
        project_root,
        live_root,
        corpus_id="perplexity-history-memory",
        name="Perplexity History Memory",
        make_default=True,
    )
    set_source_policy(
        project_root,
        "perplexity",
        primary_root=live_root,
        primary_corpus_id="perplexity-history-memory",
        decision="manual",
        note="Use the live Perplexity corpus.",
    )
    build_federation(project_root)
    write_policy_replay_artifacts(project_root, build_policy_replay_payload(project_root))
    stage_policy_candidate(
        project_root,
        threshold_overrides={"max_warn_corpora": 1.0},
        note="Stage a policy candidate for surface export coverage.",
    )
    stage_corpus_candidate(
        project_root,
        candidate_root=candidate_root,
        provider="perplexity",
        note="Stage a candidate corpus for surface export coverage.",
    )


class SurfaceExportsTests(unittest.TestCase):
    def test_exported_surface_artifacts_validate_against_published_schemas(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            project_root = workspace_root / "project"
            source_drop_root = workspace_root / "source-drop"
            seed_surface_project(project_root, source_drop_root)

            manifest = build_surface_manifest(
                project_root,
                source_drop_root=source_drop_root,
            )
            context = build_mcp_context_payload(
                project_root,
                source_drop_root=source_drop_root,
            )
            bundle = export_surface_bundle(
                project_root,
                source_drop_root=source_drop_root,
            )

            manifest_result = validate_json_file(
                "surface-manifest",
                surface_manifest_json_path(project_root),
            )
            context_result = validate_json_file(
                "mcp-context",
                mcp_context_json_path(project_root),
            )
            bundle_result = validate_json_file(
                "surface-bundle",
                surface_bundle_json_path(project_root),
            )

            self.assertEqual(manifest["registry"]["default_corpus_id"], "perplexity-history-memory")
            self.assertEqual(context["summary"]["active_corpus_count"], 1)
            self.assertEqual(context["summary"]["provider_count"], 6)
            self.assertTrue(bundle["summary"]["valid"])
            self.assertTrue(manifest_result["valid"], manifest_result["errors"])
            self.assertTrue(context_result["valid"], context_result["errors"])
            self.assertTrue(bundle_result["valid"], bundle_result["errors"])


if __name__ == "__main__":
    unittest.main()
