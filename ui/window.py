"""Frameless main window: a single rounded panel with a custom draggable
title bar. No native chrome (Qt.FramelessWindowHint); the panel paints its
own fill and border, the window paints a soft outer shadow.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.theme import Color, Radius, Space, display_font, mono_font

MARGIN = 16
RADIUS = Radius.XL


class TitleButton(QPushButton):
    """Small minimize/close glyph button for the title bar."""

    def __init__(self, kind: str, parent=None) -> None:
        super().__init__(parent)
        self._kind = kind  # "min" | "close"
        self._hover = False
        self.setFixedSize(32, 26)
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
        accent = Color.DANGER if self._kind == "close" else Color.TEXT_DIM
        if self._hover:
            bg = QColor(accent)
            bg.setAlphaF(0.14)
            p.setBrush(bg)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 6, 6)
        pen = QPen(QColor(accent if self._hover else Color.TEXT_DIM))
        pen.setWidthF(1.4)
        p.setPen(pen)
        r = self.rect()
        cx, cy = r.center().x(), r.center().y()
        if self._kind == "min":
            p.drawLine(cx - 5, cy + 3, cx + 5, cy + 3)
        else:
            p.drawLine(cx - 4, cy - 4, cx + 4, cy + 4)
            p.drawLine(cx - 4, cy + 4, cx + 4, cy - 4)
        p.end()


class TitleBar(QWidget):
    minimize_requested = Signal()
    close_requested = Signal()

    def __init__(self, title: str, subtitle: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(46)
        self._drag_offset: QPoint | None = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(Space.MD, 0, Space.SM, 0)
        lay.setSpacing(Space.SM)

        mark = QLabel()
        mark.setFixedSize(18, 18)
        mark.setStyleSheet(
            f"background: {Color.ACCENT}; border-radius: 5px;"
        )

        name = QLabel(title)
        name.setFont(display_font(12))
        name.setStyleSheet(f"color: {Color.TEXT};")

        self._status = QLabel(subtitle)
        self._status.setFont(mono_font(9))
        self._status.setStyleSheet(f"color: {Color.TEXT_FAINT};")

        self._min = TitleButton("min")
        self._close = TitleButton("close")
        self._min.clicked.connect(self.minimize_requested)
        self._close.clicked.connect(self.close_requested)

        lay.addWidget(mark)
        lay.addWidget(name)
        lay.addSpacing(Space.SM)
        lay.addWidget(self._status)
        lay.addStretch(1)
        lay.addWidget(self._min)
        lay.addWidget(self._close)

    def set_telemetry(self, text: str) -> None:
        self._status.setText(text)

    # --- drag to move the whole window ---
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            # Wayland ignores programmatic move(); let the compositor drive the
            # drag where supported, falling back to manual offset moves (X11).
            handle = self.window().windowHandle()
            if handle is not None and handle.startSystemMove():
                self._drag_offset = None
            else:
                self._drag_offset = e.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag_offset is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(e.globalPosition().toPoint() - self._drag_offset)
            e.accept()

    def mouseReleaseEvent(self, e):
        self._drag_offset = None

    def paintEvent(self, _e):
        p = QPainter(self)
        pen = QPen(QColor(Color.LINE))
        pen.setWidthF(1.0)
        p.setPen(pen)
        y = self.height() - 1
        p.drawLine(Space.MD, y, self.width() - Space.SM, y)
        p.end()


class RoundedPanel(QWidget):
    """The body panel: flat fill + a single hairline border."""

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QColor(Color.BG_PANEL))
        grad.setColorAt(1.0, QColor(Color.BG))
        p.setBrush(grad)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, RADIUS, RADIUS)

        pen = QPen(QColor(Color.LINE))
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, RADIUS, RADIUS)
        p.end()


class FramelessWindow(QWidget):
    def __init__(self, title: str = "Pass Manager", subtitle: str = "") -> None:
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(1120, 720)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)

        self.panel = RoundedPanel()
        outer.addWidget(self.panel)

        panel_lay = QVBoxLayout(self.panel)
        panel_lay.setContentsMargins(0, 0, 0, 0)
        panel_lay.setSpacing(0)

        self.title_bar = TitleBar(title, subtitle)
        self.title_bar.minimize_requested.connect(self.showMinimized)
        self.title_bar.close_requested.connect(self.close)
        panel_lay.addWidget(self.title_bar)

        self._content = QWidget()
        self._content_lay = QVBoxLayout(self._content)
        self._content_lay.setContentsMargins(0, 0, 0, 0)
        self._content_lay.setSpacing(0)
        panel_lay.addWidget(self._content, 1)

    def content_layout(self) -> QVBoxLayout:
        return self._content_lay

    def set_content(self, widget: QWidget) -> None:
        while self._content_lay.count():
            item = self._content_lay.takeAt(0)
            if item.widget():
                item.widget().hide()  # deleteLater() alone can leave it painting until the next idle loop
                item.widget().deleteLater()  # tear down old subtree + its timers
        self._content_lay.addWidget(widget)

    def paintEvent(self, _e):
        # soft outer shadow around the panel
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        base = QRectF(self.rect()).adjusted(MARGIN, MARGIN, -MARGIN, -MARGIN)
        for i, alpha in enumerate([0.05, 0.09, 0.14]):
            grow = (3 - i) * 3
            col = QColor(0, 0, 0)
            col.setAlphaF(alpha)
            pen = QPen(col)
            pen.setWidthF(2.0)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(base.adjusted(-grow, -grow, grow, grow), RADIUS + grow, RADIUS + grow)
        p.end()
