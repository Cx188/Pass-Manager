"""Palette, spacing, fonts and the base stylesheet — the one place that owns
the app's look. Fonts resolve against whatever is actually installed, so the
app still looks reasonable on a bare system instead of falling back to a
default UI font mid-session.
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtGui import QColor, QFont, QFontDatabase


# --------------------------------------------------------------------------- #
#  Palette                                                                     #
# --------------------------------------------------------------------------- #
class Color:
    BG = "#0C0D10"
    BG_PANEL = "#15171C"
    BG_RAISED = "#1C1F26"

    ACCENT = "#4C7DF0"
    ACCENT_SOFT = "#274690"
    TEAL = "#2FB6A6"
    AMBER = "#D99A3D"
    VIOLET = "#8B7FE0"

    SUCCESS = "#3FBF7F"
    WARNING = "#D99A3D"
    DANGER = "#E5484D"

    TEXT = "#E7E9EE"
    TEXT_DIM = "#8B909C"
    TEXT_FAINT = "#565B66"

    LINE = "#262A32"


def qcolor(hex_str: str, alpha: float = 1.0) -> QColor:
    c = QColor(hex_str)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


def rgba(hex_str: str, alpha: float) -> str:
    c = QColor(hex_str)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha:.3f})"


# --------------------------------------------------------------------------- #
#  Geometry tokens                                                             #
# --------------------------------------------------------------------------- #
class Radius:
    SM = 6
    MD = 8
    LG = 12
    XL = 16


class Space:
    XS = 4
    SM = 8
    MD = 14
    LG = 22
    XL = 34


# --------------------------------------------------------------------------- #
#  Fonts (resolved against installed families, sane fallback either way)       #
# --------------------------------------------------------------------------- #
_HEADING_STACK = ["Inter", "Segoe UI Semibold", "Segoe UI", "Cantarell",
                  "Noto Sans", "DejaVu Sans", "Liberation Sans", "Arial"]
_BODY_STACK = ["Inter", "Segoe UI", "Cantarell", "Noto Sans",
               "DejaVu Sans", "Liberation Sans", "Tahoma", "Arial"]
_MONO_STACK = ["JetBrains Mono", "Cascadia Mono", "Consolas",
               "Noto Sans Mono", "DejaVu Sans Mono",
               "Liberation Mono", "Courier New", "monospace"]


@lru_cache(maxsize=8)
def _first_available(stack: tuple[str, ...]) -> str:
    families = set(QFontDatabase.families())
    for fam in stack:
        if fam in families:
            return fam
    return stack[-1]


def display_font(size: int, weight: QFont.Weight = QFont.Weight.DemiBold,
                 spacing: float = 0.0) -> QFont:
    f = QFont(_first_available(tuple(_HEADING_STACK)), size)
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


def body_font(size: int, weight: QFont.Weight = QFont.Weight.Normal,
              spacing: float = 0.0) -> QFont:
    f = QFont(_first_available(tuple(_BODY_STACK)), size)
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


def mono_font(size: int, weight: QFont.Weight = QFont.Weight.Medium,
              spacing: float = 0.3) -> QFont:
    f = QFont(_first_available(tuple(_MONO_STACK)), size)
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


def font_names() -> dict[str, str]:
    return {
        "heading": _first_available(tuple(_HEADING_STACK)),
        "body": _first_available(tuple(_BODY_STACK)),
        "mono": _first_available(tuple(_MONO_STACK)),
    }


# --------------------------------------------------------------------------- #
#  Global stylesheet                                                           #
# --------------------------------------------------------------------------- #
def global_stylesheet() -> str:
    return f"""
    QWidget {{
        color: {Color.TEXT};
        background: transparent;
        selection-background-color: {rgba(Color.ACCENT, 0.35)};
        selection-color: {Color.TEXT};
    }}
    QToolTip {{
        color: {Color.TEXT};
        background-color: {Color.BG_RAISED};
        border: 1px solid {Color.LINE};
        padding: 6px 9px;
        border-radius: {Radius.SM}px;
    }}
    QScrollBar:vertical {{
        background: transparent; width: 10px; margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {rgba(Color.TEXT_DIM, 0.28)}; border-radius: 4px; min-height: 28px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {rgba(Color.TEXT_DIM, 0.45)}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QLineEdit, QPlainTextEdit {{
        background: {Color.BG_RAISED};
        border: 1px solid {Color.LINE};
        border-radius: {Radius.MD}px;
        padding: 9px 12px;
        color: {Color.TEXT};
    }}
    QLineEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {rgba(Color.ACCENT, 0.75)}; }}
    """


def apply_theme(app) -> None:
    app.setFont(body_font(11))
    app.setStyleSheet(global_stylesheet())
