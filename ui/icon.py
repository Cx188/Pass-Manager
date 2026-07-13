"""Programmatic application icon: a flat padlock mark on a rounded tile.

Drawn with QPainter so no external image asset is required at import time;
:func:`save_icon_files` still writes real PNG/ICO files for the desktop entry
and window manager to pick up.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

from ui.theme import Color


def build_pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    s = size
    cx = cy = s / 2
    radius = s * 0.22

    bg = QLinearGradient(0, 0, 0, s)
    bg.setColorAt(0.0, QColor(Color.BG_PANEL))
    bg.setColorAt(1.0, QColor(Color.BG))
    p.setBrush(QBrush(bg))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(0, 0, s, s), radius, radius)

    accent = QColor(Color.ACCENT)

    # shackle
    shackle_w = s * 0.34
    shackle_h = s * 0.30
    shackle_top = s * 0.24
    pen = QPen(accent)
    pen.setWidthF(max(2.0, s * 0.055))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    shackle_rect = QRectF(cx - shackle_w / 2, shackle_top, shackle_w, shackle_h * 2)
    p.drawArc(shackle_rect, 0, 180 * 16)

    # body
    body_w = s * 0.52
    body_h = s * 0.40
    body_top = shackle_top + shackle_h * 0.72
    body_rect = QRectF(cx - body_w / 2, body_top, body_w, body_h)
    body = QLinearGradient(0, body_rect.top(), 0, body_rect.bottom())
    body.setColorAt(0.0, accent)
    darker = QColor(accent).darker(115)
    body.setColorAt(1.0, darker)
    p.setBrush(QBrush(body))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(body_rect, s * 0.06, s * 0.06)

    # keyhole
    hole_r = s * 0.045
    hole_cx = cx
    hole_cy = body_rect.top() + body_h * 0.42
    path = QPainterPath()
    path.addEllipse(hole_cx - hole_r, hole_cy - hole_r, hole_r * 2, hole_r * 2)
    path.moveTo(hole_cx - hole_r * 0.45, hole_cy)
    path.lineTo(hole_cx - hole_r * 0.9, body_rect.bottom() - s * 0.05)
    path.lineTo(hole_cx + hole_r * 0.9, body_rect.bottom() - s * 0.05)
    path.lineTo(hole_cx + hole_r * 0.45, hole_cy)
    path.closeSubpath()
    p.setBrush(QColor(Color.BG))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawPath(path)

    p.end()
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(build_pixmap(size))
    return icon


def save_icon_files(icons_dir: str | Path) -> dict[str, bool]:
    """Write app.png (always) and app.ico (if the platform's ICO writer exists)."""
    d = Path(icons_dir)
    d.mkdir(parents=True, exist_ok=True)
    results = {}
    png = build_pixmap(256)
    results["png"] = png.save(str(d / "app.png"), "PNG")
    results["ico"] = build_pixmap(256).save(str(d / "app.ico"), "ICO")
    return results
