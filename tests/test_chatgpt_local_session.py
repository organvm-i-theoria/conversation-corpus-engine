from __future__ import annotations

import json
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversation_corpus_engine import chatgpt_local_session as module  # noqa: E402


def build_binary_cookie_jar(cookies: list[dict[str, str]]) -> bytes:
    """Build a minimal Apple binary cookie jar for testing."""
    pages: list[bytes] = []
    page_cookies: list[bytes] = []
    for cookie in cookies:
        domain = cookie["domain"].encode("utf-8") + b"\x00"
        name = cookie["name"].encode("utf-8") + b"\x00"
        path = cookie.get("path", "/").encode("utf-8") + b"\x00"
        value = cookie["value"].encode("utf-8") + b"\x00"
        flags = 0
        if cookie.get("secure"):
            flags |= 1
        if cookie.get("http_only"):
            flags |= 4

        header_size = 32
        domain_offset = header_size
        name_offset = domain_offset + len(domain)
        path_offset = name_offset + len(name)
        value_offset = path_offset + len(path)
        total_size = value_offset + len(value)

        chunk = bytearray(total_size)
        struct.pack_into("<I", chunk, 0, total_size)
        struct.pack_into("<I", chunk, 8, flags)
        struct.pack_into("<I", chunk, 16, domain_offset)
        struct.pack_into("<I", chunk, 20, name_offset)
        struct.pack_into("<I", chunk, 24, path_offset)
        struct.pack_into("<I", chunk, 28, value_offset)
        chunk[domain_offset : domain_offset + len(domain)] = domain
        chunk[name_offset : name_offset + len(name)] = name
        chunk[path_offset : path_offset + len(path)] = path
        chunk[value_offset : value_offset + len(value)] = value
        page_cookies.append(bytes(chunk))

    cookie_count = len(page_cookies)
    offsets_area_size = 8 + 4 * cookie_count
    cookie_offsets = []
    running_offset = offsets_area_size
    for pc in page_cookies:
        cookie_offsets.append(running_offset)
        running_offset += len(pc)

    page = bytearray()
    page += struct.pack("<I", 0x00000100)  # page header magic
    page += struct.pack("<I", cookie_count)
    for co in cookie_offsets:
        page += struct.pack("<I", co)
    for pc in page_cookies:
        page += pc
    page_bytes = bytes(page)
    pages.append(page_bytes)

    data = bytearray()
    data += b"cook"
    data += struct.pack(">I", len(pages))
    for p in pages:
        data += struct.pack(">I", len(p))
    for p in pages:
        data += p
    return bytes(data)


def test_parse_binary_cookies_extracts_domain_name_value(tmp_path: Path) -> None:
    jar = tmp_path / "test.binarycookies"
    jar.write_bytes(
        build_binary_cookie_jar(
            [
                {"domain": ".chatgpt.com", "name": "session", "value": "abc123"},
                {"domain": ".openai.com", "name": "oai-did", "value": "device-1"},
            ]
        )
    )

    cookies = module.parse_binary_cookies(jar)

    assert len(cookies) == 2
    assert cookies[0].domain == ".chatgpt.com"
    assert cookies[0].name == "session"
    assert cookies[0].value == "abc123"
    assert cookies[1].name == "oai-did"
    assert cookies[1].value == "device-1"


def test_parse_binary_cookies_rejects_non_cook_magic(tmp_path: Path) -> None:
    jar = tmp_path / "bad.binarycookies"
    jar.write_bytes(b"BAAD" + b"\x00" * 100)

    with pytest.raises(module.ChatGPTLocalSessionError, match="Unsupported cookie jar"):
        module.parse_binary_cookies(jar)


def test_cookie_matches_host_handles_domain_prefix() -> None:
    cookie = module.Cookie(
        domain=".chatgpt.com", name="x", path="/", value="y", secure=False, http_only=False
    )
    assert module.cookie_matches_host(cookie, "chatgpt.com")
    assert module.cookie_matches_host(cookie, "www.chatgpt.com")
    assert not module.cookie_matches_host(cookie, "evil-chatgpt.com")


def test_build_cookie_header_selects_matching_cookies() -> None:
    cookies = [
        module.Cookie(".chatgpt.com", "a", "/", "1", False, False),
        module.Cookie(".openai.com", "b", "/", "2", False, False),
    ]

    header = module.build_cookie_header(cookies, "https://chatgpt.com/api/test")
    assert header == "a=1"


def test_find_cookie_value_returns_match_or_empty() -> None:
    cookies = [
        module.Cookie(".chatgpt.com", "oai-did", "/", "device-42", False, False),
    ]

    assert module.find_cookie_value(cookies, "chatgpt.com", "oai-did") == "device-42"
    assert module.find_cookie_value(cookies, "chatgpt.com", "missing") == ""


def test_resolve_chatgpt_cookie_jar_validates_existence_and_magic(tmp_path: Path) -> None:
    with pytest.raises(module.ChatGPTLocalSessionError, match="does not exist"):
        module.resolve_chatgpt_cookie_jar(tmp_path / "nonexistent.binarycookies")

    bad = tmp_path / "bad.binarycookies"
    bad.write_bytes(b"NOPE" + b"\x00" * 100)
    with pytest.raises(module.ChatGPTLocalSessionError, match="unexpected format"):
        module.resolve_chatgpt_cookie_jar(bad)

    good = tmp_path / "good.binarycookies"
    good.write_bytes(build_binary_cookie_jar([{"domain": ".chatgpt.com", "name": "x", "value": "y"}]))
    assert module.resolve_chatgpt_cookie_jar(good) == good.resolve()


def test_build_chatgpt_session_extracts_token_and_account(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    jar = tmp_path / "test.binarycookies"
    jar.write_bytes(
        build_binary_cookie_jar(
            [
                {"domain": ".chatgpt.com", "name": "session", "value": "sess"},
                {"domain": ".chatgpt.com", "name": "oai-did", "value": "device-1"},
            ]
        )
    )

    monkeypatch.setattr(
        module,
        "_fetch_session",
        lambda cookies: {
            "accessToken": "tok-abc",  # allow-secret
            "account": {"id": "acct-1", "account_id": "acct-1"},
            "user": {"email": "user@example.com"},
        },
    )

    session = module.build_chatgpt_session(jar)

    assert session.access_token == "tok-abc"  # allow-secret
    assert session.account_id == "acct-1"
    assert session.device_id == "device-1"


def test_discover_chatgpt_local_session_returns_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    jar = tmp_path / "test.binarycookies"
    jar.write_bytes(
        build_binary_cookie_jar([{"domain": ".chatgpt.com", "name": "x", "value": "y"}])
    )

    monkeypatch.setattr(
        module,
        "build_chatgpt_session",
        lambda cookie_jar: module.ChatGPTHttpSession(
            cookies=[],
            session_payload={
                "account": {"id": "acct-1"},
                "user": {"email": "user@example.com", "name": "Test"},
            },
            access_token="tok",  # allow-secret
            account_id="acct-1",
            device_id="dev-1",
        ),
    )
    monkeypatch.setattr(
        module,
        "fetch_json",
        lambda session, url: {"total": 42, "items": []},
    )

    payload = module.discover_chatgpt_local_session(jar)

    assert payload["session_state"] == "ready"
    assert payload["conversation_count"] == 42
    assert payload["account_email"] == "user@example.com"


def test_fetch_chatgpt_local_session_bundle_returns_conversations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    jar = tmp_path / "test.binarycookies"
    jar.write_bytes(
        build_binary_cookie_jar([{"domain": ".chatgpt.com", "name": "x", "value": "y"}])
    )

    monkeypatch.setattr(
        module,
        "build_chatgpt_session",
        lambda cookie_jar: module.ChatGPTHttpSession(
            cookies=[],
            session_payload={
                "account": {"id": "acct-1"},
                "user": {"email": "user@example.com"},
            },
            access_token="tok",  # allow-secret
            account_id="acct-1",
            device_id="dev-1",
        ),
    )

    def fake_fetch_json(session: module.ChatGPTHttpSession, url: str) -> object:
        if "conversations?" in url:
            return {
                "total": 1,
                "items": [{"id": "conv-1", "title": "Test Chat"}],
            }
        if "conversation/conv-1" in url:
            return {
                "conversation_id": "conv-1",
                "title": "Test Chat",
                "create_time": 1711900000,
                "update_time": 1711900100,
                "mapping": {"node-1": {"id": "node-1"}},
                "current_node": "node-1",
            }
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(module, "fetch_json", fake_fetch_json)

    bundle = module.fetch_chatgpt_local_session_bundle(jar, limit=10)

    assert bundle["fetched_count"] == 1
    assert bundle["total_count"] == 1
    assert bundle["conversations"][0]["conversation_id"] == "conv-1"
    assert bundle["conversations"][0]["mapping"]["node-1"]["id"] == "node-1"
    assert bundle["conversation_detail_failures"] == []


def test_render_discovery_text_includes_key_fields() -> None:
    text = module.render_discovery_text(
        {
            "cookie_jar": "/tmp/cookies",
            "generated_at": "2026-03-25T00:00:00+00:00",
            "session_state": "ready",
            "account_email": "user@example.com",
            "account_id": "acct-1",
            "conversation_count": 42,
            "calibration_only": True,
            "recommended_command": "cce provider import --provider chatgpt --mode local-session",
        }
    )

    assert "ChatGPT cookie jar: /tmp/cookies" in text
    assert "user@example.com" in text
    assert "Conversations: 42" in text


def test_acquisition_state_persistence_roundtrips(tmp_path: Path) -> None:
    conversations = {
        "conv-1": {"update_time": 1711900000, "fetched_at": "2026-03-25T00:00:00Z"},
        "conv-2": {"update_time": 1711900100, "fetched_at": "2026-03-25T00:01:00Z"},
    }
    report = {"fetched_count": 2, "reused_count": 0}
    module.save_acquisition_state(tmp_path, conversations, report=report)
    loaded = module.load_prior_acquisition(tmp_path)

    assert loaded["conv-1"]["update_time"] == 1711900000
    assert loaded["conv-2"]["update_time"] == 1711900100
    assert len(loaded) == 2


def test_load_prior_acquisition_returns_empty_when_missing(tmp_path: Path) -> None:
    assert module.load_prior_acquisition(tmp_path) == {}


def test_conversation_payload_cache_roundtrips(tmp_path: Path) -> None:
    payload = {"conversation_id": "conv-1", "title": "Test", "mapping": {"n1": {}}}
    path = module.cache_conversation_payload(tmp_path, "conv-1", payload)
    assert path.exists()

    loaded = module.load_cached_conversation(tmp_path, "conv-1")
    assert loaded is not None
    assert loaded["conversation_id"] == "conv-1"
    assert loaded["mapping"] == {"n1": {}}


def test_load_cached_conversation_returns_none_when_missing(tmp_path: Path) -> None:
    assert module.load_cached_conversation(tmp_path, "nonexistent") is None


def test_delta_aware_fetch_reuses_cached_conversations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    jar = tmp_path / "test.binarycookies"
    jar.write_bytes(
        build_binary_cookie_jar([{"domain": ".chatgpt.com", "name": "x", "value": "y"}])
    )
    output_root = tmp_path / "output"

    # Cache a conversation
    module.cache_conversation_payload(
        output_root,
        "conv-1",
        {"conversation_id": "conv-1", "title": "Cached", "update_time": 100, "mapping": {}},
    )

    monkeypatch.setattr(
        module,
        "build_chatgpt_session",
        lambda cookie_jar: module.ChatGPTHttpSession(
            cookies=[],
            session_payload={"account": {"id": "acct-1"}, "user": {"email": "u@e.com"}},
            access_token="tok",  # allow-secret
            account_id="acct-1",
            device_id="dev-1",
        ),
    )

    fetch_calls: list[str] = []

    def fake_fetch_json(session: module.ChatGPTHttpSession, url: str) -> object:
        if "conversations?" in url:
            return {
                "total": 2,
                "items": [
                    {"id": "conv-1", "title": "Cached", "update_time": 100},
                    {"id": "conv-2", "title": "New", "update_time": 200},
                ],
            }
        if "conversation/conv-2" in url:
            fetch_calls.append("conv-2")
            return {
                "conversation_id": "conv-2",
                "title": "New",
                "update_time": 200,
                "mapping": {"n": {}},
            }
        raise AssertionError(f"unexpected fetch: {url}")

    monkeypatch.setattr(module, "fetch_json", fake_fetch_json)

    prior_state = {"conv-1": {"update_time": 100}}
    bundle = module.fetch_chatgpt_local_session_bundle(
        jar,
        limit=100,
        prior_state=prior_state,
        output_root=output_root,
    )

    assert bundle["reused_count"] == 1
    assert bundle["fetched_count"] == 1
    assert bundle["acquisition_report"]["reused_count"] == 1
    assert bundle["acquisition_report"]["fetched_count"] == 1
    assert fetch_calls == ["conv-2"]
    assert len(bundle["conversations"]) == 2
