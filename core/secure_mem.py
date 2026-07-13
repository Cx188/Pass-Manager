"""Best-effort zeroing of sensitive material in memory.

CPython gives no guarantee that a value has exactly one copy in memory, so this
is mitigation, not a hard guarantee — documented and accepted. The rule we *can*
enforce: keep all live key material in ``bytearray`` (mutable) so we can
overwrite it on lock, and never let plaintext keys live in ``str`` (immutable,
interned, uncontrollable).
"""

from __future__ import annotations

from typing import Iterable


def wipe(*buffers: bytearray | None) -> None:
    """Overwrite each bytearray in place with zeros, then truncate to empty.

    Accepts ``None`` and already-empty buffers for convenience so callers can
    wipe optional secrets without guarding every one.
    """
    for buf in buffers:
        if not buf:
            continue
        if not isinstance(buf, bytearray):
            raise TypeError(f"wipe() requires bytearray, got {type(buf).__name__}")
        for i in range(len(buf)):
            buf[i] = 0
        del buf[:]


def wipe_all(buffers: Iterable[bytearray | None]) -> None:
    """Wipe an iterable of buffers (convenience wrapper around :func:`wipe`)."""
    wipe(*buffers)


class SecretBox:
    """Context manager that holds secret bytes and wipes them on exit.

    Example::

        with SecretBox(derive_kek_b(code, salt)) as kek:
            blob = wrap_dek(dek, pub, bytes(kek.data))
        # kek is zeroed here, even on exception
    """

    __slots__ = ("data",)

    def __init__(self, data: bytes | bytearray) -> None:
        self.data: bytearray = bytearray(data)

    def __enter__(self) -> "SecretBox":
        return self

    def __exit__(self, *_exc) -> None:
        wipe(self.data)

    def __bytes__(self) -> bytes:
        return bytes(self.data)

    def __len__(self) -> int:
        return len(self.data)
