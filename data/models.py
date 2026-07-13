"""Domain model: services, accounts, backup codes — with secret fields kept as
ciphertext both on disk and in memory.

Design note on the two encryption layers:
  * Each Service is stored on disk as ONE AES-256-GCM record (unique nonce per
    record) so even metadata (service name, usernames, URLs) is ciphertext at rest.
  * Inside that record, every individual secret (password, TOTP seed, backup code)
    is *additionally* sealed as its own :class:`EncryptedField` under the DEK with
    its own nonce. So after a session unlock we hold metadata in memory but each
    secret stays encrypted until a specific reveal decrypts it on demand — the
    plaintext password is never sitting in memory for the whole session.

This module has no crypto/IO dependencies (pure data + (de)serialization) so it
can be imported anywhere without cycles. The repository performs the actual seal/
open using the DEK.
"""

from __future__ import annotations

import base64
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def new_id() -> str:
    """Random, non-sequential record id (CSPRNG). Not secret, just unique."""
    return secrets.token_hex(8)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


class EntryType(str, Enum):
    APPLICATION = "application"
    WEBSITE = "website"
    BACKUP_CODES = "backup_codes"


@dataclass
class EncryptedField:
    """A secret sealed with AES-256-GCM under the DEK (nonce + ciphertext+tag)."""

    nonce: bytes
    ct: bytes

    def to_dict(self) -> dict:
        return {"n": _b64e(self.nonce), "c": _b64e(self.ct)}

    @classmethod
    def from_dict(cls, d: dict | None) -> "EncryptedField | None":
        if not d:
            return None
        return cls(nonce=_b64d(d["n"]), ct=_b64d(d["c"]))


@dataclass
class Account:
    """One login under a service (e.g. one of several Valorant accounts)."""

    id: str
    username: str
    password: EncryptedField
    totp: EncryptedField | None = None
    created: str = field(default_factory=_now)
    rotated: str = field(default_factory=_now)

    @property
    def has_totp(self) -> bool:
        return self.totp is not None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "password": self.password.to_dict(),
            "totp": self.totp.to_dict() if self.totp else None,
            "created": self.created,
            "rotated": self.rotated,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Account":
        return cls(
            id=d["id"],
            username=d["username"],
            password=EncryptedField.from_dict(d["password"]),
            totp=EncryptedField.from_dict(d.get("totp")),
            created=d.get("created", _now()),
            rotated=d.get("rotated", _now()),
        )


@dataclass
class BackupCode:
    """One one-time backup code with used/unused state."""

    id: str
    code: EncryptedField
    used: bool = False

    def to_dict(self) -> dict:
        return {"id": self.id, "code": self.code.to_dict(), "used": self.used}

    @classmethod
    def from_dict(cls, d: dict) -> "BackupCode":
        return cls(id=d["id"], code=EncryptedField.from_dict(d["code"]), used=d["used"])


@dataclass
class Service:
    """A grouping (service) holding N accounts, or a set of backup codes."""

    id: str
    type: EntryType
    name: str
    url: str | None = None
    icon: str | None = None
    accounts: list[Account] = field(default_factory=list)
    backup_codes: list[BackupCode] = field(default_factory=list)
    created: str = field(default_factory=_now)
    modified: str = field(default_factory=_now)

    def touch(self) -> None:
        self.modified = _now()

    @property
    def count(self) -> int:
        """Account-count badge value (or number of backup codes)."""
        return len(self.backup_codes) if self.type is EntryType.BACKUP_CODES else len(self.accounts)

    def to_plain_dict(self) -> dict:
        """Full record (metadata + nested encrypted-field blobs) for sealing."""
        return {
            "id": self.id,
            "type": self.type.value,
            "name": self.name,
            "url": self.url,
            "icon": self.icon,
            "accounts": [a.to_dict() for a in self.accounts],
            "backup_codes": [b.to_dict() for b in self.backup_codes],
            "created": self.created,
            "modified": self.modified,
        }

    @classmethod
    def from_plain_dict(cls, d: dict) -> "Service":
        return cls(
            id=d["id"],
            type=EntryType(d["type"]),
            name=d["name"],
            url=d.get("url"),
            icon=d.get("icon"),
            accounts=[Account.from_dict(a) for a in d.get("accounts", [])],
            backup_codes=[BackupCode.from_dict(b) for b in d.get("backup_codes", [])],
            created=d.get("created", _now()),
            modified=d.get("modified", _now()),
        )
