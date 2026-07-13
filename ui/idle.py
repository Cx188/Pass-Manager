"""Idle auto lock watcher.

Installs a global event filter; any mouse/keyboard activity resets a single-shot
timer. When the timer fires (default 5 min) it emits :attr:`timed_out`, which the
controller uses to zero the DEK and return to the lock screen. Active only while
the vault is unlocked (controller calls start/stop).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer, Signal


_RESET_EVENTS = {
    QEvent.Type.MouseMove,
    QEvent.Type.MouseButtonPress,
    QEvent.Type.MouseButtonRelease,
    QEvent.Type.KeyPress,
    QEvent.Type.Wheel,
    QEvent.Type.TouchBegin,
    QEvent.Type.TouchUpdate,
}


class IdleWatcher(QObject):
    timed_out = Signal()

    def __init__(self, timeout_seconds: int, parent=None) -> None:
        super().__init__(parent)
        self._timeout_ms = max(10_000, timeout_seconds * 1000)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.timed_out)
        self._active = False

    def set_timeout(self, seconds: int) -> None:
        self._timeout_ms = max(10_000, seconds * 1000)
        if self._active:
            self._timer.start(self._timeout_ms)

    def start(self) -> None:
        self._active = True
        self._timer.start(self._timeout_ms)

    def stop(self) -> None:
        self._active = False
        self._timer.stop()

    def seconds_remaining(self) -> int:
        if not self._active or not self._timer.isActive():
            return 0
        return max(0, self._timer.remainingTime() // 1000)

    def eventFilter(self, obj, event) -> bool:
        if self._active and event.type() in _RESET_EVENTS:
            self._timer.start(self._timeout_ms)
        return super().eventFilter(obj, event)
