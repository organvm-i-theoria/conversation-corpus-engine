from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .source_adapter_registry import RedactedSourceRecord

_ROLE_POLICY: dict[str, tuple[str, str, str]] = {
    "operator": ("operator_intent", "operator_intent", "operator_intent"),
    "assistant": ("artifact", "assistant_artifact", "artifact"),
    "system": ("system_metadata", "system_instruction", "artifact"),
    "tool": ("transport_echo", "tool_echo", "artifact"),
    "continuation_summary": (
        "system_metadata",
        "continuation_summary",
        "artifact",
    ),
    "memory_summary": ("unknown", "memory_summary", "artifact"),
    "unknown": ("unknown", "unknown_role", "artifact"),
}
_ROLE_ALIASES = {"user": "operator", "human": "operator"}
_SPECIAL_KINDS = {"continuation_summary", "memory_summary"}
_SAFE_SOURCE_INSTANCE = re.compile(r"^[A-Za-z0-9_.:-]+$")


class AuthorityProjectionError(ValueError):
    """A parsed event cannot satisfy the authority projection contract."""


@dataclass
class ProjectionCandidate:
    record: RedactedSourceRecord
    envelope: dict[str, Any]
    event: dict[str, Any]


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def sha256_contract(value: Any) -> str:
    return f"sha256:{hashlib.sha256(canonical_bytes(value)).hexdigest()}"


def body_hash(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def normalize_timestamp(value: str) -> str:
    candidate = value.strip()
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuthorityProjectionError("timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise AuthorityProjectionError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_role(role: str, kind: str) -> str:
    normalized_kind = kind.strip().lower().replace("-", "_")
    if normalized_kind in _SPECIAL_KINDS:
        return normalized_kind
    normalized_role = role.strip().lower().replace("-", "_")
    normalized_role = _ROLE_ALIASES.get(normalized_role, normalized_role)
    return normalized_role if normalized_role in _ROLE_POLICY else "unknown"


def _source_id(identity: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_bytes(identity)).hexdigest()
    return f"src_{digest[:32]}"


def build_projection_candidate(
    record: RedactedSourceRecord,
    provider: dict[str, Any],
    *,
    snapshot_id: str,
    captured_at: str,
    snapshot_hash: str,
    custody_pointer: str,
) -> ProjectionCandidate:
    normalized_timestamp = normalize_timestamp(record.event_timestamp)
    normalized_captured_at = normalize_timestamp(captured_at)
    normalized_role = normalize_role(record.role, record.kind)
    authority_class, authority_detail, origin_lane = _ROLE_POLICY[normalized_role]
    event_body_hash = body_hash(record.text)
    source_instance = record.metadata.get("source_instance")
    if not isinstance(source_instance, str) or not source_instance.strip():
        source_instance = f"{provider['provider_id']}-session-meta"
    elif not _SAFE_SOURCE_INSTANCE.fullmatch(source_instance):
        raise AuthorityProjectionError("source_instance must be a safe identifier")
    native_identifiers = {
        "atom_id": record.atom_id,
        "session_id": record.session_id,
        "ordinal": str(record.ordinal),
        "input_reference": record.input_reference,
    }
    identity = {
        "snapshot_id": snapshot_id,
        "source_family": record.source_family,
        "source_instance": source_instance,
        "native_identifiers": native_identifiers,
        "role": normalized_role,
        "body_hash": event_body_hash,
    }
    source_id = _source_id(identity)
    provider_metadata = {
        "provider_id": provider["provider_id"],
        "source": record.source_family,
        "source_role": record.role,
        "kind": record.kind,
        "source_content_sha": f"sha256:{record.content_sha}",
        "authority_detail": authority_detail,
        "origin_lane": origin_lane,
        "effective_lane": origin_lane,
        "adoption_state": "not_applicable" if normalized_role != "assistant" else "not_adopted",
    }
    envelope = {
        "contract_name": "source-envelope.v1",
        "contract_version": 1,
        "source_id": source_id,
        "source_family": record.source_family,
        "source_instance": source_instance,
        "format_adapter": provider["default_adapter_id"],
        "custody_snapshot": {
            "snapshot_id": snapshot_id,
            "captured_at": normalized_captured_at,
            "snapshot_hash": snapshot_hash,
            "custody_pointer": custody_pointer,
            "immutable": True,
        },
        "native_identifiers": native_identifiers,
        "role": normalized_role,
        "event_timestamp": normalized_timestamp,
        "ingestion_timestamp": normalized_captured_at,
        "authority_class": authority_class,
        "body_hash": event_body_hash,
        "private_custody_pointer": f"{custody_pointer}#atom:{record.atom_id}",
        "historical_branding": provider["display_name"],
        "redacted_projection_pointer": f"source-envelope.v1.jsonl#{source_id}",
        "provider_metadata": provider_metadata,
    }
    if record.attachments:
        envelope["attachments"] = list(record.attachments)
    event = {
        "contract_name": "normalized-authority-event.v1",
        "contract_version": 1,
        "source_id": source_id,
        "source_family": record.source_family,
        "source_instance": source_instance,
        "provider_id": provider["provider_id"],
        "role": normalized_role,
        "kind": record.kind,
        "source": record.source_family,
        "body_hash": event_body_hash,
        "source_content_sha": f"sha256:{record.content_sha}",
        "authority_class": authority_class,
        "authority_detail": authority_detail,
        "origin_lane": origin_lane,
        "effective_lane": origin_lane,
        "adoption_state": provider_metadata["adoption_state"],
        "event_timestamp": normalized_timestamp,
        "snapshot_id": snapshot_id,
        "snapshot_hash": snapshot_hash,
        "native_identifiers": native_identifiers,
        "evidence_references": [record.input_reference, f"custody:{custody_pointer}"],
    }
    return ProjectionCandidate(record=record, envelope=envelope, event=event)


def apply_reviewed_adoptions(candidates: list[ProjectionCandidate]) -> None:
    operator_adoptions: dict[str, ProjectionCandidate] = {}
    for candidate in candidates:
        metadata = candidate.record.metadata
        if (
            candidate.event["role"] == "operator"
            and candidate.event["kind"] == "adoption"
            and metadata.get("review_state") == "reviewed"
            and isinstance(metadata.get("adopts_atom_id"), str)
        ):
            operator_adoptions[candidate.record.atom_id] = candidate

    for candidate in candidates:
        if candidate.event["role"] != "assistant":
            continue
        adoption_event_id = candidate.record.metadata.get("adoption_event_id")
        if not isinstance(adoption_event_id, str):
            continue
        adoption = operator_adoptions.get(adoption_event_id)
        if adoption is None:
            candidate.event["adoption_state"] = "unverified_reference"
            candidate.envelope["provider_metadata"]["adoption_state"] = "unverified_reference"
            continue
        if adoption.record.metadata.get("adopts_atom_id") != candidate.record.atom_id:
            candidate.event["adoption_state"] = "mismatched_reference"
            candidate.envelope["provider_metadata"]["adoption_state"] = "mismatched_reference"
            continue
        candidate.event["effective_lane"] = "operator_intent"
        candidate.event["adoption_state"] = "reviewed_operator_adoption"
        candidate.event["adoption_evidence_source_id"] = adoption.event["source_id"]
        candidate.envelope["provider_metadata"]["effective_lane"] = "operator_intent"
        candidate.envelope["provider_metadata"]["adoption_state"] = "reviewed_operator_adoption"
        candidate.envelope["provider_metadata"]["adoption_evidence_source_id"] = adoption.event[
            "source_id"
        ]
