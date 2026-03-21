from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversation_corpus_engine.corpus_diff import build_corpus_diff_payload


def token_map(*tokens: str) -> dict[str, float]:
    return {token: round(1.0 - (index * 0.08), 4) for index, token in enumerate(tokens)}  # allow-secret


def seed_corpus(
    root: Path,
    *,
    corpus_title: str,
    family_title: str,
    family_id: str,
    thread_uid: str,
    action_key: str,
    action_text: str,
    question_key: str,
    question_text: str,
    entity_label: str,
    gate_state: str = "pass",
) -> None:
    corpus_dir = root / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    tokens = [token.lower() for token in family_title.split()]
    vectors = token_map(*tokens)
    (corpus_dir / "threads-index.json").write_text(
        json.dumps(
            [
                {
                    "thread_uid": thread_uid,
                    "title_normalized": family_title,
                    "semantic_v3_summary": f"{family_title} governs the {corpus_title}.",
                    "semantic_v3_themes": tokens,
                    "semantic_v3_entities": [entity_label],
                    "family_ids": [family_id],
                },
            ],
        ),
        encoding="utf-8",
    )
    (corpus_dir / "semantic-v3-index.json").write_text(
        json.dumps(
            {
                "threads": [
                    {
                        "thread_uid": thread_uid,
                        "title": family_title,
                        "search_text": f"{family_title} {corpus_title} {action_text}",
                        "vector_terms": vectors,
                        "family_ids": [family_id],
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    (corpus_dir / "pairs-index.json").write_text(
        json.dumps(
            [
                {
                    "pair_id": f"{thread_uid}-pair-001",
                    "thread_uid": thread_uid,
                    "family_ids": [family_id],
                    "search_text": f"{action_text} inside {family_title}",
                    "summary": action_text,
                    "vector_terms": vectors,
                },
            ],
        ),
        encoding="utf-8",
    )
    (corpus_dir / "doctrine-briefs.json").write_text(
        json.dumps(
            [
                {
                    "family_id": family_id,
                    "canonical_title": family_title,
                    "canonical_thread_uid": thread_uid,
                    "stable_themes": tokens,
                    "brief_text": f"{family_title} doctrine for {corpus_title}.",
                    "search_text": f"{family_title} {corpus_title}",
                    "vector_terms": vectors,
                },
            ],
        ),
        encoding="utf-8",
    )
    (corpus_dir / "family-dossiers.json").write_text(
        json.dumps(
            [
                {
                    "family_id": family_id,
                    "canonical_title": family_title,
                    "canonical_thread_uid": thread_uid,
                    "member_count": 1,
                    "stable_themes": tokens,
                    "doctrine_summary": f"{family_title} doctrine for {corpus_title}.",
                    "search_text": f"{family_title} {action_text}",
                    "actions": [{"action_key": action_key, "canonical_action": action_text}],
                    "unresolved": [{"question_key": question_key, "canonical_question": question_text}],
                    "key_entities": [{"canonical_label": entity_label, "entity_type": "concept"}],
                    "vector_terms": vectors,
                },
            ],
        ),
        encoding="utf-8",
    )
    (corpus_dir / "canonical-families.json").write_text(
        json.dumps(
            [
                {
                    "canonical_family_id": family_id,
                    "canonical_title": family_title,
                    "canonical_thread_uid": thread_uid,
                    "thread_uids": [thread_uid],
                },
            ],
        ),
        encoding="utf-8",
    )
    (corpus_dir / "action-ledger.json").write_text(
        json.dumps(
            [
                {
                    "action_key": action_key,
                    "canonical_action": action_text,
                    "family_ids": [family_id],
                    "thread_uids": [thread_uid],
                },
            ],
        ),
        encoding="utf-8",
    )
    (corpus_dir / "unresolved-ledger.json").write_text(
        json.dumps(
            [
                {
                    "question_key": question_key,
                    "canonical_question": question_text,
                    "why_unresolved": "Open design question.",
                    "family_ids": [family_id],
                    "thread_uids": [thread_uid],
                },
            ],
        ),
        encoding="utf-8",
    )
    (corpus_dir / "canonical-entities.json").write_text(
        json.dumps(
            [
                {
                    "canonical_entity_id": f"entity-{thread_uid}",
                    "canonical_label": entity_label,
                    "aliases": [family_title],
                },
            ],
        ),
        encoding="utf-8",
    )
    (corpus_dir / "evaluation-summary.json").write_text(
        json.dumps({"regression_gates": {"overall_state": gate_state}}),
        encoding="utf-8",
    )
    (corpus_dir / "regression-gates.json").write_text(
        json.dumps({"overall_state": gate_state, "source_reliability_state": "pass"}),
        encoding="utf-8",
    )
    (corpus_dir / "contract.json").write_text(
        json.dumps(
            {
                "contract_name": "conversation-corpus-engine-v1",
                "contract_version": 1,
                "adapter_type": "manual-export",
                "name": corpus_title,
            },
        ),
        encoding="utf-8",
    )


class CorpusDiffTests(unittest.TestCase):
    def test_build_corpus_diff_payload_reports_structural_and_query_deltas(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            live_root = workspace_root / "live-corpus"
            candidate_root = workspace_root / "candidate-corpus"
            seed_corpus(
                live_root,
                corpus_title="Alpha Memory",
                family_title="Alpha Launch",
                family_id="family-launch",
                thread_uid="thread-alpha",
                action_key="action-alpha",
                action_text="Implement alpha rollout",
                question_key="question-alpha",
                question_text="How should alpha launch evolve?",
                entity_label="Alpha Engine",
            )
            seed_corpus(
                candidate_root,
                corpus_title="Alpha Memory Candidate",
                family_title="Beta Launch",
                family_id="family-launch",
                thread_uid="thread-beta",
                action_key="action-beta",
                action_text="Implement beta rollout",
                question_key="question-beta",
                question_text="How should beta launch evolve?",
                entity_label="Beta Engine",
            )

            payload = build_corpus_diff_payload(
                {
                    "corpus_id": "alpha-memory",
                    "name": "Alpha Memory",
                    "root": str(live_root),
                    "contract": "conversation-corpus-engine-v1",
                    "status": "active",
                    "default": True,
                },
                candidate_root,
                provider="claude",
            )

            self.assertEqual(payload["provider"], "claude")
            self.assertEqual(payload["summary"]["changed_family_title_count"], 1)
            self.assertEqual(payload["summary"]["added_action_count"], 1)
            self.assertEqual(payload["summary"]["removed_action_count"], 1)
            self.assertGreater(payload["summary"]["changed_query_count"], 0)
            self.assertEqual(payload["evaluation"]["overall_state"], "review")


if __name__ == "__main__":
    unittest.main()
