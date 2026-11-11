from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str
    bg2: str
    card: str
    card_border: str
    track: str
    text: str
    text_dim: str
    text_faint: str
    green: str = "#22C55E"
    blue: str = "#38BDF8"
    purple: str = "#A78BFA"
    amber: str = "#FBBF24"
    red: str = "#F87171"
    card_alt: str = "#162033"
    primary: str = "#3B82F6"


DARK = Palette(
    "dark",
    bg="#090D16",
    bg2="#0F172A",
    card="#111827",
    card_border="#28354D",
    track="#222F45",
    text="#FFFFFF",
    text_dim="#FFFFFF",
    text_faint="#FFFFFF",
    green="#22C55E",
    blue="#38BDF8",
    purple="#A78BFA",
    amber="#FBBF24",
    red="#F87171",
    card_alt="#162033",
    primary="#3B82F6",
)

LIGHT = Palette(
    "light",
    bg="#F1F5F9",
    bg2="#E8EEF5",
    card="#FFFFFF",
    card_border="#CBD5E1",
    track="#E2E8F0",
    text="#0F172A",
    text_dim="#0F172A",
    text_faint="#1E293B",
    green="#16A34A",
    blue="#2563EB",
    purple="#7C3AED",
    amber="#D97706",
    red="#DC2626",
    card_alt="#F8FAFC",
    primary="#2563EB",
)

THEMES = {"dark": DARK, "light": LIGHT}


def get(name: str) -> Palette:
    return THEMES.get(name, DARK)


def rgba(hex_color: str, alpha: float) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {max(0, min(255, int(alpha * 255)))})"


def level_color(p: Palette, level: int | None) -> str:
    if level is None:
        return p.text_faint
    if level <= 15:
        return p.red
    if level <= 35:
        return p.amber
    return p.green


def stylesheet(p: Palette) -> str:
    accent_tint = rgba(p.primary, 0.14 if p.name == "dark" else 0.08)
    danger_tint = rgba(p.red, 0.16 if p.name == "dark" else 0.09)
    return f"""
    * {{
        font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif;
        color: {p.text};
    }}
    QMainWindow, QDialog {{
        background: {p.bg};
    }}
    #Root {{
        background: qlineargradient(x1:0, y1:0, x2:0.6, y2:1, stop:0 {p.bg}, stop:1 {p.bg2});
    }}
    QLabel {{
        background: transparent;
    }}
    QLabel[role="dim"] {{
        color: {p.text_dim};
        font-size: 12px;
    }}
    QLabel[role="faint"] {{
        color: {p.text_faint};
        font-size: 11px;
        font-weight: 500;
    }}
    QLabel[role="title"] {{
        font-size: 11px;
        font-weight: 700;
        color: {p.text_faint};
        letter-spacing: 0.9px;
    }}
    QLabel[role="h1"] {{
        font-size: 19px;
        font-weight: 700;
        color: {p.text};
    }}
    QLabel[role="value"] {{
        font-size: 12.5px;
        font-weight: 600;
        color: {p.text};
    }}

    QPushButton {{
        background: {p.card_alt};
        border: 1px solid {p.card_border};
        border-radius: 9px;
        padding: 7px 13px;
        font-size: 12.5px;
        font-weight: 600;
        color: {p.text};
    }}
    QPushButton:hover {{
        background: {p.track};
        border-color: {p.blue};
    }}
    QPushButton:pressed {{
        background: {p.card};
    }}
    QPushButton:disabled {{
        color: {p.text_faint};
        background: {p.card};
        border-color: {p.card_border};
    }}
    QPushButton[accent="true"] {{
        background: {p.primary};
        border: 1px solid {p.primary};
        color: #FFFFFF;
    }}
    QPushButton[accent="true"]:hover {{
        background: {p.blue};
        border-color: {p.blue};
    }}
    QPushButton[accent="true"]:disabled {{
        background: {p.track};
        border-color: {p.card_border};
        color: {p.text_faint};
    }}
    QPushButton[danger="true"] {{
        background: {p.red};
        border: 1px solid {p.red};
        color: #FFFFFF;
    }}
    QPushButton[danger="true"]:hover {{
        background: {rgba(p.red, 0.85)};
    }}
    QPushButton[subtle="true"] {{
        background: {accent_tint};
        border: 1px solid {rgba(p.blue, 0.35)};
        color: {p.blue if p.name == "dark" else p.primary};
    }}
    QPushButton[subtle="true"]:hover {{
        border-color: {p.blue};
        background: {rgba(p.blue, 0.22 if p.name == "dark" else 0.14)};
    }}
    QPushButton#SegBtn {{
        border-radius: 8px;
        padding: 7px 12px;
        background: transparent;
        border: 1px solid transparent;
        color: {p.text_dim};
    }}
    QPushButton#SegBtn:hover {{
        color: {p.text};
        background: {p.track};
    }}
    QPushButton#SegBtn:checked {{
        background: {p.card};
        border: 1px solid {p.blue};
        color: {p.blue if p.name == "dark" else p.primary};
    }}

    QTabWidget::pane {{
        border: 1px solid {p.card_border};
        border-radius: 12px;
        background: {p.card};
        padding: 4px;
        top: -1px;
    }}
    QTabBar {{
        background: transparent;
    }}
    QTabBar::tab {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 8px;
        padding: 7px 14px;
        margin-right: 6px;
        margin-bottom: 6px;
        font-size: 12.5px;
        font-weight: 600;
        color: {p.text_dim};
    }}
    QTabBar::tab:hover {{
        color: {p.text};
        background: {p.track};
    }}
    QTabBar::tab:selected {{
        background: {p.card_alt};
        border-color: {p.card_border};
        color: {p.blue if p.name == "dark" else p.primary};
    }}

    QCheckBox {{
        spacing: 10px;
        padding: 4px 0;
    }}
    QComboBox, QLineEdit, QSpinBox {{
        background: {p.card_alt};
        border: 1px solid {p.card_border};
        border-radius: 8px;
        padding: 6px 10px;
        min-height: 20px;
        color: {p.text};
    }}
    QComboBox:hover, QSpinBox:hover, QLineEdit:hover {{
        border-color: {p.text_faint};
    }}
    QComboBox:focus, QSpinBox:focus, QLineEdit:focus {{
        border: 1.5px solid {p.blue};
    }}
    QComboBox QAbstractItemView {{
        background: {p.card};
        border: 1px solid {p.card_border};
        selection-background-color: {p.primary};
        selection-color: #FFFFFF;
        outline: none;
        padding: 4px;
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QSpinBox {{
        padding-right: 26px;
    }}
    QSpinBox::up-button, QSpinBox::down-button {{
        subcontrol-origin: border;
        width: 20px;
        border-left: 1px solid {p.card_border};
        background: {p.card};
    }}
    QSpinBox::up-button {{
        subcontrol-position: top right;
        border-top-right-radius: 8px;
        border-bottom: 1px solid {p.card_border};
    }}
    QSpinBox::down-button {{
        subcontrol-position: bottom right;
        border-bottom-right-radius: 8px;
    }}
    QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
        background: {p.track};
    }}

    QPlainTextEdit {{
        background: {p.bg};
        border: 1px solid {p.card_border};
        border-radius: 10px;
        padding: 10px;
        font-family: 'Cascadia Mono', 'Consolas', monospace;
        font-size: 12px;
        color: {p.text};
    }}

    QGroupBox {{
        border: 1px solid {p.card_border};
        border-radius: 12px;
        margin-top: 12px;
        padding: 16px 14px 12px 14px;
        background: {p.card};
        font-size: 12px;
        font-weight: 700;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
        color: {p.text_faint};
        letter-spacing: 0.4px;
    }}

    QFrame#BannerInfo {{
        background: {accent_tint};
        border: 1px solid {rgba(p.blue, 0.35)};
        border-radius: 10px;
    }}
    QFrame#BannerWarn {{
        background: {rgba(p.amber, 0.14 if p.name == "dark" else 0.10)};
        border: 1px solid {rgba(p.amber, 0.42)};
        border-radius: 10px;
    }}
    QFrame#BannerDanger {{
        background: {danger_tint};
        border: 1px solid {rgba(p.red, 0.40)};
        border-radius: 10px;
    }}
    QFrame#SegContainer {{
        background: {p.bg};
        border: 1px solid {p.card_border};
        border-radius: 10px;
    }}
    QFrame#InfoRowBox {{
        background: {p.card_alt};
        border: 1px solid {p.card_border};
        border-radius: 9px;
    }}
    QFrame#InfoRowBox QLabel {{
        background: transparent;
        border: none;
    }}
    QFrame#ChronoSeg {{
        background: {p.bg};
        border: 1px solid {p.card_border};
        border-radius: 9px;
    }}
    QFrame#ChronoSeg QLabel {{
        background: transparent;
        border: none;
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 9px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {p.card_border};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {p.text_faint};
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{
        height: 0;
    }}

    QToolTip {{
        background: {p.card_alt};
        color: {p.text};
        border: 1px solid {p.card_border};
        padding: 6px 8px;
        border-radius: 7px;
        font-size: 12px;
    }}
    QMenu {{
        background: {p.card};
        border: 1px solid {p.card_border};
        border-radius: 10px;
        padding: 6px;
    }}
    QMenu::item {{
        padding: 7px 22px 7px 14px;
        border-radius: 6px;
        font-weight: 500;
    }}
    QMenu::item:selected {{
        background: {p.track};
        color: {p.blue if p.name == "dark" else p.primary};
    }}
    QMenu::item:disabled {{
        color: {p.text_faint};
    }}
    QMenu::separator {{
        height: 1px;
        background: {p.card_border};
        margin: 5px 8px;
    }}
    """

