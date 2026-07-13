"""Explicit exception types for the security core.

Crypto operations must never fail silently — every failure path raises one of
these so callers can surface a clear message instead of swallowing it.
"""


class CryptoError(Exception):
    """Base class for all security-core failures."""


class DecryptionError(CryptoError):
    """AEAD authentication failed or ciphertext is malformed.

    Raised when the wrong key/credential is used — i.e. exactly the case that
    must remain *mathematically* unrecoverable. Never downgrade this to a
    boolean check; propagate it.
    """


class KeyDerivationError(CryptoError):
    """A KDF (Argon2id / HKDF) failed to produce key material."""


class UnlockProviderError(CryptoError):
    """System keyring (Secret Service) / unlock-provider failure."""


class ProviderUnavailableError(UnlockProviderError):
    """No usable unlock provider on this machine."""


class UnlockCancelledError(UnlockProviderError):
    """The user cancelled or dismissed the keyring unlock prompt."""


class KeyfileError(CryptoError):
    """A key-file protect/unprotect call failed."""
