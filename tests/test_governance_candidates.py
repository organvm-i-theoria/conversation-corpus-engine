from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversation_corpus_engine.federation import upsert_corpus
from conversation_corpus_engine.governance_candidates import (
    apply_policy_candidate,
    policy_application_latest_json_path,
    policy_candidates_dir,
    policy_live_pointer_path,
    review_policy_candidate,
    rollback_policy_application,
    stage_policy_candidate,
)
from conversation_corpus_engine.governance_policy import load_or_create_promotion_policy


def seed_valid_corpus(root: Path, *, name: str, gate_state: str = "pass") -> None:
    corpus_dir = root / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    for rel in (
        "threads-index.json",
        "pairs-index.json",
        "doctrine-briefs.json",
        "family-dossiers.json",
        "canonical-families.json",
        "action-ledger.json",
        "unresolved-ledger.json",
        "canonical-entities.json",
    ):
        (corpus_dir / rel).write_text("[]", encoding="utf-8")
    (corpus_dir / "semantic-v3-index.json").write_text('{"threads":[]}', encoding="utf-8")
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
                "name": name,
            },
        ),
        encoding="utf-8",
    )


class GovernanceCandidatesTests(unittest.TestCase):
    def test_stage_review_apply_and_rollback_policy_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            project_root = workspace_root / "project"
            corpus_root = workspace_root / "claude-local-session-memory"
            seed_valid_corpus(corpus_root, name="Claude Local Session Memory")
            upsert_corpus(
                project_root,
                corpus_root,
                corpus_id="claude-local-session-memory",
                name="Claude Local Session Memory",
            )

            staged = stage_policy_candidate(
                project_root,
                threshold_overrides={"max_warn_corpora": 1.0},
                note="Allow one warn corpus during transition.",
            )
            approved = review_policy_candidate(
                project_root, staged["candidate_id"], decision="approve", note="Ready to apply."
            )
            applied = apply_policy_candidate(
                project_root, staged["candidate_id"], note="Promote the reviewed threshold."
            )
            live_policy = load_or_create_promotion_policy(project_root)
            rollback = rollback_policy_application(
                project_root, note="Restore the prior live thresholds."
            )
            restored_policy = load_or_create_promotion_policy(project_root)
            latest_application = json.loads(
                policy_application_latest_json_path(project_root).read_text(encoding="utf-8")
            )
            live_pointer = json.loads(
                policy_live_pointer_path(project_root).read_text(encoding="utf-8")
            )

            self.assertEqual(staged["status"], "staged")
            self.assertTrue(
                (
                    policy_candidates_dir(project_root) / staged["candidate_id"] / "replay.json"
                ).exists()
            )
            self.assertEqual(approved["status"], "approved")
            self.assertEqual(applied["candidate_id"], staged["candidate_id"])
            self.assertEqual(live_policy["version"], 2)
            self.assertEqual(live_policy["thresholds"]["max_warn_corpora"], 1.0)
            self.assertEqual(latest_application["candidate_id"], staged["candidate_id"])
            self.assertEqual(rollback["source_candidate_id"], staged["candidate_id"])
            self.assertEqual(restored_policy["thresholds"]["max_warn_corpora"], 0.0)
            self.assertEqual(live_pointer["event"], "rollback")

    def test_apply_rejected_candidate_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            project_root = workspace_root / "project"
            corpus_root = workspace_root / "gemini-history-memory"
            seed_valid_corpus(corpus_root, name="Gemini History Memory")
            upsert_corpus(
                project_root,
                corpus_root,
                corpus_id="gemini-history-memory",
                name="Gemini History Memory",
            )

            staged = stage_policy_candidate(
                project_root,
                threshold_overrides={"max_warn_corpora": 1.0},
            )
            review_policy_candidate(
                project_root,
                staged["candidate_id"],
                decision="reject",
                note="Keep the stricter threshold.",
            )

            with self.assertRaisesRegex(ValueError, "must be approved"):
                apply_policy_candidate(project_root, staged["candidate_id"])


if __name__ == "__main__":
    unittest.main()
