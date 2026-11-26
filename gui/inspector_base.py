"""Основа панелей інспектора: декларативна прив'язка контролів до документа.

Кожен контрол створюється разом із парою get/set: set викликається при зміні користувачем,
get — при оновленні панелі (з заблокованими сигналами, щоб не було циклів).
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QLineEdit, QPlainTextEdit, QSpinBox, QVBoxLayout, QWidget

from core.exceptions import CertificateError
from gui.document import EditorDocument
from gui.widgets import ColorButton, Section, Segmented, SliderField, Switch

SPIN_MIN_WIDTH = 64
TEXT_AREA_LINES = 3

Getter = Callable[[], Any]
Setter = Callable[[Any], None]


@dataclass(frozen=True)
class InspectorContext:
    doc: EditorDocument
    report_error: Callable[[str], None]
    pick_image: Callable[[], Path | None]
    pick_font: Callable[[], Path | None]
    center_layer: Callable[[str, str], None]  # (id, "horizontal" | "vertical")
    open_canvas_size: Callable[[], None]


class Panel(QWidget):
    def __init__(self, ctx: InspectorContext) -> None:
        super().__init__()
        self.ctx = ctx
        self._binders: list[Callable[[], None]] = []
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(14, 16, 14, 20)
        self.body.setSpacing(18)

    @property
    def doc(self) -> EditorDocument:
        return self.ctx.doc

    def bind(self) -> None:
        for binder in self._binders:
            binder()

    def focus_primary(self) -> None:
        """Фокус на головному полі панелі (подвійний клік по шару на полотні)."""

    def finish(self) -> None:
        self.body.addStretch(1)
        self.bind()

    def section(self, title: str) -> Section:
        section = Section(title)
        self.body.addWidget(section)
        return section

    def guard(self, action: Callable[[], None]) -> None:
        """Виконує дію; помилку валідації показує користувачу і повертає контроли до стану документа."""
        try:
            action()
        except CertificateError as exc:
            self.ctx.report_error(str(exc))
            self.bind()

    def on_bind(self, binder: Callable[[], None]) -> None:
        self._binders.append(binder)

    def visible_when(self, predicate: Callable[[], bool], *widgets: QWidget) -> None:
        def binder() -> None:
            shown = predicate()
            for widget in widgets:
                widget.setVisible(shown)

        self.on_bind(binder)

    # ------------------------------------------------------------------ #
    # Фабрики контролів
    # ------------------------------------------------------------------ #

    def slider(
        self,
        get: Getter,
        set_: Setter,
        minimum: float,
        maximum: float,
        scale: float = 1.0,
        suffix: str = "",
        decimals: int = 0,
    ) -> SliderField:
        widget = SliderField(minimum, maximum, scale, suffix, decimals)
        widget.value_changed.connect(lambda value: self.guard(lambda: set_(value)))
        self.on_bind(lambda: widget.set_value(get()))
        return widget

    def spin(
        self,
        get: Getter,
        set_: Setter,
        minimum: int,
        maximum: int,
        suffix: str = "",
        zero_text: str | None = None,
    ) -> QSpinBox:
        """zero_text: якщо задано, 0 означає None («Авто», «Без обмеження»)."""
        widget = QSpinBox()
        widget.setRange(0 if zero_text else minimum, maximum)
        widget.setSuffix(suffix)
        widget.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        widget.setMinimumWidth(SPIN_MIN_WIDTH)
        widget.setKeyboardTracking(False)
        if zero_text:
            widget.setSpecialValueText(zero_text)

        def on_change(value: int) -> None:
            converted = None if (zero_text and value == 0) else value
            self.guard(lambda: set_(converted))

        def binder() -> None:
            widget.blockSignals(True)
            value = get()
            widget.setValue(0 if value is None else int(value))
            widget.blockSignals(False)

        widget.valueChanged.connect(on_change)
        self.on_bind(binder)
        return widget

    def line(self, get: Getter, set_: Setter, placeholder: str = "") -> QLineEdit:
        widget = QLineEdit()
        widget.setPlaceholderText(placeholder)
        widget.textEdited.connect(lambda text: self.guard(lambda: set_(text)))

        def binder() -> None:
            value = get() or ""
            if widget.text() != value:
                widget.blockSignals(True)
                widget.setText(value)
                widget.blockSignals(False)

        self.on_bind(binder)
        return widget

    def text_area(self, get: Getter, set_: Setter, placeholder: str = "") -> QPlainTextEdit:
        """Багаторядкове поле: Enter — новий рядок у тексті сертифіката."""
        widget = QPlainTextEdit()
        widget.setPlaceholderText(placeholder)
        widget.setTabChangesFocus(True)
        line_height = widget.fontMetrics().lineSpacing()
        widget.setFixedHeight(line_height * TEXT_AREA_LINES + 16)
        widget.textChanged.connect(lambda: self.guard(lambda: set_(widget.toPlainText())))

        def binder() -> None:
            value = get() or ""
            if widget.toPlainText() != value:
                widget.blockSignals(True)
                widget.setPlainText(value)
                widget.blockSignals(False)

        self.on_bind(binder)
        return widget

    def color(self, get: Getter, set_: Setter) -> ColorButton:
        widget = ColorButton()
        widget.color_changed.connect(lambda value: self.guard(lambda: set_(value)))
        self.on_bind(lambda: widget.set_hex(get()))
        return widget

    def segmented(self, options: list[tuple[str, str]], get: Getter, set_: Setter) -> Segmented:
        widget = Segmented(options)
        widget.changed.connect(lambda value: self.guard(lambda: set_(value)))
        self.on_bind(lambda: widget.set_value(get()))
        return widget

    def switch(self, get: Getter, set_: Setter) -> Switch:
        widget = Switch()
        widget.clicked.connect(lambda checked: self.guard(lambda: set_(checked)))
        self.on_bind(lambda: widget.setChecked(bool(get())))
        return widget

    def caption(self, get: Getter) -> QLabel:
        widget = QLabel()
        widget.setObjectName("Caption")
        widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.on_bind(lambda: widget.setText(get()))
        return widget

    @staticmethod
    def hint(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("Hint")
        label.setWordWrap(True)
        return label
