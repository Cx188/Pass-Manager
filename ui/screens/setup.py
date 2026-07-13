"""First run setup screen: create the vault, show the one time recovery code,
enroll the system keyring protection.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.errors import CryptoError, UnlockCancelledError
from data.repository import Vault
from ui.icon import build_pixmap
from ui.theme import Color, Space, body_font, display_font, mono_font
from ui.widgets.buttons import Button
from ui.widgets.glass import GlassPanel, SectionHeader
from ui.widgets.modal import RecoveryCodeModal, Toast


class SetupScreen(QWidget):
    completed = Signal()

    def __init__(self, vault: Vault, parent=None) -> None:
        super().__init__(parent)
        self._vault = vault
        self._busy = False

        root = QVBoxLayout(self)
        root.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)

        card = GlassPanel(radius=14)
        card.setFixedWidth(600)
        b = card.body()
        b.setSpacing(Space.MD)

        mark_row = QHBoxLayout()
        mark_row.addStretch(1)
        mark = QLabel()
        mark.setPixmap(build_pixmap(56))
        mark_row.addWidget(mark)
        mark_row.addStretch(1)
        b.addLayout(mark_row)

        title = QLabel("Create your vault")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(display_font(17))
        title.setStyleSheet(f"color: {Color.TEXT};")
        b.addWidget(title)

        sub = QLabel("A new encryption key will be generated and protected by your "
                     "system keyring, with a one time recovery code as a backup.")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        sub.setFont(body_font(11))
        sub.setStyleSheet(f"color: {Color.TEXT_DIM};")
        b.addWidget(sub)

        b.addSpacing(Space.SM)
        b.addWidget(SectionHeader("What happens next?"))
        for step in ("Generate a 256 bit encryption key",
                     "Show a one time recovery code, save it",
                     "Enroll system keyring protection",
                     "Seal the vault, nothing is ever stored in plaintext"):
            line = QLabel(f"·  {step}")
            line.setFont(body_font(10))
            line.setStyleSheet(f"color: {Color.TEXT_DIM};")
            b.addWidget(line)

        b.addSpacing(Space.SM)
        self._status = QLabel(self._provider_message())
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setFont(mono_font(10))
        self._status.setStyleSheet(f"color: {Color.TEXT_DIM};")
        self._status.setWordWrap(True)
        b.addWidget(self._status)

        self._btn = Button("Create vault", variant="primary")
        self._btn.clicked.connect(self._start)
        b.addWidget(self._btn)

        row.addWidget(card)
        row.addStretch(1)
        root.addLayout(row)
        root.addStretch(1)

    # ------------------------------------------------------------------ logic
    def _provider_message(self) -> str:
        from core import keyring

        if keyring.secret_service_available():
            return "System keyring detected, it will be used to unlock automatically."
        return "No system keyring found, falling back to a local key file (weaker)."

    def _start(self) -> None:
        if self._busy:
            return
        self._busy = True
        self._btn.setEnabled(False)
        self._status.setStyleSheet(f"color: {Color.ACCENT};")
        self._status.setText("Setting things up — approve any keyring prompts…")
        # let the UI repaint before the blocking crypto/keyring work
        QTimer.singleShot(80, self._do_init)

    def _do_init(self) -> None:
        from core import keyring

        try:
            provider = keyring.detect_provider()
            result = self._vault.initialize(provider=provider)
        except UnlockCancelledError:
            self._fail("Keyring access cancelled, click Create vault to retry")
            return
        except CryptoError as exc:
            self._fail(f"Setup failed: {exc}")
            return
        except Exception as exc:  # pragma: no cover
            self._fail(f"Unexpected error: {exc}")
            return

        modal = RecoveryCodeModal(self, result.recovery_code)
        modal.confirmed.connect(self._on_recovery_saved)
        modal.open()

    def _on_recovery_saved(self) -> None:
        Toast(self, "Vault created", accent=Color.SUCCESS, ms=1200)
        QTimer.singleShot(500, self.completed.emit)

    def _fail(self, message: str) -> None:
        self._busy = False
        self._btn.setEnabled(True)
        self._status.setStyleSheet(f"color: {Color.DANGER};")
        self._status.setText(message)
