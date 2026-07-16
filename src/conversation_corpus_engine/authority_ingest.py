from __future__ import annotations

import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .authority_projection import (
    AuthorityProjectionError,
    ProjectionCandidate,
    apply_reviewed_adoptions,
    body_hash,
    build_projection_candidate,
    canonical_bytes,
    normalize_timestamp,
    sha256_contract,
)
from .provider_catalog import load_provider_manifest_snapshot
from .source_adapter_registry import (
    AdapterDiagnostic,
    AdapterResult,
    RedactedSourceRecord,
    SourceBundleError,
    read_source_bundle,
)

_COVERAGE_STATUSES = (
    "acquired",
    "parsed",
    "quarantined",
    "inaccessible",
    "missing_expected",
    "owner_blocked",
)


class AuthorityIngestError(ValueError):
    """The authority-ingest run configuration is incomplete or contradictory."""


def _residual_source_id(identity: dict[str, Any]) -> str:
    return f"src_residual_{sha256_contract(identity).removeprefix('sha256:')[:24]}"


def _write_canonical(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(canonical_bytes(payload))
    temporary.replace(path)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("wb") as handle:
        for row in sorted(rows, key=lambda item: item["source_id"]):
            handle.write(canonical_bytes(row))
    temporary.replace(path)


def _source_alias_map(catalog: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {
        alias: provider_id
        for provider_id, provider in catalog.items()
        for alias in provider["source_family_aliases"]
    }


def _blocker_source(
    *,
    snapshot_id: str,
    blocker: dict[str, str],
    identity: dict[str, Any],
    evidence_references: list[str],
    status: str = "owner_blocked",
    accessible: bool = False,
) -> dict[str, Any]:
    return {
        "source_id": _residual_source_id(
            {"snapshot_id": snapshot_id, "status": status, **identity}
        ),
        "status": status,
        "accessible": accessible,
        "owner_reference": blocker["owner_reference"],
        "failed_predicate": blocker["failed_predicate"],
        "next_action": blocker["next_action"],
        "evidence_references": sorted(set(evidence_references)),
    }


def _quarantine_source(
    *,
    snapshot_id: str,
    diagnostic: AdapterDiagnostic,
    blocker: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    coverage = _blocker_source(
        snapshot_id=snapshot_id,
        blocker=blocker,
        identity={"input_reference": diagnostic.input_reference, "code": diagnostic.code},
        evidence_references=[diagnostic.input_reference],
        status="quarantined",
        accessible=True,
    )
    row = {
        "contract_name": "authority-ingest-quarantine.v1",
        "contract_version": 1,
        "source_id": coverage["source_id"],
        "snapshot_id": snapshot_id,
        "status": "quarantined",
        "body_hash": diagnostic.body_hash,
        "input_reference": diagnostic.input_reference,
        "diagnostic": {"code": diagnostic.code, "message": diagnostic.message},
        "blocker": blocker,
    }
    return coverage, row


def _record_projection_diagnostic(record: RedactedSourceRecord, message: str) -> AdapterDiagnostic:
    return AdapterDiagnostic(
        line_number=record.line_number,
        input_reference=record.input_reference,
        body_hash=body_hash(record.text),
        code="invalid-authority-projection",
        message=message,
    )


def _resolve_runs(
    catalog: dict[str, dict[str, Any]], source_root: Path | None
) -> tuple[list[tuple[Path, tuple[str, ...], str]], list[str]]:
    if source_root is not None:
        adapter_ids = {provider["default_adapter_id"] for provider in catalog.values()}
        if len(adapter_ids) != 1:
            raise AuthorityIngestError(
                "an explicit shared bundle requires one common configured adapter"
            )
        return [
            (
                source_root,
                tuple(sorted(catalog)),
                next(iter(adapter_ids)),
            )
        ], []

    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    unresolved: list[str] = []
    for provider_id, provider in catalog.items():
        root_env = provider["source_contract"]["root_env"]
        value = os.environ.get(root_env)
        if not value:
            unresolved.append(provider_id)
            continue
        grouped[(str(Path(value).expanduser().resolve()), provider["default_adapter_id"])].append(
            provider_id
        )
    runs = [
        (Path(path), tuple(sorted(provider_ids)), adapter_id)
        for (path, adapter_id), provider_ids in sorted(grouped.items())
    ]
    return runs, sorted(unresolved)


def _read_runs(
    runs: list[tuple[Path, tuple[str, ...], str]],
) -> tuple[
    list[tuple[AdapterResult, tuple[str, ...]]],
    list[tuple[tuple[str, ...], str]],
]:
    results: list[tuple[AdapterResult, tuple[str, ...]]] = []
    failures: list[tuple[tuple[str, ...], str]] = []
    for source_root, provider_ids, adapter_id in runs:
        try:
            result = read_source_bundle(adapter_id, source_root)
        except SourceBundleError as exc:
            failures.append((provider_ids, str(exc)))
            continue
        results.append((result, provider_ids))
    return results, failures


def _coverage_receipt(
    *,
    snapshot_id: str,
    captured_at: str,
    manifest_hash: str,
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    ordered_sources = sorted(sources, key=lambda item: item["source_id"])
    counts = Counter(item["status"] for item in ordered_sources)
    count_payload = {status: counts.get(status, 0) for status in _COVERAGE_STATUSES}
    unique_ids = len({item["source_id"] for item in ordered_sources}) == len(ordered_sources)
    exact_all = (
        unique_ids
        and sum(count_payload.values()) == len(ordered_sources)
        and all(
            item["status"] == "parsed"
            or all(
                item.get(field) for field in ("owner_reference", "failed_predicate", "next_action")
            )
            for item in ordered_sources
        )
    )
    residual_owners = [
        {
            "source_id": item["source_id"],
            "owner_reference": item["owner_reference"],
            "failed_predicate": item["failed_predicate"],
            "next_action": item["next_action"],
        }
        for item in ordered_sources
        if item["status"] != "parsed"
    ]
    receipt_id = _residual_source_id(
        {"snapshot_id": snapshot_id, "manifest_hash": manifest_hash, "kind": "coverage"}
    ).removeprefix("src_")
    receipt: dict[str, Any] = {
        "contract_name": "coverage-receipt.v1",
        "contract_version": 1,
        "receipt_id": receipt_id,
        "snapshot_id": snapshot_id,
        "generated_at": normalize_timestamp(captured_at),
        "denominator": {
            "discovery_manifest_reference": f"provider-manifest:{manifest_hash}",
            "count": len(ordered_sources),
            "manifest_hash": manifest_hash,
        },
        "sources": ordered_sources,
        "counts": count_payload,
        "exact_all": exact_all,
        "ready": exact_all and count_payload["parsed"] == len(ordered_sources),
        "residual_owners": residual_owners,
    }
    receipt["receipt_hash"] = sha256_contract(receipt)
    return receipt


def ingest_authority_bundle(
    *,
    output_root: Path,
    snapshot_id: str,
    captured_at: str,
    custody_pointer: str,
    source_root: Path | None = None,
    provider_manifest: Path | None = None,
) -> dict[str, Any]:
    if not snapshot_id.strip():
        raise AuthorityIngestError("snapshot_id must be non-empty")
    if not custody_pointer.strip():
        raise AuthorityIngestError("custody_pointer must be non-empty")
    normalize_timestamp(captured_at)
    manifest = load_provider_manifest_snapshot(provider_manifest)
    catalog = manifest["providers"]
    aliases = _source_alias_map(catalog)
    manifest_hash = sha256_contract(manifest)
    runs, unresolved_provider_ids = _resolve_runs(catalog, source_root)
    read_results, read_failures = _read_runs(runs)
    snapshot_hash = sha256_contract(
        {"source_hashes": sorted({result.source_hash for result, _ in read_results})}
    )

    candidates: list[ProjectionCandidate] = []
    coverage_sources: list[dict[str, Any]] = []
    quarantine_rows: list[dict[str, Any]] = []
    blocker_rows: list[dict[str, Any]] = []
    duplicate_keys: Counter[tuple[str, ...]] = Counter()

    for provider_id in unresolved_provider_ids:
        provider = catalog[provider_id]
        coverage = _blocker_source(
            snapshot_id=snapshot_id,
            blocker=provider["blocker"],
            identity={"provider_id": provider_id, "reason": "unresolved-root"},
            evidence_references=[f"provider-manifest:{manifest_hash}"],
        )
        coverage_sources.append(coverage)
        blocker_rows.append({"snapshot_id": snapshot_id, **coverage})

    for provider_ids, message in read_failures:
        for provider_id in provider_ids:
            provider = catalog[provider_id]
            coverage = _blocker_source(
                snapshot_id=snapshot_id,
                blocker=provider["blocker"],
                identity={"provider_id": provider_id, "reason": "unreadable-root"},
                evidence_references=[f"provider-manifest:{manifest_hash}"],
            )
            coverage_sources.append(coverage)
            blocker_rows.append(
                {
                    "snapshot_id": snapshot_id,
                    "diagnostic": {"code": "unreadable-source-root", "message": message},
                    **coverage,
                }
            )

    for result, expected_provider_ids in read_results:
        seen_provider_ids: set[str] = set()
        for diagnostic in result.diagnostics:
            coverage, quarantine = _quarantine_source(
                snapshot_id=snapshot_id,
                diagnostic=diagnostic,
                blocker=manifest["unknown_source_blocker"],
            )
            coverage_sources.append(coverage)
            quarantine_rows.append(quarantine)
        for record in result.records:
            matched_provider_id = aliases.get(record.source_family)
            if matched_provider_id is None or matched_provider_id not in expected_provider_ids:
                coverage = _blocker_source(
                    snapshot_id=snapshot_id,
                    blocker=manifest["unknown_source_blocker"],
                    identity={
                        "source_family": record.source_family,
                        "input_reference": record.input_reference,
                    },
                    evidence_references=[
                        record.input_reference,
                        f"provider-manifest:{manifest_hash}",
                    ],
                    accessible=True,
                )
                coverage_sources.append(coverage)
                blocker_rows.append({"snapshot_id": snapshot_id, **coverage})
                continue
            seen_provider_ids.add(matched_provider_id)
            provider = catalog[matched_provider_id]
            try:
                candidate = build_projection_candidate(
                    record,
                    provider,
                    snapshot_id=snapshot_id,
                    captured_at=captured_at,
                    snapshot_hash=snapshot_hash,
                    custody_pointer=custody_pointer,
                )
            except AuthorityProjectionError as exc:
                diagnostic = _record_projection_diagnostic(record, str(exc))
                coverage, quarantine = _quarantine_source(
                    snapshot_id=snapshot_id,
                    diagnostic=diagnostic,
                    blocker=provider["blocker"],
                )
                coverage_sources.append(coverage)
                quarantine_rows.append(quarantine)
                continue
            candidates.append(candidate)
            coverage_sources.append(
                {
                    "source_id": candidate.event["source_id"],
                    "status": "parsed",
                    "accessible": True,
                    "evidence_references": [record.input_reference],
                }
            )
            duplicate_keys[
                (
                    candidate.event["body_hash"],
                    candidate.event["role"],
                    candidate.event["kind"],
                    candidate.event["source"],
                    record.session_id,
                )
            ] += 1
        for provider_id in set(expected_provider_ids) - seen_provider_ids:
            provider = catalog[provider_id]
            coverage = _blocker_source(
                snapshot_id=snapshot_id,
                blocker=provider["blocker"],
                identity={"provider_id": provider_id, "reason": "missing-expected-source"},
                evidence_references=[
                    f"bundle:sha256:{result.source_hash}",
                    f"provider-manifest:{manifest_hash}",
                ],
                status="missing_expected",
            )
            coverage_sources.append(coverage)
            blocker_rows.append({"snapshot_id": snapshot_id, **coverage})

    apply_reviewed_adoptions(candidates)
    envelopes = [candidate.envelope for candidate in candidates]
    events = [candidate.event for candidate in candidates]
    coverage = _coverage_receipt(
        snapshot_id=snapshot_id,
        captured_at=captured_at,
        manifest_hash=manifest_hash,
        sources=coverage_sources,
    )
    event_by_id = {event["source_id"]: event for event in events}
    envelope_by_id = {envelope["source_id"]: envelope for envelope in envelopes}
    shared_source_ids = set(event_by_id) & set(envelope_by_id)
    parity_exact = (
        len(event_by_id) == len(events) == len(envelope_by_id) == len(envelopes)
        and shared_source_ids == set(event_by_id) == set(envelope_by_id)
        and all(
            event_by_id[source_id]["body_hash"] == envelope_by_id[source_id]["body_hash"]
            for source_id in shared_source_ids
        )
        and coverage["counts"]["parsed"] == len(events)
    )
    parity = {
        "contract_name": "provider-authority-parity-receipt.v1",
        "contract_version": 1,
        "snapshot_id": snapshot_id,
        "snapshot_hash": snapshot_hash,
        "provider_manifest_hash": manifest_hash,
        "counts": {
            "source_envelopes": len(envelopes),
            "normalized_events": len(events),
            "quarantined": len(quarantine_rows),
            "owner_blocked": len(blocker_rows),
            "duplicate_transports": sum(count - 1 for count in duplicate_keys.values()),
        },
        "parity_exact": parity_exact,
        "legacy_importers": "retained",
        "retirement_allowed": parity_exact and coverage["ready"],
    }
    parity["receipt_hash"] = sha256_contract(parity)

    resolved_output = output_root.resolve()
    paths = {
        "source_envelopes": resolved_output / "source-envelope.v1.jsonl",
        "normalized_events": resolved_output / "normalized-events.v1.jsonl",
        "quarantine": resolved_output / "quarantine.jsonl",
        "owner_blockers": resolved_output / "owner-blockers.jsonl",
        "coverage_receipt": resolved_output / "coverage-receipt.v1.json",
        "parity_receipt": resolved_output / "parity-receipt.v1.json",
    }
    _write_jsonl(paths["source_envelopes"], envelopes)
    _write_jsonl(paths["normalized_events"], events)
    _write_jsonl(paths["quarantine"], quarantine_rows)
    _write_jsonl(paths["owner_blockers"], blocker_rows)
    _write_canonical(paths["coverage_receipt"], coverage)
    _write_canonical(paths["parity_receipt"], parity)
    return {
        "snapshot_id": snapshot_id,
        "snapshot_hash": snapshot_hash,
        "provider_manifest_hash": manifest_hash,
        "coverage": coverage,
        "parity": parity,
        "paths": {key: str(path) for key, path in paths.items()},
    }
