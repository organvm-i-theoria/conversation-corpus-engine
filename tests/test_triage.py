from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from conversation_corpus_engine.triage import (
    _strip_uuid_suffix,
    build_triage_plan,
    classify_item,
    execute_triage_plan,
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


if __name__ == "__main__":
    unittest.main()
