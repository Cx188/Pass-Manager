"""Pass Manager — local encrypted credential vault. Application entry point.

    pip install -r requirements.txt
    python main.py
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ui.app import PassManagerApp
from ui.icon import app_icon
from ui.theme import apply_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Pass Manager")
    app.setDesktopFileName("pass-manager")
    apply_theme(app)
    app.setWindowIcon(app_icon())

    controller = PassManagerApp()
    controller.show()
    controller.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
