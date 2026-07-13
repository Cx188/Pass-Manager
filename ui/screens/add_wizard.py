"""Add-entry wizard: type -> details -> password -> save, with animated steps."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from core.errors import CryptoError
from core import generator
from data.models import EntryType, Service, new_id
from data.repository import Vault
from ui.theme import Color, Space, body_font, display_font, mono_font
from ui.transitions import fade_in
from ui.widgets.buttons import Button
from ui.widgets.glass import GlassPanel, SectionHeader
from ui.widgets.meters import StrengthMeter

_TYPE_META = {
    EntryType.APPLICATION: ("A", "Application", "A desktop or game login", Color.ACCENT),
    EntryType.WEBSITE: ("W", "Website", "A site with a URL", Color.TEAL),
    EntryType.BACKUP_CODES: ("B", "Backup codes", "A set of one-time codes", Color.AMBER),
}


def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(mono_font(9))
    lbl.setStyleSheet(f"color: {Color.TEXT_DIM};")
    return lbl


class _TypeTile(QWidget):
    chosen = Signal(object)

    def __init__(self, etype: EntryType, parent=None) -> None:
        super().__init__(parent)
        self._etype = etype
        self._letter, self._title, self._desc, self._accent = _TYPE_META[etype]
        self._hover = False
        self.setMinimumSize(180, 190)
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
        if e.button() == Qt.MouseButton.LeftButton:
            self.chosen.emit(self._etype)
        super().mouseReleaseEvent(e)

    def paintEvent(self, _e):
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QPainter, QPen

        from ui.theme import Radius

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        fill = QColor(Color.BG_PANEL)
        p.setBrush(fill)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, Radius.LG, Radius.LG)

        border = QColor(self._accent if self._hover else Color.LINE)
        pen = QPen(border)
        pen.setWidthF(1.4 if self._hover else 1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, Radius.LG, Radius.LG)

        badge_r = 26
        bcx, bcy = rect.center().x(), rect.top() + 54
        badge_fill = QColor(self._accent)
        badge_fill.setAlphaF(0.16)
        p.setBrush(badge_fill)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(bcx - badge_r, bcy - badge_r, badge_r * 2, badge_r * 2), Radius.MD, Radius.MD)
        p.setPen(QColor(self._accent))
        p.setFont(display_font(18))
        p.drawText(QRectF(bcx - badge_r, bcy - badge_r, badge_r * 2, badge_r * 2),
                   Qt.AlignmentFlag.AlignCenter, self._letter)

        p.setPen(QColor(Color.TEXT))
        p.setFont(display_font(12))
        p.drawText(QRectF(rect.left(), rect.top() + 100, rect.width(), 26),
                   Qt.AlignmentFlag.AlignCenter, self._title)
        p.setPen(QColor(Color.TEXT_DIM))
        p.setFont(body_font(9))
        p.drawText(QRectF(rect.left() + 10, rect.top() + 130, rect.width() - 20, 40),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, self._desc)
        p.end()


class AddEntryWizard(QWidget):
    saved = Signal()
    cancelled = Signal()

    def __init__(self, vault: Vault, parent=None) -> None:
        super().__init__(parent)
        self._vault = vault
        self._reset_state()

        root = QVBoxLayout(self)
        root.setContentsMargins(Space.XL, Space.LG, Space.XL, Space.LG)
        root.setSpacing(Space.MD)

        top = QHBoxLayout()
        self._header = SectionHeader("Add entry · choose a type")
        cancel = Button("Cancel", variant="ghost")
        cancel.setFixedWidth(110)
        cancel.clicked.connect(self.cancelled)
        top.addWidget(self._header, 1)
        top.addWidget(cancel)
        root.addLayout(top)

        self._panel = GlassPanel(radius=14)
        root.addWidget(self._panel, 1)

        nav = QHBoxLayout()
        self._back = Button("‹ Back", variant="ghost")
        self._back.setFixedWidth(110)
        self._back.clicked.connect(self._go_back)
        self._next = Button("Next ›", variant="primary")
        self._next.setFixedWidth(180)
        self._next.clicked.connect(self._go_next)
        nav.addWidget(self._back)
        nav.addStretch(1)
        nav.addWidget(self._next)
        root.addLayout(nav)

    # ------------------------------------------------------------------ state
    def _reset_state(self) -> None:
        self._type: EntryType | None = None
        self._order: list[str] = ["type"]
        self._step = 0
        self._name = ""
        self._username = ""
        self._url = ""
        self._password = ""
        self._totp = ""
        self._codes: list[str] = []
        self._opts = generator.PasswordOptions()

    def reset(self) -> None:
        self._reset_state()
        self._render()

    # --------------------------------------------------------------- rendering
    def _clear_panel(self) -> None:
        body = self._panel.body()
        while body.count():
            item = body.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._drop_layout(item.layout())

    def _drop_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._drop_layout(item.layout())

    def _render(self) -> None:
        self._clear_panel()
        key = self._order[self._step]
        titles = {"type": "choose a type", "identity": "details",
                  "password": "password", "save": "saving"}
        self._header.setTitle(f"Add entry · {titles[key]}")
        self._back.setVisible(self._step > 0 and key != "save")
        self._next.setVisible(key not in ("type", "save"))
        getattr(self, f"_render_{key}")()
        fade_in(self._panel, 180)

    def _render_type(self) -> None:
        body = self._panel.body()
        row = QHBoxLayout()
        row.setSpacing(Space.LG)
        row.addStretch(1)
        for etype in (EntryType.APPLICATION, EntryType.WEBSITE, EntryType.BACKUP_CODES):
            tile = _TypeTile(etype)
            tile.chosen.connect(self._choose_type)
            row.addWidget(tile)
        row.addStretch(1)
        body.addStretch(1)
        body.addLayout(row)
        body.addStretch(1)

    def _choose_type(self, etype: EntryType) -> None:
        self._type = etype
        if etype is EntryType.BACKUP_CODES:
            self._order = ["type", "identity", "save"]
        else:
            self._order = ["type", "identity", "password", "save"]
        self._step = 1
        self._render()

    def _render_identity(self) -> None:
        body = self._panel.body()
        body.addWidget(_field_label("Service name"))
        self._name_in = QLineEdit(self._name)
        self._name_in.setMinimumHeight(40)
        self._name_in.setFont(body_font(12))
        body.addWidget(self._name_in)

        if self._type is EntryType.BACKUP_CODES:
            body.addWidget(_field_label("Codes — one per line"))
            self._codes_in = QPlainTextEdit("\n".join(self._codes))
            self._codes_in.setFont(mono_font(12))
            self._codes_in.setMinimumHeight(160)
            body.addWidget(self._codes_in)
        else:
            body.addWidget(_field_label("Username / email"))
            self._user_in = QLineEdit(self._username)
            self._user_in.setMinimumHeight(40)
            self._user_in.setFont(body_font(12))
            body.addWidget(self._user_in)
            if self._type is EntryType.WEBSITE:
                body.addWidget(_field_label("URL"))
                self._url_in = QLineEdit(self._url)
                self._url_in.setMinimumHeight(40)
                self._url_in.setFont(body_font(12))
                body.addWidget(self._url_in)
        body.addStretch(1)

    def _render_password(self) -> None:
        body = self._panel.body()
        if not self._password:
            self._password = generator.generate_password(self._opts)

        top = QHBoxLayout()
        self._pw_label = QLabel(self._password)
        self._pw_label.setFont(mono_font(15))
        self._pw_label.setWordWrap(True)
        self._pw_label.setStyleSheet(f"color: {Color.TEXT};")
        regen = Button("↻", variant="ghost")
        regen.setFixedWidth(56)
        regen.clicked.connect(self._regenerate)
        top.addWidget(self._pw_label, 1)
        top.addWidget(regen)
        body.addLayout(top)

        self._meter = StrengthMeter()
        body.addWidget(self._meter)
        self._entropy_lbl = QLabel("")
        self._entropy_lbl.setFont(mono_font(9))
        self._entropy_lbl.setStyleSheet(f"color: {Color.TEXT_FAINT};")
        body.addWidget(self._entropy_lbl)

        len_row = QHBoxLayout()
        len_row.addWidget(_field_label("Length"))
        self._len_slider = QSlider(Qt.Orientation.Horizontal)
        self._len_slider.setRange(generator.MIN_LENGTH, generator.MAX_LENGTH)
        self._len_slider.setValue(self._opts.length)
        self._len_slider.valueChanged.connect(self._on_length)
        self._len_val = QLabel(str(self._opts.length))
        self._len_val.setFont(mono_font(11))
        self._len_val.setStyleSheet(f"color: {Color.ACCENT};")
        len_row.addWidget(self._len_slider, 1)
        len_row.addWidget(self._len_val)
        body.addLayout(len_row)

        cs_row = QHBoxLayout()
        self._checks = {}
        for key, label, attr in (("upper", "A-Z", "use_upper"), ("lower", "a-z", "use_lower"),
                                 ("digits", "0-9", "use_digits"), ("symbols", "!@#", "use_symbols")):
            cb = QCheckBox(label)
            cb.setChecked(getattr(self._opts, attr))
            cb.setFont(mono_font(10))
            cb.setStyleSheet(self._check_style())
            cb.toggled.connect(lambda v, a=attr: self._on_charset(a, v))
            self._checks[key] = cb
            cs_row.addWidget(cb)
        cs_row.addStretch(1)
        body.addLayout(cs_row)

        body.addWidget(_field_label("TOTP secret (optional)"))
        self._totp_in = QLineEdit(self._totp)
        self._totp_in.setPlaceholderText("Base32 2FA seed, e.g. JBSWY3DPEHPK3PXP")
        self._totp_in.setFont(mono_font(11))
        self._totp_in.setMinimumHeight(38)
        body.addWidget(self._totp_in)
        body.addStretch(1)

        self._next.setText("Save entry")
        self._refresh_strength()

    def _check_style(self) -> str:
        return (f"QCheckBox {{ color: {Color.TEXT_DIM}; spacing: 6px; }}"
                f"QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px;"
                f" border: 1px solid {Color.LINE}; }}"
                f"QCheckBox::indicator:checked {{ background: {Color.ACCENT};"
                f" border: 1px solid {Color.ACCENT}; }}")

    def _regenerate(self) -> None:
        try:
            self._password = generator.generate_password(self._opts)
        except ValueError:
            return
        self._pw_label.setText(self._password)
        self._refresh_strength()

    def _on_length(self, value: int) -> None:
        self._opts.length = value
        self._len_val.setText(str(value))
        self._regenerate()

    def _on_charset(self, attr: str, value: bool) -> None:
        setattr(self._opts, attr, value)
        if not self._opts.classes():
            setattr(self._opts, attr, True)
            self._checks_restore(attr)
            return
        self._regenerate()

    def _checks_restore(self, attr: str) -> None:
        mapping = {"use_upper": "upper", "use_lower": "lower",
                   "use_digits": "digits", "use_symbols": "symbols"}
        cb = self._checks.get(mapping[attr])
        if cb:
            cb.blockSignals(True)
            cb.setChecked(True)
            cb.blockSignals(False)

    def _refresh_strength(self) -> None:
        score = generator.strength_score(self._password, self._opts)
        bits = generator.entropy_bits(self._password, self._opts)
        self._meter.set_value(score)
        self._entropy_lbl.setText(f"{len(self._password)} characters · {bits:.0f} bits of entropy")

    def _render_save(self) -> None:
        body = self._panel.body()
        body.addStretch(1)
        self._save_status = QLabel("Saving…")
        self._save_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._save_status.setFont(display_font(14))
        self._save_status.setStyleSheet(f"color: {Color.TEXT};")
        body.addWidget(self._save_status)
        body.addStretch(1)
        QTimer.singleShot(120, self._do_save)

    # ----------------------------------------------------------------- nav/logic
    def _collect_identity(self) -> bool:
        self._name = self._name_in.text().strip()
        if not self._name:
            return False
        if self._type is EntryType.BACKUP_CODES:
            self._codes = [ln.strip() for ln in self._codes_in.toPlainText().splitlines() if ln.strip()]
            return bool(self._codes)
        self._username = self._user_in.text().strip()
        if self._type is EntryType.WEBSITE:
            self._url = self._url_in.text().strip()
        return bool(self._username)

    def _collect_password(self) -> bool:
        self._totp = self._totp_in.text().strip()
        return bool(self._password)

    def _go_next(self) -> None:
        key = self._order[self._step]
        if key == "identity" and not self._collect_identity():
            return
        if key == "password" and not self._collect_password():
            return
        self._step += 1
        self._next.setText("Next ›")
        self._render()

    def _go_back(self) -> None:
        if self._step > 0:
            self._step -= 1
            self._next.setText("Next ›")
            self._render()

    def _do_save(self) -> None:
        try:
            if self._type is EntryType.BACKUP_CODES:
                codes = [self._vault.make_backup_code(c) for c in self._codes]
                svc = Service(id=new_id(), type=self._type, name=self._name, backup_codes=codes)
            else:
                acc = self._vault.make_account(self._username, self._password, self._totp or None)
                svc = Service(id=new_id(), type=self._type, name=self._name,
                              url=self._url or None, accounts=[acc])
            self._vault.add_service(svc)
        except CryptoError as exc:
            self._save_status.setStyleSheet(f"color: {Color.DANGER};")
            self._save_status.setText(f"Couldn't save: {exc}")
            return
        self._save_status.setStyleSheet(f"color: {Color.SUCCESS};")
        self._save_status.setText("Saved")
        QTimer.singleShot(500, self.saved.emit)
