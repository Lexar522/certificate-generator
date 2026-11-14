"""Перевикористовувані контроли у стилі macOS."""

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QColorDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from gui import theme

CAPTION_MAX_WIDTH = 104


class Switch(QAbstractButton):
    """Перемикач у стилі iOS з анімацією."""

    TRACK_SIZE = QSize(38, 22)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._offset = 0.0
        self._animation = QPropertyAnimation(self, b"offset", self)
        self._animation.setDuration(140)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def sizeHint(self) -> QSize:
        return self.TRACK_SIZE

    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, value: float) -> None:
        self._offset = value
        self.update()

    offset = Property(float, _get_offset, _set_offset)

    def setChecked(self, checked: bool) -> None:  # noqa: N802 — Qt API
        super().setChecked(checked)
        self._animation.stop()
        self._set_offset(1.0 if checked else 0.0)

    def _animate(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._offset)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def paintEvent(self, _event) -> None:  # noqa: N802 — Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.TRACK_SIZE.width(), self.TRACK_SIZE.height()
        off, on = QColor(theme.CONTROL_FILL).darker(108), QColor("#34C759")
        track = QColor(
            round(off.red() + (on.red() - off.red()) * self._offset),
            round(off.green() + (on.green() - off.green()) * self._offset),
            round(off.blue() + (on.blue() - off.blue()) * self._offset),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(0, 0, width, height), height / 2, height / 2)
        knob = height - 4
        x = 2 + (width - knob - 4) * self._offset
        painter.setBrush(QColor(0, 0, 0, 30))
        painter.drawEllipse(QRectF(x, 2.6, knob, knob))
        painter.setBrush(QColor("white"))
        painter.drawEllipse(QRectF(x, 2, knob, knob))


class Segmented(QFrame):
    """Сегментований контрол (як NSSegmentedControl)."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Segmented")
        self.setStyleSheet(
            f"""
            QFrame#Segmented {{ background: {theme.CONTROL_FILL}; border-radius: 8px; }}
            QFrame#Segmented QPushButton {{
                background: transparent; border: 1px solid transparent; border-radius: 6px;
                padding: 3px 6px; min-height: 16px; color: {theme.TEXT};
            }}
            QFrame#Segmented QPushButton:hover {{ background: rgba(255,255,255,0.5); }}
            QFrame#Segmented QPushButton:checked {{
                background: white; border: 1px solid rgba(0,0,0,0.08); font-weight: 600;
            }}
            """
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        self._group = QButtonGroup(self)
        self._buttons: dict[str, QPushButton] = {}
        for value, label in options:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self._group.addButton(button)
            self._buttons[value] = button
            layout.addWidget(button)
            button.clicked.connect(lambda _=False, v=value: self.changed.emit(v))

    def set_value(self, value: str) -> None:
        button = self._buttons.get(value)
        if button is not None:
            button.setChecked(True)


class ColorButton(QPushButton):
    """Кругла плашка кольору; відкриває системний діалог з альфа-каналом."""

    color_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(QSize(44, 26))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hex = "#000000"
        self.clicked.connect(self._choose)

    def set_hex(self, value: str) -> None:
        self._hex = value
        self.setToolTip(value.upper())
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 — Qt API
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(5, 5, -5, -5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawRoundedRect(rect, 5, 5)
        checker = QColor("#D1D1D6")
        for i in range(0, int(rect.width()), 6):
            for j in range(0, int(rect.height()), 6):
                if (i // 6 + j // 6) % 2:
                    painter.fillRect(QRectF(rect.x() + i, rect.y() + j, 6, 6).intersected(rect), checker)
        painter.setBrush(hex_to_qcolor(self._hex))
        painter.setPen(QPen(QColor(0, 0, 0, 40), 1))
        painter.drawRoundedRect(rect, 5, 5)

    def _choose(self) -> None:
        color = QColorDialog.getColor(
            hex_to_qcolor(self._hex), self, "Колір", QColorDialog.ColorDialogOption.ShowAlphaChannel
        )
        if color.isValid():
            value = qcolor_to_hex(color)
            self.set_hex(value)
            self.color_changed.emit(value)


class SliderField(QWidget):
    """Слайдер із підписом значення; працює з float через множник scale."""

    value_changed = Signal(float)

    def __init__(self, minimum: float, maximum: float, scale: float = 1.0, suffix: str = "", decimals: int = 0) -> None:
        super().__init__()
        self._scale, self._suffix, self._decimals = scale, suffix, decimals
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(round(minimum * scale), round(maximum * scale))
        self._slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self._value = QLabel()
        self._value.setObjectName("ValueLabel")
        self._value.setMinimumWidth(48)
        self._value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._slider, 1)
        layout.addWidget(self._value)
        self._slider.valueChanged.connect(self._on_change)

    def set_value(self, value: float) -> None:
        self._slider.blockSignals(True)
        self._slider.setValue(round(value * self._scale))
        self._slider.blockSignals(False)
        self._update_label(value)

    def _on_change(self, raw: int) -> None:
        value = raw / self._scale
        self._update_label(value)
        self.value_changed.emit(value)

    def _update_label(self, value: float) -> None:
        shown = value * (100 if self._suffix == "%" else 1)
        self._value.setText(f"{shown:.{self._decimals}f}{self._suffix}")


class Section(QWidget):
    """Іменована група рядків «підпис — контрол» усередині картки."""

    def __init__(self, title: str, caption_width: int = CAPTION_MAX_WIDTH) -> None:
        super().__init__()
        self._caption_width = caption_width
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        heading = QLabel(title.upper())
        heading.setObjectName("SectionTitle")
        outer.addWidget(heading)
        self._card = QFrame()
        self._card.setObjectName("Card")
        self._grid = QGridLayout(self._card)
        self._grid.setContentsMargins(12, 10, 12, 10)
        self._grid.setHorizontalSpacing(12)
        self._grid.setVerticalSpacing(10)
        self._grid.setColumnStretch(1, 1)
        outer.addWidget(self._card)
        self._row = 0

    def add_row(self, label: str, widget: QWidget) -> QLabel:
        caption = QLabel(label)
        caption.setObjectName("Caption")
        caption.setWordWrap(True)
        caption.setMaximumWidth(self._caption_width)
        # Короткі підписи — в один рядок; переносимо лише ті, що ширші за caption_width.
        caption.setMinimumWidth(min(self._caption_width, caption.fontMetrics().horizontalAdvance(label) + 4))
        self._grid.addWidget(caption, self._row, 0, Qt.AlignmentFlag.AlignVCenter)
        self._grid.addWidget(widget, self._row, 1)
        self._row += 1
        return caption

    def add_full(self, widget: QWidget) -> None:
        self._grid.addWidget(widget, self._row, 0, 1, 2)
        self._row += 1


def hbox(*widgets: QWidget, spacing: int = 6, stretch_first: bool = True) -> QWidget:
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    for index, widget in enumerate(widgets):
        layout.addWidget(widget, 1 if (index == 0 and stretch_first) else 0)
    return container


def hex_to_qcolor(value: str) -> QColor:
    digits = value.lstrip("#")
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    color = QColor(f"#{digits[:6]}")
    if len(digits) == 8:
        color.setAlpha(int(digits[6:8], 16))
    return color


def qcolor_to_hex(color: QColor) -> str:
    base = f"#{color.red():02X}{color.green():02X}{color.blue():02X}"
    return base if color.alpha() == 255 else f"{base}{color.alpha():02X}"
