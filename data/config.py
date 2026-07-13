"""Non-sensitive app settings (app.cfg). No secrets ever live here.

Holds only cosmetic / behavioral preferences: theme, idle-timeout, last window
geometry. Plain JSON — safe to read, contains nothing useful to an attacker.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from data import store_io
from data.store_io import StoragePaths

IDLE_TIMEOUT_DEFAULT = 300  # seconds (5 minutes)
CLIPBOARD_CLEAR_DEFAULT = 15  # seconds
REVEAL_TIMEOUT_DEFAULT = 20  # seconds a revealed password stays visible


@dataclass
class AppConfig:
    theme: str = "dark"
    idle_timeout_seconds: int = IDLE_TIMEOUT_DEFAULT
    clipboard_clear_seconds: int = CLIPBOARD_CLEAR_DEFAULT
    reveal_timeout_seconds: int = REVEAL_TIMEOUT_DEFAULT
    window_geometry: str | None = None  # base64 QByteArray, set by the UI

    @classmethod
    def load(cls, paths: StoragePaths) -> "AppConfig":
        if not store_io.exists(paths.config):
            return cls()
        try:
            data = store_io.read_json(paths.config)
        except Exception:
            return cls()  # corrupt config -> fall back to defaults, never crash
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, paths: StoragePaths) -> None:
        store_io.write_json(paths.config, asdict(self))
