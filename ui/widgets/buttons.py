"""Buttons and left-nav items with a subtle hover/press response."""

from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QPushButton

from ui.theme import Color, Radius, display_font


class Button(QPushButton):
    """Rounded button; fill and border brighten slightly on hover."""

    def __init__(self, text: str, variant: str = "primary", parent=None) -> None:
        super().__init__(text, parent)
        self._variant = variant
        self._hover_t = 0.0
        self.setMinimumHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(display_font(11))
        self._anim = QPropertyAnimation(self, b"hoverAmount", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _accent(self) -> str:
        return {"primary": Color.ACCENT, "ghost": Color.TEXT_DIM,
                "danger": Color.DANGER, "accent2": Color.TEAL}.get(self._variant, Color.ACCENT)

    def getHoverAmount(self) -> float:
        return self._hover_t

    def setHoverAmount(self, v: float) -> None:
        self._hover_t = v
        self.update()

    hoverAmount = Property(float, getHoverAmount, setHoverAmount)

    def _animate_to(self, target: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._hover_t)
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, e):
        self._animate_to(1.0)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._animate_to(0.0)
        super().leaveEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        accent = self._accent()
        pressed = self.isDown()
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if pressed:
            rect = rect.adjusted(1, 1, -1, -1)

        ghost = self._variant == "ghost"
        if ghost:
            fill = QColor(accent)
            fill.setAlphaF(0.05 + 0.05 * self._hover_t)
        else:
            fill = QColor(accent)
            fill.setAlphaF(0.85 if not pressed else 0.7)
            if self._hover_t:
                fill = fill.lighter(100 + int(8 * self._hover_t))
        p.setBrush(fill)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, Radius.MD, Radius.MD)

        if ghost:
            border = QColor(Color.LINE)
            border = border.lighter(100 + int(30 * self._hover_t))
            pen = QPen(border)
            pen.setWidthF(1.0)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, Radius.MD, Radius.MD)

        p.setPen(QColor(Color.TEXT))
        p.setFont(self.font())
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())
        p.end()


class NavItem(QPushButton):
    """Left-nav entry: label with an active accent bar."""

    def __init__(self, label: str, parent=None) -> None:
        super().__init__(parent)
        self._label = label
        self._hover = False
        self.setCheckable(True)
        self.setMinimumHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        active = self.isChecked()
        rect = QRectF(self.rect()).adjusted(0, 2, 0, -2)

        if active or self._hover:
            fill = QColor(Color.TEXT)
            fill.setAlphaF(0.08 if active else 0.04)
            p.setBrush(fill)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, Radius.MD, Radius.MD)

        if active:
            bar = QColor(Color.ACCENT)
            p.setBrush(bar)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(rect.left(), rect.top() + 8, 3, rect.height() - 16), 1.5, 1.5)

        text_col = QColor(Color.TEXT if (active or self._hover) else Color.TEXT_DIM)
        p.setPen(text_col)
        p.setFont(display_font(11))
        p.drawText(QRectF(rect.left() + 18, rect.top(), rect.width() - 26, rect.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._label)
        p.end()
