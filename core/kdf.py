"""Key-derivation primitives: Argon2id (recovery KDF) and HKDF-SHA256.

Argon2id parameters target OWASP's current minimum:
    time_cost >= 3, memory_cost >= 262144 KiB (256 MiB), parallelism >= 4.
We use time_cost=4 for a little extra margin on modern hardware.
"""

from __future__ import annotations

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from core.errors import KeyDerivationError

# --- Argon2id parameters (the recovery-code KDF) -------------------------------
ARGON2_TIME_COST = 4          # iterations
ARGON2_MEMORY_COST = 262_144  # KiB == 256 MiB
ARGON2_PARALLELISM = 4        # lanes
ARGON2_HASH_LEN = 32          # 256-bit output

KEY_LEN = 32  # all symmetric keys are 256-bit


def argon2id(
    password: bytes,
    salt: bytes,
    *,
    time_cost: int = ARGON2_TIME_COST,
    memory_cost: int = ARGON2_MEMORY_COST,
    parallelism: int = ARGON2_PARALLELISM,
    hash_len: int = ARGON2_HASH_LEN,
) -> bytearray:
    """Derive raw key material from ``password`` with Argon2id.

    Returns a ``bytearray`` so the caller can wipe it after use.
    """
    if len(salt) < 16:
        raise KeyDerivationError("Argon2id salt must be >= 16 bytes")
    try:
        raw = hash_secret_raw(
            secret=bytes(password),
            salt=bytes(salt),
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
            hash_len=hash_len,
            type=Type.ID,
        )
    except Exception as exc:  # pragma: no cover - argon2 backend failure
        raise KeyDerivationError(f"Argon2id derivation failed: {exc}") from exc
    return bytearray(raw)


def hkdf_sha256(ikm: bytes, salt: bytes, info: bytes, length: int = KEY_LEN) -> bytearray:
    """HKDF-SHA256 expand of input keying material into a stable key.

    Used to turn a raw keyring signature into a usable key. Returns a ``bytearray``.
    """
    try:
        raw = HKDF(
            algorithm=hashes.SHA256(),
            length=length,
            salt=bytes(salt),
            info=bytes(info),
        ).derive(bytes(ikm))
    except Exception as exc:  # pragma: no cover
        raise KeyDerivationError(f"HKDF derivation failed: {exc}") from exc
    return bytearray(raw)
