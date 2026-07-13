"""Clipboard with visible auto clear countdown.

Copies a secret to the system clipboard and clears it after N seconds. Clearing
only happens if the clipboard *still holds our value* — so we never wipe whatever
the user copied in the meantime.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication


class ClipboardManager(QObject):
    tick = Signal(int)   # seconds remaining
    cleared = Signal()

    def __init__(self, seconds: int = 15, parent=None) -> None:
        super().__init__(parent)
        self._seconds = seconds
        self._remaining = 0
        self._value: str | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

    def copy(self, text: str, seconds: int | None = None) -> None:
        QGuiApplication.clipboard().setText(text)
        self._value = text
        self._remaining = seconds if seconds is not None else self._seconds
        self.tick.emit(self._remaining)
        self._timer.start()

    def _on_tick(self) -> None:
        self._remaining -= 1
        if self._remaining <= 0:
            self.clear_now()
            return
        self.tick.emit(self._remaining)

    def clear_now(self) -> None:
        self._timer.stop()
        clip = QGuiApplication.clipboard()
        if self._value is not None and clip.text() == self._value:
            clip.clear()
        self._value = None
        self._remaining = 0
        self.cleared.emit()
