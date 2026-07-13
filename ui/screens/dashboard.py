"""Main dashboard: left-nav categories, search, live service cards."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from data.models import EntryType, Service
from data.repository import Vault
from ui.icon import build_pixmap
from ui.theme import Color, Space, body_font, display_font, mono_font
from ui.widgets.buttons import Button, NavItem
from ui.widgets.cards import ServiceCard
from ui.widgets.glass import SectionHeader

_TYPE_ACCENT = {
    EntryType.APPLICATION: Color.ACCENT,
    EntryType.WEBSITE: Color.TEAL,
    EntryType.ACCOUNT: Color.VIOLET,
    EntryType.BACKUP_CODES: Color.AMBER,
}
_CATEGORIES = [
    ("All items", None),
    ("Applications", EntryType.APPLICATION),
    ("Accounts", EntryType.ACCOUNT),
    ("Websites", EntryType.WEBSITE),
    ("Backup codes", EntryType.BACKUP_CODES),
]


def _dim(text: str, size: int = 9) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(mono_font(size))
    lbl.setStyleSheet(f"color: {Color.TEXT_FAINT};")
    return lbl


class DashboardScreen(QWidget):
    add_requested = Signal()
    lock_requested = Signal()
    open_service = Signal(str)

    def __init__(self, vault: Vault, parent=None) -> None:
        super().__init__(parent)
        self._vault = vault
        self._filter: EntryType | None = None
        self._query = ""
        self._nav_items: list[tuple[NavItem, EntryType | None]] = []

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_nav())
        root.addWidget(self._build_main(), 1)

    # ------------------------------------------------------------------- nav
    def _build_nav(self) -> QWidget:
        nav = QWidget()
        nav.setFixedWidth(208)
        lay = QVBoxLayout(nav)
        lay.setContentsMargins(Space.LG, Space.LG, Space.SM, Space.LG)
        lay.setSpacing(Space.XS)

        brand = QHBoxLayout()
        mark = QLabel()
        mark.setPixmap(build_pixmap(22))
        brand.addWidget(mark)
        word = QLabel("Pass Manager")
        word.setFont(display_font(12))
        word.setStyleSheet(f"color: {Color.TEXT};")
        brand.addWidget(word)
        brand.addStretch(1)
        lay.addLayout(brand)
        lay.addSpacing(Space.LG)

        for label, etype in _CATEGORIES:
            item = NavItem(label)
            item.clicked.connect(lambda _checked=False, t=etype, it=item: self._select_filter(t, it))
            lay.addWidget(item)
            self._nav_items.append((item, etype))
        self._nav_items[0][0].setChecked(True)

        lay.addStretch(1)
        return nav

    def _select_filter(self, etype: EntryType | None, item: NavItem) -> None:
        self._filter = etype
        for it, _t in self._nav_items:
            it.setChecked(it is item)
        self.refresh()

    # ------------------------------------------------------------------ main
    def _build_main(self) -> QWidget:
        main = QWidget()
        lay = QVBoxLayout(main)
        lay.setContentsMargins(Space.LG, Space.MD, Space.LG, Space.LG)
        lay.setSpacing(Space.MD)

        bar = QHBoxLayout()
        bar.setSpacing(Space.MD)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search")
        self._search.setFont(body_font(11))
        self._search.setFixedHeight(40)
        self._search.textChanged.connect(self._on_search)
        bar.addWidget(self._search, 1)

        self._idle = _dim("Auto lock in 5:00", 10)
        bar.addWidget(self._idle)
        add = Button("Add", variant="primary")
        add.setFixedWidth(100)
        add.clicked.connect(self.add_requested)
        lock = Button("Lock", variant="ghost")
        lock.setFixedWidth(88)
        lock.clicked.connect(self.lock_requested)
        bar.addWidget(add)
        bar.addWidget(lock)
        lay.addLayout(bar)

        self._header = SectionHeader("All items")
        lay.addWidget(self._header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.viewport().setStyleSheet("background: transparent;")
        self._cards_host = QWidget()
        self._grid = QGridLayout(self._cards_host)
        self._grid.setContentsMargins(0, 0, Space.SM, 0)
        self._grid.setSpacing(Space.MD)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self._cards_host)
        lay.addWidget(scroll, 1)

        self._empty = QLabel("No entries yet. click Add to create one.")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setFont(body_font(11))
        self._empty.setStyleSheet(f"color: {Color.TEXT_FAINT};")
        lay.addWidget(self._empty)
        return main

    # ----------------------------------------------------------------- refresh
    def _on_search(self, text: str) -> None:
        self._query = text.strip()
        self.refresh()

    def refresh(self) -> None:
        names = {None: "All items", EntryType.APPLICATION: "Applications",
                 EntryType.ACCOUNT: "Accounts", EntryType.WEBSITE: "Websites",
                 EntryType.BACKUP_CODES: "Backup codes"}
        self._header.setTitle(names[self._filter])

        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                # hide right away — deleteLater() only runs once the event loop
                # is idle, and a transparent-background widget left visible
                # until then bleeds through whatever gets drawn in its place
                item.widget().hide()
                item.widget().deleteLater()

        services = self._vault.services(type=self._filter, query=self._query or None)
        self._empty.setVisible(not services)

        for i, svc in enumerate(services):
            card = ServiceCard(svc.id, svc.name, self._subtitle(svc), svc.count,
                               accent=_TYPE_ACCENT.get(svc.type, Color.ACCENT))
            card.clicked.connect(self.open_service)
            self._grid.addWidget(card, i // 2, i % 2)

    def _subtitle(self, svc: Service) -> str:
        if svc.type is EntryType.BACKUP_CODES:
            return f"Backup codes · {svc.count} codes"
        if svc.type is EntryType.WEBSITE and svc.url:
            return f"Website · {svc.url}"
        noun = "account" if svc.count == 1 else "accounts"
        return f"{svc.type.value.capitalize()} · {svc.count} {noun}"

    def set_idle_remaining(self, seconds: int) -> None:
        m, s = divmod(max(0, seconds), 60)
        self._idle.setText(f"Auto lock in {m}:{s:02d}")
