"""Headless self-test for the data + domain layer.

Run:
    python -m data.selftest

Uses the key-file provider (no keyring prompts) and the recovery path, so it
runs fully non-interactively. Proves: first-run setup, CRUD, on-demand reveal,
search, that NO plaintext secret or metadata reaches disk, lock-wipes-state,
and that a fresh Vault can re-open and decrypt via both the primary (key-file)
and recovery paths.
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.keyring import Provider  # noqa: E402
from data.models import EntryType, Service, new_id  # noqa: E402
from data.repository import Vault, VaultLocked  # noqa: E402
from data.store_io import StoragePaths  # noqa: E402

_PASS, _FAIL = 0, 0

SECRET_PW = "Vael0r@nt-Pr1me-7x!"
SECRET_PW2 = "9eC0nd-Acc0unt-#42"
TOTP_SEED = "JBSWY3DPEHPK3PXP"
SERVICE_NAME = "Valorant"
USERNAME = "AcePlayerOne"


def check(name: str, ok: bool) -> None:
    global _PASS, _FAIL
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if ok:
        _PASS += 1
    else:
        _FAIL += 1


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def build_vault(tmp: str):
    paths = StoragePaths.at(tmp)
    vault = Vault(paths)
    check("fresh location reports no existing vault", not vault.exists())

    init = vault.initialize(provider=Provider.KEYFILE)  # no prompts
    check("recovery code generated", bool(init.recovery_code) and "-" in init.recovery_code)
    check("vault exists after init", vault.exists())
    check("vault is unlocked after init", vault.unlocked)
    return vault, paths, init.recovery_code


def populate(vault: Vault):
    section("CRUD + seal")
    a1 = vault.make_account(USERNAME, SECRET_PW, totp_secret=TOTP_SEED)
    a2 = vault.make_account("SecondMain", SECRET_PW2)
    svc = Service(id=new_id(), type=EntryType.APPLICATION, name=SERVICE_NAME, accounts=[a1, a2])
    vault.add_service(svc)

    web = Service(id=new_id(), type=EntryType.WEBSITE, name="Gmail", url="https://mail.google.com",
                  accounts=[vault.make_account("me@gmail.com", "Em@il-Pass-001")])
    vault.add_service(web)

    codes = [vault.make_backup_code(c) for c in ("AAAA-1111", "BBBB-2222", "CCCC-3333")]
    bc = Service(id=new_id(), type=EntryType.BACKUP_CODES, name="GitHub Recovery", backup_codes=codes)
    vault.add_service(bc)

    check("three services stored", len(vault.services()) == 3)
    check("valorant has account-count badge 2", svc.count == 2)
    check("backup set count 3", bc.count == 3)
    return svc, a1, a2, bc


def test_reveal(vault: Vault, a1, a2, bc):
    section("On-demand reveal")
    check("reveal account 1 password", vault.reveal_password(a1) == SECRET_PW)
    check("reveal account 2 password", vault.reveal_password(a2) == SECRET_PW2)
    check("reveal TOTP seed", vault.reveal_totp(a1) == TOTP_SEED)
    check("account 2 has no TOTP", vault.reveal_totp(a2) is None)
    check("reveal a backup code", vault.reveal_backup_code(bc.backup_codes[0]) == "AAAA-1111")


def test_no_plaintext(paths: StoragePaths):
    section("No plaintext on disk")
    store = paths.store.read_bytes()
    meta = paths.meta.read_bytes()
    for label, needle in [
        ("password", SECRET_PW.encode()),
        ("2nd password", SECRET_PW2.encode()),
        ("totp seed", TOTP_SEED.encode()),
        ("service name", SERVICE_NAME.encode()),
        ("username", USERNAME.encode()),
        ("backup code", b"AAAA-1111"),
    ]:
        absent = needle not in store and needle not in meta
        check(f"{label} not found anywhere on disk", absent)


def test_search(vault: Vault):
    section("Search / filter")
    check("search 'valor' finds service", any(s.name == SERVICE_NAME for s in vault.services(query="valor")))
    check("search by username", any(s.name == SERVICE_NAME for s in vault.services(query="aceplayer")))
    check("filter by type WEBSITE", [s.name for s in vault.services(type=EntryType.WEBSITE)] == ["Gmail"])
    check("search miss returns empty", vault.services(query="zzzz-nope") == [])


def test_lock(vault: Vault, a1):
    section("Lock wipes state")
    vault.lock()
    check("locked vault reports not unlocked", not vault.unlocked)
    raised = False
    try:
        vault.reveal_password(a1)
    except VaultLocked:
        raised = True
    check("reveal after lock -> VaultLocked", raised)


def test_reopen(paths: StoragePaths, recovery_code: str):
    section("Reopen with a fresh Vault instance")
    # primary (key-file) path
    v2 = Vault(paths)
    check("existing vault detected", v2.exists())
    v2.unlock()  # key-file primary, no prompt
    svc = next(s for s in v2.services() if s.name == SERVICE_NAME)
    check("key-file unlock recovers password", v2.reveal_password(svc.accounts[0]) == SECRET_PW)
    v2.lock()

    # recovery path
    v3 = Vault(paths)
    v3.unlock_recovery(recovery_code)
    svc3 = next(s for s in v3.services() if s.name == SERVICE_NAME)
    check("recovery unlock recovers password", v3.reveal_password(svc3.accounts[0]) == SECRET_PW)

    # wrong recovery code must fail
    v4 = Vault(paths)
    raised = False
    try:
        v4.unlock_recovery("WRONG-0000-1111-2222-3333-4444-5555-6666")
    except Exception:
        raised = True
    check("wrong recovery code fails to unlock", raised)
    v3.lock()


def test_edit_persists(paths: StoragePaths):
    section("Edit persists across reload")
    v = Vault(paths)
    v.unlock()
    bc = next(s for s in v.services() if s.type is EntryType.BACKUP_CODES)
    bc.backup_codes[0].used = True
    v.update_service(bc)
    v.lock()

    v2 = Vault(paths)
    v2.unlock()
    bc2 = next(s for s in v2.services() if s.type is EntryType.BACKUP_CODES)
    check("backup code 'used' flag persisted", bc2.backup_codes[0].used is True)
    check("other codes still unused", bc2.backup_codes[1].used is False)
    v2.lock()


def test_recovery_param_drift(tmp: str) -> None:
    section("Recovery honors stored Argon2 params (version-drift safety)")
    import json

    from core import envelope, recovery
    from data.store_io import b64e

    drift_dir = os.path.join(tmp, "drift")
    paths = StoragePaths.at(drift_dir)
    v = Vault(paths)
    v.initialize(provider=Provider.KEYFILE)

    # Re-seal the recovery path (B) under a NON-default parallelism, as if it had
    # been created by an older/different build, and rewrite the manifest.
    manifest = json.loads(paths.meta.read_bytes())
    dek = bytes(v._dek)
    code = recovery.generate_recovery_code()
    salt = recovery.new_salt()
    kek_b = recovery.derive_kek_b(code, salt, parallelism=2)  # non-default
    blob = envelope.wrap_dek(dek, bytes(kek_b))
    manifest["paths"]["b"] = {"s": b64e(salt), "p": {"t": 4, "m": 262144, "par": 2},
                              "n": b64e(blob.nonce), "c": b64e(blob.ct)}
    paths.meta.write_bytes(json.dumps(manifest).encode())
    v.lock()

    v2 = Vault(paths)
    v2.unlock_recovery(code)  # must read par=2 from the manifest, not the default
    check("recovery unlock honors stored non-default params", v2.unlocked)
    v2.lock()


def main() -> int:
    print("Pass Manager data-layer self-test")
    with tempfile.TemporaryDirectory(prefix="passmanager_test_") as tmp:
        section("First-run setup (key-file provider)")
        vault, paths, recovery_code = build_vault(tmp)
        svc, a1, a2, bc = populate(vault)
        test_reveal(vault, a1, a2, bc)
        test_no_plaintext(paths)
        test_search(vault)
        test_lock(vault, a1)
        test_reopen(paths, recovery_code)
        test_edit_persists(paths)
        test_recovery_param_drift(tmp)

    print(f"\n--- {_PASS} passed, {_FAIL} failed ---")
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
