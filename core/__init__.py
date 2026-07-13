"""Crypto core — no GUI, headless-testable.

Modules:
    kdf         Argon2id + HKDF wrappers
    envelope    AES 256 GCM primitives; DEK wrap/unwrap
    keyring     system keyring provider + local key file fallback
    recovery    one time recovery code generation + KEK derivation
    secure_mem  bytearray zeroing helpers
    generator   CSPRNG password generator
"""
