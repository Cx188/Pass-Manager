"""Vault: ties the crypto core to the data model.

* First run — generate a DEK, wrap it under both unlock paths (system keyring
  / key file = path A, recovery code = path B), write meta.bin.
* Unlock — release the DEK via the keyring, key file, or recovery code, then
  decrypt service records into memory. Individual secrets stay sealed until a
  caller explicitly reveals them.
* CRUD + search over services/accounts/backup codes; every save re-encrypts
  and writes atomically.
* Lock — wipe the DEK and drop all decrypted state from memory.

meta.bin layout (short opaque keys, nothing here is plaintext-secret)::

    { "v": 1,
      "paths": {
        "a": {"t": "keyring", "ch": .., "s": .., "n": .., "c": ..}
           | {"t": "keyfile", "d": ..},
        "b": {"s": .., "p": {...argon2 params...}, "n": .., "c": ..}
      } }
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from core import envelope, keyring, recovery, secure_mem
from core.envelope import GcmBlob
from core.errors import CryptoError
from core.kdf import ARGON2_MEMORY_COST, ARGON2_PARALLELISM, ARGON2_TIME_COST
from core.keyring import Provider
from data import store_io
from data.models import Account, BackupCode, EncryptedField, EntryType, Service, new_id
from data.store_io import StoragePaths, b64d, b64e

MANIFEST_VERSION = 1
STORE_VERSION = 1


class VaultLocked(CryptoError):
    """Raised when an operation needs an unlocked vault but the DEK is absent."""


class VaultStateError(CryptoError):
    """Raised on inconsistent on-disk state (e.g. unlock before setup)."""


@dataclass
class InitResult:
    recovery_code: str
    provider: Provider


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# AAD binders tie each ciphertext to where it lives, so a blob copied to a
# different record/field/account won't decrypt even with the right DEK.
def _record_aad(service_id: str) -> bytes:
    return f"pm:rec:v1:{service_id}".encode()


def _field_aad(account_id: str, field: str) -> bytes:
    return f"pm:fld:v1:{account_id}:{field}".encode()


def _code_aad(code_id: str) -> bytes:
    return f"pm:bc:v1:{code_id}".encode()


class Vault:
    def __init__(self, paths: StoragePaths | None = None) -> None:
        self.paths = paths or StoragePaths.default()
        self._dek: bytearray | None = None
        self._records: dict[str, Service] = {}

    @property
    def unlocked(self) -> bool:
        return self._dek is not None

    def exists(self) -> bool:
        return all(store_io.exists(p) for p in (self.paths.meta, self.paths.store))

    def _require_unlocked(self) -> None:
        if self._dek is None:
            raise VaultLocked("Vault is locked")

    # ------------------------------------------------------------- first run
    def initialize(self, provider: Provider | None = None) -> InitResult:
        """Create a brand-new vault, leaving it unlocked. Returns the one-time
        recovery code — callers must show it once and never persist it."""
        if self.exists():
            raise VaultStateError("A vault already exists at this location")
        if provider is None:
            provider = keyring.detect_provider()

        store_io.ensure_dir(self.paths.directory)
        dek = envelope.generate_dek()

        manifest = {"v": MANIFEST_VERSION, "paths": {}}
        manifest["paths"]["a"] = self._build_path_a(provider, dek)
        code, path_b = self._build_path_b(dek)
        manifest["paths"]["b"] = path_b
        store_io.write_json(self.paths.meta, manifest)

        self._dek = dek
        self._records = {}
        self.save()
        return InitResult(recovery_code=code, provider=provider)

    def _build_path_a(self, provider: Provider, dek: bytearray) -> dict:
        if provider is Provider.SECRET_SERVICE:
            keyring.enroll()
            challenge = keyring.new_challenge()
            salt = keyring.new_salt()
            kek_a = keyring.derive_kek_a(challenge, salt)
            try:
                blob = envelope.wrap_dek(bytes(dek), bytes(kek_a))
            finally:
                secure_mem.wipe(kek_a)
            return {
                "t": "keyring",
                "ch": b64e(challenge),
                "s": b64e(salt),
                "n": b64e(blob.nonce),
                "c": b64e(blob.ct),
            }
        # Key-file fallback: no keyring gate, just filesystem permissions.
        return {"t": "keyfile", "d": b64e(keyring.keyfile_protect(bytes(dek)))}

    def _build_path_b(self, dek: bytearray) -> tuple[str, dict]:
        code = recovery.generate_recovery_code()
        salt = recovery.new_salt()
        kek_b = recovery.derive_kek_b(code, salt)
        try:
            blob = envelope.wrap_dek(bytes(dek), bytes(kek_b))
        finally:
            secure_mem.wipe(kek_b)
        path_b = {
            "s": b64e(salt),
            "p": {"t": ARGON2_TIME_COST, "m": ARGON2_MEMORY_COST, "par": ARGON2_PARALLELISM},
            "n": b64e(blob.nonce),
            "c": b64e(blob.ct),
        }
        return code, path_b

    # ---------------------------------------------------------------- unlock
    def _manifest(self) -> dict:
        if not store_io.exists(self.paths.meta):
            raise VaultStateError("No vault has been set up yet")
        return store_io.read_json(self.paths.meta)

    @property
    def primary_provider(self) -> Provider:
        a = self._manifest()["paths"]["a"]
        return Provider.SECRET_SERVICE if a["t"] == "keyring" else Provider.KEYFILE

    def unlock(self) -> None:
        t = self._manifest()["paths"]["a"]["t"]
        if t == "keyring":
            self.unlock_keyring()
        elif t == "keyfile":
            self.unlock_keyfile()
        else:
            raise VaultStateError(f"Unknown unlock path {t!r}; use your recovery code")

    def unlock_keyring(self) -> None:
        a = self._manifest()["paths"]["a"]
        if a["t"] != "keyring":
            raise VaultStateError("This vault is not configured for the system keyring")
        kek_a = keyring.derive_kek_a(b64d(a["ch"]), b64d(a["s"]))
        try:
            dek = envelope.unwrap_dek(GcmBlob(b64d(a["n"]), b64d(a["c"])), bytes(kek_a))
        finally:
            secure_mem.wipe(kek_a)
        self._activate(dek)

    def unlock_keyfile(self) -> None:
        a = self._manifest()["paths"]["a"]
        if a["t"] != "keyfile":
            raise VaultStateError("This vault is not configured for the key-file provider")
        dek = bytearray(keyring.keyfile_unprotect(b64d(a["d"])))
        self._activate(dek)

    def unlock_recovery(self, code: str) -> None:
        b = self._manifest()["paths"]["b"]
        # Honor the params recorded at setup so bumping the module defaults
        # later never invalidates an existing recovery code.
        p = b.get("p", {})
        kek_b = recovery.derive_kek_b(
            code,
            b64d(b["s"]),
            time_cost=int(p.get("t", ARGON2_TIME_COST)),
            memory_cost=int(p.get("m", ARGON2_MEMORY_COST)),
            parallelism=int(p.get("par", ARGON2_PARALLELISM)),
        )
        try:
            dek = envelope.unwrap_dek(GcmBlob(b64d(b["n"]), b64d(b["c"])), bytes(kek_b))
        finally:
            secure_mem.wipe(kek_b)
        self._activate(dek)

    def _activate(self, dek: bytearray) -> None:
        self._dek = dek
        self._load_store()

    def _load_store(self) -> None:
        self._require_unlocked()
        self._records = {}
        data = store_io.read_json(self.paths.store)
        for rec in data.get("records", []):
            blob = GcmBlob(b64d(rec["n"]), b64d(rec["c"]))
            plain = envelope.aesgcm_decrypt(bytes(self._dek), blob, _record_aad(rec["id"]))
            svc = Service.from_plain_dict(json.loads(plain.decode("utf-8")))
            self._records[svc.id] = svc

    # ------------------------------------------------------------------ lock
    def lock(self) -> None:
        """Zero the DEK and drop all decrypted state. Safe to call twice."""
        if self._dek is not None:
            secure_mem.wipe(self._dek)
        self._dek = None
        self._records = {}

    # ------------------------------------------------------------------ save
    def save(self) -> None:
        """Re-encrypt every record (fresh nonce each time) and write store.dat."""
        self._require_unlocked()
        records = []
        for svc in self._records.values():
            plain = json.dumps(svc.to_plain_dict(), separators=(",", ":")).encode("utf-8")
            blob = envelope.aesgcm_encrypt(bytes(self._dek), plain, _record_aad(svc.id))
            records.append({"id": svc.id, "n": b64e(blob.nonce), "c": b64e(blob.ct)})
        store_io.write_json(self.paths.store, {"v": STORE_VERSION, "records": records})

    # ------------------------------------------------------------- CRUD/query
    def services(self, type: EntryType | None = None, query: str | None = None) -> list[Service]:
        items = list(self._records.values())
        if type is not None:
            items = [s for s in items if s.type is type]
        if query:
            q = query.lower()
            items = [
                s
                for s in items
                if q in s.name.lower()
                or (s.url and q in s.url.lower())
                or any(q in a.username.lower() for a in s.accounts)
            ]
        return sorted(items, key=lambda s: s.name.lower())

    def get(self, service_id: str) -> Service | None:
        return self._records.get(service_id)

    def add_service(self, service: Service) -> None:
        self._require_unlocked()
        self._records[service.id] = service
        self.save()

    def update_service(self, service: Service) -> None:
        self._require_unlocked()
        service.touch()
        self._records[service.id] = service
        self.save()

    def delete_service(self, service_id: str) -> None:
        self._require_unlocked()
        self._records.pop(service_id, None)
        self.save()

    def add_account(self, service: Service, account: Account) -> None:
        self._require_unlocked()
        service.accounts.append(account)
        self.update_service(service)

    def update_account(self, account: Account, *, username: str | None = None,
                       password: str | None = None, totp: str | None = None) -> None:
        """Mutate (and re-seal) an account in place; caller still needs to
        persist via update_service()."""
        self._require_unlocked()
        if username is not None:
            account.username = username
        if password is not None:
            account.password = self._seal(password, _field_aad(account.id, "pw"))
            account.rotated = _now_iso()
        if totp is not None:
            account.totp = self._seal(totp, _field_aad(account.id, "totp")) if totp else None

    def delete_account(self, service: Service, account_id: str) -> None:
        self._require_unlocked()
        service.accounts = [a for a in service.accounts if a.id != account_id]
        self.update_service(service)

    def set_backup_code_used(self, service: Service, code_id: str, used: bool) -> None:
        self._require_unlocked()
        for bc in service.backup_codes:
            if bc.id == code_id:
                bc.used = used
        self.update_service(service)

    # ------------------------------------------------- secret seal / reveal
    def _seal(self, plaintext: str, aad: bytes) -> EncryptedField:
        self._require_unlocked()
        blob = envelope.aesgcm_encrypt(bytes(self._dek), plaintext.encode("utf-8"), aad)
        return EncryptedField(nonce=blob.nonce, ct=blob.ct)

    def _open(self, field: EncryptedField, aad: bytes) -> str:
        self._require_unlocked()
        return envelope.aesgcm_decrypt(bytes(self._dek), GcmBlob(field.nonce, field.ct), aad).decode("utf-8")

    def make_account(self, username: str, password: str, totp_secret: str | None = None) -> Account:
        aid = new_id()
        pw = self._seal(password, _field_aad(aid, "pw"))
        tt = self._seal(totp_secret, _field_aad(aid, "totp")) if totp_secret else None
        return Account(id=aid, username=username, password=pw, totp=tt)

    def make_backup_code(self, value: str) -> BackupCode:
        cid = new_id()
        return BackupCode(id=cid, code=self._seal(value, _code_aad(cid)))

    def reveal_password(self, account: Account) -> str:
        return self._open(account.password, _field_aad(account.id, "pw"))

    def reveal_totp(self, account: Account) -> str | None:
        if account.totp is None:
            return None
        return self._open(account.totp, _field_aad(account.id, "totp"))

    def reveal_backup_code(self, code: BackupCode) -> str:
        return self._open(code.code, _code_aad(code.id))
