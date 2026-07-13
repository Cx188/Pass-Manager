"""Lock screen: unlock via the system keyring, with a recovery-code fallback."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from core.errors import CryptoError, UnlockCancelledError
from core.keyring import Provider
from data.repository import Vault
from ui.icon import build_pixmap
from ui.theme import Color, Space, body_font, display_font, mono_font
from ui.widgets.buttons import Button
from ui.widgets.glass import GlassPanel
from ui.widgets.modal import ModalOverlay


class RecoveryUnlockModal(ModalOverlay):
    submitted = Signal(str)

    def __init__(self, host: QWidget) -> None:
        super().__init__(host, accent=Color.TEAL, card_width=520)
        b = self.card_body()
        b.setSpacing(Space.MD)

        title = QLabel("Recovery unlock")
        title.setFont(display_font(15))
        title.setStyleSheet(f"color: {Color.TEXT};")
        b.addWidget(title)

        sub = QLabel("Enter your one-time recovery code to unlock without the system keyring.")
        sub.setWordWrap(True)
        sub.setFont(body_font(11))
        sub.setStyleSheet(f"color: {Color.TEXT_DIM};")
        b.addWidget(sub)

        self._input = QLineEdit()
        self._input.setPlaceholderText("XXXXX-XXXXX-XXXXX-XXXXX-…")
        self._input.setFont(mono_font(12))
        self._input.setMinimumHeight(42)
        b.addWidget(self._input)

        row = QHBoxLayout()
        cancel = Button("Cancel", variant="ghost")
        unlock = Button("Unlock", variant="accent2")
        cancel.clicked.connect(lambda: self.dismiss())
        unlock.clicked.connect(self._submit)
        self._input.returnPressed.connect(self._submit)
        row.addWidget(cancel)
        row.addWidget(unlock)
        b.addLayout(row)

    def _submit(self) -> None:
        code = self._input.text().strip()
        if code:
            self.dismiss(on_done=lambda: self.submitted.emit(code))


class LockScreen(QWidget):
    unlocked = Signal()

    def __init__(self, vault: Vault, parent=None) -> None:
        super().__init__(parent)
        self._vault = vault
        self._busy = False

        root = QVBoxLayout(self)
        root.addStretch(2)

        mark_row = QHBoxLayout()
        mark_row.addStretch(1)
        self._mark = QLabel()
        self._mark.setPixmap(build_pixmap(72))
        mark_row.addWidget(self._mark)
        mark_row.addStretch(1)
        root.addLayout(mark_row)
        root.addSpacing(Space.LG)

        title = QLabel("Welcome back")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(display_font(22))
        title.setStyleSheet(f"color: {Color.TEXT};")
        root.addWidget(title)

        self._status = QLabel("Vault locked")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setFont(body_font(11))
        self._status.setStyleSheet(f"color: {Color.TEXT_DIM};")
        root.addWidget(self._status)

        root.addSpacing(Space.LG)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        col = QVBoxLayout()
        col.setSpacing(Space.SM)
        self._auth = Button("Unlock", variant="primary")
        self._auth.setFixedWidth(300)
        self._auth.clicked.connect(self._authenticate)
        col.addWidget(self._auth)
        self._recovery = Button("Use recovery code", variant="ghost")
        self._recovery.setFixedWidth(300)
        self._recovery.clicked.connect(self._open_recovery)
        col.addWidget(self._recovery)
        btn_row.addLayout(col)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        root.addStretch(3)

    # ------------------------------------------------------------------ state
    def reset(self) -> None:
        self._busy = False
        self._auth.setEnabled(True)
        self._recovery.setEnabled(True)
        self._status.setStyleSheet(f"color: {Color.TEXT_DIM};")
        self._status.setText("Vault locked")

    # ------------------------------------------------------------ keyring path
    def _authenticate(self) -> None:
        if self._busy:
            return
        self._busy = True
        self._auth.setEnabled(False)
        self._recovery.setEnabled(False)
        self._status.setStyleSheet(f"color: {Color.ACCENT};")
        prompt = ("Checking system keyring…"
                  if self._vault.primary_provider is Provider.SECRET_SERVICE
                  else "Decrypting…")
        self._status.setText(prompt)
        QTimer.singleShot(80, self._do_unlock)

    def _do_unlock(self) -> None:
        try:
            self._vault.unlock()
        except UnlockCancelledError:
            self._fail("Unlock cancelled")
            return
        except CryptoError as exc:
            self._fail(f"Couldn't unlock: {exc}")
            return
        except Exception as exc:  # pragma: no cover
            self._fail(f"Error: {exc}")
            return
        self._succeed()

    # ------------------------------------------------------------- recovery path
    def _open_recovery(self) -> None:
        modal = RecoveryUnlockModal(self)
        modal.submitted.connect(self._do_recovery)
        modal.open()

    def _do_recovery(self, code: str) -> None:
        self._busy = True
        self._auth.setEnabled(False)
        self._status.setStyleSheet(f"color: {Color.TEAL};")
        self._status.setText("Deriving key from recovery code…")

        def run():
            try:
                self._vault.unlock_recovery(code)
            except CryptoError:
                self._fail("Invalid recovery code")
                return
            except Exception as exc:  # pragma: no cover
                self._fail(f"Error: {exc}")
                return
            self._succeed()

        QTimer.singleShot(80, run)

    # ------------------------------------------------------------------ outcome
    def _succeed(self) -> None:
        self._status.setStyleSheet(f"color: {Color.SUCCESS};")
        self._status.setText("Unlocked")
        QTimer.singleShot(360, self.unlocked.emit)

    def _fail(self, message: str) -> None:
        self._busy = False
        self._auth.setEnabled(True)
        self._recovery.setEnabled(True)
        self._status.setStyleSheet(f"color: {Color.DANGER};")
        self._status.setText(message)
