from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from conversation_corpus_engine.dashboard import (
    corpus_gate_summary,
    federation_summary,
    render_dashboard_text,
    review_queue_summary,
)
from conversation_corpus_engine.federation import upsert_corpus


def seed_minimal_corpus(root: Path, *, gate_state: str = "pass") -> Path:
    corpus_dir = root / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    for filename, payload in {
        "threads-index.json": [],
        "semantic-v3-index.json": {"threads": []},
        "pairs-index.json": [],
        "doctrine-briefs.json": [],
        "family-dossiers.json": [],
    }.items():
        (corpus_dir / filename).write_text(json.dumps(payload), encoding="utf-8")
    (corpus_dir / "regression-gates.json").write_text(
        json.dumps(
            {
                "overall_state": gate_state,
                "source_reliability_state": "pass",
                "gates": [],
            }
        ),
        encoding="utf-8",
    )
    return root


class DashboardTests(unittest.TestCase):
    def test_corpus_gate_summary_reads_gate_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()
            corpus_root = Path(tmpdir) / "test-corpus"
            seed_minimal_corpus(corpus_root, gate_state="pass")
            upsert_corpus(project_root, corpus_root, corpus_id="test", name="Test")

            summary = corpus_gate_summary(project_root)
            self.assertEqual(len(summary), 1)
            self.assertEqual(summary[0]["corpus_id"], "test")
            self.assertEqual(summary[0]["overall_state"], "pass")

    def test_federation_summary_handles_list_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            fed_dir = project_root / "federation"
            fed_dir.mkdir(parents=True)
            (fed_dir / "registry.json").write_text(
                json.dumps({"corpora": [{"corpus_id": "a"}, {"corpus_id": "b"}]})
            )
            (fed_dir / "corpora-summary.json").write_text(
                json.dumps(
                    [
                        {
                            "corpus_id": "a",
                            "family_count": 10,
                            "entity_count": 5,
                            "action_count": 3,
                        },
                        {
                            "corpus_id": "b",
                            "family_count": 20,
                            "entity_count": 15,
                            "action_count": 7,
                        },
                    ]
                )
            )
            (fed_dir / "conflict-report.json").write_text(json.dumps({"conflicts": []}))

            result = federation_summary(project_root)
            self.assertEqual(result["corpus_count"], 2)
            self.assertEqual(result["family_count"], 30)
            self.assertEqual(result["entity_count"], 20)
            self.assertEqual(result["action_count"], 10)

    def test_review_queue_summary_counts_open_and_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_dir = project_root / "state"
            state_dir.mkdir()
            (state_dir / "federated-review-queue.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {"status": "open"},
                            {"status": "open"},
                            {"status": "accepted"},
                        ]
                    }
                )
            )
            result = review_queue_summary(project_root)
            self.assertEqual(result["open"], 2)
            self.assertEqual(result["resolved"], 1)

    def test_render_dashboard_text_produces_output(self) -> None:
        payload = {
            "generated_at": "2026-03-24T00:00:00Z",
            "provider_count": 8,
            "corpora": [
                {
                    "corpus_id": "test",
                    "name": "Test",
                    "default": True,
                    "overall_state": "pass",
                    "source_reliability": "pass",
                    "gate_count": 8,
                    "pass_count": 8,
                    "warn_count": 0,
                    "fail_count": 0,
                }
            ],
            "federation": {
                "corpus_count": 1,
                "family_count": 10,
                "entity_count": 5,
                "action_count": 3,
            },
            "review_queue": {"total": 100, "open": 40, "resolved": 60},
            "readiness": {"providers": []},
        }
        text = render_dashboard_text(payload)
        self.assertIn("CCE Dashboard", text)
        self.assertIn("[+] test", text)
        self.assertIn("8P/0W/0F", text)
        self.assertIn("Open: 40", text)

    def test_render_dashboard_handles_empty_corpora(self) -> None:
        payload = {
            "generated_at": "2026-03-24T00:00:00Z",
            "provider_count": 0,
            "corpora": [],
            "federation": {
                "corpus_count": 0,
                "family_count": 0,
                "entity_count": 0,
                "action_count": 0,
            },
            "review_queue": {"total": 0, "open": 0, "resolved": 0},
            "readiness": {"providers": []},
        }
        text = render_dashboard_text(payload)
        self.assertIn("(none registered)", text)


if __name__ == "__main__":
    unittest.main()
