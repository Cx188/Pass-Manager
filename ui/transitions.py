"""Smooth screen transitions via QPropertyAnimation.

Helpers for fading a widget in/out, and cross-fading a QStackedWidget between
pages so screen switches don't feel like a hard cut.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtWidgets import QGraphicsOpacityEffect, QStackedWidget, QWidget


def fade_in(widget: QWidget, duration: int = 320) -> QPropertyAnimation:
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


def fade_out(widget: QWidget, duration: int = 240, on_done=None) -> QPropertyAnimation:
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setEasingCurve(QEasingCurve.Type.InCubic)

    def _finish():
        widget.setGraphicsEffect(None)
        if on_done:
            on_done()

    anim.finished.connect(_finish)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


class FadeStack(QStackedWidget):
    """A QStackedWidget that cross-fades when the current page changes."""

    def __init__(self, parent=None, duration: int = 300) -> None:
        super().__init__(parent)
        self._duration = duration

    def fade_to(self, index: int) -> None:
        if index == self.currentIndex() or not (0 <= index < self.count()):
            self.setCurrentIndex(index)
            return
        incoming = self.widget(index)
        self.setCurrentIndex(index)
        incoming.show()
        fade_in(incoming, self._duration)

    def fade_to_widget(self, widget: QWidget) -> None:
        self.fade_to(self.indexOf(widget))
