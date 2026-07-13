"""Animated indicators: password strength meter and countdown ring."""

from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
)
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ui.theme import Color, mono_font


def _lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def _lerp_color(c1: str, c2: str, t: float) -> QColor:
    a, b = QColor(c1), QColor(c2)
    return QColor(_lerp(a.red(), b.red(), t), _lerp(a.green(), b.green(), t), _lerp(a.blue(), b.blue(), t))


def strength_color(value: float) -> QColor:
    """Red -> amber -> blue -> green as strength rises."""
    if value < 0.5:
        return _lerp_color(Color.DANGER, Color.WARNING, value / 0.5)
    return _lerp_color(Color.WARNING, Color.SUCCESS, (value - 0.5) / 0.5)


class StrengthMeter(QWidget):
    """Horizontal bar; ``set_value(0..1)`` animates the fill + colour."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._value = 0.0
        self.setMinimumHeight(8)
        self.setMaximumHeight(8)
        self._anim = QPropertyAnimation(self, b"value", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def getValue(self) -> float:
        return self._value

    def setValue(self, v: float) -> None:
        self._value = max(0.0, min(1.0, v))
        self.update()

    value = Property(float, getValue, setValue)

    def set_value(self, v: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._value)
        self._anim.setEndValue(max(0.0, min(1.0, v)))
        self._anim.start()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = r.height() / 2

        track = QColor(Color.LINE)
        p.setBrush(track)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(r, radius, radius)

        if self._value > 0.0:
            fill_w = max(r.height(), r.width() * self._value)
            col = strength_color(self._value)
            grad = QLinearGradient(0, 0, fill_w, 0)
            dark = QColor(col)
            dark.setAlphaF(0.7)
            grad.setColorAt(0.0, dark)
            grad.setColorAt(1.0, col)
            p.setBrush(grad)
            p.drawRoundedRect(QRectF(r.left(), r.top(), fill_w, r.height()), radius, radius)
        p.end()


class CountdownRing(QWidget):
    """Circular progress ring with centre text (TOTP timer, reveal countdown)."""

    def __init__(self, parent=None, accent: str = Color.ACCENT, diameter: int = 64) -> None:
        super().__init__(parent)
        self._fraction = 1.0
        self._text = ""
        self._accent = accent
        self.setFixedSize(diameter, diameter)
        self._anim = QPropertyAnimation(self, b"fraction", self)
        self._anim.setDuration(350)

    def getFraction(self) -> float:
        return self._fraction

    def setFraction(self, v: float) -> None:
        self._fraction = max(0.0, min(1.0, v))
        self.update()

    fraction = Property(float, getFraction, setFraction)

    def set_fraction(self, v: float, animate: bool = True) -> None:
        if not animate:
            self.setFraction(v)
            return
        self._anim.stop()
        self._anim.setStartValue(self._fraction)
        self._anim.setEndValue(max(0.0, min(1.0, v)))
        self._anim.start()

    def set_text(self, text: str) -> None:
        self._text = text
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        m = 5
        rect = QRectF(self.rect()).adjusted(m, m, -m, -m)

        track = QColor(Color.LINE)
        pen = QPen(track)
        pen.setWidthF(3.5)
        p.setPen(pen)
        p.drawArc(rect, 0, 360 * 16)

        pen = QPen(QColor(self._accent))
        pen.setWidthF(3.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        span = int(-360 * self._fraction * 16)
        p.drawArc(rect, 90 * 16, span)

        if self._text:
            p.setPen(QColor(Color.TEXT))
            p.setFont(mono_font(12))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)
        p.end()
