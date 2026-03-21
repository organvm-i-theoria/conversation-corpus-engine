from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversation_corpus_engine import evaluation as MODULE


class EvaluationTests(unittest.TestCase):
    def build_root(self) -> Path:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        root = Path(tmpdir.name)
        (root / "corpus").mkdir(parents=True, exist_ok=True)
        (root / "state").mkdir(parents=True, exist_ok=True)
        return root

    def seed_corpus(self, root: Path) -> None:
        (root / "state" / "canonical-decisions.json").write_text(
            json.dumps(
                {
                    "accepted_duplicates": [
                        {"review_id": "r1", "thread_uids": ["thread-a", "thread-b"]}
                    ],
                    "rejected_contradictions": [
                        {"review_id": "r2", "thread_uids": ["thread-a", "thread-c"]}
                    ],
                },
            ),
            encoding="utf-8",
        )
        (root / "corpus" / "canonical-families.json").write_text(
            json.dumps(
                [
                    {
                        "canonical_family_id": "family-001-alpha",
                        "canonical_title": "Alpha Pipeline",
                        "canonical_thread_uid": "thread-a",
                        "thread_uids": ["thread-a", "thread-b"],
                    },
                ],
            ),
            encoding="utf-8",
        )
        (root / "corpus" / "doctrine-briefs.json").write_text(
            json.dumps(
                [
                    {
                        "family_id": "family-001-alpha",
                        "canonical_title": "Alpha Pipeline",
                        "canonical_thread_uid": "thread-a",
                        "stable_themes": ["alpha", "pipeline"],
                        "brief_text": "Alpha Pipeline governs alpha registry.",
                        "search_text": "Alpha Pipeline alpha registry",
                    },
                ],
            ),
            encoding="utf-8",
        )
        (root / "corpus" / "family-dossiers.json").write_text(
            json.dumps(
                [
                    {
                        "family_id": "family-001-alpha",
                        "canonical_title": "Alpha Pipeline",
                        "canonical_thread_uid": "thread-a",
                        "member_count": 2,
                        "stable_themes": ["alpha", "pipeline"],
                        "doctrine_summary": "Alpha Pipeline governs alpha registry.",
                        "search_text": "Alpha Pipeline alpha registry",
                        "actions": [
                            {
                                "action_key": "action-alpha",
                                "canonical_action": "Implement alpha registry",
                            }
                        ],
                        "unresolved": [
                            {
                                "question_key": "question-alpha",
                                "canonical_question": "How should alpha evolve?",
                            }
                        ],
                        "key_entities": [
                            {"canonical_label": "Alpha System", "entity_type": "concept"}
                        ],
                    },
                ],
            ),
            encoding="utf-8",
        )
        (root / "corpus" / "threads-index.json").write_text(
            json.dumps(
                [
                    {
                        "thread_uid": "thread-a",
                        "title_normalized": "Alpha Pipeline",
                        "semantic_v3_summary": "Canonical alpha thread summary.",
                        "semantic_v3_themes": ["alpha", "pipeline"],
                        "semantic_v3_entities": ["Alpha System"],
                        "family_ids": ["family-001-alpha"],
                    },
                    {
                        "thread_uid": "thread-b",
                        "title_normalized": "Alpha Pipeline",
                        "semantic_v3_summary": "Older alpha thread summary.",
                        "semantic_v3_themes": ["alpha"],
                        "semantic_v3_entities": ["Alpha System"],
                        "family_ids": ["family-001-alpha"],
                    },
                ],
            ),
            encoding="utf-8",
        )
        (root / "corpus" / "semantic-v3-index.json").write_text(
            json.dumps(
                {
                    "threads": [
                        {
                            "thread_uid": "thread-a",
                            "title": "Alpha Pipeline",
                            "search_text": "Alpha Pipeline alpha registry governance canonical thread",
                            "vector_terms": {"alpha": 1.0, "pipeline": 0.8, "registry": 0.7},
                            "family_ids": ["family-001-alpha"],
                        },
                        {
                            "thread_uid": "thread-b",
                            "title": "Alpha Pipeline",
                            "search_text": "Older alpha thread",
                            "vector_terms": {"alpha": 0.5},
                            "family_ids": ["family-001-alpha"],
                        },
                    ],
                },
            ),
            encoding="utf-8",
        )
        (root / "corpus" / "pairs-index.json").write_text(
            json.dumps(
                [
                    {
                        "pair_id": "pair-a-001",
                        "thread_uid": "thread-a",
                        "family_ids": ["family-001-alpha"],
                        "search_text": "Implement alpha registry governance in the canonical pipeline",
                        "summary": "Implement alpha registry governance",
                        "vector_terms": {"alpha": 0.7, "registry": 0.9},
                    },
                ],
            ),
            encoding="utf-8",
        )
        (root / "corpus" / "action-ledger.json").write_text(
            json.dumps(
                [
                    {
                        "action_key": "action-alpha",
                        "canonical_action": "Implement alpha registry",
                        "family_ids": ["family-001-alpha"],
                        "thread_uids": ["thread-a"],
                    },
                ],
            ),
            encoding="utf-8",
        )
        (root / "corpus" / "unresolved-ledger.json").write_text(
            json.dumps(
                [
                    {
                        "question_key": "question-alpha",
                        "canonical_question": "How should alpha evolve?",
                        "why_unresolved": "Design is open.",
                        "family_ids": ["family-001-alpha"],
                        "thread_uids": ["thread-a"],
                    },
                ],
            ),
            encoding="utf-8",
        )
        (root / "corpus" / "doctrine-timeline.json").write_text(json.dumps([]), encoding="utf-8")
        (root / "corpus" / "canonical-entities.json").write_text(
            json.dumps(
                [
                    {
                        "canonical_entity_id": "entity-alpha",
                        "canonical_label": "Alpha System",
                        "aliases": ["Alpha"],
                    },
                ],
            ),
            encoding="utf-8",
        )
        (root / "corpus" / "entity-aliases.json").write_text(
            json.dumps([{"canonical_label": "Alpha System", "labels": ["Alpha"]}]),
            encoding="utf-8",
        )

    def test_seed_gold_writes_seeded_and_manual_templates(self) -> None:
        root = self.build_root()
        self.seed_corpus(root)

        paths = MODULE.seed_gold(root)

        self.assertTrue(paths["detectors"].exists())
        self.assertTrue(paths["families"].exists())
        self.assertTrue(paths["retrieval"].exists())
        self.assertTrue(paths["answers"].exists())
        self.assertTrue((root / "eval" / "gold" / "manual" / "detectors.json").exists())
        self.assertTrue((root / "eval" / "fixtures" / "manual" / "retrieval.json").exists())

    def test_manual_fixtures_take_precedence_when_populated(self) -> None:
        root = self.build_root()
        self.seed_corpus(root)
        MODULE.seed_gold(root)
        manual_answers = root / "eval" / "gold" / "manual" / "answers.json"
        manual_answers.write_text(
            json.dumps(
                {
                    "fixtures": [
                        {
                            "query": "Alpha Pipeline",
                            "expected_state": "grounded",
                            "required_citations": ["family:family-001-alpha"],
                            "min_evidence_count": 1,
                        },
                    ],
                },
            ),
            encoding="utf-8",
        )

        payload, source, _ = MODULE.load_preferred_fixture(root, "answers")

        self.assertEqual(source, "manual")
        self.assertEqual(len(payload["fixtures"]), 1)

    def test_empty_manual_detector_gold_can_be_explicitly_marked_review_complete(self) -> None:
        root = self.build_root()
        self.seed_corpus(root)
        MODULE.seed_gold(root)
        manual_detectors = root / "eval" / "gold" / "manual" / "detectors.json"
        manual_detectors.write_text(
            json.dumps(
                {
                    "manual_review_complete": True,
                    "accepted_duplicates": [],
                    "rejected_duplicates": [],
                    "accepted_drift_pairs": [],
                    "rejected_drift_pairs": [],
                    "accepted_contradictions": [],
                    "rejected_contradictions": [],
                    "accepted_entity_aliases": [],
                    "rejected_entity_aliases": [],
                },
            ),
            encoding="utf-8",
        )

        payload, source, _ = MODULE.load_preferred_fixture(root, "detectors")

        self.assertEqual(source, "manual")
        self.assertTrue(payload["manual_review_complete"])

    def test_evaluate_current_corpus_computes_retrieval_answer_and_gate_metrics(self) -> None:
        root = self.build_root()
        self.seed_corpus(root)
        MODULE.seed_gold(root)

        scorecard = MODULE.evaluate_current_corpus(root)

        self.assertEqual(scorecard["detector_metrics"]["accepted_duplicates"]["true_positive"], 1)
        self.assertEqual(scorecard["family_stability"]["exact_member_match_rate"], 1.0)
        self.assertEqual(scorecard["retrieval_metrics"]["family_hit_at_1"], 1.0)
        self.assertEqual(scorecard["retrieval_metrics"]["thread_hit_at_1"], 1.0)
        self.assertGreaterEqual(scorecard["answer_metrics"]["state_match_rate"], 0.5)
        self.assertIn(scorecard["regression_gates"]["overall_state"], {"pass", "warn"})

    def test_build_regression_gates_warns_when_manual_gold_is_missing(self) -> None:
        scorecard = {
            "fixture_sources": {
                "detectors": {"source": "seeded"},
                "families": {"source": "seeded"},
                "retrieval": {"source": "seeded"},
                "answers": {"source": "seeded"},
            },
            "family_stability": {"exact_member_match_rate": 1.0},
            "retrieval_metrics": {
                "family_hit_at_1": 1.0,
                "thread_hit_at_1": 1.0,
                "pair_hit_at_3": 1.0,
            },
            "answer_metrics": {
                "state_match_rate": 1.0,
                "required_citation_coverage_avg": 1.0,
                "forbidden_citation_violation_rate": 0.0,
                "abstention_match_rate": 1.0,
            },
        }

        gates = MODULE.build_regression_gates(scorecard)

        self.assertEqual(gates["source_reliability_state"], "warn")
        self.assertEqual(gates["overall_state"], "warn")


if __name__ == "__main__":
    unittest.main()
