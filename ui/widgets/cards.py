"""Service card for the dashboard grid: monogram badge, name, account count."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ui.theme import Color, Radius, body_font, display_font, mono_font


class ServiceCard(QWidget):
    clicked = Signal(str)  # emits service id

    def __init__(self, service_id: str, name: str, subtitle: str, count: int,
                 accent: str = Color.ACCENT, parent=None) -> None:
        super().__init__(parent)
        self._id = service_id
        self._name = name
        self._subtitle = subtitle
        self._count = count
        self._accent = accent
        self._hover = False
        self.setMinimumSize(250, 92)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit(self._id)
        super().mouseReleaseEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)

        fill = QColor(Color.BG_PANEL)
        p.setBrush(fill)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, Radius.LG, Radius.LG)

        border = QColor(self._accent if self._hover else Color.LINE)
        border.setAlphaF(0.7 if self._hover else 1.0)
        pen = QPen(border)
        pen.setWidthF(1.2 if self._hover else 1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, Radius.LG, Radius.LG)

        # monogram badge
        bcx, bcy, br = rect.left() + 36, rect.center().y(), 20
        badge_fill = QColor(self._accent)
        badge_fill.setAlphaF(0.16)
        p.setBrush(badge_fill)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(bcx - br, bcy - br, br * 2, br * 2), Radius.MD, Radius.MD)

        p.setPen(QColor(self._accent))
        p.setFont(display_font(15))
        initial = (self._name[:1] or "?").upper()
        p.drawText(QRectF(bcx - br, bcy - br, br * 2, br * 2), Qt.AlignmentFlag.AlignCenter, initial)

        # name + subtitle
        text_left = rect.left() + 70
        p.setPen(QColor(Color.TEXT))
        p.setFont(display_font(12))
        p.drawText(QRectF(text_left, rect.top() + 20, rect.width() - 140, 22),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._name)

        p.setPen(QColor(Color.TEXT_DIM))
        p.setFont(body_font(9))
        p.drawText(QRectF(text_left, rect.top() + 46, rect.width() - 140, 20),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._subtitle)

        # count badge at the right
        badge_text = str(self._count)
        p.setFont(mono_font(11))
        bw = 32
        brect = QRectF(rect.right() - bw - 14, rect.center().y() - 13, bw, 26)
        cbg = QColor(Color.BG_RAISED)
        p.setBrush(cbg)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(brect, Radius.SM, Radius.SM)
        p.setPen(QColor(Color.TEXT_DIM))
        p.drawText(brect, Qt.AlignmentFlag.AlignCenter, badge_text)
        p.end()
