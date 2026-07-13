"""Low-level file I/O for the runtime data files.

No crypto lives here — just atomic reads/writes and JSON framing for the
already-encrypted containers the repository builds. Writes go through a temp
file + os.replace() so a crash mid-write can never leave a half-written store
behind. Filenames are deliberately generic; there's nothing in the names or
the raw bytes that hints at what the app does.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path

STORE_NAME = "store.dat"
META_NAME = "meta.bin"
CONFIG_NAME = "app.cfg"


def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


@dataclass(frozen=True)
class StoragePaths:
    directory: Path

    @property
    def store(self) -> Path:
        return self.directory / STORE_NAME

    @property
    def meta(self) -> Path:
        return self.directory / META_NAME

    @property
    def config(self) -> Path:
        return self.directory / CONFIG_NAME

    @classmethod
    def default(cls) -> "StoragePaths":
        """Data dir lives inside the app folder by default (portable install),
        override with PASSMANAGER_DATA_DIR for a different location."""
        env = os.environ.get("PASSMANAGER_DATA_DIR")
        if env:
            return cls(Path(env))
        return cls(Path(__file__).resolve().parent.parent / "vault")

    @classmethod
    def at(cls, directory: str | os.PathLike) -> "StoragePaths":
        return cls(Path(directory))


def ensure_dir(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)


def write_bytes(path: Path, data: bytes) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def read_bytes(path: Path) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def write_json(path: Path, obj: dict) -> None:
    write_bytes(path, json.dumps(obj, separators=(",", ":")).encode("utf-8"))


def read_json(path: Path) -> dict:
    return json.loads(read_bytes(path).decode("utf-8"))


def exists(path: Path) -> bool:
    return path.is_file()
