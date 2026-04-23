from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversation_corpus_engine.workspace_inventory import (  # noqa: E402
    commerce_meta_root,
    find_commerce_engagement_record,
    find_commerce_engagement_records,
)


def _write_engagement(path: Path, engagement_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"engagement_id: {engagement_id}\nname: test\n", encoding="utf-8")


def test_commerce_inventory_finds_eng_001_through_eng_005(tmp_path: Path, monkeypatch) -> None:
    workspace_root = tmp_path / "Workspace"
    commerce_root = workspace_root / "organvm" / "commerce--meta"
    _write_engagement(commerce_root / "engagements" / "active" / "sovereign-systems.yaml", "ENG-001")
    _write_engagement(
        commerce_root / "engagements" / "active" / "public-record-data-scrapper.yaml",
        "ENG-002",
    )
    _write_engagement(
        commerce_root / "engagements" / "active" / "peer-audited-behavioral-blockchain.yaml",
        "ENG-003",
    )
    _write_engagement(
        commerce_root / "engagements" / "prospects" / "post-proto-mousike-nomos.yaml",
        "ENG-004",
    )
    _write_engagement(
        commerce_root / "engagements" / "active" / "content-engine-asset-amplifier.yaml",
        "ENG-005",
    )
    monkeypatch.setenv("CCE_WORKSPACE_ROOT", str(workspace_root))

    records = find_commerce_engagement_records(
        ["ENG-001", "ENG-002", "ENG-003", "ENG-004", "ENG-005"]
    )

    assert commerce_meta_root() == commerce_root.resolve()
    assert set(records) == {"ENG-001", "ENG-002", "ENG-003", "ENG-004", "ENG-005"}
    assert records["ENG-001"].name == "sovereign-systems.yaml"
    assert records["ENG-004"].name == "post-proto-mousike-nomos.yaml"
    assert find_commerce_engagement_record("ENG-005") == (
        commerce_root / "engagements" / "active" / "content-engine-asset-amplifier.yaml"
    ).resolve()
