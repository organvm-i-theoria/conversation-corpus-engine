from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversation_corpus_engine.federation import upsert_corpus
from conversation_corpus_engine.governance_policy import policy_calibration_path
from conversation_corpus_engine.governance_replay import (
    build_policy_replay_payload,
    policy_replay_history_path,
    write_policy_replay_artifacts,
)


def seed_valid_corpus(
    root: Path,
    *,
    name: str,
    gate_state: str = "pass",
    adapter_type: str = "manual-export",
    source_input: Path | None = None,
) -> None:
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
    contract = {
        "contract_name": "conversation-corpus-engine-v1",
        "contract_version": 1,
        "adapter_type": adapter_type,
        "name": name,
    }
    if source_input is not None:
        contract["source_input"] = str(source_input.resolve())
    (corpus_dir / "contract.json").write_text(json.dumps(contract), encoding="utf-8")


class GovernanceReplayTests(unittest.TestCase):
    def test_build_policy_replay_payload_reports_warn_metrics_and_threshold_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            project_root = workspace_root / "project"
            pass_root = workspace_root / "claude-local-session-memory"
            warn_root = workspace_root / "gemini-history-memory"
            seed_valid_corpus(pass_root, name="Claude Local Session Memory", gate_state="pass")
            seed_valid_corpus(warn_root, name="Gemini History Memory", gate_state="warn")
            upsert_corpus(
                project_root,
                pass_root,
                corpus_id="claude-local-session-memory",
                name="Claude Local Session Memory",
            )
            upsert_corpus(
                project_root,
                warn_root,
                corpus_id="gemini-history-memory",
                name="Gemini History Memory",
            )

            default_payload = build_policy_replay_payload(project_root)
            override_payload = build_policy_replay_payload(
                project_root,
                threshold_overrides={
                    "max_warn_corpora": 1.0,
                    "min_manual_pass_rate": 0.5,
                    "min_registered_active_corpora": 2.0,
                },
            )

            self.assertEqual(default_payload["summary"]["active_corpus_count"], 2)
            self.assertEqual(default_payload["summary"]["warn_corpus_count"], 1)
            self.assertEqual(default_payload["summary"]["manual_pass_count"], 1)
            self.assertEqual(default_payload["summary"]["manual_pass_rate"], 0.5)
            self.assertEqual(default_payload["evaluation"]["overall_state"], "fail")
            self.assertEqual(override_payload["policy"]["mode"], "candidate-preview")
            self.assertEqual(override_payload["evaluation"]["overall_state"], "pass")

    def test_write_policy_replay_artifacts_persists_history_and_calibration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            project_root = workspace_root / "project"
            source_drop_root = workspace_root / "source-drop"
            source_input = source_drop_root / "perplexity" / "inbox"
            source_input.mkdir(parents=True, exist_ok=True)
            (source_input / "export.md").write_text("# export\n", encoding="utf-8")

            stale_root = workspace_root / "perplexity-history-memory"
            seed_valid_corpus(
                stale_root,
                name="Perplexity History Memory",
                gate_state="pass",
                adapter_type="perplexity-export",
                source_input=source_input,
            )
            upsert_corpus(
                project_root,
                stale_root,
                corpus_id="perplexity-history-memory",
                name="Perplexity History Memory",
            )

            payload = build_policy_replay_payload(
                project_root,
                threshold_overrides={"max_stale_corpora": 1.0},
            )
            artifacts = write_policy_replay_artifacts(project_root, payload)
            history = json.loads(
                policy_replay_history_path(project_root).read_text(encoding="utf-8")
            )
            calibration = json.loads(
                policy_calibration_path(project_root).read_text(encoding="utf-8")
            )

            self.assertEqual(payload["summary"]["stale_corpus_count"], 1)
            self.assertEqual(payload["cases"][0]["source_freshness_state"], "missing_snapshot")
            self.assertTrue(Path(artifacts["latest_json_path"]).exists())
            self.assertTrue(Path(artifacts["latest_markdown_path"]).exists())
            self.assertEqual(history["count"], 1)
            self.assertEqual(calibration["policy_learning"]["state"], "ready")


if __name__ == "__main__":
    unittest.main()
