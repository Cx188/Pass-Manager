"""Data + domain layer.

Modules:
    store_io    read/write store.dat, meta.bin, app.cfg
    models      Service / Account / BackupCode dataclasses + serialization
    repository  CRUD over the decrypted model, re-encrypt on save, search/filter
    config      app.cfg load/save (non-sensitive settings)
"""
