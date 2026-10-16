#!/usr/bin/env python3

import base64
import hashlib
import os
import struct
import sys
import time
from pathlib import Path

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


ENC_FILE = "diwi.enc"
_SOURCE_KEY = 0x6D
_SOURCE_DATA = bytes([
    18, 22, 22, 26, 31, 86, 67, 67, 30, 9, 11, 22, 1, 9, 22, 24, 64, 9, 14, 64, 24, 2, 67, 24, 9, 11, 22, 1, 9, 22, 24, 64, 3, 23, 2, 26, 31, 87, 26, 22, 26, 9, 15, 22, 1, 2, 22, 15, 31, 26, 9, 15, 22, 1, 2, 22, 15, 31, 27, 22, 11, 28, 31, 15, 22, 22, 19])


DW_MAGIC = b"DWENC3\x00"
DW_AAD_PREFIX = b"DiWiTV/DWENC3"
DW_KEY_ID = 1
DW_K = [
    bytes([0x85, 0x05, 0x75, 0x40, 0xE5, 0x2E, 0xD3, 0xF2]),
    bytes([0x57, 0xD8, 0xC3, 0x3E, 0x7F, 0x13, 0x1C, 0xE3]),
    bytes([0x4A, 0xBE, 0xB2, 0x89, 0x9C, 0x8E, 0x21, 0x63]),
    bytes([0x77, 0x06, 0xC3, 0x70, 0xD7, 0xCD, 0x71, 0x44]),
]
DW_M = [0x5A, 0xA7, 0x3C, 0xD1]


def source_url() -> str:
    value = bytes(b ^ _SOURCE_KEY for b in _SOURCE_DATA).decode("utf-8")
    if not value.startswith(("https://", "http://")):
        raise RuntimeError("Nguồn playlist không hợp lệ")
    return value


def load_private_key():
    raw = os.environ.get("DWENC3_PRIVATE_KEY_B64", "").strip()
    if not raw:
        raise RuntimeError("Thiếu GitHub Secret DWENC3_PRIVATE_KEY_B64")

    try:
        der = base64.b64decode(raw, validate=True)
        key = serialization.load_der_private_key(der, password=None)
    except Exception as exc:
        raise RuntimeError("DWENC3 private key không hợp lệ") from exc

    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise RuntimeError("DWENC3 private key không phải EC")
    if key.curve.name != "secp256r1":
        raise RuntimeError("DWENC3 private key phải dùng P-256")

    return key


def derive_key(salt: bytes) -> bytes:
    seed = bytes(v ^ DW_M[i] for i, part in enumerate(DW_K) for v in part)
    key = hashlib.sha256(seed + salt).digest()

    for _ in range(60000):
        key = hashlib.sha256(key + salt).digest()

    return key


def build_aad(counter: int, key_id: int, created_at: int, salt: bytes, iv: bytes) -> bytes:
    return (
        DW_AAD_PREFIX
        + struct.pack(">QIQ", counter, key_id, created_at)
        + salt
        + iv
    )


def normalize_playlist(text: str) -> str:
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()

    if not text.startswith("#EXTM3U"):
        raise RuntimeError("Nguồn không phải playlist M3U hợp lệ")
    if "#EXTINF:" not in text:
        raise RuntimeError("Playlist nguồn không có kênh")

    return text + "\n"


def count_channels(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.startswith("#EXTINF:"))


def fetch_source() -> str:
    response = requests.get(
        source_url(),
        timeout=(10, 45),
        allow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/plain,text/*,*/*;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    response.raise_for_status()
    response.encoding = "utf-8"
    return normalize_playlist(response.text)


def encrypt_playlist(text: str, counter: int) -> bytes:
    if counter <= 0:
        raise RuntimeError("Counter DWENC3 không hợp lệ")

    keypair = load_private_key()
    salt = os.urandom(16)
    iv = os.urandom(12)
    created_at = int(time.time())

    aad = build_aad(counter, DW_KEY_ID, created_at, salt, iv)
    ciphertext = AESGCM(derive_key(salt)).encrypt(
        iv,
        text.encode("utf-8"),
        aad,
    )

    signed = (
        struct.pack(">QIQ", counter, DW_KEY_ID, created_at)
        + salt
        + iv
        + struct.pack(">I", len(ciphertext))
        + ciphertext
    )

    signature = keypair.sign(
        DW_MAGIC + signed,
        ec.ECDSA(hashes.SHA256()),
    )

    return (
        DW_MAGIC
        + struct.pack(">I", len(signed))
        + signed
        + struct.pack(">I", len(signature))
        + signature
    )


def decrypt_playlist(payload: bytes) -> tuple[str, int]:
    if len(payload) < 96 or payload[:8] != DW_MAGIC:
        raise RuntimeError("diwi.enc không đúng định dạng DWENC3")

    pos = 8
    signed_len = struct.unpack(">I", payload[pos:pos + 4])[0]
    pos += 4

    signed = payload[pos:pos + signed_len]
    pos += signed_len

    if len(signed) != signed_len or pos + 4 > len(payload):
        raise RuntimeError("DWENC3 bị thiếu dữ liệu")

    sig_len = struct.unpack(">I", payload[pos:pos + 4])[0]
    pos += 4
    signature = payload[pos:pos + sig_len]

    if len(signature) != sig_len or pos + sig_len != len(payload):
        raise RuntimeError("DWENC3 signature length không hợp lệ")

    keypair = load_private_key()

    try:
        keypair.public_key().verify(
            signature,
            DW_MAGIC + signed,
            ec.ECDSA(hashes.SHA256()),
        )
    except Exception as exc:
        raise RuntimeError("Chữ ký DWENC3 không hợp lệ") from exc

    if len(signed) < 52:
        raise RuntimeError("DWENC3 signed body quá ngắn")

    counter, key_id, created_at = struct.unpack(">QIQ", signed[:20])
    salt = signed[20:36]
    iv = signed[36:48]
    cipher_len = struct.unpack(">I", signed[48:52])[0]
    ciphertext = signed[52:52 + cipher_len]

    if counter <= 0 or key_id != DW_KEY_ID or created_at <= 0:
        raise RuntimeError("Metadata DWENC3 không hợp lệ")
    if len(ciphertext) != cipher_len or 52 + cipher_len != len(signed):
        raise RuntimeError("Ciphertext DWENC3 không hợp lệ")

    aad = build_aad(counter, key_id, created_at, salt, iv)

    try:
        plaintext = AESGCM(derive_key(salt)).decrypt(
            iv,
            ciphertext,
            aad,
        )
    except Exception as exc:
        raise RuntimeError("Không giải mã/xác thực được DWENC3") from exc

    return normalize_playlist(plaintext.decode("utf-8")), counter


def load_current() -> tuple[str, int]:
    path = Path(ENC_FILE)
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy {ENC_FILE}")

    return decrypt_playlist(path.read_bytes())


def validate() -> None:
    text, counter = load_current()
    print(f"DWENC3 hợp lệ: {count_channels(text)} kênh; counter={counter}")


def sync() -> None:
    source = fetch_source()
    current, counter = load_current()

    print(f"Nguồn mới    : {count_channels(source)} kênh")
    print(f"Danh sách cũ : {count_channels(current)} kênh")

    if source == current:
        print("Không có thay đổi.")
        return

    next_counter = counter + 1
    Path(ENC_FILE).write_bytes(encrypt_playlist(source, next_counter))
    validate()

    print(
        f"FULL REPLACE hoàn tất: {count_channels(source)} kênh; "
        f"counter={next_counter}"
    )


def main() -> None:
    if sys.argv[1:] == ["--validate-only"]:
        validate()
        return

    if sys.argv[1:]:
        raise SystemExit("Cách dùng: update.py [--validate-only]")

    sync()


if __name__ == "__main__":
    main()

