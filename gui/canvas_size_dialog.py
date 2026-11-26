"""Діалог «Розмір полотна»: формат сторінки, орієнтація, DPI, власний розмір і масштабування вмісту."""

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.models import MAX_CANVAS_SIDE
from gui import theme
from gui.document import EditorDocument
from gui.page_size import CUSTOM_FORMAT, PAGE_FORMATS, detect_format, format_by_key, format_pixels, px_to_mm
from gui.widgets import Section, Segmented, Switch, hbox

PREVIEW_SIZE = 120
MIN_DPI, MAX_DPI = 72, 1200


class _PagePreview(QWidget):
    """Мініатюра пропорцій сторінки: старий розмір пунктиром, новий — суцільним."""

    def __init__(self, old_size: tuple[int, int]) -> None:
        super().__init__()
        self.setFixedSize(PREVIEW_SIZE, PREVIEW_SIZE)
        self._old = old_size
        self._new = old_size

    def set_size(self, width: int, height: int) -> None:
        self._new = (width, height)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 — Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        largest = max(*self._old, *self._new)
        for (width, height), style, fill in (
            (self._old, Qt.PenStyle.DashLine, None),
            (self._new, Qt.PenStyle.SolidLine, theme.CONTROL_FILL),
        ):
            w, h = width / largest * (PREVIEW_SIZE - 8), height / largest * (PREVIEW_SIZE - 8)
            rect = QRectF((PREVIEW_SIZE - w) / 2, (PREVIEW_SIZE - h) / 2, w, h)
            painter.setPen(QPen(QColor(theme.ACCENT if fill else theme.TEXT_TERTIARY), 1.5, style))
            painter.setBrush(QColor(fill) if fill else Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, 3, 3)
        painter.end()


class CanvasSizeDialog(QDialog):
    """Після accept() у width, height, dpi і scale_content — обрані значення."""

    def __init__(self, doc: EditorDocument, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Розмір полотна")
        self.setMinimumWidth(440)
        canvas = doc.config.canvas
        self.width, self.height = canvas.width, canvas.height
        self.dpi = doc.config.output.dpi
        self.scale_content = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 16)
        layout.setSpacing(14)
        title = QLabel("Розмір полотна")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        self._preview = _PagePreview((canvas.width, canvas.height))
        layout.addWidget(self._preview, alignment=Qt.AlignmentFlag.AlignHCenter)

        page = Section("Сторінка")
        self._format = QComboBox()
        for item in PAGE_FORMATS:
            self._format.addItem(item.title, item.key)
        self._format.addItem("Власний розмір", CUSTOM_FORMAT)
        page.add_row("Формат", self._format)
        self._orientation = Segmented([("landscape", "Горизонтально"), ("portrait", "Вертикально")])
        page.add_row("Орієнтація", self._orientation)
        self._dpi = self._spin(MIN_DPI, MAX_DPI, " DPI")
        self._dpi.setValue(self.dpi)
        page.add_row("Роздільність", self._dpi)
        self._width = self._spin(1, MAX_CANVAS_SIDE, " px")
        self._height = self._spin(1, MAX_CANVAS_SIDE, " px")
        page.add_row("Ш × В", hbox(self._width, QLabel("×"), self._height, stretch_first=False))
        self._mm = QLabel()
        self._mm.setObjectName("Hint")
        page.add_full(self._mm)
        layout.addWidget(page)

        content = Section("Вміст")
        self._scale = Switch()
        self._scale.setChecked(True)
        content.add_row("Масштабувати об'єкти", self._scale)
        hint = QLabel("Тексти, зображення й QR-коди пропорційно переносяться на нову сторінку; "
                      "рамки на всю сторінку розтягуються. Вимкніть, щоб лише змінити межі.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        content.add_full(hint)
        layout.addWidget(content)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        apply = buttons.button(QDialogButtonBox.StandardButton.Ok)
        apply.setText("Застосувати")
        apply.setObjectName("Accent")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Скасувати")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._set_size(canvas.width, canvas.height)
        self._sync_format_from_size()
        self._format.currentIndexChanged.connect(lambda _: self._apply_format())
        self._orientation.changed.connect(lambda _: self._apply_format(swap_custom=True))
        self._dpi.valueChanged.connect(lambda _: self._on_dpi_changed())
        self._width.valueChanged.connect(lambda _: self._on_size_edited())
        self._height.valueChanged.connect(lambda _: self._on_size_edited())

    @staticmethod
    def _spin(minimum: int, maximum: int, suffix: str) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSuffix(suffix)
        spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        spin.setMinimumWidth(90)
        return spin

    def sizeHint(self) -> QSize:  # noqa: N802 — Qt API
        return QSize(460, super().sizeHint().height())

    # ------------------------------------------------------------------ #

    def _landscape(self) -> bool:
        return self._orientation.value() == "landscape"

    def _set_size(self, width: int, height: int) -> None:
        for spin, value in ((self._width, width), (self._height, height)):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        self._orientation.blockSignals(True)
        self._orientation.set_value("portrait" if height > width else "landscape")
        self._orientation.blockSignals(False)
        self._refresh()

    def _refresh(self) -> None:
        width, height, dpi = self._width.value(), self._height.value(), self._dpi.value()
        self._mm.setText(f"{px_to_mm(width, dpi):.1f} × {px_to_mm(height, dpi):.1f} мм при друку з {dpi} DPI")
        self._preview.set_size(width, height)

    def _sync_format_from_size(self) -> None:
        key = detect_format(self._width.value(), self._height.value(), self._dpi.value())
        self._format.blockSignals(True)
        self._format.setCurrentIndex(self._format.findData(key))
        self._format.blockSignals(False)

    def _apply_format(self, swap_custom: bool = False) -> None:
        key = self._format.currentData()
        if key == CUSTOM_FORMAT:
            width, height = self._width.value(), self._height.value()
            if swap_custom and (width > height) != self._landscape():
                self._set_size(height, width)
            return
        self._set_size(*format_pixels(format_by_key(key), self._dpi.value(), self._landscape()))

    def _on_dpi_changed(self) -> None:
        if self._format.currentData() == CUSTOM_FORMAT:
            self._refresh()
        else:
            self._apply_format()  # мм-формати перераховуються під нову роздільність

    def _on_size_edited(self) -> None:
        self._set_size(self._width.value(), self._height.value())
        self._sync_format_from_size()

    def _accept(self) -> None:
        self.width, self.height = self._width.value(), self._height.value()
        self.dpi = self._dpi.value()
        self.scale_content = self._scale.isChecked()
        self.accept()
