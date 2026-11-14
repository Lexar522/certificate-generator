"""Візуальна тема у стилі macOS: палітра, шрифти та QSS."""

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = "#0071E3"
ACCENT_HOVER = "#0077ED"
ACCENT_PRESSED = "#006EDB"
TEXT = "#1D1D1F"
TEXT_SECONDARY = "#6E6E73"
TEXT_TERTIARY = "#A1A1A6"
WINDOW = "#F5F5F7"
SURFACE = "#FFFFFF"
SIDEBAR = "#F2F2F5"
CANVAS = "#E8E8ED"
HAIRLINE = "#D9D9DE"
FIELD_BORDER = "#D2D2D7"
CONTROL_FILL = "#E9E9EE"
DANGER = "#D70015"
SUCCESS = "#248A3D"

FONT_CANDIDATES = ("SF Pro Text", "SF Pro Display", "Inter", "Helvetica Neue", "Noto Sans")
BASE_FONT_SIZE = 10


def pick_font_family() -> str:
    available = set(QFontDatabase.families())
    return next((family for family in FONT_CANDIDATES if family in available), QFont().family())


STYLESHEET = f"""
* {{ color: {TEXT}; outline: none; }}
QMainWindow, QWidget#Root {{ background: {WINDOW}; }}
QWidget#TopBar {{ background: {SURFACE}; border-bottom: 1px solid {HAIRLINE}; }}
QWidget#Sidebar, QWidget#Inspector {{ background: {SIDEBAR}; }}
QWidget#Sidebar {{ border-right: 1px solid {HAIRLINE}; }}
QWidget#Inspector {{ border-left: 1px solid {HAIRLINE}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}

QLabel#AppTitle {{ font-size: 15px; font-weight: 600; letter-spacing: -0.2px; }}
QLabel#SectionTitle {{
    color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 600;
    letter-spacing: 0.6px; padding: 0 2px;
}}
QLabel#PanelTitle {{ font-size: 17px; font-weight: 600; letter-spacing: -0.3px; }}
QLabel#Caption {{ color: {TEXT_SECONDARY}; }}
QLabel#Hint {{ color: {TEXT_TERTIARY}; font-size: 11px; }}
QLabel#ValueLabel {{ color: {TEXT_SECONDARY}; }}
QFrame#Card {{ background: {SURFACE}; border: 1px solid {HAIRLINE}; border-radius: 12px; }}
QFrame#Separator {{ background: {HAIRLINE}; max-height: 1px; min-height: 1px; border: none; }}

QPushButton, QToolButton {{
    background: {SURFACE}; border: 1px solid {FIELD_BORDER}; border-radius: 8px;
    padding: 5px 12px; min-height: 18px;
}}
QPushButton:hover, QToolButton:hover {{ background: #FAFAFC; border-color: #C7C7CC; }}
QPushButton:pressed, QToolButton:pressed {{ background: {CONTROL_FILL}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {TEXT_TERTIARY}; background: #F7F7F9; }}
QPushButton#Accent {{
    background: {ACCENT}; color: white; border: 1px solid {ACCENT}; font-weight: 600; padding: 5px 16px;
}}
QPushButton#Accent:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#Accent:pressed {{ background: {ACCENT_PRESSED}; }}
QToolButton#Ghost, QPushButton#Ghost {{ background: transparent; border: 1px solid transparent; padding: 4px 6px; }}
QToolButton#Ghost:hover, QPushButton#Ghost:hover {{ background: rgba(0,0,0,0.06); }}
QToolButton#Ghost:checked {{ background: rgba(0,113,227,0.12); }}
QToolButton::menu-indicator {{ image: none; width: 0; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox, QPlainTextEdit {{
    background: {SURFACE}; border: 1px solid {FIELD_BORDER}; border-radius: 7px;
    padding: 4px 8px; selection-background-color: {ACCENT}; selection-color: white; min-height: 18px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border: 2px solid rgba(0,113,227,0.55); padding: 3px 7px;
}}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; width: 0px; border: none;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE}; border: 1px solid {HAIRLINE}; border-radius: 8px; padding: 4px;
    selection-background-color: {ACCENT}; selection-color: white;
}}

QSlider::groove:horizontal {{ height: 4px; background: {CONTROL_FILL}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: white; border: 1px solid #C7C7CC; width: 18px; height: 18px; margin: -8px 0; border-radius: 10px;
}}
QSlider::handle:horizontal:hover {{ border-color: #A1A1A6; }}

QListWidget {{ background: transparent; border: none; padding: 4px; }}
QListWidget::item {{ border-radius: 8px; padding: 0; margin: 1px 0; }}
QListWidget::item:hover {{ background: rgba(0,0,0,0.05); }}
QListWidget::item:selected {{ background: rgba(0,113,227,0.14); }}

QMenu {{ background: {SURFACE}; border: 1px solid {HAIRLINE}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {ACCENT}; color: white; }}
QMenu::separator {{ height: 1px; background: {HAIRLINE}; margin: 4px 6px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: rgba(0,0,0,0.22); border-radius: 3px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: rgba(0,0,0,0.22); border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QStatusBar {{ background: {SURFACE}; border-top: 1px solid {HAIRLINE}; color: {TEXT_SECONDARY}; }}
QStatusBar::item {{ border: none; }}
QSplitter::handle {{ background: transparent; }}
QToolTip {{ background: #2C2C2E; color: white; border: none; border-radius: 6px; padding: 4px 8px; }}
QCalendarWidget QWidget {{ alternate-background-color: {SURFACE}; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    font = QFont(pick_font_family(), BASE_FONT_SIZE)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)

    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor(WINDOW))
    palette.setColor(QPalette.ColorRole.Base, QColor(SURFACE))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)
