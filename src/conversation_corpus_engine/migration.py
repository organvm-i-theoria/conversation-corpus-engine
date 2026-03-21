from __future__ import annotations

from pathlib import Path

from .federation import upsert_corpus, validate_corpus_root


def discover_staging_corpora(staging_root: Path) -> list[Path]:
    staging_root = staging_root.resolve()
    if not staging_root.exists():
        return []

    corpora: list[Path] = []
    for child in sorted(staging_root.iterdir()):
        if not child.is_dir():
            continue
        if validate_corpus_root(child)["valid"]:
            corpora.append(child.resolve())
    return corpora


def seed_registry_from_staging(
    project_root: Path,
    staging_root: Path,
    *,
    prefer_default: str = "chatgpt-history",
) -> dict[str, object]:
    discovered = discover_staging_corpora(staging_root)
    registered: list[dict[str, str]] = []

    for corpus_root in discovered:
        corpus_id = corpus_root.name
        entry = upsert_corpus(
            project_root,
            corpus_root,
            corpus_id=corpus_id,
            name=corpus_root.name.replace("-", " ").title(),
            make_default=corpus_root.name == prefer_default,
        )
        registered.append(
            {
                "corpus_id": entry["corpus_id"],
                "name": entry["name"],
                "root": entry["root"],
                "default": str(bool(entry.get("default"))).lower(),
            },
        )

    return {
        "staging_root": str(staging_root.resolve()),
        "registered_count": len(registered),
        "registered": registered,
    }
