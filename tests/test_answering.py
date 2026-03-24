from __future__ import annotations

import unittest

from conversation_corpus_engine.answering import (
    rerank_family_hits,
    tokenize,
)


class RerankFamilyHitsTests(unittest.TestCase):
    def test_matched_bonus_exceeds_high_base_scores(self) -> None:
        """Matched families must outrank high-scoring unmatched families."""
        family_hits = [
            {
                "family_id": "family-irrelevant-high-score",
                "title": "Irrelevant Document",
                "text": "lots of keywords",
                "score": 10.0,
                "diagnostics": {},
                "kind": "family_brief",
                "doc_id": "brief:irrelevant",
            },
            {
                "family_id": "family-target-match",
                "title": "Hellraiser Puzzle Box 3D Model",
                "text": "hellraiser puzzle box",
                "score": 0.0,
                "diagnostics": {},
                "kind": "family_brief",
                "doc_id": "brief:target",
            },
        ]
        matched_ids = {"family-target-match"}
        query = "Hellraiser Puzzle Box 3D Model"
        raw_tokens = tokenize(query)

        reranked = rerank_family_hits(query, raw_tokens, family_hits, matched_ids)

        self.assertEqual(reranked[0]["family_id"], "family-target-match")
        self.assertGreater(reranked[0]["score"], reranked[1]["score"])
        self.assertGreater(
            reranked[0]["diagnostics"]["matched_family_bonus"],
            0,
        )

    def test_exact_title_match_gets_highest_bonus(self) -> None:
        """Exact title match should get a larger bonus than partial match."""
        hits = [
            {
                "family_id": "family-exact",
                "title": "Cosmic Universal Laws",
                "text": "",
                "score": 1.0,
                "diagnostics": {},
                "kind": "family_brief",
                "doc_id": "brief:exact",
            },
            {
                "family_id": "family-partial",
                "title": "Cosmic Laws Overview Plus Extra",
                "text": "",
                "score": 1.0,
                "diagnostics": {},
                "kind": "family_brief",
                "doc_id": "brief:partial",
            },
        ]
        matched_ids = {"family-exact", "family-partial"}
        query = "Cosmic Universal Laws"
        raw_tokens = tokenize(query)

        reranked = rerank_family_hits(query, raw_tokens, hits, matched_ids)
        exact = next(h for h in reranked if h["family_id"] == "family-exact")
        partial = next(h for h in reranked if h["family_id"] == "family-partial")
        self.assertGreater(
            exact["diagnostics"]["matched_family_bonus"],
            partial["diagnostics"]["matched_family_bonus"],
        )

    def test_no_bonus_without_match(self) -> None:
        hits = [
            {
                "family_id": "family-nomatch",
                "title": "Something Else",
                "text": "",
                "score": 5.0,
                "diagnostics": {},
                "kind": "family_brief",
                "doc_id": "brief:nomatch",
            },
        ]
        reranked = rerank_family_hits("query text", ["query", "text"], hits, set())
        self.assertEqual(reranked[0]["diagnostics"]["matched_family_bonus"], 0.0)


if __name__ == "__main__":
    unittest.main()
