"""CSPRNG password generator (Section 4 rules).

- Default 35 chars, configurable 12-64.
- Guarantees >= 1 each of any enabled class (upper/lower/digit/symbol).
- Shuffles via ``secrets`` so guaranteed classes are not positional.
- Every draw uses :mod:`secrets` (never :mod:`random`).
"""

from __future__ import annotations

import math
import secrets
from dataclasses import dataclass

UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
LOWER = "abcdefghijklmnopqrstuvwxyz"
DIGITS = "0123456789"
DEFAULT_SYMBOLS = "!@#$%^&*()-_=+[]{};:,.?/"

DEFAULT_LENGTH = 35
MIN_LENGTH = 12
MAX_LENGTH = 64


@dataclass
class PasswordOptions:
    length: int = DEFAULT_LENGTH
    use_upper: bool = True
    use_lower: bool = True
    use_digits: bool = True
    use_symbols: bool = True
    symbols: str = DEFAULT_SYMBOLS

    def classes(self) -> list[str]:
        sets = []
        if self.use_upper:
            sets.append(UPPER)
        if self.use_lower:
            sets.append(LOWER)
        if self.use_digits:
            sets.append(DIGITS)
        if self.use_symbols and self.symbols:
            sets.append(self.symbols)
        return sets


def _secure_shuffle(items: list) -> None:
    """In-place Fisher-Yates shuffle using a CSPRNG."""
    for i in range(len(items) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        items[i], items[j] = items[j], items[i]


def generate_password(options: PasswordOptions | None = None) -> str:
    """Generate a password honoring class guarantees, then shuffle."""
    opts = options or PasswordOptions()
    if not MIN_LENGTH <= opts.length <= MAX_LENGTH:
        raise ValueError(f"length must be {MIN_LENGTH}-{MAX_LENGTH}, got {opts.length}")

    classes = opts.classes()
    if not classes:
        raise ValueError("at least one character class must be enabled")
    if opts.length < len(classes):
        raise ValueError("length too short to include every enabled class")

    # One guaranteed character from each enabled class...
    chars = [secrets.choice(cls) for cls in classes]
    # ...then fill the remainder from the combined pool.
    pool = "".join(classes)
    chars += [secrets.choice(pool) for _ in range(opts.length - len(chars))]
    _secure_shuffle(chars)
    return "".join(chars)


def _pool_size(password: str) -> int:
    """Effective character-pool size, detected from what the password actually
    contains — not from generator settings, since a typed-in password may not
    match whatever the class checkboxes happen to say."""
    size = 0
    if any(c in UPPER for c in password):
        size += len(UPPER)
    if any(c in LOWER for c in password):
        size += len(LOWER)
    if any(c in DIGITS for c in password):
        size += len(DIGITS)
    if any(c not in UPPER + LOWER + DIGITS for c in password):
        size += len(DEFAULT_SYMBOLS)
    return size or len(set(password)) or 1


def entropy_bits(password: str) -> float:
    """Estimate password entropy in bits from the character classes it contains."""
    return len(password) * math.log2(_pool_size(password))


def strength_score(password: str) -> float:
    """Map entropy to a 0.0-1.0 meter value (saturates at ~120 bits)."""
    return max(0.0, min(1.0, entropy_bits(password) / 120.0))
