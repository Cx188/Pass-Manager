"""Application controller: hosts the screen stack and the state machine
(setup -> lock -> dashboard -> wizard/detail), plus idle auto-lock and the
clipboard manager.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication

from data.config import AppConfig
from data.repository import Vault
from ui.clipboard import ClipboardManager
from ui.idle import IdleWatcher
from ui.screens.add_wizard import AddEntryWizard
from ui.screens.dashboard import DashboardScreen
from ui.screens.detail import DetailScreen
from ui.screens.lock import LockScreen
from ui.screens.setup import SetupScreen
from ui.transitions import FadeStack
from PySide6.QtWidgets import QApplication


class PassManagerApp:
    """Owns the window, screens and global state. Not a QWidget itself so the
    window stays a plain FramelessWindow; this keeps wiring in one place."""

    def __init__(self, vault: Vault | None = None) -> None:
        from ui.window import FramelessWindow

        self.window = FramelessWindow(title="Pass Manager", subtitle="starting…")
        self.window.setMinimumSize(1040, 680)

        self.vault = vault or Vault()
        self.config = AppConfig.load(self.vault.paths)
        self.clipboard = ClipboardManager(self.config.clipboard_clear_seconds)
        self.idle = IdleWatcher(self.config.idle_timeout_seconds)
        self.idle.timed_out.connect(self._lock)
        QApplication.instance().installEventFilter(self.idle)

        self.stack = FadeStack(duration=260)
        self.setup = SetupScreen(self.vault)
        self.lock = LockScreen(self.vault)
        self.dashboard = DashboardScreen(self.vault)
        self.wizard = AddEntryWizard(self.vault)
        self.detail = DetailScreen(self.vault, self.clipboard)
        self.detail.reveal_seconds = self.config.reveal_timeout_seconds
        self.detail.clipboard_seconds = self.config.clipboard_clear_seconds
        for screen in (self.setup, self.lock, self.dashboard, self.wizard, self.detail):
            self.stack.addWidget(screen)

        self.window.set_content(self.stack)
        self._wire()

        # one-second tick to refresh the idle indicator while unlocked
        self._idle_ui = QTimer(self.window)
        self._idle_ui.setInterval(1000)
        self._idle_ui.timeout.connect(self._update_idle_label)

    # ------------------------------------------------------------------ wiring
    def _wire(self) -> None:
        self.setup.completed.connect(self._enter_dashboard)
        self.lock.unlocked.connect(self._enter_dashboard)
        self.dashboard.add_requested.connect(self._open_wizard)
        self.dashboard.lock_requested.connect(self._lock)
        self.dashboard.open_service.connect(self._open_detail)
        self.wizard.saved.connect(self._after_wizard)
        self.wizard.cancelled.connect(self._back_to_dashboard)
        self.detail.back.connect(self._back_to_dashboard)

    # ------------------------------------------------------------------ states
    def start(self) -> None:
        if self.vault.exists():
            self.lock.reset()
            self.stack.fade_to_widget(self.lock)
            self.window.title_bar.set_telemetry("locked")
        else:
            self.stack.fade_to_widget(self.setup)
            self.window.title_bar.set_telemetry("setting up")

    def _enter_dashboard(self) -> None:
        self.dashboard.refresh()
        self.window.title_bar.set_telemetry("unlocked")
        self.idle.start()
        self._idle_ui.start()
        self._update_idle_label()
        self.stack.fade_to_widget(self.dashboard)

    def _back_to_dashboard(self) -> None:
        self.dashboard.refresh()
        self.stack.fade_to_widget(self.dashboard)

    def _after_wizard(self) -> None:
        self.dashboard.refresh()
        self.stack.fade_to_widget(self.dashboard)

    def _open_wizard(self) -> None:
        self.wizard.reset()
        self.stack.fade_to_widget(self.wizard)

    def _open_detail(self, service_id: str) -> None:
        service = self.vault.get(service_id)
        if service is None:
            return
        self.detail.set_service(service)
        self.stack.fade_to_widget(self.detail)

    def _lock(self) -> None:
        if not self.vault.unlocked:
            return
        self.clipboard.clear_now()
        self.vault.lock()
        self.idle.stop()
        self._idle_ui.stop()
        self.lock.reset()
        self.window.title_bar.set_telemetry("locked")
        self.stack.fade_to_widget(self.lock)

    def _update_idle_label(self) -> None:
        self.dashboard.set_idle_remaining(self.idle.seconds_remaining())

    def show(self) -> None:
        self.window.show()
        self._center()

    def _center(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.window.move(geo.center().x() - self.window.width() // 2,
                             geo.center().y() - self.window.height() // 2)
