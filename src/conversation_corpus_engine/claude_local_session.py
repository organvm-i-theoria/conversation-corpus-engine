#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import pbkdf2_hmac, sha256
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

DEFAULT_CLAUDE_LOCAL_ROOT = Path("/Users/4jp/Library/Application Support/Claude")
CLAUDE_COOKIE_HOST = ".claude.ai"
CLAUDE_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Claude/1.1.4498 Chrome/144.0.7559.173 Electron/40.4.1 Safari/537.36"
)
SAFE_STORAGE_SERVICES = (
    "Claude Safe Storage",
    "Chrome Safe Storage",
    "Chromium Safe Storage",
)
CLAUDE_COOKIE_NAMES = (
    "sessionKey",
    "cf_clearance",
    "lastActiveOrg",
    "routingHint",
    "__cf_bm",
    "__ssid",
    "ajs_user_id",
    "ajs_anonymous_id",
    "anthropic-consent-preferences",
    "app-shell-mode",
    "intercom-device-id-lupk8zyo",
    "intercom-session-lupk8zyo",
    "user-sidebar-pinned",
    "user-sidebar-visible-on-load",
)


class ClaudeLocalSessionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClaudeSessionArtifacts:
    local_root: Path
    safe_storage_service: str
    active_org_uuid: str
    account_uuid: str | None
    cookies: dict[str, str]


@dataclass(frozen=True)
class ClaudeHttpSession:
    headers: dict[str, str]
    cookie_header: str


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_claude_local_root(local_root: Path) -> Path:
    root = local_root.resolve()
    if not root.exists():
        raise FileNotFoundError(f"Claude local root does not exist: {root}")
    cookies_path = root / "Cookies"
    if not cookies_path.exists():
        raise FileNotFoundError(f"Claude local root does not contain Cookies: {cookies_path}")
    return root


def find_safe_storage_password() -> tuple[str, str]:
    for service in SAFE_STORAGE_SERVICES:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-w"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            password = result.stdout.strip()  # allow-secret
            if password:
                return service, password
    raise ClaudeLocalSessionError(
        "Unable to read a Chromium-style safe storage password for Claude from the macOS keychain.",
    )


def decrypt_chromium_cookie(
    encrypted_value: bytes, host_key: str, safe_storage_password: str
) -> str:
    if not encrypted_value:
        return ""
    if not encrypted_value.startswith(b"v10"):
        return encrypted_value.decode("utf-8", errors="replace")
    key = pbkdf2_hmac("sha1", safe_storage_password.encode("utf-8"), b"saltysalt", 1003, 16)
    iv = b" " * 16
    result = subprocess.run(
        [
            "openssl",
            "enc",
            "-aes-128-cbc",
            "-d",
            "-K",
            key.hex(),
            "-iv",
            iv.hex(),
            "-nopad",
        ],
        input=encrypted_value[3:],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise ClaudeLocalSessionError(
            f"OpenSSL failed to decrypt a Claude cookie: {stderr or 'unknown error'}"
        )
    padded = result.stdout
    if not padded:
        return ""
    pad_length = padded[-1]
    if pad_length < 1 or pad_length > 16:
        raise ClaudeLocalSessionError(
            f"Unexpected PKCS7 padding length while decrypting Claude cookie: {pad_length}"
        )
    decrypted = padded[:-pad_length]
    host_hash = sha256(host_key.encode("utf-8")).digest()
    if decrypted.startswith(host_hash):
        decrypted = decrypted[len(host_hash) :]
    return decrypted.decode("utf-8", errors="replace")


def load_cookie_value(
    connection: sqlite3.Connection,
    *,
    host_key: str,
    cookie_name: str,
    safe_storage_password: str,
) -> str | None:
    row = connection.execute(
        "select value, encrypted_value from cookies where host_key = ? and name = ?",
        (host_key, cookie_name),
    ).fetchone()
    if not row:
        return None
    value, encrypted_value = row
    if value:
        return value
    if encrypted_value:
        return decrypt_chromium_cookie(encrypted_value, host_key, safe_storage_password)
    return None


def load_claude_cookies(local_root: Path, *, safe_storage_password: str) -> dict[str, str]:
    cookies_path = local_root / "Cookies"
    connection = sqlite3.connect(cookies_path)
    try:
        cookies: dict[str, str] = {}
        for cookie_name in CLAUDE_COOKIE_NAMES:
            value = load_cookie_value(
                connection,
                host_key=CLAUDE_COOKIE_HOST,
                cookie_name=cookie_name,
                safe_storage_password=safe_storage_password,
            )
            if value:
                cookies[cookie_name] = value
        if "sessionKey" not in cookies:
            raise ClaudeLocalSessionError(
                "Claude session cookie `sessionKey` is not present in the local cookie store."
            )
        if "lastActiveOrg" not in cookies:
            raise ClaudeLocalSessionError(
                "Claude local session did not expose `lastActiveOrg` in the local cookie store."
            )
        return cookies
    finally:
        connection.close()


def claude_request_headers() -> dict[str, str]:
    return {
        "User-Agent": CLAUDE_USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://claude.ai",
        "Referer": "https://claude.ai/",
    }


def build_claude_requests_session(cookies: dict[str, str]) -> ClaudeHttpSession:
    return ClaudeHttpSession(
        headers=claude_request_headers(),
        cookie_header="; ".join(f"{name}={value}" for name, value in cookies.items()),
    )


def fetch_json(session: ClaudeHttpSession, url: str) -> Any:
    headers = dict(session.headers)
    if session.cookie_header:
        headers["Cookie"] = session.cookie_header
    request = Request(url, headers=headers, method="GET")
    with urlopen(request, timeout=30) as response:
        body = response.read()
    return json.loads(body.decode("utf-8"))


def fetch_claude_bootstrap(session: ClaudeHttpSession) -> dict[str, Any]:
    payload = fetch_json(session, "https://claude.ai/api/bootstrap")
    if not isinstance(payload, dict):
        raise ClaudeLocalSessionError("Claude bootstrap payload was not a JSON object.")
    return payload


def discover_claude_local_session(local_root: Path = DEFAULT_CLAUDE_LOCAL_ROOT) -> dict[str, Any]:
    local_root = resolve_claude_local_root(local_root)
    safe_storage_service, safe_storage_password = find_safe_storage_password()
    cookies = load_claude_cookies(local_root, safe_storage_password=safe_storage_password)
    session = build_claude_requests_session(cookies)
    bootstrap = fetch_claude_bootstrap(session)
    active_org_uuid = cookies["lastActiveOrg"]
    organizations = fetch_json(session, "https://claude.ai/api/organizations")
    projects = fetch_json(
        session, f"https://claude.ai/api/organizations/{active_org_uuid}/projects"
    )
    conversations = fetch_json(
        session, f"https://claude.ai/api/organizations/{active_org_uuid}/chat_conversations"
    )
    account = bootstrap.get("account") or {}
    return {
        "generated_at": now_iso(),
        "local_root": str(local_root),
        "adapter_type": "claude-local-session",
        "collection_scope": "local-session",
        "safe_storage_service": safe_storage_service,
        "session_state": "ready",
        "active_org_uuid": active_org_uuid,
        "account_uuid": account.get("uuid"),
        "account_email": account.get("email_address"),
        "account_display_name": account.get("display_name"),
        "organization_count": len(organizations) if isinstance(organizations, list) else 0,
        "project_count": len(projects) if isinstance(projects, list) else 0,
        "conversation_count": len(conversations) if isinstance(conversations, list) else 0,
        "recommended_command": (
            "cce provider import --provider claude --mode local-session --register --build"
        ),
        "calibration_only": True,
    }


def fetch_claude_local_session_bundle(
    local_root: Path = DEFAULT_CLAUDE_LOCAL_ROOT,
) -> dict[str, Any]:
    local_root = resolve_claude_local_root(local_root)
    safe_storage_service, safe_storage_password = find_safe_storage_password()
    cookies = load_claude_cookies(local_root, safe_storage_password=safe_storage_password)
    session = build_claude_requests_session(cookies)
    bootstrap = fetch_claude_bootstrap(session)
    account = bootstrap.get("account") or {}
    organizations = fetch_json(session, "https://claude.ai/api/organizations")
    active_org_uuid = cookies["lastActiveOrg"]
    projects = fetch_json(
        session, f"https://claude.ai/api/organizations/{active_org_uuid}/projects"
    )
    summaries = fetch_json(
        session, f"https://claude.ai/api/organizations/{active_org_uuid}/chat_conversations"
    )

    detailed_conversations: list[dict[str, Any]] = []
    detail_failures: list[dict[str, Any]] = []
    detail_root = f"https://claude.ai/api/organizations/{active_org_uuid}/chat_conversations"
    for summary in summaries:
        conversation_uuid = summary.get("uuid")
        if not conversation_uuid:
            continue
        try:
            detail = fetch_json(
                session, f"{detail_root}/{conversation_uuid}?tree=true&rendering_mode=messages"
            )
            detailed_conversations.append(detail)
        except Exception as exc:  # pragma: no cover - exercised live; unit tests mock this path.
            detail_failures.append({"uuid": conversation_uuid, "error": str(exc)})

    return {
        "generated_at": now_iso(),
        "local_root": str(local_root),
        "adapter_type": "claude-local-session",
        "collection_scope": "local-session",
        "safe_storage_service": safe_storage_service,
        "active_org_uuid": active_org_uuid,
        "account": account,
        "bootstrap": bootstrap,
        "organizations": organizations,
        "projects": projects,
        "conversation_summaries": summaries,
        "conversations": detailed_conversations,
        "conversation_detail_failures": detail_failures,
        "users": [account] if account else [],
        "memories": [],
        "cookie_names": sorted(cookies.keys()),
    }


def render_discovery_text(payload: dict[str, Any]) -> str:
    lines = [
        f"Claude local root: {payload['local_root']}",
        f"Generated: {payload['generated_at']}",
        f"Session state: {payload['session_state']}",
        f"Safe storage service: {payload['safe_storage_service']}",
        f"Active org: {payload['active_org_uuid']}",
        f"Organizations: {payload['organization_count']}",
        f"Projects: {payload['project_count']}",
        f"Conversations: {payload['conversation_count']}",
        f"Calibration only: {payload['calibration_only']}",
        f"Recommended command: {payload['recommended_command']}",
    ]
    if payload.get("account_email"):
        lines.append(f"Account: {payload['account_email']}")
    return "\n".join(lines)
