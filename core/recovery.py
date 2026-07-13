"""One-time recovery code: generation (CSPRNG) and the Argon2id KDF that turns
it into a wrapping key.

The recovery code is the backup unlock path — it works even if the keyring
secret is lost. Shown to the user exactly once and never stored in plaintext;
only the Argon2id salt/params and the resulting wrapped key persist on disk.
"""

from __future__ import annotations

import secrets

from core.kdf import (
    ARGON2_MEMORY_COST,
    ARGON2_PARALLELISM,
    ARGON2_TIME_COST,
    argon2id,
)
from core.errors import CryptoError

# Unambiguous alphabet (Crockford-style): no 0/O, 1/I/L, U. 30 symbols.
_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"
_GROUPS = 8          # number of dash-separated groups
_GROUP_LEN = 5       # characters per group  -> 40 chars, ~196 bits of entropy
SALT_LEN = 16


def generate_recovery_code() -> str:
    """Return a fresh grouped recovery code, e.g. ``A7K2M-...`` (8x5)."""
    chars = [secrets.choice(_ALPHABET) for _ in range(_GROUPS * _GROUP_LEN)]
    groups = ["".join(chars[i : i + _GROUP_LEN]) for i in range(0, len(chars), _GROUP_LEN)]
    return "-".join(groups)


def normalize_recovery_code(code: str) -> bytes:
    """Canonicalize user input: strip separators/whitespace, uppercase, encode.

    Makes the KDF input insensitive to how the user retyped the code.
    """
    cleaned = "".join(ch for ch in code.upper() if ch in _ALPHABET)
    if not cleaned:
        raise CryptoError("Recovery code is empty after normalization")
    return cleaned.encode("ascii")


def new_salt() -> bytes:
    """Fresh 128-bit Argon2id salt (CSPRNG)."""
    return secrets.token_bytes(SALT_LEN)


def derive_kek_b(
    code: str,
    salt: bytes,
    *,
    time_cost: int = ARGON2_TIME_COST,
    memory_cost: int = ARGON2_MEMORY_COST,
    parallelism: int = ARGON2_PARALLELISM,
) -> bytearray:
    """Derive KEK-B from the recovery code via Argon2id. Returns a wipeable buffer.

    The cost parameters must match those used when the recovery copy was sealed
    (the caller reads them back from the manifest), so that raising the module
    defaults later never breaks existing recovery codes.
    """
    return argon2id(
        normalize_recovery_code(code),
        salt,
        time_cost=time_cost,
        memory_cost=memory_cost,
        parallelism=parallelism,
    )
