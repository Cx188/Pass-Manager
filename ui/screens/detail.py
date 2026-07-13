"""Entry detail / reveal: reveal/copy with auto clear + re-mask, TOTP, backup
codes used/unused, edit and delete.

Unlocking happens once per session on the lock screen; reveals here don't
re-prompt. The idle auto-lock and the manual Lock button are what protect the
session in between (see ui/idle.py and data/repository.py Vault.lock()).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core import generator, totp as totplib
from data.models import Account, EntryType, Service
from data.repository import Vault
from ui.clipboard import ClipboardManager
from ui.theme import Color, Space, body_font, display_font, mono_font
from ui.widgets.buttons import Button
from ui.widgets.glass import GlassPanel, SectionHeader
from ui.widgets.meters import CountdownRing
from ui.widgets.modal import ConfirmModal, ModalOverlay, Toast

_MASK = "•" * 14


def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(mono_font(9))
    lbl.setStyleSheet(f"color: {Color.TEXT_DIM};")
    return lbl


class EditAccountModal(ModalOverlay):
    """Add or edit an account: username + optional new password + optional TOTP."""

    saved = Signal(dict)

    def __init__(self, host: QWidget, *, title: str, username: str = "",
                 require_password: bool = False) -> None:
        super().__init__(host, accent=Color.ACCENT, card_width=560)
        self._require_password = require_password
        b = self.card_body()
        b.setSpacing(Space.SM)

        t = QLabel(title)
        t.setFont(display_font(15))
        t.setStyleSheet(f"color: {Color.TEXT};")
        b.addWidget(t)

        b.addWidget(_field_label("Username / email"))
        self._user = QLineEdit(username)
        self._user.setMinimumHeight(38)
        self._user.setFont(body_font(12))
        b.addWidget(self._user)

        b.addWidget(_field_label("New password" if require_password else "New password (blank = keep current)"))
        pw_row = QHBoxLayout()
        self._pw = QLineEdit()
        self._pw.setMinimumHeight(38)
        self._pw.setFont(mono_font(12))
        gen = Button("Generate", variant="ghost")
        gen.setFixedWidth(100)
        gen.clicked.connect(lambda: self._pw.setText(generator.generate_password()))
        pw_row.addWidget(self._pw, 1)
        pw_row.addWidget(gen)
        b.addLayout(pw_row)
        if require_password:
            self._pw.setText(generator.generate_password())

        b.addWidget(_field_label("TOTP secret (optional, blank = keep current)"))
        self._totp = QLineEdit()
        self._totp.setMinimumHeight(38)
        self._totp.setFont(mono_font(11))
        b.addWidget(self._totp)

        self._err = QLabel("")
        self._err.setFont(body_font(9))
        self._err.setStyleSheet(f"color: {Color.DANGER};")
        b.addWidget(self._err)

        row = QHBoxLayout()
        cancel = Button("Cancel", variant="ghost")
        save = Button("Save", variant="primary")
        cancel.clicked.connect(lambda: self.dismiss())
        save.clicked.connect(self._submit)
        row.addWidget(cancel)
        row.addWidget(save)
        b.addLayout(row)

    def _submit(self) -> None:
        username = self._user.text().strip()
        password = self._pw.text()
        totp = self._totp.text().strip()
        if not username:
            self._err.setText("Username is required")
            return
        if self._require_password and not password:
            self._err.setText("Password is required")
            return
        if totp and not totplib.is_valid_secret(totp):
            self._err.setText("That TOTP secret doesn't look valid")
            return
        payload = {"username": username,
                   "password": password or None,
                   "totp": totp or None}
        self.dismiss(on_done=lambda: self.saved.emit(payload))


class AccountRow(GlassPanel):
    reveal_clicked = Signal(object)
    copy_clicked = Signal(object)
    totp_clicked = Signal(object)
    edit_clicked = Signal(object)
    delete_clicked = Signal(object)

    def __init__(self, account: Account, parent=None) -> None:
        super().__init__(radius=12, parent=parent)
        self._account = account
        self._remaining = 0
        self._remask_timer = QTimer(self)
        self._remask_timer.setInterval(1000)
        self._remask_timer.timeout.connect(self._remask_tick)
        self._totp_secret: str | None = None
        self._totp_timer = QTimer(self)
        self._totp_timer.setInterval(1000)
        self._totp_timer.timeout.connect(self._totp_tick)

        b = self.body()
        b.setSpacing(Space.SM)

        top = QHBoxLayout()
        info = QVBoxLayout()
        info.setSpacing(2)
        user = QLabel(account.username)
        user.setFont(display_font(13))
        user.setStyleSheet(f"color: {Color.TEXT};")
        self._secret = QLabel(_MASK)
        self._secret.setFont(mono_font(14))
        self._secret.setStyleSheet(f"color: {Color.TEXT_DIM};")
        self._secret.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info.addWidget(user)
        info.addWidget(self._secret)
        top.addLayout(info, 1)

        self._remask_lbl = QLabel("")
        self._remask_lbl.setFont(mono_font(9))
        self._remask_lbl.setStyleSheet(f"color: {Color.WARNING};")
        top.addWidget(self._remask_lbl)

        reveal = Button("Reveal", variant="ghost")
        reveal.setFixedWidth(96)
        reveal.clicked.connect(lambda: self.reveal_clicked.emit(account))
        copy = Button("Copy", variant="ghost")
        copy.setFixedWidth(84)
        copy.clicked.connect(lambda: self.copy_clicked.emit(account))
        top.addWidget(reveal)
        top.addWidget(copy)
        b.addLayout(top)

        actions = QHBoxLayout()
        if account.has_totp:
            twofa = Button("2FA code", variant="accent2")
            twofa.setFixedWidth(96)
            twofa.clicked.connect(lambda: self.totp_clicked.emit(account))
            actions.addWidget(twofa)
            self._totp_code = QLabel("")
            self._totp_code.setFont(mono_font(15, spacing=1.5))
            self._totp_code.setStyleSheet(f"color: {Color.TEAL};")
            actions.addWidget(self._totp_code)
            self._totp_ring = CountdownRing(accent=Color.TEAL, diameter=36)
            self._totp_ring.setVisible(False)
            actions.addWidget(self._totp_ring)
        actions.addStretch(1)
        edit = Button("Edit", variant="ghost")
        edit.setFixedWidth(76)
        edit.clicked.connect(lambda: self.edit_clicked.emit(account))
        rm = Button("Delete", variant="danger")
        rm.setFixedWidth(88)
        rm.clicked.connect(lambda: self.delete_clicked.emit(account))
        actions.addWidget(edit)
        actions.addWidget(rm)
        b.addLayout(actions)

    # reveal / re-mask
    def show_password(self, pw: str, seconds: int) -> None:
        self._secret.setText(pw)
        self._secret.setStyleSheet(f"color: {Color.TEXT};")
        self._remaining = seconds
        self._remask_lbl.setText(f"hides in {seconds}s")
        self._remask_timer.start()

    def _remask_tick(self) -> None:
        self._remaining -= 1
        if self._remaining <= 0:
            self.remask()
            return
        self._remask_lbl.setText(f"hides in {self._remaining}s")

    def remask(self) -> None:
        self._remask_timer.stop()
        self._secret.setText(_MASK)
        self._secret.setStyleSheet(f"color: {Color.TEXT_DIM};")
        self._remask_lbl.setText("")

    # totp
    def start_totp(self, secret: str | None) -> None:
        if not secret:
            return
        self._totp_secret = secret
        self._totp_ring.setVisible(True)
        self._totp_tick()
        self._totp_timer.start()

    def _totp_tick(self) -> None:
        if not self._totp_secret:
            return
        try:
            code, _rem, frac = totplib.code_and_remaining(self._totp_secret)
        except Exception:
            self._totp_code.setText("error")
            self._totp_timer.stop()
            return
        self._totp_code.setText(f"{code[:3]} {code[3:]}")
        self._totp_ring.set_fraction(frac, animate=False)


class BackupCodeRow(QWidget):
    toggled = Signal(str, bool)  # code_id, used

    def __init__(self, code_id: str, used: bool, parent=None) -> None:
        super().__init__(parent)
        self._id = code_id
        self._used = used
        lay = QHBoxLayout(self)
        lay.setContentsMargins(Space.MD, Space.SM, Space.MD, Space.SM)
        self._label = QLabel(_MASK)
        self._label.setFont(mono_font(13))
        self._apply_style()
        lay.addWidget(self._label, 1)
        self._btn = Button("Used" if used else "Mark used", variant="ghost")
        self._btn.setFixedWidth(128)
        self._btn.clicked.connect(self._toggle)
        lay.addWidget(self._btn)

    def reveal(self, value: str) -> None:
        self._plain = value
        self._render_value()

    def _render_value(self) -> None:
        text = getattr(self, "_plain", _MASK)
        if self._used and text != _MASK:
            self._label.setText(f"<s>{text}</s>")
        else:
            self._label.setText(text)

    def _apply_style(self) -> None:
        color = Color.TEXT_FAINT if self._used else Color.TEXT
        self._label.setStyleSheet(f"color: {color};")

    def _toggle(self) -> None:
        self._used = not self._used
        self._btn.setText("Used" if self._used else "Mark used")
        self._apply_style()
        self._render_value()
        self.toggled.emit(self._id, self._used)


class DetailScreen(QWidget):
    back = Signal()
    changed = Signal()

    def __init__(self, vault: Vault, clipboard: ClipboardManager, parent=None) -> None:
        super().__init__(parent)
        self._vault = vault
        self._clipboard = clipboard
        self._service: Service | None = None
        self.reveal_seconds = 20
        self.clipboard_seconds = 15

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(Space.XL, Space.LG, Space.XL, Space.LG)
        self._root.setSpacing(Space.MD)
        self._clipboard.tick.connect(self._on_clip_tick)
        self._clipboard.cleared.connect(self._on_clip_cleared)

        # live clipboard auto-clear countdown pill (anchored bottom-centre, outside _root)
        self._clip_pill = QLabel("", self)
        self._clip_pill.setFont(mono_font(10))
        self._clip_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._clip_pill.setStyleSheet(
            f"color: {Color.TEXT}; background: {Color.BG_RAISED};"
            f"border: 1px solid {Color.LINE}; border-radius: 14px; padding: 8px 16px;")
        self._clip_pill.hide()

    # ------------------------------------------------------------------ render
    def set_service(self, service: Service) -> None:
        self._service = service
        self._render()

    def _clear(self) -> None:
        while self._root.count():
            item = self._root.takeAt(0)
            if item.widget():
                # hide right away — deleteLater() only runs once the event loop
                # is idle, and a transparent-background widget left visible
                # until then bleeds through whatever gets drawn in its place
                item.widget().hide()
                item.widget().deleteLater()
            elif item.layout():
                self._drop(item.layout())

    def _drop(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                # hide right away — deleteLater() only runs once the event loop
                # is idle, and a transparent-background widget left visible
                # until then bleeds through whatever gets drawn in its place
                item.widget().hide()
                item.widget().deleteLater()
            elif item.layout():
                self._drop(item.layout())

    def _render(self) -> None:
        self._clear()
        svc = self._service

        top = QHBoxLayout()
        back = Button("‹ Back", variant="ghost")
        back.setFixedWidth(100)
        back.clicked.connect(self.back)
        top.addWidget(back)
        top.addStretch(1)
        if svc.type is not EntryType.BACKUP_CODES:
            add = Button("Add account", variant="primary")
            add.setFixedWidth(130)
            add.clicked.connect(self._add_account)
            top.addWidget(add)
        delete = Button("Delete service", variant="danger")
        delete.setFixedWidth(150)
        delete.clicked.connect(self._delete_service)
        top.addWidget(delete)
        self._root.addLayout(top)

        title = QLabel(svc.name)
        title.setFont(display_font(22))
        title.setStyleSheet(f"color: {Color.TEXT};")
        self._root.addWidget(title)
        sub = QLabel(self._subtitle(svc))
        sub.setFont(body_font(10))
        sub.setStyleSheet(f"color: {Color.TEXT_DIM};")
        self._root.addWidget(sub)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.viewport().setStyleSheet("background: transparent;")
        host = QWidget()
        col = QVBoxLayout(host)
        col.setContentsMargins(0, 0, Space.SM, 0)
        col.setSpacing(Space.MD)

        if svc.type is EntryType.BACKUP_CODES:
            self._render_backup(col, svc)
        else:
            self._render_accounts(col, svc)
        col.addStretch(1)
        scroll.setWidget(host)
        self._root.addWidget(scroll, 1)

    def _subtitle(self, svc: Service) -> str:
        if svc.type is EntryType.BACKUP_CODES:
            unused = sum(1 for c in svc.backup_codes if not c.used)
            return f"Backup codes · {unused}/{len(svc.backup_codes)} unused"
        if svc.type is EntryType.WEBSITE and svc.url:
            return f"Website · {svc.url}"
        return f"{svc.type.value.capitalize()} · {svc.count} accounts"

    def _render_accounts(self, col, svc: Service) -> None:
        col.addWidget(SectionHeader("Accounts"))
        for acc in svc.accounts:
            row = AccountRow(acc)
            row.reveal_clicked.connect(self._reveal_password)
            row.copy_clicked.connect(self._copy_password)
            row.totp_clicked.connect(self._reveal_totp)
            row.edit_clicked.connect(self._edit_account)
            row.delete_clicked.connect(self._delete_account)
            col.addWidget(row)

    def _render_backup(self, col, svc: Service) -> None:
        head = QHBoxLayout()
        sh = SectionHeader("Backup codes", accent=Color.AMBER)
        reveal = Button("Reveal codes", variant="ghost")
        reveal.setFixedWidth(150)
        reveal.clicked.connect(lambda: self._reveal_backup(svc))
        head.addWidget(sh, 1)
        head.addWidget(reveal)
        col.addLayout(head)
        self._backup_rows = []
        for bc in svc.backup_codes:
            row = BackupCodeRow(bc.id, bc.used)
            row.toggled.connect(lambda cid, used: self._toggle_backup(svc, cid, used))
            self._backup_rows.append((row, bc))
            col.addWidget(row)

    # ------------------------------------------------------------------ actions
    def _reveal_password(self, account: Account) -> None:
        row = self.sender()
        row.show_password(self._vault.reveal_password(account), self.reveal_seconds)

    def _copy_password(self, account: Account) -> None:
        self._clipboard.copy(self._vault.reveal_password(account), self.clipboard_seconds)

    def _reveal_totp(self, account: Account) -> None:
        row = self.sender()
        row.start_totp(self._vault.reveal_totp(account))

    def _reveal_backup(self, svc: Service) -> None:
        for row, bc in self._backup_rows:
            row.reveal(self._vault.reveal_backup_code(bc))

    def _toggle_backup(self, svc: Service, code_id: str, used: bool) -> None:
        self._vault.set_backup_code_used(svc, code_id, used)
        self.changed.emit()

    def _add_account(self) -> None:
        modal = EditAccountModal(self, title="Add account", require_password=True)
        modal.saved.connect(self._on_add_account)
        modal.open()

    def _on_add_account(self, payload: dict) -> None:
        acc = self._vault.make_account(payload["username"], payload["password"], payload["totp"])
        self._vault.add_account(self._service, acc)
        Toast(self, "Account added", accent=Color.SUCCESS)
        self.changed.emit()
        self._render()

    def _edit_account(self, account: Account) -> None:
        modal = EditAccountModal(self, title="Edit account", username=account.username)
        modal.saved.connect(lambda payload: self._on_edit_account(account, payload))
        modal.open()

    def _on_edit_account(self, account: Account, payload: dict) -> None:
        self._vault.update_account(account, username=payload["username"],
                                   password=payload["password"], totp=payload["totp"])
        self._vault.update_service(self._service)
        Toast(self, "Account updated", accent=Color.SUCCESS)
        self.changed.emit()
        self._render()

    def _delete_account(self, account: Account) -> None:
        modal = ConfirmModal(self, "Delete account",
                             f"Permanently delete the account “{account.username}”?",
                             confirm_text="Delete")
        modal.accepted.connect(lambda: self._do_delete_account(account))
        modal.open()

    def _do_delete_account(self, account: Account) -> None:
        self._vault.delete_account(self._service, account.id)
        Toast(self, "Account deleted", accent=Color.DANGER)
        self.changed.emit()
        if not self._service.accounts:
            self.back.emit()
        else:
            self._render()

    def _delete_service(self) -> None:
        modal = ConfirmModal(self, "Delete service",
                             f"Permanently delete “{self._service.name}” and all its entries?",
                             confirm_text="Delete")
        modal.accepted.connect(self._do_delete_service)
        modal.open()

    def _do_delete_service(self) -> None:
        self._vault.delete_service(self._service.id)
        self.changed.emit()
        self.back.emit()

    # ----------------------------------------------------------------- clipboard
    def _on_clip_tick(self, seconds: int) -> None:
        self._clip_pill.setText(f"Clipboard clears in {seconds}s")
        self._clip_pill.adjustSize()
        self._position_clip_pill()
        self._clip_pill.show()
        self._clip_pill.raise_()

    def _on_clip_cleared(self) -> None:
        self._clip_pill.hide()
        if self.isVisible():
            Toast(self, "Clipboard cleared", accent=Color.TEXT_DIM, ms=1200)

    def _position_clip_pill(self) -> None:
        x = (self.width() - self._clip_pill.width()) // 2
        y = self.height() - self._clip_pill.height() - 28
        self._clip_pill.move(max(0, x), max(0, y))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._clip_pill.isVisible():
            self._position_clip_pill()
