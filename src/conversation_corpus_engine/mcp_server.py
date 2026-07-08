from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TextIO

from . import __version__
from .answering import render_answer_text
from .federation import build_federated_answer, list_registered_corpora
from .paths import default_project_root
from .provider_catalog import default_source_drop_root
from .provider_readiness import build_provider_readiness, render_provider_readiness_text

MCP_PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = {"2024-11-05", "2025-03-26", MCP_PROTOCOL_VERSION}
SERVER_NAME = "conversation-corpus-engine"

JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603

SESSION = {"project_root": default_project_root()}


def set_session_project_root(project_root: Path) -> None:
    SESSION["project_root"] = project_root.expanduser().resolve()


def resolve_project_root(arguments: dict[str, Any] | None) -> Path:
    raw_value = (arguments or {}).get("project_root")
    if not raw_value:
        return SESSION["project_root"]
    return Path(str(raw_value)).expanduser().resolve()


def text_result(text: str, structured_content: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "content": [{"type": "text", "text": text}],
        "isError": False,
    }
    if structured_content is not None:
        result["structuredContent"] = structured_content
    return result


def error_tool_result(
    message: str, structured_content: dict[str, Any] | None = None
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }
    if structured_content is not None:
        result["structuredContent"] = structured_content
    return result


def mcp_tools() -> list[dict[str, Any]]:
    project_root_property = {
        "type": "string",
        "description": "Project root that contains CCE state, federation, and reports.",
    }
    return [
        {
            "name": "cce_search",
            "title": "Search Federated Conversation Corpus",
            "description": "Search registered CCE corpora and return a grounded answer dossier.",
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language query to answer from the corpus.",
                    },
                    "project_root": project_root_property,
                    "mode": {
                        "type": "string",
                        "enum": ["family_brief", "action", "unresolved", "timeline"],
                        "description": "Optional retrieval mode for focused ledger searches.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum retrieval results to consider.",
                        "minimum": 1,
                        "maximum": 25,
                    },
                    "corpus_id": {
                        "type": "string",
                        "description": "Optional registered corpus ID to search within.",
                    },
                },
            },
            "annotations": {"readOnlyHint": True},
        },
        {
            "name": "cce_list_corpora",
            "title": "List Registered Corpora",
            "description": "List corpus registrations visible to the CCE federation registry.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_root": project_root_property,
                    "active_only": {
                        "type": "boolean",
                        "description": "Only include active corpus registrations.",
                    },
                },
            },
            "annotations": {"readOnlyHint": True},
        },
        {
            "name": "cce_provider_readiness",
            "title": "Inspect Provider Readiness",
            "description": "Summarize provider intake readiness for a project/source-drop pair.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_root": project_root_property,
                    "source_drop_root": {
                        "type": "string",
                        "description": "Provider source-drop root. Defaults to the project setting.",
                    },
                },
            },
            "annotations": {"readOnlyHint": True},
        },
    ]


def call_cce_search(arguments: dict[str, Any]) -> dict[str, Any]:
    query = str(arguments.get("query") or "").strip()
    if not query:
        return error_tool_result("Missing required argument: query")
    project_root = resolve_project_root(arguments)
    raw_limit = arguments.get("limit", 8)
    try:
        limit = max(1, min(25, int(raw_limit)))
    except (TypeError, ValueError):
        return error_tool_result("Argument limit must be an integer.")
    answer = build_federated_answer(
        project_root,
        query,
        mode=arguments.get("mode"),
        limit=limit,
        corpus_id=arguments.get("corpus_id"),
    )
    return text_result(render_answer_text(answer), answer)


def call_cce_list_corpora(arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = resolve_project_root(arguments)
    active_only = bool(arguments.get("active_only", False))
    corpora = list_registered_corpora(project_root, active_only=active_only)
    payload = {
        "project_root": str(project_root),
        "active_only": active_only,
        "count": len(corpora),
        "corpora": corpora,
    }
    if corpora:
        lines = [
            f"{item['corpus_id']}: {item['name']} [{item.get('status', 'active')}]"
            for item in corpora
        ]
    else:
        lines = ["No registered corpora."]
    return text_result("\n".join(lines), payload)


def call_cce_provider_readiness(arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = resolve_project_root(arguments)
    raw_source_drop_root = arguments.get("source_drop_root")
    source_drop_root = (
        Path(str(raw_source_drop_root)).expanduser().resolve()
        if raw_source_drop_root
        else default_source_drop_root(project_root)
    )
    payload = build_provider_readiness(project_root, source_drop_root)
    return text_result(render_provider_readiness_text(payload), payload)


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved_arguments = arguments or {}
    if name == "cce_search":
        return call_cce_search(resolved_arguments)
    if name == "cce_list_corpora":
        return call_cce_list_corpora(resolved_arguments)
    if name == "cce_provider_readiness":
        return call_cce_provider_readiness(resolved_arguments)
    return error_tool_result(f"Unknown CCE MCP tool: {name}")


def jsonrpc_result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def jsonrpc_error(
    request_id: Any,
    code: int,
    message: str,
    *,
    data: Any | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def initialize_result(params: dict[str, Any] | None = None) -> dict[str, Any]:
    requested_version = (params or {}).get("protocolVersion")
    protocol_version = (
        requested_version
        if requested_version in SUPPORTED_PROTOCOL_VERSIONS
        else MCP_PROTOCOL_VERSION
    )
    return {
        "protocolVersion": protocol_version,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {
            "name": SERVER_NAME,
            "title": "Conversation Corpus Engine",
            "version": __version__,
        },
        "instructions": (
            "Use cce_search for read-only answers from registered conversation corpora. "
            "Use cce_list_corpora and cce_provider_readiness to inspect available context."
        ),
    }


def handle_jsonrpc_message(message: Any) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        return jsonrpc_error(None, JSONRPC_INVALID_REQUEST, "Invalid JSON-RPC request.")
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    is_notification = "id" not in message
    if not isinstance(method, str):
        if is_notification:
            return None
        return jsonrpc_error(request_id, JSONRPC_INVALID_REQUEST, "Missing JSON-RPC method.")

    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return jsonrpc_result(request_id, initialize_result(params))
    if method == "ping":
        return jsonrpc_result(request_id, {})
    if method == "tools/list":
        return jsonrpc_result(request_id, {"tools": mcp_tools()})
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return jsonrpc_error(
                request_id,
                JSONRPC_INVALID_PARAMS,
                "tools/call requires string name and object arguments.",
            )
        try:
            return jsonrpc_result(request_id, call_tool(name, arguments))
        except Exception as exc:  # pragma: no cover - defensive protocol boundary
            return jsonrpc_error(request_id, JSONRPC_INTERNAL_ERROR, str(exc))
    if is_notification:
        return None
    return jsonrpc_error(request_id, JSONRPC_METHOD_NOT_FOUND, f"Unknown method: {method}")


def serve_stdio(
    *,
    project_root: Path | None = None,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> None:
    if project_root is not None:
        set_session_project_root(project_root)
    stdin = input_stream or sys.stdin
    stdout = output_stream or sys.stdout
    for raw_line in stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            response = jsonrpc_error(None, JSONRPC_PARSE_ERROR, "Parse error.", data=str(exc))
        else:
            response = handle_jsonrpc_message(message)
        if response is None:
            continue
        stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
        stdout.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Conversation Corpus Engine MCP server")
    parser.add_argument("--project-root", type=Path, default=default_project_root())
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    serve_stdio(project_root=args.project_root)


if __name__ == "__main__":
    main()
