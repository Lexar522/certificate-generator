"""Візуальна тема: світла/темна палітра, колір акценту, шрифти та QSS.

Кольори читаються як атрибути модуля (`theme.ACCENT`, `theme.TEXT`, …) — завдяки `__getattr__`
вони завжди відповідають поточній палітрі, тож тему можна перемкнути без перезапуску.
"""

from dataclasses import dataclass, fields
from typing import Literal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

ThemeMode = Literal["system", "light", "dark"]

FONT_CANDIDATES = ("SF Pro Text", "SF Pro Display", "Inter", "Helvetica Neue", "Noto Sans")
BASE_FONT_SIZE = 10

# Колір акценту: назва, відтінок для світлої теми, відтінок для темної (як системні кольори macOS).
ACCENTS: dict[str, tuple[str, str, str]] = {
    "blue": ("Синій", "#0071E3", "#0A84FF"),
    "purple": ("Фіолетовий", "#8944AB", "#BF5AF2"),
    "green": ("Зелений", "#1E8E3E", "#30D158"),
    "orange": ("Помаранчевий", "#D9620B", "#FF9F0A"),
    "pink": ("Рожевий", "#D6215F", "#FF375F"),
}
DEFAULT_ACCENT = "blue"


@dataclass(frozen=True)
class Palette:
    is_dark: bool
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_soft: str  # фон виділення
    focus_ring: str
    text: str
    text_secondary: str
    text_tertiary: str
    window: str
    surface: str
    surface_hover: str
    sidebar: str
    canvas: str
    hairline: str
    field_border: str
    control_fill: str
    row_hover: str
    scrollbar: str
    tooltip: str
    danger: str
    success: str


_LIGHT = {
    "text": "#1D1D1F",
    "text_secondary": "#6E6E73",
    "text_tertiary": "#A1A1A6",
    "window": "#F5F5F7",
    "surface": "#FFFFFF",
    "surface_hover": "#F9F9FB",
    "sidebar": "#F6F6F8",
    "canvas": "#E9E9EE",
    "hairline": "#E3E3E8",
    "field_border": "#D5D5DB",
    "control_fill": "#ECECF1",
    "row_hover": "rgba(0,0,0,0.045)",
    "scrollbar": "rgba(0,0,0,0.22)",
    "tooltip": "#2C2C2E",
    "danger": "#D70015",
    "success": "#248A3D",
}
_DARK = {
    "text": "#F5F5F7",
    "text_secondary": "#A1A1A6",
    "text_tertiary": "#6E6E73",
    "window": "#1C1C1E",
    "surface": "#2C2C2E",
    "surface_hover": "#343437",
    "sidebar": "#232325",
    "canvas": "#141416",
    "hairline": "#38383B",
    "field_border": "#4A4A4E",
    "control_fill": "#3A3A3D",
    "row_hover": "rgba(255,255,255,0.06)",
    "scrollbar": "rgba(255,255,255,0.28)",
    "tooltip": "#48484A",
    "danger": "#FF453A",
    "success": "#32D74B",
}


def build_palette(dark: bool, accent: str = DEFAULT_ACCENT) -> Palette:
    _, light_accent, dark_accent = ACCENTS.get(accent, ACCENTS[DEFAULT_ACCENT])
    base = QColor(dark_accent if dark else light_accent)
    return Palette(
        is_dark=dark,
        accent=base.name(),
        accent_hover=base.lighter(108).name(),
        accent_pressed=base.darker(110).name(),
        accent_soft=_rgba(base, 0.24 if dark else 0.14),
        focus_ring=_rgba(base, 0.55),
        **(_DARK if dark else _LIGHT),
    )


def _rgba(color: QColor, alpha: float) -> str:
    return f"rgba({color.red()},{color.green()},{color.blue()},{alpha})"


_current = build_palette(dark=False)
_PALETTE_FIELDS = frozenset(f.name for f in fields(Palette))


def palette() -> Palette:
    return _current


def __getattr__(name: str) -> str:
    """theme.ACCENT, theme.TEXT_SECONDARY, … — поля поточної палітри."""
    if name.isupper() and name.lower() in _PALETTE_FIELDS:
        return getattr(_current, name.lower())
    raise AttributeError(f"module 'gui.theme' has no attribute '{name}'")


def pick_font_family() -> str:
    available = set(QFontDatabase.families())
    return next((family for family in FONT_CANDIDATES if family in available), QFont().family())


def system_prefers_dark() -> bool:
    hints = QGuiApplication.styleHints()
    return hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark


def resolve_dark(mode: ThemeMode) -> bool:
    return system_prefers_dark() if mode == "system" else mode == "dark"


def stylesheet(p: Palette) -> str:
    handle_border = "#5A5A5E" if p.is_dark else "#C7C7CC"
    handle_bg = "#E5E5EA" if p.is_dark else "white"
    return f"""
* {{ color: {p.text}; outline: none; }}
QMainWindow, QWidget#Root, QDialog {{ background: {p.window}; }}
QWidget#TopBar {{ background: {p.surface}; border-bottom: 1px solid {p.hairline}; }}
QWidget#Sidebar, QWidget#Inspector {{ background: {p.sidebar}; }}
QWidget#Sidebar {{ border-right: 1px solid {p.hairline}; }}
QWidget#Inspector {{ border-left: 1px solid {p.hairline}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}

QLabel {{ background: transparent; }}
QLabel#AppTitle {{ font-size: 15px; font-weight: 700; letter-spacing: -0.3px; }}
QLabel#SectionTitle {{
    color: {p.text_secondary}; font-size: 11px; font-weight: 600; letter-spacing: 0.6px; padding: 0 2px;
}}
QLabel#PanelTitle {{ font-size: 18px; font-weight: 700; letter-spacing: -0.4px; }}
QLabel#Caption {{ color: {p.text_secondary}; }}
QLabel#Hint {{ color: {p.text_tertiary}; font-size: 11px; }}
QLabel#ValueLabel {{ color: {p.text_secondary}; }}
QFrame#Card {{ background: {p.surface}; border: 1px solid {p.hairline}; border-radius: 14px; }}
QFrame#Separator {{ background: {p.hairline}; max-height: 1px; min-height: 1px; border: none; }}

QPushButton, QToolButton {{
    background: {p.surface}; border: 1px solid {p.field_border}; border-radius: 9px;
    padding: 5px 13px; min-height: 18px;
}}
QPushButton:hover, QToolButton:hover {{ background: {p.surface_hover}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {p.control_fill}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {p.text_tertiary}; background: {p.window}; }}
QPushButton#Accent {{
    background: {p.accent}; color: white; border: 1px solid {p.accent}; font-weight: 600; padding: 5px 16px;
}}
QPushButton#Accent:hover {{ background: {p.accent_hover}; border-color: {p.accent_hover}; }}
QPushButton#Accent:pressed {{ background: {p.accent_pressed}; }}
QPushButton#Accent:disabled {{ background: {p.control_fill}; border-color: {p.control_fill}; color: {p.text_tertiary}; }}
QToolButton#Ghost, QPushButton#Ghost {{ background: transparent; border: 1px solid transparent; padding: 4px 6px; }}
QToolButton#Ghost:hover, QPushButton#Ghost:hover {{ background: {p.row_hover}; }}
QToolButton#Ghost:checked {{ background: {p.accent_soft}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox, QPlainTextEdit {{
    background: {p.surface}; border: 1px solid {p.field_border}; border-radius: 8px;
    padding: 4px 8px; selection-background-color: {p.accent}; selection-color: white; min-height: 18px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border: 2px solid {p.focus_ring}; padding: 3px 7px;
}}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; width: 0px; border: none;
}}
QComboBox QAbstractItemView {{
    background: {p.surface}; border: 1px solid {p.hairline}; border-radius: 10px; padding: 4px;
    selection-background-color: {p.accent}; selection-color: white;
}}

QSlider::groove:horizontal {{ height: 4px; background: {p.control_fill}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {p.accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {handle_bg}; border: 1px solid {handle_border}; width: 18px; height: 18px;
    margin: -8px 0; border-radius: 10px;
}}

QListWidget {{ background: transparent; border: none; padding: 4px; }}
QListWidget::item {{ border-radius: 10px; padding: 0; margin: 1px 0; }}
QListWidget::item:hover {{ background: {p.row_hover}; }}
QListWidget::item:selected {{ background: {p.accent_soft}; }}

QMenu {{ background: {p.surface}; border: 1px solid {p.hairline}; border-radius: 12px; padding: 6px; }}
QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 7px; }}
QMenu::item:selected {{ background: {p.accent}; color: white; }}
QMenu::item:disabled {{ color: {p.text_tertiary}; }}
QMenu::separator {{ height: 1px; background: {p.hairline}; margin: 4px 6px; }}

QTableWidget {{ background: {p.surface}; border: 1px solid {p.hairline}; border-radius: 12px; gridline-color: {p.hairline}; }}
QHeaderView::section {{
    background: {p.sidebar}; border: none; border-bottom: 1px solid {p.hairline};
    padding: 6px 8px; font-weight: 600; color: {p.text_secondary};
}}
QTableWidget::item {{ padding: 4px 8px; border-bottom: 1px solid {p.hairline}; }}
QTableWidget::item:selected {{ background: {p.accent_soft}; color: {p.text}; }}
QProgressBar {{ background: {p.control_fill}; border: none; border-radius: 3px; }}
QProgressBar::chunk {{ background: {p.accent}; border-radius: 3px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.scrollbar}; border-radius: 3px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p.scrollbar}; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QStatusBar {{ background: {p.surface}; border-top: 1px solid {p.hairline}; color: {p.text_secondary}; }}
QStatusBar::item {{ border: none; }}
QSplitter::handle {{ background: transparent; }}
QToolTip {{ background: {p.tooltip}; color: white; border: none; border-radius: 6px; padding: 4px 8px; }}
QCalendarWidget QWidget {{ alternate-background-color: {p.surface}; }}
"""


def _qpalette(p: Palette) -> QPalette:
    qp = QPalette()
    roles = {
        QPalette.ColorRole.Window: p.window,
        QPalette.ColorRole.WindowText: p.text,
        QPalette.ColorRole.Base: p.surface,
        QPalette.ColorRole.AlternateBase: p.sidebar,
        QPalette.ColorRole.Text: p.text,
        QPalette.ColorRole.Button: p.surface,
        QPalette.ColorRole.ButtonText: p.text,
        QPalette.ColorRole.ToolTipBase: p.tooltip,
        QPalette.ColorRole.ToolTipText: "#FFFFFF",
        QPalette.ColorRole.PlaceholderText: p.text_tertiary,
        QPalette.ColorRole.Highlight: p.accent,
        QPalette.ColorRole.HighlightedText: "#FFFFFF",
        QPalette.ColorRole.Link: p.accent,
        QPalette.ColorRole.Light: p.surface_hover,
        QPalette.ColorRole.Mid: p.field_border,
        QPalette.ColorRole.Dark: p.hairline,
    }
    for role, color in roles.items():
        qp.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        qp.setColor(QPalette.ColorGroup.Disabled, role, QColor(p.text_tertiary))
    return qp


def apply_theme(app: QApplication, mode: ThemeMode = "system", accent: str = DEFAULT_ACCENT) -> Palette:
    """Застосовує тему до всього застосунку й повертає активну палітру."""
    global _current  # стан теми навмисно один на застосунок
    _current = build_palette(resolve_dark(mode), accent)

    app.setStyle("Fusion")
    font = QFont(pick_font_family(), BASE_FONT_SIZE)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)
    app.setPalette(_qpalette(_current))
    app.setStyleSheet(stylesheet(_current))
    return _current
