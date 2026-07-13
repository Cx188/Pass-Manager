"""TOTP / 2FA helpers (thin wrapper over pyotp).

Used at reveal time to show a rolling 6 digit code with the seconds remaining in
the current period. The TOTP seed itself is stored sealed under the DEK and only
decrypted on demand (see repository.reveal_totp).
"""

from __future__ import annotations

import time

import pyotp

PERIOD = 30


def is_valid_secret(secret: str) -> bool:
    """True if ``secret`` is a usable Base32 TOTP seed."""
    try:
        pyotp.TOTP(secret.strip().replace(" ", "")).now()
        return True
    except Exception:
        return False


def code_and_remaining(secret: str, period: int = PERIOD) -> tuple[str, float, float]:
    """Return ``(code, seconds_remaining, fraction_remaining)`` for ``secret``."""
    cleaned = secret.strip().replace(" ", "")
    totp = pyotp.TOTP(cleaned, interval=period)
    now = time.time()
    remaining = period - (now % period)
    return totp.now(), remaining, remaining / period
