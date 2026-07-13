"""Headless self-test for the crypto core.

Run:
    python -m core.selftest             # non-interactive crypto proof
    python -m core.selftest --keyring   # also exercise the real system keyring
                                        # (may prompt once to unlock it)

Proves: envelope wrap/unwrap on both unlock paths, that a wrong credential
makes the DEK unobtainable, recovery code + generator behavior, and keyring
signature determinism.
"""

from __future__ import annotations

import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import envelope, generator, kdf, recovery, secure_mem  # noqa: E402
from core.errors import DecryptionError  # noqa: E402

_PASS, _FAIL = 0, 0


def check(name: str, ok: bool) -> None:
    global _PASS, _FAIL
    mark = "PASS" if ok else "FAIL"
    if ok:
        _PASS += 1
    else:
        _FAIL += 1
    print(f"  [{mark}] {name}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


# --------------------------------------------------------------------------- #
def test_generator() -> None:
    section("Password generator")
    pw = generator.generate_password()
    check("default length is 35", len(pw) == 35)
    check("has upper", any(c in generator.UPPER for c in pw))
    check("has lower", any(c in generator.LOWER for c in pw))
    check("has digit", any(c in generator.DIGITS for c in pw))
    check("has symbol", any(c in generator.DEFAULT_SYMBOLS for c in pw))

    short = generator.generate_password(generator.PasswordOptions(length=12))
    check("respects min length 12", len(short) == 12)

    rejected = False
    try:
        generator.generate_password(generator.PasswordOptions(length=8))
    except ValueError:
        rejected = True
    check("rejects length below 12", rejected)
    check("entropy of 35-char is high (>180 bits)", generator.entropy_bits(pw) > 180)


def test_recovery_and_generator_uniqueness() -> None:
    section("Recovery code")
    c1 = recovery.generate_recovery_code()
    c2 = recovery.generate_recovery_code()
    check("recovery code has 8 groups", c1.count("-") == 7)
    check("two codes differ (CSPRNG)", c1 != c2)
    check(
        "normalization ignores formatting",
        recovery.normalize_recovery_code(c1.lower().replace("-", " "))
        == recovery.normalize_recovery_code(c1),
    )


def test_secure_mem() -> None:
    section("Secure memory")
    buf = bytearray(b"super-secret-key-material")
    secure_mem.wipe(buf)
    check("wipe zeroes and empties the buffer", len(buf) == 0)
    with secure_mem.SecretBox(b"\x01\x02\x03") as box:
        held = bytes(box)
    check("SecretBox exposes data inside context", held == b"\x01\x02\x03")
    check("SecretBox wipes on exit", len(box.data) == 0)


def test_envelope_aes_gate() -> None:
    section("AES-GCM gate (wrong key is unrecoverable)")
    key = secrets.token_bytes(32)
    blob = envelope.aesgcm_encrypt(key, b"top secret", aad=b"ctx")
    check("round-trips with correct key+aad", envelope.aesgcm_decrypt(key, blob, b"ctx") == b"top secret")

    wrong = bytearray(key)
    wrong[0] ^= 0xFF
    raised = False
    try:
        envelope.aesgcm_decrypt(bytes(wrong), blob, b"ctx")
    except DecryptionError:
        raised = True
    check("wrong key -> DecryptionError (not a boolean gate)", raised)

    raised = False
    try:
        envelope.aesgcm_decrypt(key, blob, b"different-aad")
    except DecryptionError:
        raised = True
    check("wrong AAD -> DecryptionError", raised)


def test_full_envelope_dual_path() -> None:
    section("Envelope: DEK wrapped under KEK-A (simulated) and KEK-B (recovery)")
    dek = envelope.generate_dek()
    check("DEK is 32 bytes", len(dek) == 32)

    # --- KEK-B: real recovery path (Argon2id) ---
    code = recovery.generate_recovery_code()
    salt_b = recovery.new_salt()
    kek_b = recovery.derive_kek_b(code, salt_b)
    protected_b = envelope.wrap_dek(bytes(dek), bytes(kek_b))
    unwrapped_b = envelope.unwrap_dek(protected_b, bytes(kek_b))
    check("KEK-B path recovers the exact DEK", bytes(unwrapped_b) == bytes(dek))

    wrong_kek_b = recovery.derive_kek_b("WRONG-CODE-2222-3333-4444-5555-6666-7777", salt_b)
    raised = False
    try:
        envelope.unwrap_dek(protected_b, bytes(wrong_kek_b))
    except DecryptionError:
        raised = True
    check("wrong recovery code -> DEK unobtainable", raised)

    # --- KEK-A: simulated keyring HMAC (deterministic) ---
    fake_signature = secrets.token_bytes(512)  # stands in for the keyring HMAC
    salt_a = secrets.token_bytes(16)
    kek_a1 = kdf.hkdf_sha256(fake_signature, salt_a, b"pm:kek-a:v1")
    kek_a2 = kdf.hkdf_sha256(fake_signature, salt_a, b"pm:kek-a:v1")
    check("KEK-A derivation is deterministic for same signature", bytes(kek_a1) == bytes(kek_a2))
    protected_a = envelope.wrap_dek(bytes(dek), bytes(kek_a1))
    unwrapped_a = envelope.unwrap_dek(protected_a, bytes(kek_a2))
    check("KEK-A path recovers the exact DEK", bytes(unwrapped_a) == bytes(dek))

    secure_mem.wipe(dek, kek_b, wrong_kek_b, kek_a1, kek_a2, unwrapped_a, unwrapped_b)


def test_argon2_params() -> None:
    section("Argon2id parameters")
    check("time_cost >= 3", kdf.ARGON2_TIME_COST >= 3)
    check("memory_cost >= 262144 KiB", kdf.ARGON2_MEMORY_COST >= 262_144)
    check("parallelism >= 4", kdf.ARGON2_PARALLELISM >= 4)


def test_keyring_interactive() -> None:
    section("System keyring (may prompt to unlock it)")
    from core import keyring

    if not keyring.secret_service_available():
        check("secret service available", False)
        print("    (skipping: no keyring daemon — the key-file fallback would be used)")
        return
    check("secret service available", True)

    # Dedicated test credential so this can never touch a real vault's secret.
    name = "PassManager.selftest.v1"
    challenge = keyring.new_challenge()
    salt = keyring.new_salt()
    try:
        print("    > enrolling test keyring secret...")
        keyring.enroll(name=name)
        print("    > signing challenge (1/2)...")
        sig1 = keyring.sign_challenge(challenge, name=name)
        print("    > signing challenge (2/2)...")
        sig2 = keyring.sign_challenge(challenge, name=name)
        check("keyring signature is deterministic", sig1 == sig2)

        kek_a = kdf.hkdf_sha256(sig1, salt, keyring.HKDF_INFO_A)
        dek = envelope.generate_dek()
        protected = envelope.wrap_dek(bytes(dek), bytes(kek_a))
        recovered = envelope.unwrap_dek(protected, bytes(kek_a))
        check("real keyring KEK-A unwraps the DEK", bytes(recovered) == bytes(dek))
        secure_mem.wipe(dek, kek_a, recovered)
    finally:
        try:
            keyring.delete_credential(name=name)
        except Exception:
            pass


# --------------------------------------------------------------------------- #
def main() -> int:
    print("Pass Manager crypto-core self-test")
    test_generator()
    test_recovery_and_generator_uniqueness()
    test_secure_mem()
    test_envelope_aes_gate()
    test_full_envelope_dual_path()
    test_argon2_params()

    if "--keyring" in sys.argv:
        test_keyring_interactive()

    print(f"\n--- {_PASS} passed, {_FAIL} failed ---")
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
