#!/usr/bin/env python3
"""Spike: Investigate Gemini macOS app local conversation cache.

Attempts to:
1. Read the Gemini Safe Storage password from macOS keychain
2. Read ChatInfo2.store (Core Data SQLite) for conversation metadata
3. Decrypt ZENCRYPTEDPROTOBYTES using Chrome-style AES-128-CBC
4. Decode the resulting protobuf wire format
5. Report what fields contain (titles, messages, timestamps)
"""
from __future__ import annotations

import json
import sqlite3
import struct
import subprocess
import sys
from hashlib import pbkdf2_hmac
from pathlib import Path
from typing import Any

GEMINI_CACHE_DB = Path.home() / "Library/Caches/com.google.GeminiMacOS/Gemini/user1/ChatInfo2.store"
GEMINI_SAFE_STORAGE_SERVICES = ("Gemini Safe Storage",)
MAGIC_HEADER = bytes.fromhex("2ebafeca2ebafeca")
# Core Data epoch: 2001-01-01 00:00:00 UTC (978307200 seconds after Unix epoch)
COREDATA_EPOCH_OFFSET = 978307200


def find_gemini_safe_storage_password() -> str:
    for service in GEMINI_SAFE_STORAGE_SERVICES:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-w"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            pw = result.stdout.strip()
            if pw:
                print(f"  Found keychain password for service: {service}")
                return pw
    raise RuntimeError("No Gemini Safe Storage password found in keychain")


def derive_key(password: str) -> bytes:  # allow-secret
    """Derive AES-128 key using Chrome-style PBKDF2 parameters."""
    return pbkdf2_hmac("sha1", password.encode("utf-8"), b"saltysalt", 1003, 16)


def decrypt_aes_cbc(ciphertext: bytes, key: bytes, iv: bytes = b" " * 16) -> bytes | None:
    """Decrypt AES-128-CBC using openssl (stdlib-only, no pycryptodome)."""
    result = subprocess.run(
        ["openssl", "enc", "-aes-128-cbc", "-d", "-K", key.hex(), "-iv", iv.hex(), "-nopad"],
        input=ciphertext,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    padded = result.stdout
    if not padded:
        return None
    # Strip PKCS7 padding
    pad_length = padded[-1]
    if pad_length < 1 or pad_length > 16:
        return padded  # Return as-is if padding looks wrong
    return padded[:-pad_length]


def decode_varint(data: bytes, pos: int) -> tuple[int, int]:
    """Decode a protobuf varint, return (value, new_position)."""
    val = 0
    shift = 0
    while pos < len(data):
        b = data[pos]
        val |= (b & 0x7F) << shift
        shift += 7
        pos += 1
        if not (b & 0x80):
            break
    return val, pos


def decode_protobuf_fields(data: bytes) -> list[dict[str, Any]]:
    """Decode protobuf wire format into a list of field entries."""
    fields: list[dict[str, Any]] = []
    pos = 0
    while pos < len(data):
        if pos >= len(data):
            break
        tag, pos = decode_varint(data, pos)
        field_num = tag >> 3
        wire_type = tag & 0x07

        if wire_type == 0:  # varint
            val, pos = decode_varint(data, pos)
            fields.append({"field": field_num, "type": "varint", "value": val})
        elif wire_type == 1:  # 64-bit
            if pos + 8 > len(data):
                break
            val = struct.unpack("<d", data[pos : pos + 8])[0]
            fields.append({"field": field_num, "type": "fixed64", "value": val, "raw": data[pos : pos + 8].hex()})
            pos += 8
        elif wire_type == 2:  # length-delimited
            length, pos = decode_varint(data, pos)
            if pos + length > len(data):
                break
            content = data[pos : pos + length]
            # Try to decode as UTF-8 string
            try:
                text = content.decode("utf-8")
                if text.isprintable() or "\n" in text:
                    fields.append({"field": field_num, "type": "string", "value": text, "length": length})
                else:
                    # Try recursive protobuf decode
                    sub = decode_protobuf_fields(content)
                    if sub and len(sub) > 1:
                        fields.append({"field": field_num, "type": "message", "value": sub, "length": length})
                    else:
                        fields.append({"field": field_num, "type": "bytes", "value": content.hex(), "length": length})
            except UnicodeDecodeError:
                # Try recursive protobuf decode
                sub = decode_protobuf_fields(content)
                if sub and len(sub) > 1:
                    fields.append({"field": field_num, "type": "message", "value": sub, "length": length})
                else:
                    fields.append({"field": field_num, "type": "bytes", "value": content.hex()[:100], "length": length})
            pos += length
        elif wire_type == 5:  # 32-bit
            if pos + 4 > len(data):
                break
            val = struct.unpack("<f", data[pos : pos + 4])[0]
            fields.append({"field": field_num, "type": "fixed32", "value": val})
            pos += 4
        else:
            fields.append({"field": field_num, "type": f"unknown_wire_{wire_type}", "pos": pos})
            break
    return fields


def strip_gemini_header(data: bytes) -> tuple[bytes, dict[str, Any]]:
    """Strip the 8-byte magic + 4-byte length header from Gemini protobytes."""
    info: dict[str, Any] = {}
    if data[:8] == MAGIC_HEADER:
        info["magic"] = "CAFEBA2E (doubled)"
        length = struct.unpack("<I", data[8:12])[0]
        info["declared_length"] = length
        info["actual_payload_length"] = len(data) - 12
        return data[12:], info
    info["magic"] = "MISSING — raw data"
    return data, info


def try_decrypt_payload(payload: bytes, key: bytes) -> tuple[bytes | None, str]:
    """Try multiple decryption strategies on the protobuf payload."""
    # Strategy 1: Entire payload is encrypted (after header strip)
    decrypted = decrypt_aes_cbc(payload, key)
    if decrypted and len(decrypted) > 8:
        fields = decode_protobuf_fields(decrypted)
        strings = [f for f in fields if f.get("type") == "string"]
        if strings:
            return decrypted, "full-payload"

    # Strategy 2: v10-prefixed (like Chrome cookies)
    if payload[:3] == b"v10":
        decrypted = decrypt_aes_cbc(payload[3:], key)
        if decrypted:
            return decrypted, "v10-prefix"

    # Strategy 3: Payload starts with proto metadata fields, encrypted blob follows
    # Parse the leading proto fields until we hit non-parseable data
    fields = decode_protobuf_fields(payload)
    if fields:
        # Find the first bytes/unknown field — that's likely where encryption starts
        for f in fields:
            if f.get("type") == "bytes" and f.get("length", 0) > 32:
                encrypted_hex = f["value"]
                if len(encrypted_hex) > 200:
                    encrypted_hex = encrypted_hex[:200]
                encrypted_data = bytes.fromhex(f["value"]) if len(f["value"]) <= 200 else None
                if encrypted_data:
                    decrypted = decrypt_aes_cbc(encrypted_data, key)
                    if decrypted:
                        return decrypted, f"field-{f['field']}-encrypted"

    # Strategy 4: Try with zero IV instead of space IV
    decrypted = decrypt_aes_cbc(payload, key, iv=b"\x00" * 16)
    if decrypted and len(decrypted) > 8:
        fields = decode_protobuf_fields(decrypted)
        strings = [f for f in fields if f.get("type") == "string"]
        if strings:
            return decrypted, "full-payload-zero-iv"

    return None, "failed"


def format_fields(fields: list[dict[str, Any]], indent: int = 0) -> str:
    """Pretty-print decoded protobuf fields."""
    lines = []
    prefix = "  " * indent
    for f in fields:
        ftype = f.get("type", "?")
        fnum = f.get("field", "?")
        if ftype == "string":
            val = f["value"]
            if len(val) > 120:
                val = val[:120] + "..."
            lines.append(f"{prefix}field {fnum} (string, {f.get('length', '?')}b): {val!r}")
        elif ftype == "varint":
            lines.append(f"{prefix}field {fnum} (varint): {f['value']}")
        elif ftype == "message":
            lines.append(f"{prefix}field {fnum} (message, {f.get('length', '?')}b):")
            lines.append(format_fields(f["value"], indent + 1))
        elif ftype == "bytes":
            val = f.get("value", "")
            if len(val) > 60:
                val = val[:60] + "..."
            lines.append(f"{prefix}field {fnum} (bytes, {f.get('length', '?')}b): {val}")
        elif ftype == "fixed64":
            lines.append(f"{prefix}field {fnum} (fixed64): {f['value']} raw={f.get('raw', '?')}")
        else:
            lines.append(f"{prefix}field {fnum} ({ftype}): {f.get('value', '?')}")
    return "\n".join(lines)


def main() -> int:
    print("=== Gemini Local Cache Spike ===\n")

    if not GEMINI_CACHE_DB.exists():
        print(f"ERROR: Cache database not found: {GEMINI_CACHE_DB}")
        return 1

    # Step 1: Read keychain password
    print("[1] Reading Gemini Safe Storage from keychain...")
    try:
        password = find_gemini_safe_storage_password()  # allow-secret
        key = derive_key(password)
        print(f"  Derived AES key: {key.hex()[:16]}...\n")
    except RuntimeError as e:
        print(f"  WARNING: {e}")
        print("  Continuing without decryption...\n")
        password = ""
        key = b""

    # Step 2: Read conversations from cache
    print("[2] Reading ChatInfo2.store...")
    conn = sqlite3.connect(GEMINI_CACHE_DB)
    try:
        chats = conn.execute(
            "SELECT ZCHATUUID, ZROBINCONVERSATIONID, ZLASTUPDATEDTIME, ZENCRYPTEDPROTOBYTES "
            "FROM ZCHATINFOSTOREDMODEL ORDER BY ZLASTUPDATEDTIME DESC"
        ).fetchall()
        messages = conn.execute(
            "SELECT ZCHATUUID, ZMESSAGEUUID, ZMESSAGEINDEX, ZCREATEDTIME, ZENCRYPTEDPROTOBYTES "
            "FROM ZCHATMESSAGESTOREDMODEL ORDER BY ZCHATUUID, ZMESSAGEINDEX"
        ).fetchall()
    finally:
        conn.close()

    print(f"  Conversations: {len(chats)}")
    print(f"  Messages: {len(messages)}\n")

    # Step 3: Decode conversation protobytes
    print("[3] Analyzing conversation protobytes...\n")
    for i, (chat_uuid, robin_id, updated_time, proto_bytes) in enumerate(chats[:5]):
        print(f"--- Conversation {i+1}: {chat_uuid} ---")
        print(f"  Robin ID: {robin_id or '(none)'}")
        if updated_time:
            from datetime import datetime, timezone
            ts = updated_time + COREDATA_EPOCH_OFFSET
            print(f"  Updated: {datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()}")

        if not proto_bytes:
            print("  No protobytes\n")
            continue

        print(f"  Proto bytes length: {len(proto_bytes)}")
        payload, header_info = strip_gemini_header(proto_bytes)
        print(f"  Header: {header_info}")

        # Try raw decode first (before decryption)
        print("\n  [Raw protobuf decode]:")
        raw_fields = decode_protobuf_fields(payload)
        print(format_fields(raw_fields, indent=2))

        # Try decryption
        if key:
            print("\n  [Decryption attempts]:")
            decrypted, strategy = try_decrypt_payload(payload, key)
            if decrypted:
                print(f"  SUCCESS via: {strategy}")
                dec_fields = decode_protobuf_fields(decrypted)
                print(format_fields(dec_fields, indent=2))
            else:
                print(f"  All strategies failed")

                # Additional: try decrypting just the bytes fields from raw decode
                for f in raw_fields:
                    if f.get("type") == "bytes" and f.get("length", 0) > 16:
                        raw_hex = f.get("value", "")
                        if len(raw_hex) <= 200:
                            raw_bytes = bytes.fromhex(raw_hex)
                            if len(raw_bytes) % 16 == 0:  # AES block-aligned
                                d = decrypt_aes_cbc(raw_bytes, key)
                                if d:
                                    try:
                                        text = d.decode("utf-8", errors="replace")
                                        print(f"  Decrypted field {f['field']}: {text!r}")
                                    except Exception:
                                        pass
        print()

    # Step 4: Analyze messages if any
    if messages:
        print(f"[4] Analyzing message protobytes ({len(messages)} messages)...\n")
        for i, (chat_uuid, msg_uuid, msg_idx, created_time, proto_bytes) in enumerate(messages[:5]):
            print(f"--- Message {i+1}: {msg_uuid} (chat: {chat_uuid}, idx: {msg_idx}) ---")
            if not proto_bytes:
                print("  No protobytes\n")
                continue
            payload, header_info = strip_gemini_header(proto_bytes)
            raw_fields = decode_protobuf_fields(payload)
            print(format_fields(raw_fields, indent=2))

            if key:
                decrypted, strategy = try_decrypt_payload(payload, key)
                if decrypted:
                    print(f"\n  Decrypted ({strategy}):")
                    dec_fields = decode_protobuf_fields(decrypted)
                    print(format_fields(dec_fields, indent=2))
            print()
    else:
        print("[4] No messages in cache (messages may be embedded in conversation protobytes)\n")

    print("=== Spike complete ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
