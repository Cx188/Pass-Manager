"""Unlock-credential providers: system keyring (primary) and a local key file
(fallback) for whenever no keyring daemon is reachable.

The keyring path stores a random secret in the user's login keyring via the
freedesktop Secret Service API (GNOME Keyring, KWallet) and only releases it
once the keyring itself is unlocked. That secret feeds a deterministic HMAC
over a stored challenge, which then gets stretched into the wrapping key —
so the wrapping key only ever exists transiently, derived at unlock time,
never stored anywhere.

The key-file fallback trades that keyring gate for plain filesystem
permissions; noticeably weaker, so the UI flags it when it's in use.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from enum import Enum
from pathlib import Path

from core.errors import (
    KeyfileError,
    ProviderUnavailableError,
    UnlockCancelledError,
    UnlockProviderError,
)
from core.kdf import hkdf_sha256

# --- Optional platform import (guarded so the module still imports headless) --
try:
    import secretstorage

    _SS_OK = True
except Exception:  # pragma: no cover - secretstorage not installed
    _SS_OK = False


CRED_NAME = "PassManager.dek.v1"
HKDF_INFO_A = b"pm:kek-a:v1"
CHALLENGE_LEN = 32
SALT_LEN = 16
SECRET_LEN = 32
_KEYFILE_AAD = b"pm:keyfile:v1"

# The key file lives next to the vault data, inside the app directory.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_KEYFILE_PATH = _PROJECT_ROOT / "vault" / "local.key"


class Provider(Enum):
    SECRET_SERVICE = "secret_service"
    KEYFILE = "keyfile"


# ----------------------------------------------------------------------------- #
#  challenge / salt helpers                                                      #
# ----------------------------------------------------------------------------- #
def new_challenge() -> bytes:
    return secrets.token_bytes(CHALLENGE_LEN)


def new_salt() -> bytes:
    return secrets.token_bytes(SALT_LEN)


# ----------------------------------------------------------------------------- #
#  Secret Service (GNOME Keyring / KWallet)                                      #
# ----------------------------------------------------------------------------- #
def _attrs(name: str) -> dict:
    return {"application": "passmanager", "credential": name}


def _connect():
    if not _SS_OK:
        raise ProviderUnavailableError("secretstorage is not installed")
    try:
        return secretstorage.dbus_init()
    except Exception as exc:
        raise ProviderUnavailableError(f"Secret Service (D-Bus) unavailable: {exc}") from exc


def _default_collection(conn):
    try:
        collection = secretstorage.get_default_collection(conn)
    except Exception as exc:
        raise ProviderUnavailableError(f"No default keyring collection: {exc}") from exc
    if collection.is_locked():
        dismissed = collection.unlock()
        if dismissed:
            raise UnlockCancelledError("Keyring unlock prompt was dismissed")
    return collection


def secret_service_available() -> bool:
    """True only if secretstorage is importable AND a daemon answers on D-Bus."""
    if not _SS_OK:
        return False
    try:
        conn = secretstorage.dbus_init()
        try:
            secretstorage.get_default_collection(conn)
        finally:
            conn.close()
        return True
    except Exception:
        return False


def enroll(name: str = CRED_NAME, *, replace: bool = True) -> None:
    """Create (or replace) the keyring unlock secret. May prompt to unlock
    the login keyring.

    Raises :class:`UnlockCancelledError` if the user dismisses the prompt, or
    :class:`UnlockProviderError` for any other failure.
    """
    conn = _connect()
    try:
        collection = _default_collection(conn)
        existing = list(collection.search_items(_attrs(name)))
        if existing and not replace:
            raise UnlockProviderError(f"Keyring credential '{name}' already exists")
        for item in existing:
            item.delete()
        collection.create_item("Pass Manager unlock secret", _attrs(name), secrets.token_bytes(SECRET_LEN))
    except (UnlockProviderError, UnlockCancelledError):
        raise
    except Exception as exc:
        raise UnlockProviderError(f"Failed to enroll keyring credential: {exc}") from exc
    finally:
        conn.close()


def credential_exists(name: str = CRED_NAME) -> bool:
    if not _SS_OK:
        return False
    try:
        conn = secretstorage.dbus_init()
        try:
            collection = secretstorage.get_default_collection(conn)
            return any(True for _ in collection.search_items(_attrs(name)))
        finally:
            conn.close()
    except Exception:
        return False


def delete_credential(name: str = CRED_NAME) -> None:
    conn = _connect()
    try:
        collection = _default_collection(conn)
        for item in collection.search_items(_attrs(name)):
            item.delete()
    except (UnlockProviderError, UnlockCancelledError):
        raise
    except Exception as exc:
        raise UnlockProviderError(f"Failed to delete keyring credential: {exc}") from exc
    finally:
        conn.close()


def sign_challenge(challenge: bytes, name: str = CRED_NAME) -> bytes:
    """HMAC-SHA256 the challenge with the keyring-held secret.

    Deterministic for a given (secret, challenge), so the derived key is
    stable across sessions. May prompt to unlock the keyring.
    """
    conn = _connect()
    try:
        collection = _default_collection(conn)
        items = list(collection.search_items(_attrs(name)))
        if not items:
            raise UnlockProviderError(f"Keyring credential '{name}' is not enrolled")
        item = items[0]
        if item.is_locked():
            if item.unlock():
                raise UnlockCancelledError("Keyring unlock prompt was dismissed")
        secret = item.get_secret()
        return hmac.new(bytes(secret), bytes(challenge), hashlib.sha256).digest()
    except (UnlockProviderError, UnlockCancelledError):
        raise
    except Exception as exc:
        raise UnlockProviderError(f"Failed to read keyring credential: {exc}") from exc
    finally:
        conn.close()


def derive_kek_a(challenge: bytes, salt: bytes, name: str = CRED_NAME) -> bytearray:
    """Full KEK-A derivation: HMAC(secret, challenge) -> HKDF-SHA256. Wipeable buffer."""
    signature = sign_challenge(challenge, name)
    return hkdf_sha256(signature, salt, HKDF_INFO_A)


# ----------------------------------------------------------------------------- #
#  key-file fallback                                                             #
# ----------------------------------------------------------------------------- #
def keyfile_available() -> bool:
    return True


def _load_or_create_keyfile_key() -> bytes:
    path = _KEYFILE_PATH
    if path.is_file():
        key = path.read_bytes()
        if len(key) != SECRET_LEN:
            raise KeyfileError(f"Corrupt key file at {path}")
        return key
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        key = secrets.token_bytes(SECRET_LEN)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(key)
        return key
    except OSError as exc:
        raise KeyfileError(f"Cannot create key file at {path}: {exc}") from exc


def keyfile_protect(data: bytes) -> bytes:
    from core import envelope

    key = _load_or_create_keyfile_key()
    blob = envelope.aesgcm_encrypt(key, bytes(data), _KEYFILE_AAD)
    return blob.nonce + blob.ct


def keyfile_unprotect(blob: bytes) -> bytes:
    from core import envelope
    from core.envelope import GcmBlob

    if not _KEYFILE_PATH.is_file():
        raise KeyfileError(f"Key file missing at {_KEYFILE_PATH}")
    key = _load_or_create_keyfile_key()
    return envelope.aesgcm_decrypt(key, GcmBlob(blob[:12], blob[12:]), _KEYFILE_AAD)


# ----------------------------------------------------------------------------- #
#  provider selection                                                            #
# ----------------------------------------------------------------------------- #
def detect_provider() -> Provider:
    """Prefer the Secret Service keyring; fall back to the local key file."""
    if secret_service_available():
        return Provider.SECRET_SERVICE
    return Provider.KEYFILE
