"""Dev tool: render every screen to PNG (no keyring prompts, temp key-file vault).

    python tools/shots.py <output_dir>

Renders setup / lock / dashboard / add-wizard / detail using the real platform +
WA_DontShowOnScreen (offscreen has no font DB). Used to visually verify the UI.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core.keyring import Provider  # noqa: E402
from data.models import EntryType, Service, new_id  # noqa: E402
from data.repository import Vault  # noqa: E402
from data.store_io import StoragePaths  # noqa: E402
from ui.app import PassManagerApp  # noqa: E402
from ui.icon import app_icon  # noqa: E402
from ui.theme import apply_theme  # noqa: E402


def seed(vault: Vault) -> Service:
    a1 = vault.make_account("AcePlayerOne", "8sK#v2$Lq9!mZ4@rT7nW^cF1&bH6", totp_secret="JBSWY3DPEHPK3PXP")
    a2 = vault.make_account("SmurfMain", "Zx9-Qw2-Lp4-Mn8-Rt6")
    valorant = Service(id=new_id(), type=EntryType.APPLICATION, name="Valorant", accounts=[a1, a2])
    vault.add_service(valorant)
    vault.add_service(Service(id=new_id(), type=EntryType.WEBSITE, name="Gmail",
                              url="https://mail.google.com",
                              accounts=[vault.make_account("me@gmail.com", "Em@il-Pass-001!")]))
    vault.add_service(Service(id=new_id(), type=EntryType.WEBSITE, name="GitHub", url="https://github.com",
                              accounts=[vault.make_account("dev@x.io", "Gh-Tok-22-xy")]))
    vault.add_service(Service(id=new_id(), type=EntryType.APPLICATION, name="Steam",
                              accounts=[vault.make_account("gamer42", "St3am-Pw-77")]))
    codes = [vault.make_backup_code(c) for c in
             ("4F2A-9KX1", "7M3B-2QZ8", "1C9D-5RT4", "8H6E-3WP2", "0N1F-6YL9")]
    vault.add_service(Service(id=new_id(), type=EntryType.BACKUP_CODES, name="GitHub Recovery",
                              backup_codes=codes))
    return valorant


def render(win, path: str) -> None:
    shot = QPixmap(win.size())
    shot.fill(QColor("#0C0D10"))
    win.render(shot)
    shot.save(path, "PNG")
    print("saved", path)


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out, exist_ok=True)

    app = QApplication(sys.argv)
    apply_theme(app)
    app.setWindowIcon(app_icon())

    with tempfile.TemporaryDirectory(prefix="passmanager_shots_") as tmp:
        vault = Vault(StoragePaths.at(tmp))
        vault.initialize(provider=Provider.KEYFILE)
        sample = seed(vault)

        controller = PassManagerApp(vault=vault)
        win = controller.window
        win.resize(1180, 770)
        win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        win.show()

        def _telemetry(text):
            return lambda: win.title_bar.set_telemetry(text)

        def _combine(*fns):
            return lambda: [f() for f in fns]

        scenes = [
            ("setup", controller.setup, _telemetry("setting up")),
            ("lock", controller.lock, _combine(lambda: controller.lock.reset(), _telemetry("locked"))),
            ("dashboard", controller.dashboard,
             _combine(lambda: controller.dashboard.refresh(), _telemetry("unlocked"))),
            ("wizard", controller.wizard, lambda: controller.wizard.reset()),
            ("detail", controller.detail, lambda: controller.detail.set_service(sample)),
        ]
        for name, screen, prep in scenes:
            if prep:
                prep()
            controller.stack.setCurrentWidget(screen)
            # pump the event loop with real wall-clock so fade-in animations settle
            t0 = time.time()
            while time.time() - t0 < 0.5:
                app.processEvents()
            render(win, os.path.join(out, f"screen_{name}.png"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
