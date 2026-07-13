"""Overlay modals: a dimming backdrop plus the recovery-code, confirm, and
toast variants used across the screens.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ui.theme import Color, Space, body_font, display_font, mono_font
from ui.transitions import fade_in, fade_out
from ui.widgets.buttons import Button
from ui.widgets.glass import GlassPanel


class ModalOverlay(QWidget):
    """Full-bleed dimming overlay hosting a centered card."""

    def __init__(self, host: QWidget, accent: str = Color.ACCENT, card_width: int = 540) -> None:
        super().__init__(host)
        self._host = host
        self._card = GlassPanel(accent=accent, radius=14)
        self._card.setMaximumWidth(card_width)
        self._card.setMinimumWidth(min(card_width, 420))

        outer = QVBoxLayout(self)
        outer.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self._card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

        host.installEventFilter(self)
        self._sync_geometry()

    def card_body(self) -> QVBoxLayout:
        return self._card.body()

    def _sync_geometry(self) -> None:
        self.setGeometry(self._host.rect())

    def eventFilter(self, obj, event) -> bool:
        if obj is self._host and event.type() == QEvent.Type.Resize:
            self._sync_geometry()
        return super().eventFilter(obj, event)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(4, 5, 7, 190))
        p.end()

    def mousePressEvent(self, e) -> None:
        # swallow backdrop clicks so they never reach the screen beneath
        e.accept()

    def open(self) -> None:
        self._sync_geometry()
        self.show()
        self.raise_()
        fade_in(self, 180)

    def dismiss(self, on_done=None) -> None:
        def _done():
            self._host.removeEventFilter(self)
            if on_done:
                on_done()
            self.deleteLater()

        fade_out(self, 140, on_done=_done)


class RecoveryCodeModal(ModalOverlay):
    """The one-time recovery-code gate shown right after setup."""

    confirmed = Signal()

    def __init__(self, host: QWidget, code: str) -> None:
        super().__init__(host, accent=Color.WARNING, card_width=600)
        self._code = code
        b = self.card_body()
        b.setSpacing(Space.MD)

        title = QLabel("Save your recovery code")
        title.setFont(display_font(16))
        title.setStyleSheet(f"color: {Color.TEXT};")
        b.addWidget(title)

        sub = QLabel("This code is shown once. It's the only way back into your vault if "
                     "the system keyring or this device is lost, store it somewhere safe "
                     "and offline.")
        sub.setWordWrap(True)
        sub.setFont(body_font(11))
        sub.setStyleSheet(f"color: {Color.TEXT_DIM};")
        b.addWidget(sub)

        code_box = QLabel(code)
        code_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        code_box.setFont(mono_font(15, spacing=1.0))
        code_box.setWordWrap(True)
        code_box.setStyleSheet(
            f"color: {Color.TEXT}; background: {Color.BG_RAISED};"
            f"border: 1px solid rgba(217,154,61,0.4); border-radius: 10px; padding: 16px;"
        )
        b.addWidget(code_box)

        copy_row = QHBoxLayout()
        self._copied = QLabel("")
        self._copied.setFont(mono_font(9))
        self._copied.setStyleSheet(f"color: {Color.SUCCESS};")
        copy_btn = Button("Copy code", variant="ghost")
        copy_btn.setFixedWidth(140)
        copy_btn.clicked.connect(self._copy)
        copy_row.addWidget(self._copied)
        copy_row.addStretch(1)
        copy_row.addWidget(copy_btn)
        b.addLayout(copy_row)

        self._check = QCheckBox("  I have saved my recovery code")
        self._check.setFont(body_font(11))
        self._check.setCursor(Qt.CursorShape.PointingHandCursor)
        self._check.setStyleSheet(
            f"QCheckBox {{ color: {Color.TEXT}; spacing: 8px; }}"
            f"QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 4px;"
            f" border: 1px solid {Color.LINE}; background: {Color.BG_RAISED}; }}"
            f"QCheckBox::indicator:checked {{ background: {Color.ACCENT};"
            f" border: 1px solid {Color.ACCENT}; }}"
        )
        self._check.toggled.connect(self._on_toggle)
        b.addWidget(self._check)

        self._confirm = Button("Continue", variant="primary")
        self._confirm.setEnabled(False)
        self._confirm.clicked.connect(self._on_confirm)
        b.addWidget(self._confirm)

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._code)
        self._copied.setText("Copied to clipboard")

    def _on_toggle(self, checked: bool) -> None:
        self._confirm.setEnabled(checked)

    def _on_confirm(self) -> None:
        if not self._check.isChecked():
            return
        self.dismiss(on_done=self.confirmed.emit)


class ConfirmModal(ModalOverlay):
    """Generic confirm / cancel dialog (e.g. delete an entry)."""

    accepted = Signal()
    rejected = Signal()

    def __init__(self, host: QWidget, title: str, message: str,
                 confirm_text: str = "Confirm", danger: bool = True) -> None:
        accent = Color.DANGER if danger else Color.ACCENT
        super().__init__(host, accent=accent, card_width=480)
        b = self.card_body()
        b.setSpacing(Space.MD)

        t = QLabel(title)
        t.setFont(display_font(14))
        t.setStyleSheet(f"color: {Color.TEXT};")
        b.addWidget(t)

        m = QLabel(message)
        m.setWordWrap(True)
        m.setFont(body_font(11))
        m.setStyleSheet(f"color: {Color.TEXT_DIM};")
        b.addWidget(m)

        row = QHBoxLayout()
        cancel = Button("Cancel", variant="ghost")
        confirm = Button(confirm_text, variant="danger" if danger else "primary")
        cancel.clicked.connect(lambda: self.dismiss(on_done=self.rejected.emit))
        confirm.clicked.connect(lambda: self.dismiss(on_done=self.accepted.emit))
        row.addWidget(cancel)
        row.addWidget(confirm)
        b.addLayout(row)


class Toast(QLabel):
    """Small transient status pill anchored near the bottom of a host widget."""

    def __init__(self, host: QWidget, text: str, accent: str = Color.ACCENT, ms: int = 1800) -> None:
        super().__init__(text, host)
        self.setFont(mono_font(10))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"color: {Color.TEXT}; background: {Color.BG_RAISED};"
            f"border: 1px solid {accent}; border-radius: 14px; padding: 9px 18px;"
        )
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()
        fade_in(self, 140)
        QTimer.singleShot(ms, lambda: fade_out(self, 200, on_done=self.deleteLater))

    def _reposition(self) -> None:
        host = self.parent()
        if host:
            x = (host.width() - self.width()) // 2
            y = host.height() - self.height() - 36
            self.move(max(0, x), max(0, y))
