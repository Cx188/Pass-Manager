"""Panel and section-header primitives used across every screen."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ui.theme import Color, Radius, Space, display_font


class GlassPanel(QWidget):
    """Flat panel with a hairline border; ``accent`` tints the border only."""

    def __init__(self, parent=None, accent: str = Color.LINE, radius: int = Radius.LG,
                 fill_alpha: float = 1.0) -> None:
        super().__init__(parent)
        self._accent = accent
        self._radius = radius
        self._fill_alpha = fill_alpha
        self._body = QVBoxLayout(self)
        self._body.setContentsMargins(Space.LG, Space.LG, Space.LG, Space.LG)
        self._body.setSpacing(Space.MD)

    def body(self) -> QVBoxLayout:
        return self._body

    def set_accent(self, hex_color: str) -> None:
        self._accent = hex_color
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        fill = QColor(Color.BG_PANEL)
        fill.setAlphaF(self._fill_alpha)
        p.setBrush(fill)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, self._radius, self._radius)

        border = QColor(self._accent)
        border.setAlphaF(0.55 if self._accent != Color.LINE else 1.0)
        pen = QPen(border)
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, self._radius, self._radius)
        p.end()


class SectionHeader(QWidget):
    """Small caps label with a thin divider beneath."""

    def __init__(self, title: str, accent: str = Color.ACCENT, parent=None) -> None:
        super().__init__(parent)
        self._title = title
        self._accent = accent
        self.setFixedHeight(32)

    def setTitle(self, title: str) -> None:
        self._title = title
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setFont(display_font(10, spacing=0.8))

        p.setPen(QColor(Color.TEXT_DIM))
        p.drawText(0, 0, self.width(), 20, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   self._title.upper())

        grad = QLinearGradient(0, 0, self.width(), 0)
        c0 = QColor(Color.LINE)
        c0.setAlphaF(1.0)
        c1 = QColor(Color.LINE)
        c1.setAlphaF(0.0)
        grad.setColorAt(0.0, c0)
        grad.setColorAt(1.0, c1)
        pen = QPen(grad, 1.0)
        p.setPen(pen)
        y = self.height() - 4
        p.drawLine(0, y, self.width(), y)
        p.end()
