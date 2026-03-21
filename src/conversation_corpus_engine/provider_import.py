from __future__ import annotations

from pathlib import Path
from typing import Any

from .claude_local_session import DEFAULT_CLAUDE_LOCAL_ROOT
from .evaluation_bootstrap import bootstrap_provider_evaluation
from .federation import build_federation, upsert_corpus
from .import_chatgpt_export_corpus import import_chatgpt_export_corpus
from .import_claude_export_corpus import import_claude_export_corpus
from .import_claude_local_session_corpus import import_claude_local_session_corpus
from .import_document_export_corpus import import_document_export_corpus
from .provider_catalog import (
    conventional_corpus_root,
    default_source_drop_root,
    get_provider_config,
)
from .provider_exports import (
    resolve_chatgpt_source_path,
    resolve_claude_source_path,
    resolve_document_export_source_path,
)


def bootstrap_manual_review(
    provider_slug: str,
    target_root: Path,
    *,
    project_root: Path,
    full_eval: bool = False,
) -> dict[str, Any]:
    return bootstrap_provider_evaluation(
        project_root=project_root,
        provider=provider_slug,
        target_root=target_root,
        full_eval=full_eval,
    )


def resolve_provider_import_source(
    *,
    provider: str,
    mode: str,
    project_root: Path,
    source_drop_root: Path | None = None,
    source_path: Path | None = None,
    local_root: Path | None = None,
) -> tuple[Path, dict[str, str]]:
    if source_path is not None:
        return source_path.resolve(), {"resolution": "explicit-source-path"}

    if provider == "claude" and mode == "local-session":
        resolved_local_root = (local_root or DEFAULT_CLAUDE_LOCAL_ROOT).resolve()
        return resolved_local_root, {"resolution": "local-session-root"}

    resolved_source_drop_root = (
        source_drop_root or default_source_drop_root(project_root)
    ).resolve()
    inbox_root = resolved_source_drop_root / provider / "inbox"
    if provider == "chatgpt":
        return resolve_chatgpt_source_path(inbox_root), {
            "resolution": "provider-inbox",
            "inbox_root": str(inbox_root),
        }
    if provider == "claude":
        return resolve_claude_source_path(inbox_root), {
            "resolution": "provider-inbox",
            "inbox_root": str(inbox_root),
        }
    return resolve_document_export_source_path(inbox_root, provider=provider), {
        "resolution": "provider-inbox",
        "inbox_root": str(inbox_root),
    }


def default_output_root(
    *,
    provider: str,
    mode: str,
    project_root: Path,
    source_drop_root: Path | None,
) -> Path:
    config = get_provider_config(provider)
    if provider == "claude" and mode == "local-session":
        corpus_id = config["default_corpus_id"]
    else:
        corpus_id = (
            config["default_corpus_id"] if provider != "claude" else config["fallback_corpus_id"]
        )
    resolved_source_drop_root = (
        source_drop_root or default_source_drop_root(project_root)
    ).resolve()
    return conventional_corpus_root(resolved_source_drop_root, corpus_id)


def import_provider_corpus(
    *,
    project_root: Path,
    provider: str,
    mode: str = "upload",
    source_drop_root: Path | None = None,
    source_path: Path | None = None,
    local_root: Path | None = None,
    output_root: Path | None = None,
    corpus_id: str | None = None,
    name: str | None = None,
    register: bool = False,
    build: bool = False,
    bootstrap_eval: bool = True,
) -> dict[str, Any]:
    config = get_provider_config(provider)
    resolved_source_path, resolution = resolve_provider_import_source(
        provider=provider,
        mode=mode,
        project_root=project_root,
        source_drop_root=source_drop_root,
        source_path=source_path,
        local_root=local_root,
    )
    resolved_output_root = (
        output_root
        or default_output_root(
            provider=provider,
            mode=mode,
            project_root=project_root,
            source_drop_root=source_drop_root,
        )
    ).resolve()
    resolved_corpus_id = corpus_id
    resolved_name = name

    if provider == "claude" and mode == "local-session":
        resolved_corpus_id = resolved_corpus_id or config["default_corpus_id"]
        resolved_name = resolved_name or config["default_corpus_name"]
        import_result = import_claude_local_session_corpus(
            resolved_source_path,
            resolved_output_root,
            corpus_id=resolved_corpus_id,
            name=resolved_name,
        )
    elif provider == "chatgpt":
        resolved_corpus_id = resolved_corpus_id or config["default_corpus_id"]
        resolved_name = resolved_name or config["default_corpus_name"]
        import_result = import_chatgpt_export_corpus(
            resolved_source_path,
            resolved_output_root,
            corpus_id=resolved_corpus_id,
            name=resolved_name,
        )
    elif provider == "claude":
        resolved_corpus_id = resolved_corpus_id or config["fallback_corpus_id"]
        resolved_name = resolved_name or config["fallback_corpus_name"]
        import_result = import_claude_export_corpus(
            resolved_source_path,
            resolved_output_root,
            corpus_id=resolved_corpus_id,
            name=resolved_name,
        )
    else:
        resolved_corpus_id = resolved_corpus_id or config["default_corpus_id"]
        resolved_name = resolved_name or config["default_corpus_name"]
        import_result = import_document_export_corpus(
            resolved_source_path,
            resolved_output_root,
            provider_slug=provider,
            corpus_id=resolved_corpus_id,
            name=resolved_name,
        )

    bootstrap_result = (
        bootstrap_manual_review(
            provider,
            resolved_output_root,
            project_root=project_root.resolve(),
            full_eval=False,
        )
        if bootstrap_eval
        else None
    )
    registered_entry = None
    federation_result = None
    if register:
        registered_entry = upsert_corpus(
            project_root.resolve(),
            resolved_output_root,
            corpus_id=resolved_corpus_id,
            name=resolved_name,
        )
    if register and build:
        federation_result = build_federation(project_root.resolve())

    return {
        "provider": provider,
        "mode": mode,
        "source_path": str(resolved_source_path),
        "output_root": str(resolved_output_root),
        "corpus_id": resolved_corpus_id,
        "name": resolved_name,
        "calibration_only": not register and not build,
        "resolution": resolution,
        "import_result": import_result,
        "bootstrap_result": bootstrap_result,
        "registered_entry": registered_entry,
        "federation_result": federation_result,
    }
