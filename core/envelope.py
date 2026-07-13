"""AES-256-GCM primitives and DEK wrap/unwrap.

Every entry in the store is encrypted under one random Data Encryption Key
(DEK). The DEK never touches disk in the clear: it's wrapped with AES 256 GCM
under a Key Encryption Key that only a successful keyring unlock or the
recovery code can reproduce (see data/repository.py for how KEK A and KEK B
get derived). Wrong key in -> DecryptionError out, never a silent fallback.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.errors import CryptoError, DecryptionError

NONCE_LEN = 12   # 96 bit GCM nonce
DEK_LEN = 32     # 256 bit data key


@dataclass(frozen=True)
class GcmBlob:
    nonce: bytes
    ct: bytes


def aesgcm_encrypt(key: bytes, plaintext: bytes, aad: bytes = b"") -> GcmBlob:
    if len(key) != 32:
        raise CryptoError("AES 256 GCM requires a 32-byte key")
    nonce = secrets.token_bytes(NONCE_LEN)
    ct = AESGCM(bytes(key)).encrypt(nonce, bytes(plaintext), bytes(aad))
    return GcmBlob(nonce=nonce, ct=ct)


def aesgcm_decrypt(key: bytes, blob: GcmBlob, aad: bytes = b"") -> bytes:
    if len(key) != 32:
        raise CryptoError("AES 256 GCM requires a 32-byte key")
    try:
        return AESGCM(bytes(key)).decrypt(blob.nonce, blob.ct, bytes(aad))
    except InvalidTag as exc:
        raise DecryptionError("authentication failed (wrong key or tampered data)") from exc


def generate_dek() -> bytearray:
    return bytearray(secrets.token_bytes(DEK_LEN))


def wrap_dek(dek: bytes, kek: bytes) -> GcmBlob:
    return aesgcm_encrypt(kek, dek, aad=b"pm:dek:v1")


def unwrap_dek(protected: GcmBlob, kek: bytes) -> bytearray:
    return bytearray(aesgcm_decrypt(kek, protected, aad=b"pm:dek:v1"))
