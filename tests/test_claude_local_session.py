from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversation_corpus_engine import claude_local_session as module  # noqa: E402


def seed_cookie_db(path: Path, rows: list[tuple[str, str, str, bytes]]) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "create table cookies (host_key text, name text, value text, encrypted_value blob)"
        )
        connection.executemany("insert into cookies values (?, ?, ?, ?)", rows)
        connection.commit()
    finally:
        connection.close()


def test_resolve_claude_local_root_requires_cookies_file(tmp_path: Path) -> None:
    root = tmp_path / "claude-local"
    root.mkdir()

    with pytest.raises(FileNotFoundError, match="does not contain Cookies"):
        module.resolve_claude_local_root(root)

    (root / "Cookies").write_text("cookies", encoding="utf-8")
    assert module.resolve_claude_local_root(root) == root.resolve()


def test_find_safe_storage_password_returns_first_success(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_run(args: list[str], **_: object) -> SimpleNamespace:
        service = args[3]
        calls.append(service)
        if service == module.SAFE_STORAGE_SERVICES[1]:
            return SimpleNamespace(returncode=0, stdout="secret\n", stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="missing")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    service, credential = module.find_safe_storage_password()

    assert service == module.SAFE_STORAGE_SERVICES[1]
    assert credential == "secret"
    assert calls[:2] == list(module.SAFE_STORAGE_SERVICES[:2])


def test_find_safe_storage_password_raises_when_no_service_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="missing"),
    )

    with pytest.raises(module.ClaudeLocalSessionError, match="safe storage password"):
        module.find_safe_storage_password()


def test_decrypt_chromium_cookie_returns_plaintext_for_non_v10() -> None:
    assert module.decrypt_chromium_cookie(b"plain-cookie", module.CLAUDE_COOKIE_HOST, "secret") == (
        "plain-cookie"
    )


def test_decrypt_chromium_cookie_handles_host_hash_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    host_hash = module.sha256(module.CLAUDE_COOKIE_HOST.encode("utf-8")).digest()
    padded = host_hash + b"session-value" + b"\x01"
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=padded, stderr=b""),
    )

    result = module.decrypt_chromium_cookie(
        b"v10ciphertext",
        module.CLAUDE_COOKIE_HOST,
        "secret",
    )

    assert result == "session-value"


def test_decrypt_chromium_cookie_raises_for_openssl_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout=b"", stderr=b"boom"),
    )

    with pytest.raises(module.ClaudeLocalSessionError, match="OpenSSL failed"):
        module.decrypt_chromium_cookie(b"v10ciphertext", module.CLAUDE_COOKIE_HOST, "secret")


def test_decrypt_chromium_cookie_raises_for_invalid_padding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=b"bad\x11", stderr=b""),
    )

    with pytest.raises(module.ClaudeLocalSessionError, match="Unexpected PKCS7 padding length"):
        module.decrypt_chromium_cookie(b"v10ciphertext", module.CLAUDE_COOKIE_HOST, "secret")


def test_load_cookie_value_prefers_plain_value_and_can_decrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(
            "create table cookies (host_key text, name text, value text, encrypted_value blob)"
        )
        connection.execute(
            "insert into cookies values (?, ?, ?, ?)",
            (module.CLAUDE_COOKIE_HOST, "sessionKey", "plain", b""),
        )
        connection.execute(
            "insert into cookies values (?, ?, ?, ?)",
            (module.CLAUDE_COOKIE_HOST, "lastActiveOrg", "", b"cipher"),
        )
        connection.commit()

        monkeypatch.setattr(module, "decrypt_chromium_cookie", lambda *args, **kwargs: "decrypted")

        assert (
            module.load_cookie_value(
                connection,
                host_key=module.CLAUDE_COOKIE_HOST,
                cookie_name="sessionKey",
                safe_storage_password="secret",
            )
            == "plain"
        )
        assert (
            module.load_cookie_value(
                connection,
                host_key=module.CLAUDE_COOKIE_HOST,
                cookie_name="lastActiveOrg",
                safe_storage_password="secret",
            )
            == "decrypted"
        )
        assert (
            module.load_cookie_value(
                connection,
                host_key=module.CLAUDE_COOKIE_HOST,
                cookie_name="missing",
                safe_storage_password="secret",
            )
            is None
        )
    finally:
        connection.close()


def test_load_claude_cookies_requires_session_and_org(tmp_path: Path) -> None:
    local_root = tmp_path / "claude-local"
    local_root.mkdir()
    cookies_path = local_root / "Cookies"
    seed_cookie_db(
        cookies_path,
        [
            (module.CLAUDE_COOKIE_HOST, "sessionKey", "session", b""),
            (module.CLAUDE_COOKIE_HOST, "lastActiveOrg", "org-1", b""),
        ],
    )

    cookies = module.load_claude_cookies(local_root, safe_storage_password="secret")
    assert cookies["sessionKey"] == "session"
    assert cookies["lastActiveOrg"] == "org-1"

    missing_root = tmp_path / "missing-org"
    missing_root.mkdir()
    seed_cookie_db(
        missing_root / "Cookies",
        [(module.CLAUDE_COOKIE_HOST, "sessionKey", "session", b"")],
    )
    with pytest.raises(module.ClaudeLocalSessionError, match="lastActiveOrg"):
        module.load_claude_cookies(missing_root, safe_storage_password="secret")


def test_claude_request_headers_and_session_builder() -> None:
    headers = module.claude_request_headers()
    session = module.build_claude_requests_session({"a": "1", "b": "2"})

    assert headers["Origin"] == "https://claude.ai"
    assert session.headers == headers
    assert session.cookie_header == "a=1; b=2"


def test_fetch_json_uses_cookie_header(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyResponse:
        def __enter__(self) -> "DummyResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def read(self) -> bytes:
            return b'{"ok": true}'

    def fake_urlopen(request, timeout: int) -> DummyResponse:
        assert timeout == 30
        assert request.full_url == "https://claude.ai/api/test"
        assert request.get_header("Cookie") == "sessionKey=abc"
        return DummyResponse()

    monkeypatch.setattr(module, "urlopen", fake_urlopen)

    payload = module.fetch_json(
        module.ClaudeHttpSession(headers={"Accept": "application/json"}, cookie_header="sessionKey=abc"),
        "https://claude.ai/api/test",
    )

    assert payload == {"ok": True}


def test_fetch_claude_bootstrap_requires_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "fetch_json", lambda session, url: [])

    with pytest.raises(module.ClaudeLocalSessionError, match="bootstrap payload was not a JSON object"):
        module.fetch_claude_bootstrap(module.ClaudeHttpSession(headers={}, cookie_header=""))


def test_discover_claude_local_session_assembles_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    local_root = Path("/tmp/claude")
    monkeypatch.setattr(module, "resolve_claude_local_root", lambda path: local_root)
    monkeypatch.setattr(module, "find_safe_storage_password", lambda: ("Claude Safe Storage", "secret"))
    monkeypatch.setattr(
        module,
        "load_claude_cookies",
        lambda root, safe_storage_password: {"sessionKey": "session", "lastActiveOrg": "org-1"},
    )
    monkeypatch.setattr(
        module,
        "build_claude_requests_session",
        lambda cookies: module.ClaudeHttpSession(headers={}, cookie_header="session"),
    )
    monkeypatch.setattr(
        module,
        "fetch_claude_bootstrap",
        lambda session: {
            "account": {
                "uuid": "acct-1",
                "email_address": "user@example.com",
                "display_name": "User",
            }
        },
    )

    def fake_fetch_json(session: module.ClaudeHttpSession, url: str) -> object:
        if url.endswith("/organizations"):
            return [{"uuid": "org-1"}]
        if url.endswith("/projects"):
            return [{"uuid": "project-1"}, {"uuid": "project-2"}]
        if url.endswith("/chat_conversations"):
            return [{"uuid": "conv-1"}]
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(module, "fetch_json", fake_fetch_json)

    payload = module.discover_claude_local_session(local_root)

    assert payload["local_root"] == str(local_root)
    assert payload["session_state"] == "ready"
    assert payload["active_org_uuid"] == "org-1"
    assert payload["organization_count"] == 1
    assert payload["project_count"] == 2
    assert payload["conversation_count"] == 1


def test_fetch_claude_local_session_bundle_collects_details_and_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_root = Path("/tmp/claude")
    monkeypatch.setattr(module, "resolve_claude_local_root", lambda path: local_root)
    monkeypatch.setattr(module, "find_safe_storage_password", lambda: ("Claude Safe Storage", "secret"))
    monkeypatch.setattr(
        module,
        "load_claude_cookies",
        lambda root, safe_storage_password: {"sessionKey": "session", "lastActiveOrg": "org-1"},
    )
    monkeypatch.setattr(
        module,
        "build_claude_requests_session",
        lambda cookies: module.ClaudeHttpSession(headers={}, cookie_header="session"),
    )
    monkeypatch.setattr(
        module,
        "fetch_claude_bootstrap",
        lambda session: {"account": {"uuid": "acct-1", "email_address": "user@example.com"}},
    )

    def fake_fetch_json(session: module.ClaudeHttpSession, url: str) -> object:
        if url.endswith("/organizations"):
            return [{"uuid": "org-1"}]
        if url.endswith("/projects"):
            return [{"uuid": "project-1"}]
        if url.endswith("/chat_conversations"):
            return [{"uuid": "conv-1"}, {"uuid": "conv-2"}, {"title": "skip"}]
        if "chat_conversations/conv-1" in url:
            return {"uuid": "conv-1", "chat_messages": []}
        if "chat_conversations/conv-2" in url:
            raise RuntimeError("detail failed")
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(module, "fetch_json", fake_fetch_json)

    bundle = module.fetch_claude_local_session_bundle(local_root)

    assert bundle["active_org_uuid"] == "org-1"
    assert bundle["conversations"] == [{"uuid": "conv-1", "chat_messages": []}]
    assert bundle["conversation_detail_failures"] == [{"uuid": "conv-2", "error": "detail failed"}]
    assert bundle["cookie_names"] == ["lastActiveOrg", "sessionKey"]


# ---------------------------------------------------------------------------
# Delta-sync / acquisition state tests
# ---------------------------------------------------------------------------


def test_acquisition_state_persistence_roundtrips(tmp_path: Path) -> None:
    conversations = {
        "conv-aaa": {"updated_at": "2026-03-25T00:00:00Z", "fetched_at": "2026-03-25T00:00:00Z"},
        "conv-bbb": {"updated_at": "2026-03-25T01:00:00Z", "fetched_at": "2026-03-25T01:00:00Z"},
    }
    report = {"fetched_count": 2, "reused_count": 0}
    module.save_acquisition_state(tmp_path, conversations, report=report)
    loaded = module.load_prior_acquisition(tmp_path)

    assert loaded["conv-aaa"]["updated_at"] == "2026-03-25T00:00:00Z"
    assert loaded["conv-bbb"]["updated_at"] == "2026-03-25T01:00:00Z"
    assert len(loaded) == 2


def test_load_prior_acquisition_returns_empty_when_missing(tmp_path: Path) -> None:
    assert module.load_prior_acquisition(tmp_path) == {}


def test_conversation_payload_cache_roundtrips(tmp_path: Path) -> None:
    payload = {"uuid": "conv-aaa", "chat_messages": [{"text": "hello"}]}
    path = module.cache_conversation_payload(tmp_path, "conv-aaa", payload)
    assert path.exists()

    loaded = module.load_cached_conversation(tmp_path, "conv-aaa")
    assert loaded is not None
    assert loaded["uuid"] == "conv-aaa"


def test_load_cached_conversation_returns_none_when_missing(tmp_path: Path) -> None:
    assert module.load_cached_conversation(tmp_path, "nonexistent") is None


def test_delta_aware_fetch_reuses_cached_conversations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local_root = Path("/tmp/claude")
    output_root = tmp_path / "output"
    monkeypatch.setattr(module, "resolve_claude_local_root", lambda path: local_root)
    monkeypatch.setattr(module, "find_safe_storage_password", lambda: ("Claude Safe Storage", "secret"))
    monkeypatch.setattr(
        module,
        "load_claude_cookies",
        lambda root, safe_storage_password: {"sessionKey": "session", "lastActiveOrg": "org-1"},
    )
    monkeypatch.setattr(
        module,
        "build_claude_requests_session",
        lambda cookies: module.ClaudeHttpSession(headers={}, cookie_header="session"),
    )
    monkeypatch.setattr(
        module,
        "fetch_claude_bootstrap",
        lambda session: {"account": {"uuid": "acct-1"}},
    )

    # Pre-cache conv-1
    module.cache_conversation_payload(
        output_root, "conv-1", {"uuid": "conv-1", "chat_messages": [], "updated_at": "T1"}
    )

    fetch_calls: list[str] = []

    def fake_fetch_json(session: module.ClaudeHttpSession, url: str) -> object:
        if url.endswith("/organizations"):
            return [{"uuid": "org-1"}]
        if url.endswith("/projects"):
            return []
        if url.endswith("/chat_conversations"):
            return [
                {"uuid": "conv-1", "updated_at": "T1"},
                {"uuid": "conv-2", "updated_at": "T2"},
            ]
        if "chat_conversations/conv-2" in url:
            fetch_calls.append("conv-2")
            return {"uuid": "conv-2", "chat_messages": [{"text": "new"}], "updated_at": "T2"}
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(module, "fetch_json", fake_fetch_json)

    prior_state = {"conv-1": {"updated_at": "T1"}}
    bundle = module.fetch_claude_local_session_bundle(
        local_root, prior_state=prior_state, output_root=output_root
    )

    assert bundle["reused_count"] == 1
    assert bundle["fetched_count"] == 1
    assert fetch_calls == ["conv-2"]
    assert len(bundle["conversations"]) == 2
    assert bundle["acquisition_report"]["reused_count"] == 1
    assert bundle["acquisition_report"]["fetched_count"] == 1


def test_render_discovery_text_includes_account_line_when_present() -> None:
    text = module.render_discovery_text(
        {
            "local_root": "/tmp/claude",
            "generated_at": "2026-03-25T00:00:00+00:00",
            "session_state": "ready",
            "safe_storage_service": "Claude Safe Storage",
            "active_org_uuid": "org-1",
            "organization_count": 1,
            "project_count": 2,
            "conversation_count": 3,
            "calibration_only": True,
            "recommended_command": "cce provider import --provider claude --mode local-session --register --build",
            "account_email": "user@example.com",
        }
    )

    assert "Claude local root: /tmp/claude" in text
    assert "Account: user@example.com" in text
