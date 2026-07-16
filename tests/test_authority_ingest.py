from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from conversation_corpus_engine.authority_ingest import ingest_authority_bundle

CAPTURED_AT = "2026-07-16T16:00:00Z"
SNAPSHOT_ID = "fixture-snapshot"
CUSTODY_POINTER = "custody:fixture-snapshot"


def source_content_sha(role: str, text: str) -> str:
    normalized = " ".join(text.split())
    return hashlib.sha256(f"{role}\x00{normalized}".encode()).hexdigest()


def atom(
    *,
    source: str,
    role: str,
    text: str,
    atom_id: str,
    ordinal: int,
    kind: str = "message",
    timestamp: str = "2026-07-16T15:00:00Z",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "atom_id": atom_id,
        "content_sha": source_content_sha(role, text),
        "blob_shas": [f"blob-{source}"],
        "source": source,
        "session_id": "session-fixture",
        "ordinal": ordinal,
        "role": role,
        "ts": timestamp,
        "text": text,
        "kind": kind,
        "meta": metadata or {},
    }


def provider(
    provider_id: str, alias: str, *, root_env: str = "CCE_TEST_BUNDLE_ROOT"
) -> dict[str, Any]:
    return {
        "provider_id": provider_id,
        "display_name": f"Configured {provider_id}",
        "adapter_state": "supported",
        "default_adapter_id": "session-meta-redacted-jsonl-v1",
        "adapter_type": "adapter-reusable",
        "discovery_mode": "redacted-bundle",
        "inbox_rel": f"{provider_id}/inbox",
        "default_corpus_id": f"{provider_id}-memory",
        "default_corpus_name": f"Configured {provider_id} Memory",
        "source_family_aliases": [alias],
        "source_contract": {
            "kind": "session-meta-redacted-bundle",
            "root_env": root_env,
        },
        "authority_policy": "native-role",
        "owner_reference": "owner:test",
        "blocker": {
            "owner_reference": "owner:test",
            "failed_predicate": "redacted source bundle is readable",
            "next_action": "configure a frozen fixture and rerun",
        },
    }


def write_manifest(path: Path, providers: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "provider-manifest.v1",
                "configuration_scope": "reusable-example",
                "unknown_source_blocker": {
                    "owner_reference": "owner:test",
                    "failed_predicate": "source family is registered",
                    "next_action": "register the source family and rerun",
                },
                "providers": providers,
            }
        ),
        encoding="utf-8",
    )


def write_atoms(path: Path, rows: list[dict[str, Any] | str]) -> None:
    path.write_text(
        "".join(
            (row if isinstance(row, str) else json.dumps(row, sort_keys=True)) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


def run_ingest(
    *,
    output_root: Path,
    atoms_path: Path | None,
    manifest_path: Path,
) -> dict[str, Any]:
    return ingest_authority_bundle(
        output_root=output_root,
        source_root=atoms_path,
        provider_manifest=manifest_path,
        snapshot_id=SNAPSHOT_ID,
        captured_at=CAPTURED_AT,
        custody_pointer=CUSTODY_POINTER,
    )


def test_identical_text_retains_five_distinct_authority_classes_and_byte_identity(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "providers.json"
    atoms_path = tmp_path / "atoms.jsonl"
    write_manifest(manifest, [provider("provider-renamed", "family-renamed")])
    shared_text = "The same transported text."
    write_atoms(
        atoms_path,
        [
            atom(
                source="family-renamed",
                role="user",
                text=shared_text,
                atom_id="operator-atom",
                ordinal=0,
            ),
            atom(
                source="family-renamed",
                role="assistant",
                text=shared_text,
                atom_id="assistant-atom",
                ordinal=1,
            ),
            atom(
                source="family-renamed",
                role="tool",
                text=shared_text,
                atom_id="tool-atom",
                ordinal=2,
                kind="tool_output",
            ),
            atom(
                source="family-renamed",
                role="system",
                text=shared_text,
                atom_id="continuation-atom",
                ordinal=3,
                kind="continuation_summary",
            ),
            atom(
                source="family-renamed",
                role="system",
                text=shared_text,
                atom_id="memory-atom",
                ordinal=4,
                kind="memory_summary",
            ),
        ],
    )

    first = run_ingest(
        output_root=tmp_path / "first", atoms_path=atoms_path, manifest_path=manifest
    )
    run_ingest(output_root=tmp_path / "second", atoms_path=atoms_path, manifest_path=manifest)
    events = read_jsonl(first["paths"]["normalized_events"])
    envelopes = read_jsonl(first["paths"]["source_envelopes"])

    assert {event["authority_class"] for event in events} == {
        "operator_intent",
        "artifact",
        "transport_echo",
        "system_metadata",
        "unknown",
    }
    assert len({event["authority_detail"] for event in events}) == 5
    assert len({event["body_hash"] for event in events}) == 1
    assert {envelope["role"] for envelope in envelopes} == {
        "operator",
        "assistant",
        "tool",
        "continuation_summary",
        "memory_summary",
    }
    assert all("text" not in envelope for envelope in envelopes)
    assert first["coverage"]["exact_all"] is True
    assert first["coverage"]["ready"] is True
    for filename in (
        "source-envelope.v1.jsonl",
        "normalized-events.v1.jsonl",
        "quarantine.jsonl",
        "owner-blockers.jsonl",
        "coverage-receipt.v1.json",
        "parity-receipt.v1.json",
    ):
        assert (tmp_path / "first" / filename).read_bytes() == (
            tmp_path / "second" / filename
        ).read_bytes()


def test_provider_manifest_reorder_and_new_provider_are_config_only(tmp_path: Path) -> None:
    first_manifest = tmp_path / "first-manifest.json"
    second_manifest = tmp_path / "second-manifest.json"
    providers = [
        provider("provider-renamed", "family-renamed"),
        provider("provider-new", "family-new"),
    ]
    write_manifest(first_manifest, providers)
    write_manifest(second_manifest, list(reversed(providers)))
    atoms_path = tmp_path / "atoms.jsonl"
    write_atoms(
        atoms_path,
        [
            atom(
                source="family-renamed",
                role="user",
                text="Renamed provider event.",
                atom_id="renamed-atom",
                ordinal=0,
            ),
            atom(
                source="family-new",
                role="assistant",
                text="New provider event.",
                atom_id="new-atom",
                ordinal=1,
            ),
        ],
    )

    first = run_ingest(
        output_root=tmp_path / "first", atoms_path=atoms_path, manifest_path=first_manifest
    )
    second = run_ingest(
        output_root=tmp_path / "second", atoms_path=atoms_path, manifest_path=second_manifest
    )

    assert first["provider_manifest_hash"] == second["provider_manifest_hash"]
    assert first["coverage"]["ready"] is True
    assert (tmp_path / "first" / "source-envelope.v1.jsonl").read_bytes() == (
        tmp_path / "second" / "source-envelope.v1.jsonl"
    ).read_bytes()
    assert (tmp_path / "first" / "coverage-receipt.v1.json").read_bytes() == (
        tmp_path / "second" / "coverage-receipt.v1.json"
    ).read_bytes()


def test_malformed_unknown_and_missing_sources_do_not_stop_valid_sibling(tmp_path: Path) -> None:
    manifest = tmp_path / "providers.json"
    write_manifest(
        manifest,
        [provider("provider-a", "family-a"), provider("provider-b", "family-b")],
    )
    atoms_path = tmp_path / "atoms.jsonl"
    write_atoms(
        atoms_path,
        [
            atom(
                source="family-a",
                role="user",
                text="Valid sibling.",
                atom_id="valid-atom",
                ordinal=0,
            ),
            "{malformed-json",
            atom(
                source="family-a",
                role="user",
                text="Attachment metadata is missing.",
                atom_id="missing-attachment",
                ordinal=1,
                kind="attachment_ref",
            ),
            atom(
                source="family-unknown",
                role="assistant",
                text="Unknown but hash-addressed.",
                atom_id="unknown-atom",
                ordinal=2,
            ),
        ],
    )

    result = run_ingest(output_root=tmp_path / "out", atoms_path=atoms_path, manifest_path=manifest)

    assert len(read_jsonl(result["paths"]["source_envelopes"])) == 1
    assert len(read_jsonl(result["paths"]["quarantine"])) == 2
    assert len(read_jsonl(result["paths"]["owner_blockers"])) == 2
    assert result["coverage"]["counts"] == {
        "acquired": 0,
        "parsed": 1,
        "quarantined": 2,
        "inaccessible": 0,
        "missing_expected": 1,
        "owner_blocked": 1,
    }
    assert result["coverage"]["exact_all"] is True
    assert result["coverage"]["ready"] is False
    assert len(result["coverage"]["residual_owners"]) == 4


def test_missing_runtime_roots_emit_owner_blockers(monkeypatch, tmp_path: Path) -> None:
    manifest = tmp_path / "providers.json"
    write_manifest(
        manifest,
        [
            provider("provider-a", "family-a", root_env="CCE_MISSING_A"),
            provider("provider-b", "family-b", root_env="CCE_MISSING_B"),
        ],
    )
    monkeypatch.delenv("CCE_MISSING_A", raising=False)
    monkeypatch.delenv("CCE_MISSING_B", raising=False)

    result = run_ingest(output_root=tmp_path / "out", atoms_path=None, manifest_path=manifest)

    assert result["coverage"]["counts"]["owner_blocked"] == 2
    assert result["coverage"]["exact_all"] is True
    assert result["coverage"]["ready"] is False
    assert len(read_jsonl(result["paths"]["owner_blockers"])) == 2


def test_assistant_plan_stays_artifact_without_reviewed_operator_adoption(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "providers.json"
    write_manifest(manifest, [provider("provider-a", "family-a")])
    atoms_path = tmp_path / "atoms.jsonl"
    write_atoms(
        atoms_path,
        [
            atom(
                source="family-a",
                role="assistant",
                text="Generated plan awaiting adoption.",
                atom_id="plan-adopted",
                ordinal=0,
                kind="plan",
                metadata={"adoption_event_id": "adoption-event"},
            ),
            atom(
                source="family-a",
                role="user",
                text="I explicitly adopt that plan.",
                atom_id="adoption-event",
                ordinal=1,
                kind="adoption",
                metadata={"review_state": "reviewed", "adopts_atom_id": "plan-adopted"},
            ),
            atom(
                source="family-a",
                role="assistant",
                text="Generated plan without adoption.",
                atom_id="plan-unadopted",
                ordinal=2,
                kind="plan",
            ),
        ],
    )

    result = run_ingest(output_root=tmp_path / "out", atoms_path=atoms_path, manifest_path=manifest)
    events = {
        event["native_identifiers"]["atom_id"]: event
        for event in read_jsonl(result["paths"]["normalized_events"])
    }

    assert events["plan-adopted"]["authority_class"] == "artifact"
    assert events["plan-adopted"]["origin_lane"] == "artifact"
    assert events["plan-adopted"]["effective_lane"] == "operator_intent"
    assert events["plan-adopted"]["adoption_state"] == "reviewed_operator_adoption"
    assert events["plan-unadopted"]["authority_class"] == "artifact"
    assert events["plan-unadopted"]["effective_lane"] == "artifact"
    assert events["plan-unadopted"]["adoption_state"] == "not_adopted"


def test_invalid_timestamp_quarantines_without_repeating_duplicate_transports(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "providers.json"
    write_manifest(manifest, [provider("provider-a", "family-a")])
    atoms_path = tmp_path / "atoms.jsonl"
    duplicate = atom(
        source="family-a",
        role="user",
        text="Repeated transport.",
        atom_id="duplicate-atom",
        ordinal=0,
    )
    invalid = atom(
        source="family-a",
        role="assistant",
        text="No native event time.",
        atom_id="invalid-time",
        ordinal=1,
        timestamp="not-a-time",
    )
    write_atoms(atoms_path, [duplicate, duplicate, invalid])

    result = run_ingest(output_root=tmp_path / "out", atoms_path=atoms_path, manifest_path=manifest)

    assert result["coverage"]["counts"]["parsed"] == 2
    assert result["coverage"]["counts"]["quarantined"] == 1
    assert result["parity"]["counts"]["duplicate_transports"] == 1
    assert result["parity"]["parity_exact"] is True
    assert result["parity"]["retirement_allowed"] is False
