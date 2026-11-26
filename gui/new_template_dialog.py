"""Вікно «Новий шаблон»: назва, папка й заготовка (розмір і кольори сторінки)."""

import re
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.exceptions import CertificateError
from core.presets import PRESETS, Preset, starter_assets, starter_config
from core.template_store import create_template
from gui import theme
from gui.widgets import Section

PREVIEW_HEIGHT = 64
TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d", "е": "e", "є": "ie", "ж": "zh", "з": "z",
    "и": "y", "і": "i", "ї": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh",
    "щ": "shch", "ь": "", "ю": "iu", "я": "ia", "'": "", "’": "",
})


def folder_from_title(title: str) -> str:
    """«Курс Python 2026» → «kurs_python_2026» (латиниця для назви папки)."""
    latin = title.lower().translate(TRANSLIT)
    slug = re.sub(r"[^a-z0-9]+", "_", latin).strip("_")
    return slug[:64] or "new_template"


def preset_icon(preset: Preset) -> QIcon:
    """Мініатюра сторінки: пропорції та кольори заготовки."""
    width = round(PREVIEW_HEIGHT * preset.width / preset.height)
    pixmap = QPixmap(PREVIEW_HEIGHT * 2, PREVIEW_HEIGHT * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    page = QRectF((PREVIEW_HEIGHT * 2 - width * 2) / 2, 0, width * 2, PREVIEW_HEIGHT * 2)
    painter.setPen(QPen(QColor(theme.HAIRLINE), 2))
    painter.setBrush(QColor(preset.background))
    painter.drawRoundedRect(page.adjusted(1, 1, -1, -1), 8, 8)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(preset.accent))
    painter.drawRoundedRect(QRectF(page.center().x() - page.width() * 0.25, page.height() * 0.18, page.width() * 0.5, 9), 4, 4)
    painter.setBrush(QColor(preset.text))
    painter.drawRoundedRect(QRectF(page.center().x() - page.width() * 0.32, page.height() * 0.4, page.width() * 0.64, 12), 5, 5)
    painter.setBrush(QColor(preset.muted))
    painter.drawRoundedRect(QRectF(page.center().x() - page.width() * 0.2, page.height() * 0.6, page.width() * 0.4, 7), 3, 3)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


class NewTemplateDialog(QDialog):
    """Після accept() у created_dir — папка створеного шаблону."""

    def __init__(self, templates_root: Path, fonts_source: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Новий шаблон")
        self.setMinimumWidth(460)
        self._templates_root = templates_root
        self._fonts_source = fonts_source
        self._folder_edited = False
        self.created_dir: Path | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 16)
        layout.setSpacing(14)
        title = QLabel("Новий шаблон")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        names = Section("Назва")
        self._title = QLineEdit()
        self._title.setPlaceholderText("Напр.: Курс Python 2026")
        self._title.textEdited.connect(self._sync_folder)
        names.add_row("Назва", self._title)
        self._folder = QLineEdit()
        self._folder.setPlaceholderText("kurs_python_2026")
        self._folder.textEdited.connect(lambda _: setattr(self, "_folder_edited", True))
        names.add_row("Папка", self._folder)
        layout.addWidget(names)

        heading = QLabel("ЗАГОТОВКА")
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)
        self._presets = QListWidget()
        self._presets.setIconSize(QSize(PREVIEW_HEIGHT, PREVIEW_HEIGHT))
        self._presets.setSpacing(2)
        for preset in PRESETS:
            item = QListWidgetItem(preset_icon(preset), f"{preset.title}\n{preset.description}")
            item.setData(Qt.ItemDataRole.UserRole, preset.key)
            item.setSizeHint(QSize(0, PREVIEW_HEIGHT + 12))
            self._presets.addItem(item)
        self._presets.setCurrentRow(0)
        self._presets.setFixedHeight((PREVIEW_HEIGHT + 18) * len(PRESETS) + 8)
        self._presets.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self._presets)

        self._error = QLabel()
        self._error.setWordWrap(True)
        self._error.setStyleSheet(f"color: {theme.DANGER};")
        self._error.hide()
        layout.addWidget(self._error)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        create = buttons.button(QDialogButtonBox.StandardButton.Ok)
        create.setText("Створити")
        create.setObjectName("Accent")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Скасувати")
        buttons.accepted.connect(self._create)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _sync_folder(self, title: str) -> None:
        if not self._folder_edited:
            self._folder.setText(folder_from_title(title))

    def _create(self) -> None:
        title = self._title.text().strip() or "Новий шаблон"
        folder = self._folder.text().strip() or folder_from_title(title)
        preset = PRESETS[max(0, self._presets.currentRow())]
        try:
            self.created_dir = create_template(
                self._templates_root,
                folder,
                starter_config(preset, title),
                self._fonts_source,
                starter_assets(preset, self._fonts_source),
            )
        except CertificateError as exc:
            self._error.setText(str(exc))
            self._error.show()
            return
        self.accept()
