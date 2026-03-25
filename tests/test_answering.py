from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from conversation_corpus_engine.answering import (
    build_answer,
    build_documents,
    expand_query_tokens,
    render_answer_markdown,
    render_answer_text,
    rerank_family_hits,
    save_answer_dossier,
    search_documents_v4,
    tokenize,
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_answer_corpus(root: Path) -> Path:
    corpus_dir = root / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        corpus_dir / "threads-index.json",
        [
            {
                "thread_uid": "thread-alpha",
                "title_normalized": "Alpha Registry Doctrine",
                "semantic_summary": "Alpha Registry Doctrine tracks the alpha registry.",
                "semantic_v2_summary": "Governance pressure is rising around the registry.",
                "semantic_v3_summary": "Pair work stabilizes the doctrine into an executable plan.",
                "semantic_v3_themes": ["alpha", "registry", "governance"],
                "semantic_v3_entities": ["Alpha Engine"],
                "family_ids": ["family-alpha"],
                "vector_terms": {"alpha": 1.0, "registry": 0.9, "doctrine": 0.8},
            }
        ],
    )
    _write_json(
        corpus_dir / "semantic-v3-index.json",
        {
            "threads": [
                {
                    "thread_uid": "thread-alpha",
                    "title": "Alpha Registry Doctrine",
                    "summary": "Alpha semantic summary",
                    "search_text": "Alpha Registry Doctrine alpha registry governance pair execution",
                    "family_ids": ["family-alpha"],
                    "vector_terms": {"alpha": 1.0, "registry": 0.95, "governance": 0.8},
                }
            ]
        },
    )
    _write_json(
        corpus_dir / "pairs-index.json",
        [
            {
                "pair_id": "pair-alpha-001",
                "thread_uid": "thread-alpha",
                "title": "Alpha Registry Doctrine pair",
                "summary": "Pair translates doctrine into implementation.",
                "search_text": "Alpha pair implements registry doctrine and stabilizes governance",
                "vector_terms": {"pair": 1.0, "registry": 0.8, "implement": 0.7},
                "family_ids": ["family-alpha"],
            }
        ],
    )
    _write_json(
        corpus_dir / "doctrine-briefs.json",
        [
            {
                "family_id": "family-alpha",
                "canonical_title": "Alpha Registry Doctrine",
                "canonical_thread_uid": "thread-alpha",
                "member_count": 1,
                "stable_themes": ["alpha", "registry", "governance"],
                "brief_text": "Alpha Registry Doctrine governs the registry through executable ritual.",
                "search_text": "Alpha Registry Doctrine alpha registry governance executable ritual",
                "vector_terms": {"alpha": 1.0, "registry": 0.9, "governance": 0.9},
            }
        ],
    )
    _write_json(
        corpus_dir / "family-dossiers.json",
        [
            {
                "family_id": "family-alpha",
                "canonical_title": "Alpha Registry Doctrine",
                "canonical_thread_uid": "thread-alpha",
                "member_count": 1,
                "stable_themes": ["alpha", "registry", "governance"],
                "doctrine_summary": "Alpha Registry Doctrine keeps the registry coherent through paired execution.",
                "search_text": "Alpha Registry Doctrine registry coherence paired execution governance",
                "actions": [
                    {
                        "action_key": "action-alpha",
                        "canonical_action": "Implement alpha registry ritual",
                    }
                ],
                "unresolved": [
                    {
                        "question_key": "question-alpha",
                        "canonical_question": "How should alpha governance evolve?",
                    }
                ],
                "key_entities": [
                    {"canonical_label": "Alpha Engine", "entity_type": "concept"}
                ],
                "vector_terms": {"registry": 1.0, "governance": 0.85, "ritual": 0.7},
            }
        ],
    )
    _write_json(
        corpus_dir / "action-ledger.json",
        [
            {
                "action_key": "action-alpha",
                "canonical_action": "Implement alpha registry ritual",
                "status": "open",
                "family_ids": ["family-alpha"],
                "thread_uids": ["thread-alpha"],
                "occurrence_count": 1,
                "vector_terms": {"implement": 1.0, "alpha": 0.9, "registry": 0.8},
            }
        ],
    )
    _write_json(
        corpus_dir / "unresolved-ledger.json",
        [
            {
                "question_key": "question-alpha",
                "canonical_question": "How should alpha governance evolve?",
                "why_unresolved": "The final synthesis is still open.",
                "family_ids": ["family-alpha"],
                "thread_uids": ["thread-alpha"],
                "occurrence_count": 1,
                "vector_terms": {"alpha": 0.9, "governance": 1.0, "evolve": 0.8},
            }
        ],
    )
    _write_json(
        corpus_dir / "doctrine-timeline.json",
        [
            {
                "canonical_family_id": "family-alpha",
                "canonical_title": "Alpha Registry Doctrine",
                "transitions": [
                    {
                        "from_title": "Alpha Notes",
                        "to_title": "Alpha Registry Doctrine",
                        "to_thread_uid": "thread-alpha",
                        "decision_state": "accepted",
                        "theme_shift": {
                            "added": ["governance", "ritual"],
                            "removed": ["drift"],
                        },
                        "vector_terms": {"governance": 1.0, "ritual": 0.7},
                    }
                ],
            }
        ],
    )
    _write_json(
        corpus_dir / "canonical-entities.json",
        [
            {
                "canonical_entity_id": "entity-alpha",
                "canonical_label": "Alpha Engine",
                "entity_type": "concept",
                "aliases": ["registry core", "alpha registry"],
            }
        ],
    )
    _write_json(
        corpus_dir / "entity-aliases.json",
        [
            {
                "canonical_label": "Alpha Engine",
                "labels": ["alpha registry", "engine"],
            }
        ],
    )
    return root


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


def test_build_documents_materializes_expected_surfaces(tmp_path: Path) -> None:
    root = _seed_answer_corpus(tmp_path)

    corpus = build_documents(root)

    assert len(corpus["documents"]) == 8
    assert len(corpus["family_docs"]) == 2
    assert len(corpus["thread_docs"]) == 2
    assert len(corpus["pair_docs"]) == 1
    assert len(corpus["ledger_docs"]) == 3
    assert corpus["thread_family_map"] == {"thread-alpha": ["family-alpha"]}
    assert corpus["family_title_map"] == {"family-alpha": "Alpha Registry Doctrine"}
    assert corpus["family_canonical_thread_map"] == {"family-alpha": "thread-alpha"}
    assert corpus["family_theme_map"]["family-alpha"] == ["alpha", "registry", "governance"]
    assert corpus["family_entity_map"]["family-alpha"] == ["Alpha Engine"]
    assert corpus["entity_alias_map"]["Alpha Engine"] == [
        "registry core",
        "alpha registry",
        "engine",
    ]
    assert any(
        doc["kind"] == "timeline"
        and doc["citations"] == ["family:family-alpha", "thread:thread-alpha"]
        for doc in corpus["ledger_docs"]
    )


def test_expand_query_tokens_uses_synonyms_aliases_and_family_context(tmp_path: Path) -> None:
    root = _seed_answer_corpus(tmp_path)

    corpus = build_documents(root)
    expanded = expand_query_tokens("alpha registry action", corpus)

    assert "implement" in expanded
    assert "task" in expanded
    assert "engine" in expanded
    assert "governance" in expanded
    assert expanded.count("alpha") == 1


def test_search_documents_and_build_answer_produce_grounded_family_answer(tmp_path: Path) -> None:
    root = _seed_answer_corpus(tmp_path)

    retrieval = search_documents_v4(root, "Alpha Registry Doctrine")
    answer = build_answer("Alpha Registry Doctrine", retrieval)

    assert retrieval["family_focus"] == ["family-alpha"]
    assert answer["answer_state"] == "grounded"
    assert answer["confidence"] > 0.8
    assert answer["corpus_facts"][0].startswith("Best matching family is Alpha Registry Doctrine")
    assert "family:family-alpha" in answer["citations"]
    assert "thread:thread-alpha" in answer["citations"]
    assert "action:action-alpha" in answer["citations"]
    assert "question:question-alpha" in answer["citations"]
    assert "pair:pair-alpha-001" in answer["citations"]
    assert answer["inference"][0].startswith("Pair-level evidence surfaces")


def test_action_mode_prefers_ledger_hits_for_answer_construction(tmp_path: Path) -> None:
    root = _seed_answer_corpus(tmp_path)

    retrieval = search_documents_v4(root, "implement alpha registry", mode="action")
    answer = build_answer("implement alpha registry", retrieval, mode="action")

    assert retrieval["hits"]
    assert all(item["kind"] == "action" for item in retrieval["hits"])
    assert answer["answer_state"] in {"grounded", "limited"}
    assert answer["corpus_facts"][0] == "Top action pressure is Implement alpha registry ritual."
    assert answer["citations"] == ["action:action-alpha"]
    assert answer["evidence"][0]["kind"] == "action"


def test_build_answer_abstain_clears_citations_and_evidence() -> None:
    retrieval = {
        "query_tokens": ["obscure", "query"],
        "family_focus": [],
        "family_hits": [
            {
                "kind": "family_brief",
                "doc_id": "family-brief:weak",
                "title": "Weak Match",
                "score": 1.05,
                "citations": ["family:weak"],
                "snippet": "barely related",
                "diagnostics": {
                    "coverage": 0.1,
                    "title_boost": 0.1,
                    "text_boost": 0.1,
                    "vector_score": 0.0,
                    "phrase_boost": 0.0,
                },
                "payload": {"family_id": "weak", "canonical_title": "Weak Match"},
                "family_id": "weak",
            }
        ],
        "thread_hits": [],
        "pair_hits": [],
        "ledger_hits": [],
        "hits": [
            {
                "kind": "family_brief",
                "doc_id": "family-brief:weak",
                "title": "Weak Match",
                "score": 1.05,
                "citations": ["family:weak"],
                "snippet": "barely related",
                "diagnostics": {
                    "coverage": 0.1,
                    "title_boost": 0.1,
                    "text_boost": 0.1,
                    "vector_score": 0.0,
                    "phrase_boost": 0.0,
                },
                "payload": {"family_id": "weak", "canonical_title": "Weak Match"},
                "family_id": "weak",
            }
        ],
    }

    answer = build_answer("obscure query", retrieval)

    assert answer["answer_state"] == "abstain"
    assert answer["citations"] == []
    assert answer["evidence"] == []
    assert "Evidence is too weak or ambiguous" in answer["answer"]


def test_render_and_save_answer_dossier_write_expected_artifacts(tmp_path: Path) -> None:
    root = _seed_answer_corpus(tmp_path)
    retrieval = search_documents_v4(root, "Alpha Registry Doctrine")
    answer = build_answer("Alpha Registry Doctrine", retrieval)

    text = render_answer_text(answer)
    markdown = render_answer_markdown(answer)
    paths = save_answer_dossier(root, answer)

    assert "State: grounded" in text
    assert "Citations" in text
    assert markdown.startswith("# Answer Dossier")
    assert "## Evidence" in markdown
    assert Path(paths["json_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    saved_answer = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    saved_markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    assert saved_answer["query"] == "Alpha Registry Doctrine"
    assert saved_markdown.startswith("# Answer Dossier")


if __name__ == "__main__":
    unittest.main()
