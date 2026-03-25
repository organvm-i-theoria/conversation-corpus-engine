from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from conversation_corpus_engine.triage import (
    _strip_uuid_suffix,
    build_entity_alias_review_apply_plan,
    build_entity_alias_reject_stage,
    build_entity_alias_review_assist,
    build_entity_alias_review_campaign,
    build_entity_alias_review_campaign_index,
    build_entity_alias_review_rollup,
    build_entity_alias_review_scoreboard,
    build_triage_plan,
    classify_item,
    compare_entity_alias_review_sample_to_proposal,
    execute_triage_plan,
    filter_entity_alias_review_assist_groups,
    hydrate_entity_alias_review_sample_packet,
    parse_entity_alias_review_sample_markdown,
    propose_entity_alias_review_sample,
    render_entity_alias_review_apply_plan,
    render_entity_alias_reject_stage,
    report_stamp,
    render_entity_alias_review_campaign,
    render_entity_alias_review_campaign_index,
    render_entity_alias_review_rollup,
    render_entity_alias_review_scoreboard,
    render_entity_alias_review_packet_hydration,
    render_entity_alias_review_checklist,
    render_entity_alias_review_sample_comparison,
    render_entity_alias_review_sample_proposal,
    render_entity_alias_review_sample,
    render_entity_alias_review_sample_summary,
    render_entity_alias_review_assist,
    sample_entity_alias_review_assist_groups,
    select_entity_alias_review_assist_batch,
    summarize_entity_alias_review_sample,
    write_entity_alias_review_assist_artifacts,
    write_entity_alias_review_campaign_artifacts,
    write_entity_alias_review_campaign_index_artifacts,
    write_entity_alias_review_rollup_artifacts,
    write_entity_alias_reject_stage_artifacts,
    write_entity_alias_review_apply_plan_artifacts,
    write_entity_alias_review_packet_hydration_artifacts,
    write_entity_alias_review_scoreboard_artifacts,
    write_entity_alias_review_sample_artifacts,
    write_entity_alias_review_sample_comparison_artifacts,
    write_entity_alias_review_sample_proposal_artifacts,
    write_entity_alias_review_sample_summary_artifacts,
)


class StripUuidSuffixTests(unittest.TestCase):
    def test_strips_8_hex_suffix(self) -> None:
        self.assertEqual(
            _strip_uuid_suffix("family-divine-comedy-f22e2b8d"),
            "family-divine-comedy",
        )

    def test_preserves_non_hex_suffix(self) -> None:
        self.assertEqual(
            _strip_uuid_suffix("family-divine-comedy-notahex!"),
            "family-divine-comedy-notahex!",
        )

    def test_preserves_short_ids(self) -> None:
        self.assertEqual(_strip_uuid_suffix("abc"), "abc")

    def test_strips_all_zero_suffix(self) -> None:
        self.assertEqual(
            _strip_uuid_suffix("entity-foo-00000000"),
            "entity-foo",
        )


class ReportStampTests(unittest.TestCase):
    def test_includes_subsecond_precision(self) -> None:
        self.assertRegex(report_stamp(), r"^\d{4}-\d{2}-\d{2}-\d{6}-\d{6}$")


class EntityAliasReviewCampaignTests(unittest.TestCase):
    @staticmethod
    def _sample_payload(
        *,
        anchor: str,
        bucket: str,
        review_id: str,
        signal_flags: list[str] | None = None,
        score: float = 0.92,
    ) -> dict[str, object]:
        group = {
            "anchor": anchor,
            "item_count": 1,
            "max_score": score,
            "relation_counts": {"disjoint": 1},
            "review_bucket": bucket,
            "signal_flags": signal_flags or [],
            "labels": [anchor, f"{anchor} alt"],
            "example_review_ids": [review_id],
            "items": [
                {
                    "review_id": review_id,
                    "title": f"{anchor.title()} <> {anchor.title()} Alt",
                    "relation": "disjoint",
                    "score": score,
                    "review_hint": "Inspect contextual identity before resolving.",
                }
            ],
            "checklist": ["Confirm concepts remain distinct."],
        }
        return {
            "open_count": 1,
            "group_count": 1,
            "batch_count": 1,
            "batch_size": 25,
            "queue_open_count": 406,
            "filtered_open_count": 1,
            "relation_counts": {"disjoint": 1},
            "source_pair_counts": {"claude-history-memory <> claude-local-session-memory": 1},
            "priority_counts": {"high": 1},
            "groups": [group],
            "batches": [
                {
                    "batch_id": "entity-alias-batch-001",
                    "group_count": 1,
                    "item_count": 1,
                    "anchors": [anchor],
                    "groups": [group],
                }
            ],
            "sample": {
                "requested_group_count": 1,
                "selected_group_count": 1,
                "requested_batch_offset": 0,
                "requested_batch_limit": 1,
                "candidate_group_count": 1,
                "candidate_batch_count": 1,
            },
            "group_filters": {"review_buckets": [bucket]},
        }

    def test_build_entity_alias_review_campaign_aggregates_selected_scenarios(self) -> None:
        scenarios = [
            {
                "label": "alpha",
                "description": "Alpha window",
                "review_buckets": ["likely-reject"],
                "sample_groups": 1,
                "sample_batches": 1,
                "batch_offset": 0,
                "anchor_contains": "alpha",
            },
            {
                "label": "beta",
                "description": "Beta window",
                "review_buckets": ["needs-context"],
                "sample_groups": 1,
                "sample_batches": 1,
                "batch_offset": 0,
                "anchor_contains": "beta",
            },
        ]
        sample_payloads = {
            "alpha": self._sample_payload(
                anchor="chapters",
                bucket="likely-reject",
                review_id="review-1",
                signal_flags=["all-zero-overlap"],
            ),
            "beta": self._sample_payload(
                anchor="outline",
                bucket="needs-context",
                review_id="review-2",
                signal_flags=["has-high-score-disjoint-pairs"],
            ),
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            with (
                patch(
                    "conversation_corpus_engine.triage.build_entity_alias_review_assist",
                    side_effect=lambda project_root, batch_size, relation_filters=None, source_pair=None, anchor_contains=None: {
                        "scenario_label": anchor_contains
                    },
                ),
                patch(
                    "conversation_corpus_engine.triage.filter_entity_alias_review_assist_groups",
                    side_effect=lambda payload, review_bucket_filters=None: payload,
                ),
                patch(
                    "conversation_corpus_engine.triage.sample_entity_alias_review_assist_groups",
                    side_effect=lambda payload, sample_groups, sample_batches=None, batch_offset=0: sample_payloads[
                        str(payload["scenario_label"])
                    ],
                ),
            ):
                payload = build_entity_alias_review_campaign(
                    project_root,
                    batch_size=11,
                    scenarios=scenarios,
                )

        self.assertEqual(payload["project_root"], str(project_root.resolve()))
        self.assertEqual(payload["batch_size"], 11)
        self.assertEqual(payload["selected_scenarios"], ["alpha", "beta"])
        self.assertEqual(payload["scenario_count"], 2)
        self.assertEqual(payload["sampled_group_count"], 2)
        self.assertEqual(payload["sampled_item_count"], 2)
        self.assertEqual(payload["assistant_outcome_counts"], {"reject": 1, "needs-context": 1})
        self.assertEqual(payload["assistant_confidence_counts"], {"high": 1, "medium": 1})
        self.assertEqual(payload["bucket_counts"], {"likely-reject": 1, "needs-context": 1})
        self.assertIsNone(payload["proposal_reject_precision"])
        self.assertEqual(payload["scenarios"][0]["proposal_payload"]["assistant_outcome_counts"], {"reject": 1})
        self.assertEqual(
            payload["scenarios"][1]["proposal_payload"]["assistant_outcome_counts"],
            {"needs-context": 1},
        )

    def test_render_entity_alias_review_campaign_formats_scenario_metrics(self) -> None:
        text = render_entity_alias_review_campaign(
            {
                "project_root": "/tmp/project",
                "scenario_count": 2,
                "batch_size": 25,
                "sampled_group_count": 3,
                "sampled_item_count": 5,
                "adjudicated_count": 0,
                "proposal_reject_precision": None,
                "assistant_outcome_counts": {"reject": 2, "needs-context": 1},
                "assistant_confidence_counts": {"high": 2, "medium": 1},
                "scenarios": [
                    {
                        "label": "likely_front",
                        "description": "Front-window likely-reject sample",
                        "sample_payload": {
                            "open_count": 3,
                            "sample": {
                                "candidate_group_count": 10,
                                "candidate_batch_count": 5,
                                "requested_batch_offset": 0,
                            },
                        },
                        "summary_payload": {"total_samples": 2},
                        "proposal_payload": {"assistant_outcome_counts": {"reject": 2}},
                        "comparison_payload": {
                            "adjudicated_count": 0,
                            "agreement_count": 0,
                            "disagreement_count": 0,
                            "proposal_reject_precision": None,
                        },
                        "artifacts": {
                            "sample": {"session_markdown_path": "/tmp/sample.md"},
                            "proposal": {"session_markdown_path": "/tmp/proposal.md"},
                            "comparison": {"session_markdown_path": "/tmp/compare.md"},
                        },
                    }
                ],
            }
        )

        self.assertIn("Entity-alias review campaign", text)
        self.assertIn("Sampled groups: 3  Sampled items: 5  Adjudicated: 0", text)
        self.assertIn("- likely_front: Front-window likely-reject sample", text)
        self.assertIn("assistant: reject=2", text)
        self.assertIn("sample_artifact: /tmp/sample.md", text)

    def test_write_entity_alias_review_campaign_artifacts_writes_manifest_and_scenarios(self) -> None:
        scenario = {
            "label": "alpha",
            "description": "Alpha window",
            "review_buckets": ["likely-reject"],
            "sample_groups": 1,
            "sample_batches": 1,
            "batch_offset": 0,
            "anchor_contains": "alpha",
        }
        sample_payload = self._sample_payload(
            anchor="chapters",
            bucket="likely-reject",
            review_id="review-1",
            signal_flags=["all-zero-overlap"],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            with (
                patch(
                    "conversation_corpus_engine.triage.build_entity_alias_review_assist",
                    side_effect=lambda project_root, batch_size, relation_filters=None, source_pair=None, anchor_contains=None: {
                        "scenario_label": anchor_contains
                    },
                ),
                patch(
                    "conversation_corpus_engine.triage.filter_entity_alias_review_assist_groups",
                    side_effect=lambda payload, review_bucket_filters=None: payload,
                ),
                patch(
                    "conversation_corpus_engine.triage.sample_entity_alias_review_assist_groups",
                    side_effect=lambda payload, sample_groups, sample_batches=None, batch_offset=0: sample_payload,
                ),
            ):
                payload = build_entity_alias_review_campaign(
                    project_root,
                    scenarios=[scenario],
                )

            artifacts = write_entity_alias_review_campaign_artifacts(project_root, payload)

            self.assertEqual(
                set(artifacts),
                {
                    "latest_json_path",
                    "latest_markdown_path",
                    "session_json_path",
                    "session_markdown_path",
                    "scenario_artifacts",
                },
            )
            self.assertTrue(Path(artifacts["latest_json_path"]).exists())
            self.assertTrue(Path(artifacts["session_markdown_path"]).exists())
            self.assertIn("alpha", artifacts["scenario_artifacts"])
            scenario_artifacts = artifacts["scenario_artifacts"]["alpha"]
            self.assertTrue(Path(scenario_artifacts["sample"]["session_markdown_path"]).exists())
            self.assertTrue(Path(scenario_artifacts["summary"]["session_markdown_path"]).exists())
            self.assertTrue(Path(scenario_artifacts["proposal"]["session_markdown_path"]).exists())
            self.assertTrue(Path(scenario_artifacts["comparison"]["session_markdown_path"]).exists())
            latest_markdown = Path(artifacts["latest_markdown_path"]).read_text(encoding="utf-8")
            self.assertIn("Entity-alias review campaign", latest_markdown)
            self.assertIn("sample_artifact:", latest_markdown)


class EntityAliasReviewCampaignLedgerTests(unittest.TestCase):
    def _write_packet(
        self,
        reports_root: Path,
        packet_id: str,
        *,
        proposal_id: str | None = None,
        compare_id: str | None = None,
        manual_outcome: str = "",
        assistant_outcome: str = "reject",
        assistant_confidence: str = "high",
        comparison_precision: float | None = None,
    ) -> None:
        sample_path = reports_root / f"review-assist-sample-{packet_id}.md"
        sample_path.write_text(
            "\n".join(
                [
                    "# Entity-alias review sample",
                    "",
                    "## Sample 1: chapters",
                    "- Bucket: likely-reject",
                    "- Review IDs: review-1, review-2",
                    "- Proposed outcome: reject",
                    f"- Manual outcome: {manual_outcome}",
                    "- Notes: packet fixture",
                ]
            ),
            encoding="utf-8",
        )
        proposal_artifact_id = proposal_id or packet_id
        (reports_root / f"review-assist-sample-proposal-{proposal_artifact_id}.json").write_text(
            json.dumps(
                {
                    "source_path": str(sample_path.resolve()),
                    "samples": [
                        {
                            "anchor": "chapters",
                            "review_ids": ["review-1", "review-2"],
                            "assistant_outcome": assistant_outcome,
                            "assistant_confidence": assistant_confidence,
                            "assistant_rationale": ["fixture rationale"],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        if comparison_precision is not None:
            compare_artifact_id = compare_id or packet_id
            (reports_root / f"review-assist-sample-compare-{compare_artifact_id}.json").write_text(
                json.dumps(
                    {
                        "sample_path": str(sample_path.resolve()),
                        "proposal_path": str(
                            reports_root
                            / f"review-assist-sample-proposal-{proposal_artifact_id}.json"
                        ),
                        "matched_samples": 1,
                        "adjudicated_count": 1 if manual_outcome else 0,
                        "comparable_count": 1 if manual_outcome else 0,
                        "agreement_count": 1 if manual_outcome == assistant_outcome else 0,
                        "disagreement_count": 0 if manual_outcome == assistant_outcome else (1 if manual_outcome else 0),
                        "proposal_reject_count": 1 if assistant_outcome == "reject" else 0,
                        "proposal_keep_count": 1 if assistant_outcome == "keep" else 0,
                        "proposal_needs_context_count": 1 if assistant_outcome == "needs-context" else 0,
                        "proposal_reject_hits": 1 if manual_outcome == "reject" and assistant_outcome == "reject" else 0,
                        "proposal_reject_false_positives": 1 if manual_outcome == "keep" and assistant_outcome == "reject" else 0,
                        "proposal_reject_precision": comparison_precision,
                        "confidence_summary": {
                            assistant_confidence: {
                                "count": 1,
                                "adjudicated_count": 1 if manual_outcome else 0,
                                "agreement_count": 1 if manual_outcome == assistant_outcome else 0,
                                "disagreement_count": 0 if manual_outcome == assistant_outcome else (1 if manual_outcome else 0),
                                "proposal_reject_count": 1 if assistant_outcome == "reject" else 0,
                                "proposal_reject_hits": 1 if manual_outcome == "reject" and assistant_outcome == "reject" else 0,
                                "proposal_reject_false_positives": 1 if manual_outcome == "keep" and assistant_outcome == "reject" else 0,
                                "reject_precision": comparison_precision,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

    def test_build_entity_alias_review_campaign_index_links_packets_and_campaigns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            reports_root = project_root / "reports"
            reports_root.mkdir()
            self._write_packet(
                reports_root,
                "2026-03-25-123012-122496-likely_front",
                manual_outcome="reject",
                comparison_precision=1.0,
            )
            campaign_path = reports_root / "review-assist-campaign-2026-03-25-123012-122496.json"
            campaign_path.write_text(
                json.dumps(
                    {
                        "sampled_group_count": 1,
                        "adjudicated_count": 1,
                        "scenario_count": 1,
                        "selected_scenarios": ["likely_front"],
                        "proposal_reject_precision": 1.0,
                        "scenarios": [
                            {
                                "label": "likely_front",
                                "artifacts": {
                                    "sample": {
                                        "session_markdown_path": str(
                                            reports_root / "review-assist-sample-2026-03-25-123012-122496-likely_front.md"
                                        )
                                    }
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            payload = build_entity_alias_review_campaign_index(project_root)

            self.assertEqual(payload["packet_count"], 1)
            self.assertEqual(payload["campaign_count"], 1)
            self.assertEqual(payload["packet_status_counts"], {"complete": 1})
            self.assertEqual(payload["campaign_status_counts"], {"complete": 1})
            self.assertEqual(payload["scenario_counts"], {"likely_front": 1})
            self.assertEqual(payload["packets"][0]["campaign_ids"], ["2026-03-25-123012-122496"])
            self.assertTrue(payload["packets"][0]["valid"])

    def test_build_entity_alias_review_rollup_aggregates_filtered_packets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            reports_root = project_root / "reports"
            reports_root.mkdir()
            self._write_packet(
                reports_root,
                "2026-03-25-123012-122496-likely_front",
                manual_outcome="reject",
                comparison_precision=1.0,
            )
            self._write_packet(
                reports_root,
                "2026-03-25-123012-122496-needs_context",
                manual_outcome="keep",
                assistant_outcome="reject",
                comparison_precision=0.0,
            )

            payload = build_entity_alias_review_rollup(
                project_root,
                scenario_labels=["likely_front"],
            )

            self.assertEqual(payload["selected_packet_count"], 1)
            self.assertEqual(payload["compared_packet_count"], 1)
            self.assertEqual(payload["selected_scenario_counts"], {"likely_front": 1})
            self.assertEqual(payload["proposal_reject_hits"], 1)
            self.assertEqual(payload["proposal_reject_false_positives"], 0)
            self.assertEqual(payload["proposal_reject_precision"], 1.0)

    def test_build_entity_alias_review_campaign_index_matches_artifacts_by_source_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            reports_root = project_root / "reports"
            reports_root.mkdir()
            self._write_packet(
                reports_root,
                "2026-03-25-113955-087698",
                proposal_id="2026-03-25-113955-153880",
                compare_id="2026-03-25-113955-214366",
                manual_outcome="reject",
                comparison_precision=1.0,
            )

            payload = build_entity_alias_review_campaign_index(project_root)

            self.assertEqual(payload["proposal_packet_count"], 1)
            self.assertEqual(payload["comparison_packet_count"], 1)
            self.assertTrue(payload["packets"][0]["proposal_path"].endswith("113955-153880.json"))
            self.assertTrue(payload["packets"][0]["compare_path"].endswith("113955-214366.json"))

    def test_hydrate_entity_alias_review_sample_packet_reports_validation_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sample_path = Path(tmpdir) / "sample.md"
            sample_path.write_text(
                "\n".join(
                    [
                        "# Entity-alias review sample",
                        "",
                        "## Sample 1: chapters",
                        "- Bucket: likely-reject",
                        "- Review IDs: review-1",
                        "- Proposed outcome: reject",
                        "- Manual outcome: maybe",
                        "",
                        "## Sample 2: appendix",
                        "- Bucket: ",
                        "- Review IDs: review-1",
                        "- Proposed outcome: reject",
                        "- Manual outcome: reject",
                    ]
                ),
                encoding="utf-8",
            )

            payload = hydrate_entity_alias_review_sample_packet(sample_path)

            self.assertFalse(payload["valid"])
            self.assertEqual(payload["error_count"], 2)
            self.assertEqual(payload["warning_count"], 2)
            self.assertEqual(payload["adjudication_record_count"], 1)
            self.assertEqual(payload["errors"][0]["type"], "invalid-manual-outcome")

    def test_build_entity_alias_reject_stage_blocks_without_sufficient_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            reports_root = project_root / "reports"
            reports_root.mkdir()
            self._write_packet(
                reports_root,
                "2026-03-25-123012-122496-likely_front",
                manual_outcome="reject",
                comparison_precision=1.0,
            )

            payload = build_entity_alias_reject_stage(
                project_root,
                scenario_labels=["likely_front"],
                min_reject_precision=0.95,
                min_adjudicated=3,
            )

            self.assertEqual(payload["stage_status"], "blocked")
            self.assertFalse(payload["ready_to_apply"])
            self.assertEqual(payload["candidate_count"], 1)
            self.assertIn("Need at least 3 adjudicated samples", payload["blocked_reasons"][0])

    def test_build_entity_alias_review_scoreboard_ranks_packets_by_gate_unlock_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            reports_root = project_root / "reports"
            reports_root.mkdir()
            self._write_packet(
                reports_root,
                "2026-03-25-123012-122496-likely_front",
                manual_outcome="",
                comparison_precision=0.0,
            )
            self._write_packet(
                reports_root,
                "2026-03-25-113955-087698",
                proposal_id="2026-03-25-113955-153880",
                compare_id="2026-03-25-113955-214366",
                manual_outcome="",
                comparison_precision=0.0,
            )

            payload = build_entity_alias_review_scoreboard(
                project_root,
                min_reject_precision=0.95,
                min_adjudicated=5,
            )

            self.assertEqual(payload["current_adjudicated"], 0)
            self.assertEqual(payload["remaining_to_threshold"], 5)
            self.assertGreaterEqual(payload["candidate_packet_count"], 2)
            self.assertIn(payload["packets"][0]["priority_bucket"], {"unlock-threshold-now", "precision-ready"})

    def test_build_entity_alias_review_apply_plan_stays_disabled_and_exposes_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            reports_root = project_root / "reports"
            reports_root.mkdir()
            self._write_packet(
                reports_root,
                "2026-03-25-123012-122496-likely_front",
                manual_outcome="reject",
                comparison_precision=1.0,
            )

            payload = build_entity_alias_review_apply_plan(
                project_root,
                min_reject_precision=0.95,
                min_adjudicated=3,
            )

            self.assertEqual(payload["apply_status"], "disabled")
            self.assertFalse(payload["ready_to_apply"])
            self.assertEqual(len(payload["snapshot_contract"]["pre_apply_snapshots"]), 3)
            self.assertIn("Apply plan remains disabled", payload["blocked_reasons"][0])

    def test_render_and_write_campaign_index_rollup_and_stage_artifacts(self) -> None:
        index_payload = {
            "project_root": "/tmp/project",
            "campaign_count": 1,
            "packet_count": 1,
            "total_samples": 1,
            "adjudicated_count": 1,
            "pending_count": 0,
            "packet_status_counts": {"complete": 1},
            "campaign_status_counts": {"complete": 1},
            "scenario_counts": {"likely_front": 1},
            "campaigns": [
                {
                    "campaign_id": "2026-03-25-123012-122496",
                    "status": "complete",
                    "scenario_count": 1,
                    "sampled_group_count": 1,
                    "adjudicated_count": 1,
                    "proposal_reject_precision": 1.0,
                }
            ],
            "packets": [
                {
                    "packet_id": "2026-03-25-123012-122496-likely_front",
                    "status": "complete",
                    "total_samples": 1,
                    "adjudicated_count": 1,
                    "scenario_label": "likely_front",
                    "campaign_ids": ["2026-03-25-123012-122496"],
                    "sample_path": "/tmp/sample.md",
                }
            ],
        }
        rollup_payload = {
            "project_root": "/tmp/project",
            "indexed_packet_count": 1,
            "selected_packet_count": 1,
            "compared_packet_count": 1,
            "matched_samples": 1,
            "adjudicated_count": 1,
            "comparable_count": 1,
            "agreement_count": 1,
            "disagreement_count": 0,
            "agreement_rate": 1.0,
            "proposal_reject_precision": 1.0,
            "selected_status_counts": {"complete": 1},
            "selected_scenario_counts": {"likely_front": 1},
            "confidence_summary": {"high": {"count": 1}},
            "filters": {},
            "packets": [
                {
                    "packet_id": "2026-03-25-123012-122496-likely_front",
                    "status": "complete",
                    "total_samples": 1,
                    "adjudicated_count": 1,
                    "scenario_label": "likely_front",
                    "compare_path": "/tmp/compare.json",
                }
            ],
        }
        stage_payload = {
            "project_root": "/tmp/project",
            "stage_status": "ready",
            "ready_to_apply": True,
            "candidate_count": 1,
            "thresholds": {"min_reject_precision": 0.95, "min_adjudicated": 1},
            "blocked_reasons": [],
            "candidates": [
                {
                    "candidate_id": "reject-stage-001",
                    "packet_id": "2026-03-25-123012-122496-likely_front",
                    "anchor": "chapters",
                    "review_ids": ["review-1", "review-2"],
                    "assistant_outcome": "reject",
                    "assistant_confidence": "high",
                    "manual_notes": "fixture",
                }
            ],
            "rollup": {"adjudicated_count": 1, "proposal_reject_precision": 1.0},
        }

        self.assertIn("Entity-alias review campaign index", render_entity_alias_review_campaign_index(index_payload))
        self.assertIn("Entity-alias review rollup", render_entity_alias_review_rollup(rollup_payload))
        self.assertIn("Entity-alias reject stage", render_entity_alias_reject_stage(stage_payload))

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            index_artifacts = write_entity_alias_review_campaign_index_artifacts(project_root, index_payload)
            rollup_artifacts = write_entity_alias_review_rollup_artifacts(project_root, rollup_payload)
            stage_artifacts = write_entity_alias_reject_stage_artifacts(project_root, stage_payload)

            self.assertTrue(Path(index_artifacts["latest_markdown_path"]).exists())
            self.assertTrue(Path(rollup_artifacts["latest_markdown_path"]).exists())
            self.assertTrue(Path(stage_artifacts["latest_markdown_path"]).exists())

    def test_render_and_write_packet_hydration_scoreboard_and_apply_plan_artifacts(self) -> None:
        hydration_payload = {
            "source_path": "/tmp/sample.md",
            "packet_id": "packet-001",
            "valid": True,
            "error_count": 0,
            "warning_count": 1,
            "total_samples": 1,
            "adjudication_record_count": 0,
            "pending_count": 1,
            "warnings": [{"sample_index": 1, "type": "missing-bucket", "message": "fixture"}],
            "errors": [],
            "samples": [{"sample_index": 1, "anchor": "chapters", "bucket": "likely-reject", "manual_outcome": "", "review_ids": ["review-1"]}],
        }
        scoreboard_payload = {
            "project_root": "/tmp/project",
            "current_adjudicated": 0,
            "remaining_to_threshold": 20,
            "current_reject_precision": None,
            "priority_bucket_counts": {"precision-ready": 1},
            "packets": [
                {
                    "packet_id": "packet-001",
                    "priority_bucket": "precision-ready",
                    "priority_score": 55,
                    "pending_samples": 12,
                    "valid": True,
                    "scenario_label": "likely_front",
                    "has_compare": True,
                    "has_proposal": True,
                    "remaining_to_threshold_after_completion": 8,
                }
            ],
        }
        apply_plan_payload = {
            "project_root": "/tmp/project",
            "apply_status": "disabled",
            "enabled": False,
            "candidate_count": 0,
            "blocked_reasons": ["fixture block"],
            "snapshot_contract": {
                "pre_apply_snapshots": [
                    {
                        "label": "review-queue",
                        "source_path": "/tmp/queue.json",
                        "planned_snapshot_path": "/tmp/queue-snapshot.json",
                    }
                ],
                "rollback_contract": {"post_restore_steps": ["restore state files"]},
            },
        }

        self.assertIn("Entity-alias review packet hydration", render_entity_alias_review_packet_hydration(hydration_payload))
        self.assertIn("Entity-alias review completion scoreboard", render_entity_alias_review_scoreboard(scoreboard_payload))
        self.assertIn("Entity-alias review apply plan", render_entity_alias_review_apply_plan(apply_plan_payload))

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            hydration_artifacts = write_entity_alias_review_packet_hydration_artifacts(project_root, hydration_payload)
            scoreboard_artifacts = write_entity_alias_review_scoreboard_artifacts(project_root, scoreboard_payload)
            apply_plan_artifacts = write_entity_alias_review_apply_plan_artifacts(project_root, apply_plan_payload)

            self.assertTrue(Path(hydration_artifacts["latest_markdown_path"]).exists())
            self.assertTrue(Path(scoreboard_artifacts["latest_markdown_path"]).exists())
            self.assertTrue(Path(apply_plan_artifacts["latest_markdown_path"]).exists())


class ClassifyItemTests(unittest.TestCase):
    def test_exact_cross_corpus_accepted(self) -> None:
        item = {
            "review_type": "entity-alias",
            "subject_ids": [
                "corpus-a:entity-python",
                "corpus-b:entity-python",
            ],
            "suggested_canonical_subject": "python",
        }
        result = classify_item(item)
        assert result is not None
        self.assertEqual(result["decision"], "accepted")
        self.assertEqual(result["policy"], "exact-cross-corpus")

    def test_same_corpus_not_matched(self) -> None:
        item = {
            "review_type": "entity-alias",
            "subject_ids": [
                "corpus-a:entity-python",
                "corpus-a:entity-python-c",
            ],
        }
        result = classify_item(item)
        # Not exact-cross-corpus (same corpus), not prefix (python is too short)
        self.assertIsNone(result)

    def test_noise_entity_rejected(self) -> None:
        item = {
            "review_type": "entity-alias",
            "subject_ids": [
                "corpus-a:entity-0-1",
                "corpus-b:entity-something",
            ],
        }
        result = classify_item(item)
        assert result is not None
        self.assertEqual(result["decision"], "rejected")
        self.assertEqual(result["policy"], "noise-entity")

    def test_short_entity_rejected(self) -> None:
        item = {
            "review_type": "entity-alias",
            "subject_ids": [
                "corpus-a:entity-ab",
                "corpus-b:entity-something-long",
            ],
        }
        result = classify_item(item)
        assert result is not None
        self.assertEqual(result["decision"], "rejected")
        self.assertEqual(result["policy"], "short-entity")

    def test_contradiction_deferred(self) -> None:
        item = {
            "review_type": "contradiction",
            "subject_ids": ["corpus-a:family-foo-12345678"],
        }
        result = classify_item(item)
        assert result is not None
        self.assertEqual(result["decision"], "deferred")
        self.assertEqual(result["policy"], "contradiction-defer")

    def test_slug_match_accepted(self) -> None:
        item = {
            "review_type": "family-merge",
            "subject_ids": [
                "corpus-a:family-divine-comedy-f22e2b8d",
                "corpus-b:family-divine-comedy-a1b2c3d4",
            ],
            "suggested_canonical_subject": "divine-comedy",
        }
        result = classify_item(item)
        assert result is not None
        self.assertEqual(result["decision"], "accepted")
        self.assertEqual(result["policy"], "slug-match")

    def test_prefix_entity_alias_accepted(self) -> None:
        item = {
            "review_type": "entity-alias",
            "subject_ids": [
                "corpus-a:entity-interactive-drum-machine",
                "corpus-b:entity-interactive-drum-machine-with-claude-api",
            ],
        }
        result = classify_item(item)
        assert result is not None
        self.assertEqual(result["decision"], "accepted")
        self.assertEqual(result["policy"], "prefix-entity-alias")

    def test_prefix_too_short_not_matched(self) -> None:
        item = {
            "review_type": "entity-alias",
            "subject_ids": [
                "corpus-a:entity-ab",
                "corpus-b:entity-abcdef",
            ],
        }
        result = classify_item(item)
        assert result is not None
        # Should hit short-entity, not prefix-entity-alias
        self.assertEqual(result["policy"], "short-entity")

    def test_entity_title_overlap_accepted(self) -> None:
        item = {
            "review_type": "entity-alias",
            "title": "Interactive Drum Machine <> Interactive Drum Machine with Claude API",
            "subject_ids": [
                "corpus-a:entity-drum-a",
                "corpus-b:entity-drum-b",
            ],
            "suggested_canonical_subject": "interactive-drum-machine",
        }
        result = classify_item(item)
        assert result is not None
        self.assertEqual(result["decision"], "accepted")
        self.assertEqual(result["policy"], "entity-title-overlap")

    def test_entity_title_overlap_respects_human_boundary_for_low_signal_labels(self) -> None:
        item = {
            "review_type": "entity-alias",
            "title": "System <> System Platform",
            "subject_ids": [
                "corpus-a:entity-system-a",
                "corpus-b:entity-system-b",
            ],
        }
        result = classify_item(item)
        self.assertIsNone(result)

    def test_generic_singleton_entity_rejected(self) -> None:
        item = {
            "review_type": "entity-alias",
            "title": "Apps <> Building apps and websites",
            "subject_ids": [
                "corpus-a:entity-apps",
                "corpus-b:entity-building-apps-and-websites",
            ],
        }
        result = classify_item(item)
        assert result is not None
        self.assertEqual(result["decision"], "rejected")
        self.assertEqual(result["policy"], "generic-singleton-entity")

    def test_family_title_overlap_accepted(self) -> None:
        item = {
            "review_type": "family-merge",
            "title": "Virtual System Architecture <> Virtual System Architecture Overview",
            "subject_ids": [
                "corpus-a:family-alpha",
                "corpus-b:family-beta",
            ],
            "suggested_canonical_subject": "virtual-system-architecture",
        }
        result = classify_item(item)
        assert result is not None
        self.assertEqual(result["decision"], "accepted")
        self.assertEqual(result["policy"], "family-title-overlap")

    def test_action_title_overlap_accepted(self) -> None:
        item = {
            "review_type": "action-merge",
            "title": "Implement alpha registry ritual <> Implement alpha registry workflow",
            "subject_ids": [
                "corpus-a:action-alpha",
                "corpus-b:action-beta",
            ],
            "suggested_canonical_subject": "implement-alpha-registry",
        }
        result = classify_item(item)
        assert result is not None
        self.assertEqual(result["decision"], "accepted")
        self.assertEqual(result["policy"], "action-title-overlap")

    def test_unresolved_title_overlap_accepted(self) -> None:
        item = {
            "review_type": "unresolved-merge",
            "title": "How should alpha governance evolve? <> How should alpha governance evolve over time?",
            "subject_ids": [
                "corpus-a:question-alpha",
                "corpus-b:question-beta",
            ],
            "suggested_canonical_subject": "alpha-governance-evolution",
        }
        result = classify_item(item)
        assert result is not None
        self.assertEqual(result["decision"], "accepted")
        self.assertEqual(result["policy"], "unresolved-title-overlap")

    def test_empty_subject_ids_returns_none(self) -> None:
        item = {"review_type": "entity-alias", "subject_ids": []}
        self.assertIsNone(classify_item(item))


class TriagePlanTests(unittest.TestCase):
    def test_build_and_execute_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_dir = project_root / "state"
            state_dir.mkdir()

            queue = {
                "items": [
                    {
                        "review_id": "review-1",
                        "review_type": "entity-alias",
                        "status": "open",
                        "subject_ids": ["a:entity-foo", "b:entity-foo"],
                        "suggested_canonical_subject": "foo",
                    },
                    {
                        "review_id": "review-2",
                        "review_type": "contradiction",
                        "status": "open",
                        "subject_ids": ["a:family-bar-12345678"],
                    },
                    {
                        "review_id": "review-3",
                        "review_type": "family-merge",
                        "status": "open",
                        "subject_ids": ["a:family-baz", "b:family-qux"],
                    },
                ]
            }
            (state_dir / "federated-review-queue.json").write_text(
                json.dumps(queue), encoding="utf-8"
            )
            (state_dir / "federated-canonical-decisions.json").write_text(
                json.dumps({}), encoding="utf-8"
            )

            plan = build_triage_plan(project_root)
            self.assertEqual(plan["total_open"], 3)
            self.assertEqual(plan["summary"]["accepted"], 1)
            self.assertEqual(plan["summary"]["deferred"], 1)
            self.assertEqual(plan["summary"]["manual"], 1)

            result = execute_triage_plan(project_root, plan)
            self.assertEqual(result["resolved"], 2)
            self.assertEqual(result["remaining_open"], 1)

    def test_execute_triage_plan_resolves_duplicate_review_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_dir = project_root / "state"
            state_dir.mkdir()

            queue = {
                "items": [
                    {
                        "review_id": "review-dup",
                        "review_type": "entity-alias",
                        "status": "open",
                        "subject_ids": ["a:entity-alpha", "b:entity-alpha"],
                        "suggested_canonical_subject": "entity-alpha",
                    },
                    {
                        "review_id": "review-dup",
                        "review_type": "entity-alias",
                        "status": "open",
                        "subject_ids": ["a:entity-alpha", "b:entity-alpha"],
                        "suggested_canonical_subject": "entity-alpha",
                    },
                ]
            }
            (state_dir / "federated-review-queue.json").write_text(
                json.dumps(queue), encoding="utf-8"
            )
            (state_dir / "federated-canonical-decisions.json").write_text(
                json.dumps({}), encoding="utf-8"
            )

            plan = build_triage_plan(project_root)
            result = execute_triage_plan(project_root, plan)
            updated_queue = json.loads(
                (state_dir / "federated-review-queue.json").read_text(encoding="utf-8")
            )

            self.assertEqual(result["resolved"], 2)
            self.assertEqual(result["errors"], [])
            self.assertEqual(result["remaining_open"], 0)
            self.assertTrue(all(item["status"] == "accepted" for item in updated_queue["items"]))


class EntityAliasReviewAssistTests(unittest.TestCase):
    def test_build_entity_alias_review_assist_groups_and_batches_open_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_dir = project_root / "state"
            state_dir.mkdir()
            queue = {
                "items": [
                    {
                        "review_id": "review-1",
                        "review_type": "entity-alias",
                        "status": "open",
                        "priority": "high",
                        "title": "Apps <> Websites",
                        "subject_ids": ["a:entity-apps", "b:entity-websites"],
                        "suggested_canonical_subject": "apps",
                        "score": 1.0,
                        "source_corpora": ["a", "b"],
                        "rationale": "High cross-corpus overlap between Apps",
                    },
                    {
                        "review_id": "review-2",
                        "review_type": "entity-alias",
                        "status": "open",
                        "priority": "high",
                        "title": "Apps <> Applications",
                        "subject_ids": ["c:entity-apps", "d:entity-applications"],
                        "suggested_canonical_subject": "apps",
                        "score": 0.82,
                        "source_corpora": ["c", "d"],
                        "rationale": "Potential broader alias",
                    },
                    {
                        "review_id": "review-3",
                        "review_type": "entity-alias",
                        "status": "open",
                        "priority": "medium",
                        "title": "Data Pipeline <> Pipeline Orchestration",
                        "subject_ids": [
                            "e:entity-data-pipeline",
                            "f:entity-pipeline-orchestration",
                        ],
                        "suggested_canonical_subject": "data-pipeline",
                        "score": 0.74,
                        "source_corpora": ["e", "f"],
                        "rationale": "Potential workflow alias",
                    },
                    {
                        "review_id": "review-4",
                        "review_type": "family-merge",
                        "status": "open",
                        "title": "Ignore <> Me",
                        "subject_ids": ["x:family-a", "y:family-b"],
                    },
                ]
            }
            (state_dir / "federated-review-queue.json").write_text(
                json.dumps(queue), encoding="utf-8"
            )

            payload = build_entity_alias_review_assist(project_root, batch_size=2)

            self.assertEqual(payload["review_type"], "entity-alias")
            self.assertEqual(payload["open_count"], 3)
            self.assertEqual(payload["group_count"], 2)
            self.assertEqual(payload["batch_count"], 2)
            self.assertEqual(payload["filters"]["source_pair"], "")
            self.assertEqual(payload["groups"][0]["anchor"], "apps")
            self.assertEqual(payload["groups"][0]["item_count"], 2)
            self.assertEqual(payload["groups"][0]["review_bucket"], "needs-context")
            self.assertIn("has-high-score-disjoint-pairs", payload["groups"][0]["signal_flags"])
            self.assertEqual(payload["groups"][0]["items"][0]["relation"], "disjoint")
            self.assertEqual(payload["groups"][1]["anchor"], "data pipeline")
            self.assertEqual(payload["groups"][1]["review_bucket"], "mixed-review")
            self.assertEqual(payload["relation_counts"]["disjoint"], 2)
            self.assertEqual(payload["relation_counts"]["partial-overlap"], 1)
            self.assertEqual(payload["batches"][0]["anchors"], ["apps"])

    def test_build_entity_alias_review_assist_applies_relation_source_and_anchor_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_dir = project_root / "state"
            state_dir.mkdir()
            queue = {
                "items": [
                    {
                        "review_id": "review-1",
                        "review_type": "entity-alias",
                        "status": "open",
                        "title": "Apps <> Websites",
                        "subject_ids": ["a:entity-apps", "b:entity-websites"],
                        "suggested_canonical_subject": "apps",
                        "score": 1.0,
                        "source_corpora": ["a", "b"],
                    },
                    {
                        "review_id": "review-2",
                        "review_type": "entity-alias",
                        "status": "open",
                        "title": "Apps <> Apps Platform",
                        "subject_ids": ["a:entity-apps", "b:entity-apps-platform"],
                        "suggested_canonical_subject": "apps",
                        "score": 0.82,
                        "source_corpora": ["a", "b"],
                    },
                    {
                        "review_id": "review-3",
                        "review_type": "entity-alias",
                        "status": "open",
                        "title": "Data Pipeline <> Pipeline Orchestration",
                        "subject_ids": ["c:entity-data-pipeline", "d:entity-pipeline-orchestration"],
                        "suggested_canonical_subject": "data-pipeline",
                        "score": 0.74,
                        "source_corpora": ["c", "d"],
                    },
                ]
            }
            (state_dir / "federated-review-queue.json").write_text(
                json.dumps(queue), encoding="utf-8"
            )

            payload = build_entity_alias_review_assist(
                project_root,
                batch_size=10,
                relation_filters=["substring"],
                source_pair="a <> b",
                anchor_contains="app",
            )

            self.assertEqual(payload["queue_open_count"], 3)
            self.assertEqual(payload["open_count"], 1)
            self.assertEqual(payload["group_count"], 1)
            self.assertEqual(payload["filters"]["relations"], ["substring"])
            self.assertEqual(payload["filters"]["source_pair"], "a <> b")
            self.assertEqual(payload["filters"]["anchor_contains"], "app")
            self.assertEqual(payload["groups"][0]["items"][0]["review_id"], "review-2")

    def test_render_entity_alias_review_assist_summarizes_batches_and_groups(self) -> None:
        text = render_entity_alias_review_assist(
            {
                "queue_open_count": 3,
                "filtered_open_count": 3,
                "open_count": 3,
                "group_count": 2,
                "batch_count": 1,
                "batch_size": 25,
                "filters": {
                    "relations": ["partial-overlap"],
                    "source_pair": "a <> b",
                    "anchor_contains": "apps",
                },
                "relation_counts": {"partial-overlap": 2, "disjoint": 1},
                "source_pair_counts": {"a <> b": 2},
                "batches": [
                    {
                        "batch_id": "entity-alias-batch-001",
                        "item_count": 3,
                        "group_count": 2,
                        "anchors": ["apps", "data pipeline"],
                    }
                ],
                "groups": [
                    {
                        "anchor": "apps",
                        "item_count": 2,
                        "max_score": 1.0,
                        "relation_counts": {"disjoint": 1, "partial-overlap": 1},
                        "review_bucket": "mixed-review",
                        "signal_flags": ["has-low-specificity-labels"],
                        "checklist": [
                            "Review the highest-scoring pair first and decide whether the shared terms imply identity or only topical overlap.",
                            "Verify labels are not headings, placeholders, fragments, or extraction residue.",
                        ],
                        "labels": ["Applications", "Apps", "Websites"],
                        "items": [
                            {
                                "title": "Apps <> Websites",
                                "relation": "disjoint",
                                "review_hint": "Queue score is high despite disjoint labels; inspect upstream context before accepting.",
                            }
                        ],
                    }
                ],
            },
            group_limit=1,
        )

        self.assertIn("Entity-alias review assist: 3 items (from 3 open)", text)
        self.assertIn("Filters: relations=partial-overlap", text)
        self.assertIn("entity-alias-batch-001  items=3  groups=2", text)
        self.assertIn("- apps  items=2  max_score=1.00", text)
        self.assertIn("bucket: mixed-review", text)
        self.assertIn("flags: has-low-specificity-labels", text)
        self.assertIn("example: Apps <> Websites [disjoint]", text)
        self.assertIn("review: Verify labels are not headings, placeholders, fragments, or extraction residue.", text)

    def test_select_entity_alias_review_assist_batch_reduces_payload_to_single_batch(self) -> None:
        payload = {
            "queue_open_count": 6,
            "filtered_open_count": 4,
            "open_count": 4,
            "group_count": 3,
            "batch_count": 2,
            "batch_size": 2,
            "filters": {"relations": ["disjoint"], "source_pair": "a <> b", "anchor_contains": ""},
            "relation_counts": {"disjoint": 4},
            "source_pair_counts": {"a <> b": 4},
            "priority_counts": {"high": 2, "medium": 2},
            "groups": [
                {
                    "anchor": "apps",
                    "item_count": 2,
                    "max_score": 1.0,
                        "relation_counts": {"disjoint": 2},
                        "source_pair_counts": {"a <> b": 2},
                        "labels": ["Apps", "Websites"],
                        "review_bucket": "needs-context",
                        "signal_flags": ["has-high-score-disjoint-pairs", "all-zero-overlap"],
                        "signal_counts": {
                            "disjoint_count": 2,
                            "zero_overlap_count": 2,
                            "high_score_count": 2,
                            "low_specificity_entry_count": 0,
                        },
                        "checklist": ["Inspect the highest-scoring pair before rejecting; upstream signal is stronger than lexical overlap."],
                        "example_review_ids": ["review-1", "review-2"],
                        "items": [
                            {
                                "review_id": "review-1",
                                "title": "Apps <> Websites",
                                "relation": "disjoint",
                            "score": 1.0,
                            "priority": "high",
                            "source_pair": "a <> b",
                        },
                        {
                            "review_id": "review-2",
                            "title": "Apps <> Portals",
                            "relation": "disjoint",
                            "score": 0.9,
                            "priority": "medium",
                            "source_pair": "a <> b",
                        },
                    ],
                },
                {
                    "anchor": "data pipeline",
                    "item_count": 1,
                    "max_score": 0.7,
                        "relation_counts": {"disjoint": 1},
                        "source_pair_counts": {"a <> b": 1},
                        "labels": ["Data Pipeline", "Workflow"],
                        "review_bucket": "likely-reject",
                        "signal_flags": ["all-zero-overlap"],
                        "signal_counts": {
                            "disjoint_count": 1,
                            "zero_overlap_count": 1,
                            "high_score_count": 0,
                            "low_specificity_entry_count": 0,
                        },
                        "checklist": ["Reject unless external context ties these labels to the same entity."],
                        "example_review_ids": ["review-3"],
                        "items": [
                            {
                                "review_id": "review-3",
                                "title": "Data Pipeline <> Workflow",
                                "relation": "disjoint",
                            "score": 0.7,
                            "priority": "high",
                            "source_pair": "a <> b",
                        }
                    ],
                },
                {
                    "anchor": "care",
                    "item_count": 1,
                    "max_score": 0.6,
                        "relation_counts": {"disjoint": 1},
                        "source_pair_counts": {"a <> b": 1},
                        "labels": ["Care", "Dog"],
                        "review_bucket": "likely-reject",
                        "signal_flags": ["all-zero-overlap"],
                        "signal_counts": {
                            "disjoint_count": 1,
                            "zero_overlap_count": 1,
                            "high_score_count": 0,
                            "low_specificity_entry_count": 0,
                        },
                        "checklist": ["Reject unless external context ties these labels to the same entity."],
                        "example_review_ids": ["review-4"],
                        "items": [
                            {
                                "review_id": "review-4",
                                "title": "Care <> Dog",
                                "relation": "disjoint",
                            "score": 0.6,
                            "priority": "medium",
                            "source_pair": "a <> b",
                        }
                    ],
                },
            ],
            "batches": [
                {
                    "batch_id": "entity-alias-batch-001",
                    "group_count": 2,
                    "item_count": 3,
                    "anchors": ["apps", "data pipeline"],
                    "groups": [],
                },
                {
                    "batch_id": "entity-alias-batch-002",
                    "group_count": 1,
                    "item_count": 1,
                    "anchors": ["care"],
                    "groups": [],
                },
            ],
        }
        payload["batches"][0]["groups"] = payload["groups"][:2]
        payload["batches"][1]["groups"] = payload["groups"][2:]

        selected = select_entity_alias_review_assist_batch(payload, "entity-alias-batch-001")

        self.assertEqual(selected["open_count"], 3)
        self.assertEqual(selected["group_count"], 2)
        self.assertEqual(selected["batch_count"], 1)
        self.assertEqual(selected["selection"]["batch_id"], "entity-alias-batch-001")
        self.assertEqual(selected["selection"]["batch_index"], 1)
        self.assertEqual(selected["selection"]["available_batch_count"], 2)
        self.assertEqual(selected["relation_counts"], {"disjoint": 3})
        self.assertEqual(selected["priority_counts"], {"high": 2, "medium": 1})
        self.assertEqual(selected["batches"][0]["anchors"], ["apps", "data pipeline"])
        self.assertEqual(selected["groups"][0]["review_bucket"], "needs-context")
        self.assertEqual(selected["groups"][0]["example_review_ids"], ["review-1", "review-2"])

    def test_select_entity_alias_review_assist_batch_rejects_unknown_batch(self) -> None:
        with self.assertRaises(ValueError):
            select_entity_alias_review_assist_batch(
                {
                    "batches": [{"batch_id": "entity-alias-batch-001"}],
                    "groups": [],
                },
                "entity-alias-batch-999",
            )

    def test_filter_entity_alias_review_assist_groups_keeps_only_requested_buckets(self) -> None:
        payload = {
            "queue_open_count": 10,
            "filtered_open_count": 6,
            "open_count": 6,
            "group_count": 3,
            "batch_count": 2,
            "batch_size": 3,
            "filters": {"relations": ["disjoint"], "source_pair": "", "anchor_contains": ""},
            "groups": [
                {
                    "anchor": "apps",
                    "item_count": 2,
                    "max_score": 1.0,
                    "relation_counts": {"disjoint": 2},
                    "source_pair_counts": {"a <> b": 2},
                    "labels": ["Apps", "Websites"],
                    "review_bucket": "needs-context",
                    "signal_flags": ["has-high-score-disjoint-pairs"],
                    "signal_counts": {"disjoint_count": 2},
                    "checklist": ["Inspect the highest-scoring pair before rejecting; upstream signal is stronger than lexical overlap."],
                    "example_review_ids": ["review-1"],
                    "items": [
                        {
                            "review_id": "review-1",
                            "title": "Apps <> Websites",
                            "relation": "disjoint",
                            "score": 1.0,
                            "priority": "high",
                            "source_pair": "a <> b",
                        },
                        {
                            "review_id": "review-2",
                            "title": "Apps <> Portals",
                            "relation": "disjoint",
                            "score": 0.9,
                            "priority": "medium",
                            "source_pair": "a <> b",
                        },
                    ],
                },
                {
                    "anchor": "care",
                    "item_count": 2,
                    "max_score": 0.7,
                    "relation_counts": {"disjoint": 2},
                    "source_pair_counts": {"a <> b": 2},
                    "labels": ["Care", "Dog"],
                    "review_bucket": "likely-reject",
                    "signal_flags": ["all-zero-overlap"],
                    "signal_counts": {"disjoint_count": 2},
                    "checklist": ["Reject unless external context ties these labels to the same entity."],
                    "example_review_ids": ["review-3"],
                    "items": [
                        {
                            "review_id": "review-3",
                            "title": "Care <> Dog",
                            "relation": "disjoint",
                            "score": 0.7,
                            "priority": "medium",
                            "source_pair": "a <> b",
                        },
                        {
                            "review_id": "review-4",
                            "title": "Care <> Cat",
                            "relation": "disjoint",
                            "score": 0.6,
                            "priority": "medium",
                            "source_pair": "a <> b",
                        },
                    ],
                },
                {
                    "anchor": "extension",
                    "item_count": 2,
                    "max_score": 0.8,
                    "relation_counts": {"disjoint": 2},
                    "source_pair_counts": {"a <> b": 2},
                    "labels": ["Extension", "Network"],
                    "review_bucket": "likely-reject",
                    "signal_flags": ["all-zero-overlap", "has-low-specificity-labels"],
                    "signal_counts": {"disjoint_count": 2},
                    "checklist": ["Reject unless external context ties these labels to the same entity."],
                    "example_review_ids": ["review-5"],
                    "items": [
                        {
                            "review_id": "review-5",
                            "title": "Extension <> Network",
                            "relation": "disjoint",
                            "score": 0.8,
                            "priority": "medium",
                            "source_pair": "a <> b",
                        },
                        {
                            "review_id": "review-6",
                            "title": "Extension <> Settings",
                            "relation": "disjoint",
                            "score": 0.7,
                            "priority": "medium",
                            "source_pair": "a <> b",
                        },
                    ],
                },
            ],
            "batches": [
                {
                    "batch_id": "entity-alias-batch-001",
                    "group_count": 2,
                    "item_count": 4,
                    "anchors": ["apps", "care"],
                    "groups": [],
                },
                {
                    "batch_id": "entity-alias-batch-002",
                    "group_count": 1,
                    "item_count": 2,
                    "anchors": ["extension"],
                    "groups": [],
                },
            ],
        }
        payload["batches"][0]["groups"] = payload["groups"][:2]
        payload["batches"][1]["groups"] = payload["groups"][2:]

        filtered = filter_entity_alias_review_assist_groups(
            payload,
            review_bucket_filters=["likely-reject"],
        )

        self.assertEqual(filtered["group_count"], 2)
        self.assertEqual(filtered["open_count"], 4)
        self.assertEqual(filtered["batch_count"], 2)
        self.assertEqual(filtered["group_filters"]["review_buckets"], ["likely-reject"])
        self.assertEqual([group["anchor"] for group in filtered["groups"]], ["care", "extension"])
        self.assertEqual(filtered["batches"][0]["anchors"], ["care"])

    def test_sample_entity_alias_review_assist_groups_spreads_across_batches(self) -> None:
        payload = {
            "queue_open_count": 20,
            "filtered_open_count": 8,
            "open_count": 8,
            "group_count": 4,
            "batch_count": 2,
            "batch_size": 4,
            "filters": {"relations": ["disjoint"], "source_pair": "", "anchor_contains": ""},
            "group_filters": {"review_buckets": ["likely-reject"]},
            "groups": [],
            "batches": [
                {
                    "batch_id": "entity-alias-batch-001",
                    "group_count": 2,
                    "item_count": 4,
                    "anchors": ["care", "extension"],
                    "groups": [
                        {
                            "anchor": "care",
                            "item_count": 2,
                            "max_score": 0.7,
                            "relation_counts": {"disjoint": 2},
                            "source_pair_counts": {"a <> b": 2},
                            "labels": ["Care", "Dog"],
                            "review_bucket": "likely-reject",
                            "signal_flags": ["all-zero-overlap"],
                            "signal_counts": {"disjoint_count": 2},
                            "checklist": ["Reject unless external context ties these labels to the same entity."],
                            "example_review_ids": ["review-1"],
                            "items": [
                                {
                                    "review_id": "review-1",
                                    "title": "Care <> Dog",
                                    "relation": "disjoint",
                                    "score": 0.7,
                                    "priority": "medium",
                                    "source_pair": "a <> b",
                                }
                            ],
                        },
                        {
                            "anchor": "extension",
                            "item_count": 2,
                            "max_score": 0.8,
                            "relation_counts": {"disjoint": 2},
                            "source_pair_counts": {"a <> b": 2},
                            "labels": ["Extension", "Network"],
                            "review_bucket": "likely-reject",
                            "signal_flags": ["all-zero-overlap"],
                            "signal_counts": {"disjoint_count": 2},
                            "checklist": ["Reject unless external context ties these labels to the same entity."],
                            "example_review_ids": ["review-2"],
                            "items": [
                                {
                                    "review_id": "review-2",
                                    "title": "Extension <> Network",
                                    "relation": "disjoint",
                                    "score": 0.8,
                                    "priority": "medium",
                                    "source_pair": "a <> b",
                                }
                            ],
                        },
                    ],
                },
                {
                    "batch_id": "entity-alias-batch-002",
                    "group_count": 2,
                    "item_count": 4,
                    "anchors": ["chapters", "von"],
                    "groups": [
                        {
                            "anchor": "chapters",
                            "item_count": 2,
                            "max_score": 0.83,
                            "relation_counts": {"disjoint": 2},
                            "source_pair_counts": {"a <> b": 2},
                            "labels": ["Chapters", "Missing"],
                            "review_bucket": "likely-reject",
                            "signal_flags": ["all-zero-overlap", "has-low-specificity-labels"],
                            "signal_counts": {"disjoint_count": 2},
                            "checklist": ["Reject unless external context ties these labels to the same entity."],
                            "example_review_ids": ["review-3"],
                            "items": [
                                {
                                    "review_id": "review-3",
                                    "title": "Chapters <> Missing",
                                    "relation": "disjoint",
                                    "score": 0.83,
                                    "priority": "medium",
                                    "source_pair": "a <> b",
                                }
                            ],
                        },
                        {
                            "anchor": "von",
                            "item_count": 2,
                            "max_score": 0.83,
                            "relation_counts": {"disjoint": 2},
                            "source_pair_counts": {"a <> b": 2},
                            "labels": ["Von", "Both"],
                            "review_bucket": "likely-reject",
                            "signal_flags": ["all-zero-overlap", "has-low-specificity-labels"],
                            "signal_counts": {"disjoint_count": 2},
                            "checklist": ["Reject unless external context ties these labels to the same entity."],
                            "example_review_ids": ["review-4"],
                            "items": [
                                {
                                    "review_id": "review-4",
                                    "title": "Von <> Both",
                                    "relation": "disjoint",
                                    "score": 0.83,
                                    "priority": "medium",
                                    "source_pair": "a <> b",
                                }
                            ],
                        },
                    ],
                },
            ],
        }
        payload["groups"] = payload["batches"][0]["groups"] + payload["batches"][1]["groups"]

        sampled = sample_entity_alias_review_assist_groups(
            payload,
            sample_groups=3,
            sample_batches=2,
        )

        self.assertEqual(sampled["group_count"], 3)
        self.assertEqual(sampled["sample"]["selected_group_count"], 3)
        self.assertEqual(sampled["sample"]["candidate_group_count"], 4)
        self.assertEqual(sampled["sample"]["candidate_batch_count"], 2)
        self.assertEqual([group["anchor"] for group in sampled["groups"]], ["care", "chapters", "extension"])
        self.assertEqual(sampled["batches"][0]["anchors"], ["care", "extension"])
        self.assertEqual(sampled["batches"][1]["anchors"], ["chapters"])

    def test_sample_entity_alias_review_assist_groups_respects_batch_offset(self) -> None:
        payload = {
            "queue_open_count": 30,
            "filtered_open_count": 6,
            "open_count": 6,
            "group_count": 6,
            "batch_count": 3,
            "batch_size": 2,
            "filters": {"relations": ["disjoint"], "source_pair": "", "anchor_contains": ""},
            "groups": [],
            "batches": [
                {
                    "batch_id": "entity-alias-batch-001",
                    "group_count": 2,
                    "item_count": 2,
                    "anchors": ["a", "b"],
                    "groups": [
                        {
                            "anchor": "a",
                            "item_count": 1,
                            "max_score": 0.9,
                            "relation_counts": {"disjoint": 1},
                            "source_pair_counts": {"x <> y": 1},
                            "labels": ["A"],
                            "review_bucket": "likely-reject",
                            "signal_flags": ["all-zero-overlap"],
                            "signal_counts": {"disjoint_count": 1},
                            "checklist": ["Reject unless external context ties these labels to the same entity."],
                            "example_review_ids": ["review-a"],
                            "items": [{"review_id": "review-a", "title": "A <> Z", "relation": "disjoint", "score": 0.9, "priority": "medium", "source_pair": "x <> y"}],
                        },
                        {
                            "anchor": "b",
                            "item_count": 1,
                            "max_score": 0.8,
                            "relation_counts": {"disjoint": 1},
                            "source_pair_counts": {"x <> y": 1},
                            "labels": ["B"],
                            "review_bucket": "likely-reject",
                            "signal_flags": ["all-zero-overlap"],
                            "signal_counts": {"disjoint_count": 1},
                            "checklist": ["Reject unless external context ties these labels to the same entity."],
                            "example_review_ids": ["review-b"],
                            "items": [{"review_id": "review-b", "title": "B <> Z", "relation": "disjoint", "score": 0.8, "priority": "medium", "source_pair": "x <> y"}],
                        },
                    ],
                },
                {
                    "batch_id": "entity-alias-batch-002",
                    "group_count": 2,
                    "item_count": 2,
                    "anchors": ["c", "d"],
                    "groups": [
                        {
                            "anchor": "c",
                            "item_count": 1,
                            "max_score": 0.7,
                            "relation_counts": {"disjoint": 1},
                            "source_pair_counts": {"x <> y": 1},
                            "labels": ["C"],
                            "review_bucket": "likely-reject",
                            "signal_flags": ["all-zero-overlap"],
                            "signal_counts": {"disjoint_count": 1},
                            "checklist": ["Reject unless external context ties these labels to the same entity."],
                            "example_review_ids": ["review-c"],
                            "items": [{"review_id": "review-c", "title": "C <> Z", "relation": "disjoint", "score": 0.7, "priority": "medium", "source_pair": "x <> y"}],
                        },
                        {
                            "anchor": "d",
                            "item_count": 1,
                            "max_score": 0.6,
                            "relation_counts": {"disjoint": 1},
                            "source_pair_counts": {"x <> y": 1},
                            "labels": ["D"],
                            "review_bucket": "likely-reject",
                            "signal_flags": ["all-zero-overlap"],
                            "signal_counts": {"disjoint_count": 1},
                            "checklist": ["Reject unless external context ties these labels to the same entity."],
                            "example_review_ids": ["review-d"],
                            "items": [{"review_id": "review-d", "title": "D <> Z", "relation": "disjoint", "score": 0.6, "priority": "medium", "source_pair": "x <> y"}],
                        },
                    ],
                },
                {
                    "batch_id": "entity-alias-batch-003",
                    "group_count": 2,
                    "item_count": 2,
                    "anchors": ["e", "f"],
                    "groups": [
                        {
                            "anchor": "e",
                            "item_count": 1,
                            "max_score": 0.5,
                            "relation_counts": {"disjoint": 1},
                            "source_pair_counts": {"x <> y": 1},
                            "labels": ["E"],
                            "review_bucket": "likely-reject",
                            "signal_flags": ["all-zero-overlap"],
                            "signal_counts": {"disjoint_count": 1},
                            "checklist": ["Reject unless external context ties these labels to the same entity."],
                            "example_review_ids": ["review-e"],
                            "items": [{"review_id": "review-e", "title": "E <> Z", "relation": "disjoint", "score": 0.5, "priority": "medium", "source_pair": "x <> y"}],
                        },
                        {
                            "anchor": "f",
                            "item_count": 1,
                            "max_score": 0.4,
                            "relation_counts": {"disjoint": 1},
                            "source_pair_counts": {"x <> y": 1},
                            "labels": ["F"],
                            "review_bucket": "likely-reject",
                            "signal_flags": ["all-zero-overlap"],
                            "signal_counts": {"disjoint_count": 1},
                            "checklist": ["Reject unless external context ties these labels to the same entity."],
                            "example_review_ids": ["review-f"],
                            "items": [{"review_id": "review-f", "title": "F <> Z", "relation": "disjoint", "score": 0.4, "priority": "medium", "source_pair": "x <> y"}],
                        },
                    ],
                },
            ],
        }
        payload["groups"] = [group for batch in payload["batches"] for group in batch["groups"]]

        sampled = sample_entity_alias_review_assist_groups(
            payload,
            sample_groups=2,
            sample_batches=1,
            batch_offset=1,
        )

        self.assertEqual(sampled["sample"]["requested_batch_offset"], 1)
        self.assertEqual(sampled["sample"]["candidate_batch_count"], 1)
        self.assertEqual([group["anchor"] for group in sampled["groups"]], ["c", "d"])

    def test_write_entity_alias_review_assist_artifacts_writes_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            payload = {
                "queue_open_count": 3,
                "filtered_open_count": 1,
                "open_count": 1,
                "group_count": 1,
                "batch_count": 1,
                "batch_size": 25,
                "filters": {"relations": [], "source_pair": "", "anchor_contains": ""},
                "relation_counts": {"partial-overlap": 1},
                "source_pair_counts": {"a <> b": 1},
                "priority_counts": {"high": 1},
                "groups": [
                    {
                        "anchor": "apps",
                        "item_count": 1,
                        "max_score": 0.82,
                        "relation_counts": {"partial-overlap": 1},
                        "source_pair_counts": {"a <> b": 1},
                        "labels": ["Apps", "Applications"],
                        "items": [
                            {
                                "title": "Apps <> Applications",
                                "relation": "partial-overlap",
                                "review_hint": "Some lexical overlap exists; verify whether shared terms indicate the same entity or a topical neighbor.",
                            }
                        ],
                    }
                ],
                "batches": [
                    {
                        "batch_id": "entity-alias-batch-001",
                        "group_count": 1,
                        "item_count": 1,
                        "anchors": ["apps"],
                        "groups": [],
                    }
                ],
            }

            artifacts = write_entity_alias_review_assist_artifacts(project_root, payload)

            stored_payload = json.loads(Path(artifacts["latest_json_path"]).read_text(encoding="utf-8"))
            latest_markdown = Path(artifacts["latest_markdown_path"]).read_text(encoding="utf-8")
            dated_markdown = Path(artifacts["report_path"]).read_text(encoding="utf-8")

            self.assertEqual(stored_payload["open_count"], 1)
            self.assertIn("Entity-alias review assist: 1 items", latest_markdown)
            self.assertEqual(latest_markdown, dated_markdown)

    def test_write_entity_alias_review_assist_artifacts_writes_batch_specific_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            payload = {
                "queue_open_count": 6,
                "filtered_open_count": 4,
                "open_count": 3,
                "group_count": 2,
                "batch_count": 1,
                "batch_size": 25,
                "filters": {"relations": ["disjoint"], "source_pair": "", "anchor_contains": ""},
                "selection": {
                    "batch_id": "entity-alias-batch-001",
                    "batch_index": 1,
                    "available_batch_count": 2,
                },
                "relation_counts": {"disjoint": 3},
                "source_pair_counts": {"a <> b": 3},
                "priority_counts": {"high": 2, "medium": 1},
                "groups": [
                    {
                        "anchor": "apps",
                        "item_count": 3,
                        "max_score": 1.0,
                        "relation_counts": {"disjoint": 3},
                        "source_pair_counts": {"a <> b": 3},
                        "labels": ["Apps", "Websites"],
                        "review_bucket": "needs-context",
                        "signal_flags": ["has-high-score-disjoint-pairs", "all-zero-overlap"],
                        "signal_counts": {
                            "disjoint_count": 3,
                            "zero_overlap_count": 3,
                            "high_score_count": 2,
                            "low_specificity_entry_count": 0,
                        },
                        "checklist": ["Inspect the highest-scoring pair before rejecting; upstream signal is stronger than lexical overlap."],
                        "example_review_ids": ["review-1"],
                        "items": [
                            {
                                "review_id": "review-1",
                                "title": "Apps <> Websites",
                                "relation": "disjoint",
                                "score": 1.0,
                                "review_hint": "Queue score is high despite disjoint labels; inspect upstream context before accepting.",
                            }
                        ],
                    }
                ],
                "batches": [
                    {
                        "batch_id": "entity-alias-batch-001",
                        "group_count": 1,
                        "item_count": 3,
                        "anchors": ["apps"],
                        "groups": [],
                    }
                ],
            }
            payload["batches"][0]["groups"] = payload["groups"]

            artifacts = write_entity_alias_review_assist_artifacts(project_root, payload)

            self.assertEqual(
                set(artifacts),
                {
                    "batch_json_path",
                    "batch_markdown_path",
                    "batch_checklist_path",
                    "batch_report_path",
                },
            )
            self.assertTrue(Path(artifacts["batch_json_path"]).exists())
            markdown = Path(artifacts["batch_markdown_path"]).read_text(encoding="utf-8")
            checklist = Path(artifacts["batch_checklist_path"]).read_text(encoding="utf-8")
            self.assertIn("Selected batch: entity-alias-batch-001 (1/2)", markdown)
            self.assertIn("from 4 filtered / 6 open", markdown)
            self.assertIn("# Entity-alias review checklist: entity-alias-batch-001", checklist)
            self.assertIn("- Bucket: needs-context", checklist)
            self.assertIn("- Review: Inspect the highest-scoring pair before rejecting; upstream signal is stronger than lexical overlap.", checklist)

    def test_render_entity_alias_review_checklist_formats_group_guidance(self) -> None:
        text = render_entity_alias_review_checklist(
            {
                "queue_open_count": 6,
                "filtered_open_count": 4,
                "open_count": 3,
                "group_count": 1,
                "selection": {
                    "batch_id": "entity-alias-batch-001",
                    "batch_index": 1,
                    "available_batch_count": 2,
                },
                "groups": [
                    {
                        "anchor": "apps",
                        "review_bucket": "needs-context",
                        "signal_flags": ["has-high-score-disjoint-pairs", "all-zero-overlap"],
                        "labels": ["Apps", "Websites"],
                        "example_review_ids": ["review-1", "review-2"],
                        "items": [
                            {
                                "title": "Apps <> Websites",
                                "relation": "disjoint",
                                "score": 1.0,
                            }
                        ],
                        "checklist": [
                            "Inspect the highest-scoring pair before rejecting; upstream signal is stronger than lexical overlap."
                        ],
                    }
                ],
            }
        )

        self.assertIn("# Entity-alias review checklist: entity-alias-batch-001", text)
        self.assertIn("- Scope: 4 filtered / 6 open", text)
        self.assertIn("## 1. apps", text)
        self.assertIn("- Flags: has-high-score-disjoint-pairs, all-zero-overlap", text)
        self.assertIn("- Example: Apps <> Websites [disjoint] score=1.00", text)

    def test_render_entity_alias_review_sample_formats_sampling_metadata(self) -> None:
        text = render_entity_alias_review_sample(
            {
                "queue_open_count": 406,
                "filtered_open_count": 400,
                "open_count": 2,
                "group_count": 2,
                "group_filters": {"review_buckets": ["likely-reject"]},
                "sample": {
                    "candidate_group_count": 20,
                    "candidate_batch_count": 4,
                    "selected_group_count": 2,
                },
                "groups": [
                    {
                        "anchor": "chapters",
                        "review_bucket": "likely-reject",
                        "signal_flags": ["all-zero-overlap", "has-low-specificity-labels"],
                        "labels": ["Chapters", "Missing"],
                        "example_review_ids": ["review-1", "review-2"],
                        "items": [
                            {
                                "title": "Chapters <> Missing",
                                "relation": "disjoint",
                                "score": 0.83,
                            }
                        ],
                        "checklist": ["Reject unless external context ties these labels to the same entity."],
                    },
                    {
                        "anchor": "von",
                        "review_bucket": "likely-reject",
                        "signal_flags": ["all-zero-overlap"],
                        "labels": ["Von", "Both"],
                        "example_review_ids": ["review-3"],
                        "items": [
                            {
                                "title": "Von <> Both",
                                "relation": "disjoint",
                                "score": 0.71,
                            }
                        ],
                        "checklist": ["Reject unless external context ties these labels to the same entity."],
                    },
                ],
            }
        )

        self.assertIn("# Entity-alias review sample", text)
        self.assertIn("- Candidate groups: 20", text)
        self.assertIn("- Buckets: likely-reject", text)
        self.assertIn("## Sample 1: chapters", text)
        self.assertIn("- Proposed outcome: reject", text)

    def test_write_entity_alias_review_sample_artifacts_writes_latest_and_session_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            payload = {
                "queue_open_count": 406,
                "filtered_open_count": 400,
                "open_count": 2,
                "group_count": 2,
                "group_filters": {"review_buckets": ["likely-reject"]},
                "sample": {
                    "candidate_group_count": 20,
                    "candidate_batch_count": 4,
                    "selected_group_count": 2,
                },
                "groups": [
                    {
                        "anchor": "chapters",
                        "review_bucket": "likely-reject",
                        "signal_flags": ["all-zero-overlap"],
                        "labels": ["Chapters", "Missing"],
                        "example_review_ids": ["review-1"],
                        "items": [
                            {
                                "title": "Chapters <> Missing",
                                "relation": "disjoint",
                                "score": 0.83,
                            }
                        ],
                        "checklist": ["Reject unless external context ties these labels to the same entity."],
                    }
                ],
                "batches": [],
            }

            artifacts = write_entity_alias_review_sample_artifacts(project_root, payload)

            self.assertEqual(
                set(artifacts),
                {
                    "latest_json_path",
                    "latest_markdown_path",
                    "session_json_path",
                    "session_markdown_path",
                },
            )
            self.assertTrue(Path(artifacts["latest_json_path"]).exists())
            self.assertTrue(Path(artifacts["session_json_path"]).exists())
            latest_markdown = Path(artifacts["latest_markdown_path"]).read_text(encoding="utf-8")
            self.assertIn("# Entity-alias review sample", latest_markdown)
            self.assertIn("- Proposed outcome: reject", latest_markdown)

    def test_parse_entity_alias_review_sample_markdown_extracts_manual_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sample.md"
            path.write_text(
                "\n".join(
                    [
                        "# Entity-alias review sample",
                        "",
                        "- Items: 4",
                        "- Groups: 2",
                        "- Scope: 400 filtered / 406 open",
                        "- Candidate groups: 20",
                        "- Candidate batches: 4",
                        "- Sampled groups: 2",
                        "- Buckets: likely-reject",
                        "",
                        "## Sample 1: chapters",
                        "- Bucket: likely-reject",
                        "- Review IDs: review-1, review-2",
                        "- Example: Chapters <> Missing [disjoint] score=0.83",
                        "- Proposed outcome: reject",
                        "- Manual outcome: reject",
                        "- Notes: clear heading residue",
                        "- Review: Reject unless external context ties these labels to the same entity.",
                        "",
                        "## Sample 2: extension",
                        "- Bucket: likely-reject",
                        "- Review IDs: review-3",
                        "- Example: Extension <> Network [disjoint] score=0.80",
                        "- Proposed outcome: reject",
                        "- Manual outcome: keep",
                        "- Notes: local context linked them",
                    ]
                ),
                encoding="utf-8",
            )

            parsed = parse_entity_alias_review_sample_markdown(path)

            self.assertEqual(parsed["metadata"]["scope"], "400 filtered / 406 open")
            self.assertEqual(len(parsed["samples"]), 2)
            self.assertEqual(parsed["samples"][0]["manual_outcome"], "reject")
            self.assertEqual(parsed["samples"][0]["notes"], "clear heading residue")
            self.assertEqual(parsed["samples"][1]["manual_outcome"], "keep")

    def test_summarize_entity_alias_review_sample_computes_precision(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sample.md"
            path.write_text(
                "\n".join(
                    [
                        "# Entity-alias review sample",
                        "",
                        "- Scope: 400 filtered / 406 open",
                        "- Buckets: likely-reject",
                        "",
                        "## Sample 1: chapters",
                        "- Bucket: likely-reject",
                        "- Proposed outcome: reject",
                        "- Manual outcome: reject",
                        "",
                        "## Sample 2: extension",
                        "- Bucket: likely-reject",
                        "- Proposed outcome: reject",
                        "- Manual outcome: keep",
                        "",
                        "## Sample 3: checklist",
                        "- Bucket: likely-reject",
                        "- Proposed outcome: reject",
                        "- Manual outcome: needs-context",
                        "",
                        "## Sample 4: family",
                        "- Bucket: likely-reject",
                        "- Proposed outcome: reject",
                        "- Manual outcome: ",
                    ]
                ),
                encoding="utf-8",
            )

            summary = summarize_entity_alias_review_sample(path)

            self.assertEqual(summary["total_samples"], 4)
            self.assertEqual(summary["adjudicated_count"], 3)
            self.assertEqual(summary["decisive_count"], 2)
            self.assertEqual(summary["confirmed_reject_count"], 1)
            self.assertEqual(summary["false_positive_count"], 1)
            self.assertEqual(summary["needs_context_count"], 1)
            self.assertEqual(summary["pending_count"], 1)
            self.assertEqual(summary["reject_precision"], 0.5)
            self.assertEqual(summary["bucket_summary"]["likely-reject"]["reject_precision"], 0.5)

    def test_render_entity_alias_review_sample_summary_formats_metrics(self) -> None:
        text = render_entity_alias_review_sample_summary(
            {
                "source_path": "/tmp/sample.md",
                "metadata": {"scope": "400 filtered / 406 open", "buckets": "likely-reject"},
                "total_samples": 4,
                "adjudicated_count": 3,
                "decisive_count": 2,
                "confirmed_reject_count": 1,
                "false_positive_count": 1,
                "needs_context_count": 1,
                "pending_count": 1,
                "reject_precision": 0.5,
                "bucket_summary": {"likely-reject": {"group_count": 4}},
                "samples": [
                    {
                        "anchor": "chapters",
                        "bucket": "likely-reject",
                        "proposed_outcome": "reject",
                        "manual_outcome": "reject",
                        "notes": "clear heading residue",
                    }
                ],
            }
        )

        self.assertIn("Entity-alias review sample summary", text)
        self.assertIn("Reject precision: 50.00%", text)
        self.assertIn("Packet: scope=400 filtered / 406 open  buckets=likely-reject", text)
        self.assertIn("- chapters  bucket=likely-reject  proposed=reject  manual=reject", text)
        self.assertIn("notes: clear heading residue", text)

    def test_write_entity_alias_review_sample_summary_artifacts_writes_latest_and_session_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            payload = {
                "source_path": "/tmp/sample.md",
                "metadata": {"scope": "400 filtered / 406 open", "buckets": "likely-reject"},
                "total_samples": 4,
                "adjudicated_count": 3,
                "decisive_count": 2,
                "confirmed_reject_count": 1,
                "false_positive_count": 1,
                "needs_context_count": 1,
                "pending_count": 1,
                "reject_precision": 0.5,
                "bucket_summary": {"likely-reject": {"group_count": 4}},
                "samples": [],
            }

            artifacts = write_entity_alias_review_sample_summary_artifacts(project_root, payload)

            self.assertEqual(
                set(artifacts),
                {
                    "latest_json_path",
                    "latest_markdown_path",
                    "session_json_path",
                    "session_markdown_path",
                },
            )
            self.assertTrue(Path(artifacts["latest_json_path"]).exists())
            markdown = Path(artifacts["latest_markdown_path"]).read_text(encoding="utf-8")
            self.assertIn("Reject precision: 50.00%", markdown)

    def test_propose_entity_alias_review_sample_assigns_assistant_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sample.md"
            path.write_text(
                "\n".join(
                    [
                        "# Entity-alias review sample",
                        "",
                        "- Scope: 400 filtered / 406 open",
                        "- Buckets: likely-reject",
                        "",
                        "## Sample 1: chapters",
                        "- Bucket: likely-reject",
                        "- Flags: has-low-specificity-labels, all-zero-overlap",
                        "- Proposed outcome: reject",
                        "- Manual outcome: ",
                        "",
                        "## Sample 2: checklist",
                        "- Bucket: likely-reject",
                        "- Flags: has-high-score-disjoint-pairs, all-zero-overlap",
                        "- Proposed outcome: reject",
                        "- Manual outcome: ",
                        "",
                        "## Sample 3: alias",
                        "- Bucket: alias-check",
                        "- Proposed outcome: reject",
                        "- Manual outcome: ",
                    ]
                ),
                encoding="utf-8",
            )

            proposal = propose_entity_alias_review_sample(path)

            self.assertEqual(proposal["total_samples"], 3)
            self.assertEqual(proposal["assistant_outcome_counts"]["reject"], 1)
            self.assertEqual(proposal["assistant_outcome_counts"]["needs-context"], 1)
            self.assertEqual(proposal["assistant_outcome_counts"]["keep"], 1)
            self.assertEqual(proposal["samples"][0]["assistant_outcome"], "reject")
            self.assertEqual(proposal["samples"][0]["assistant_confidence"], "high")
            self.assertEqual(proposal["samples"][1]["assistant_outcome"], "needs-context")
            self.assertEqual(proposal["samples"][2]["assistant_outcome"], "keep")

    def test_render_entity_alias_review_sample_proposal_formats_assistant_decisions(self) -> None:
        text = render_entity_alias_review_sample_proposal(
            {
                "source_path": "/tmp/sample.md",
                "metadata": {
                    "scope": "400 filtered / 406 open",
                    "buckets": "likely-reject",
                    "sampled_groups": "12",
                },
                "total_samples": 2,
                "assistant_outcome_counts": {"reject": 1, "needs-context": 1},
                "assistant_confidence_counts": {"high": 1, "medium": 1},
                "samples": [
                    {
                        "anchor": "chapters",
                        "bucket": "likely-reject",
                        "assistant_outcome": "reject",
                        "assistant_confidence": "high",
                        "assistant_rationale": [
                            "Group is already classified as likely-reject.",
                            "Lexical overlap is absent across the sampled pairs.",
                        ],
                    },
                    {
                        "anchor": "checklist",
                        "bucket": "likely-reject",
                        "assistant_outcome": "needs-context",
                        "assistant_confidence": "medium",
                        "assistant_rationale": [
                            "Queue score is still high, so contextual inspection remains warranted."
                        ],
                        "manual_outcome": "keep",
                    },
                ],
            }
        )

        self.assertIn("Entity-alias review sample proposal", text)
        self.assertIn("Assistant outcomes: needs-context=1, reject=1", text)
        self.assertIn("- chapters  bucket=likely-reject  assistant=reject  confidence=high", text)
        self.assertIn("rationale: Lexical overlap is absent across the sampled pairs.", text)
        self.assertIn("manual: keep", text)

    def test_write_entity_alias_review_sample_proposal_artifacts_writes_latest_and_session_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            payload = {
                "source_path": "/tmp/sample.md",
                "metadata": {"scope": "400 filtered / 406 open", "buckets": "likely-reject"},
                "total_samples": 2,
                "assistant_outcome_counts": {"reject": 2},
                "assistant_confidence_counts": {"high": 2},
                "samples": [
                    {
                        "anchor": "chapters",
                        "bucket": "likely-reject",
                        "assistant_outcome": "reject",
                        "assistant_confidence": "high",
                        "assistant_rationale": ["Group is already classified as likely-reject."],
                    }
                ],
            }

            artifacts = write_entity_alias_review_sample_proposal_artifacts(project_root, payload)

            self.assertEqual(
                set(artifacts),
                {
                    "latest_json_path",
                    "latest_markdown_path",
                    "session_json_path",
                    "session_markdown_path",
                },
            )
            self.assertTrue(Path(artifacts["latest_json_path"]).exists())
            markdown = Path(artifacts["latest_markdown_path"]).read_text(encoding="utf-8")
            self.assertIn("Entity-alias review sample proposal", markdown)
            self.assertIn("assistant=reject", markdown)

    def test_compare_entity_alias_review_sample_to_proposal_computes_agreement_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            sample_path = tmp / "sample.md"
            proposal_path = tmp / "proposal.json"
            sample_path.write_text(
                "\n".join(
                    [
                        "# Entity-alias review sample",
                        "",
                        "## Sample 1: chapters",
                        "- Bucket: likely-reject",
                        "- Review IDs: review-1, review-2",
                        "- Proposed outcome: reject",
                        "- Manual outcome: reject",
                        "",
                        "## Sample 2: extension",
                        "- Bucket: likely-reject",
                        "- Review IDs: review-3",
                        "- Proposed outcome: reject",
                        "- Manual outcome: keep",
                        "- Notes: contextual identity was stronger than lexical mismatch",
                        "",
                        "## Sample 3: alias",
                        "- Bucket: alias-check",
                        "- Review IDs: review-4",
                        "- Proposed outcome: reject",
                        "- Manual outcome: needs-context",
                    ]
                ),
                encoding="utf-8",
            )
            proposal_path.write_text(
                json.dumps(
                    {
                        "samples": [
                            {
                                "anchor": "chapters",
                                "review_ids": ["review-1", "review-2"],
                                "assistant_outcome": "reject",
                                "assistant_confidence": "high",
                                "assistant_rationale": ["Group is already classified as likely-reject."],
                            },
                            {
                                "anchor": "extension",
                                "review_ids": ["review-3"],
                                "assistant_outcome": "reject",
                                "assistant_confidence": "high",
                                "assistant_rationale": ["Lexical overlap is absent across the sampled pairs."],
                            },
                            {
                                "anchor": "alias",
                                "review_ids": ["review-4"],
                                "assistant_outcome": "keep",
                                "assistant_confidence": "medium",
                                "assistant_rationale": ["Lexical overlap is strong enough that rejection is not the safe default."],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            comparison = compare_entity_alias_review_sample_to_proposal(sample_path, proposal_path)

            self.assertEqual(comparison["matched_samples"], 3)
            self.assertEqual(comparison["adjudicated_count"], 3)
            self.assertEqual(comparison["comparable_count"], 3)
            self.assertEqual(comparison["agreement_count"], 1)
            self.assertEqual(comparison["disagreement_count"], 2)
            self.assertEqual(comparison["proposal_reject_count"], 2)
            self.assertEqual(comparison["proposal_reject_hits"], 1)
            self.assertEqual(comparison["proposal_reject_false_positives"], 1)
            self.assertEqual(comparison["proposal_reject_precision"], 0.5)
            self.assertEqual(comparison["agreement_rate"], 0.3333)
            self.assertEqual(comparison["confidence_summary"]["high"]["reject_precision"], 0.5)
            self.assertEqual(comparison["disagreements"][0]["anchor"], "extension")

    def test_compare_entity_alias_review_sample_to_proposal_leaves_precision_null_without_adjudication(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            sample_path = tmp / "sample.md"
            proposal_path = tmp / "proposal.json"
            sample_path.write_text(
                "\n".join(
                    [
                        "# Entity-alias review sample",
                        "",
                        "## Sample 1: chapters",
                        "- Bucket: likely-reject",
                        "- Review IDs: review-1",
                        "- Proposed outcome: reject",
                        "- Manual outcome: ",
                    ]
                ),
                encoding="utf-8",
            )
            proposal_path.write_text(
                json.dumps(
                    {
                        "samples": [
                            {
                                "anchor": "chapters",
                                "review_ids": ["review-1"],
                                "assistant_outcome": "reject",
                                "assistant_confidence": "high",
                                "assistant_rationale": ["Group is already classified as likely-reject."],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            comparison = compare_entity_alias_review_sample_to_proposal(sample_path, proposal_path)

            self.assertEqual(comparison["matched_samples"], 1)
            self.assertEqual(comparison["adjudicated_count"], 0)
            self.assertIsNone(comparison["proposal_reject_precision"])
            self.assertIsNone(comparison["confidence_summary"]["high"]["reject_precision"])

    def test_render_entity_alias_review_sample_comparison_formats_metrics(self) -> None:
        text = render_entity_alias_review_sample_comparison(
            {
                "sample_path": "/tmp/sample.md",
                "proposal_path": "/tmp/proposal.json",
                "matched_samples": 3,
                "adjudicated_count": 3,
                "comparable_count": 3,
                "agreement_count": 2,
                "disagreement_count": 1,
                "agreement_rate": 0.6667,
                "proposal_reject_count": 2,
                "proposal_reject_hits": 1,
                "proposal_reject_false_positives": 1,
                "proposal_reject_precision": 0.5,
                "confidence_summary": {"high": {"count": 2}, "medium": {"count": 1}},
                "disagreements": [
                    {
                        "anchor": "extension",
                        "manual_outcome": "keep",
                        "assistant_outcome": "reject",
                        "assistant_confidence": "high",
                        "notes": "context overruled lexical mismatch",
                        "assistant_rationale": ["Lexical overlap is absent across the sampled pairs."],
                    }
                ],
            }
        )

        self.assertIn("Entity-alias review sample comparison", text)
        self.assertIn("Agreement: 2  Disagreement: 1  Agreement rate: 66.67%", text)
        self.assertIn("Proposal reject precision: 50.00%", text)
        self.assertIn("- extension  manual=keep  assistant=reject  confidence=high", text)
        self.assertIn("notes: context overruled lexical mismatch", text)

    def test_write_entity_alias_review_sample_comparison_artifacts_writes_latest_and_session_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            payload = {
                "sample_path": "/tmp/sample.md",
                "proposal_path": "/tmp/proposal.json",
                "matched_samples": 3,
                "adjudicated_count": 3,
                "comparable_count": 3,
                "agreement_count": 2,
                "disagreement_count": 1,
                "agreement_rate": 0.6667,
                "proposal_reject_count": 2,
                "proposal_reject_hits": 1,
                "proposal_reject_false_positives": 1,
                "proposal_reject_precision": 0.5,
                "confidence_summary": {"high": {"count": 2}},
                "disagreements": [],
            }

            artifacts = write_entity_alias_review_sample_comparison_artifacts(project_root, payload)

            self.assertEqual(
                set(artifacts),
                {
                    "latest_json_path",
                    "latest_markdown_path",
                    "session_json_path",
                    "session_markdown_path",
                },
            )
            self.assertTrue(Path(artifacts["latest_json_path"]).exists())
            markdown = Path(artifacts["latest_markdown_path"]).read_text(encoding="utf-8")
            self.assertIn("Entity-alias review sample comparison", markdown)
            self.assertIn("Proposal reject precision: 50.00%", markdown)


if __name__ == "__main__":
    unittest.main()
