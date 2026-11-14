"""Панелі інспектора для кожного типу шару та для документа в цілому."""

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, QSize
from PySide6.QtWidgets import QComboBox, QDateEdit, QHBoxLayout, QLabel, QPushButton, QToolButton, QWidget

from core.exceptions import CertificateError
from core.models import ImageLayer, QrLayer, TextLayer, WatermarkLayer
from core.template_store import import_asset
from gui.document import new_certificate_id
from gui.inspector_base import InspectorContext, Panel
from gui.qt_utils import TYPE_NAMES, line_icon, type_icon
from gui.widgets import hbox

FONT_SUFFIXES = {".ttf", ".otf"}
MAX_COORD = 10_000


def template_fonts(template_dir: Path) -> list[str]:
    fonts_dir = template_dir / "fonts"
    if not fonts_dir.is_dir():
        return []
    return sorted(
        path.relative_to(template_dir).as_posix()
        for path in fonts_dir.iterdir()
        if path.suffix.lower() in FONT_SUFFIXES
    )


def _file_name(path: str | None, empty: str) -> str:
    return Path(path).name if path else empty


# ---------------------------------------------------------------------- #
# Документ (нічого не виділено)
# ---------------------------------------------------------------------- #


class DocumentPanel(Panel):
    def __init__(self, ctx: InspectorContext) -> None:
        super().__init__(ctx)
        self.body.addWidget(_header("Документ", self.doc.config.name, None))
        self._build_certificate()
        self._build_canvas()
        self._build_export()
        self.finish()

    def _build_certificate(self) -> None:
        doc = self.doc
        section = self.section("Сертифікат")

        id_edit = self.line(lambda: doc.state.certificate_id, doc.set_certificate_id, "CERT-...")
        refresh = QToolButton()
        refresh.setObjectName("Ghost")
        refresh.setIcon(line_icon("refresh"))
        refresh.setToolTip("Згенерувати новий ID")
        refresh.clicked.connect(lambda: self.guard(lambda: doc.set_certificate_id(new_certificate_id(date.today()))))
        section.add_row("ID", hbox(id_edit, refresh))

        date_edit = QDateEdit()
        date_edit.setCalendarPopup(True)
        date_edit.setDisplayFormat("dd.MM.yyyy")
        date_edit.dateChanged.connect(lambda value: self.guard(lambda: doc.set_issue_date(value.toPython())))

        def bind_date() -> None:
            date_edit.blockSignals(True)
            issued = doc.state.issue_date
            date_edit.setDate(QDate(issued.year, issued.month, issued.day))
            date_edit.blockSignals(False)

        self.on_bind(bind_date)
        section.add_row("Дата видачі", date_edit)
        section.add_row("Формат дати", self.line(lambda: doc.config.date_format, doc.set_date_format, "%d.%m.%Y"))
        section.add_full(self.hint("Підставляється у текст як {issue_date}; номер — як {certificate_id}."))

    def _build_canvas(self) -> None:
        doc = self.doc
        section = self.section("Полотно")
        width = self.spin(lambda: doc.config.canvas.width, lambda v: doc.update_canvas({"width": v}, "canvas:w"), 1, MAX_COORD, " px")
        height = self.spin(lambda: doc.config.canvas.height, lambda v: doc.update_canvas({"height": v}, "canvas:h"), 1, MAX_COORD, " px")
        section.add_row("Розмір", hbox(width, QLabel("×"), height, stretch_first=False))
        section.add_row(
            "Колір фону",
            self.color(lambda: doc.config.canvas.background_color, lambda v: doc.update_canvas({"background_color": v})),
        )

        choose = QPushButton("Обрати…")
        choose.clicked.connect(lambda: self.guard(self._choose_background))
        clear = QPushButton("Прибрати")
        clear.clicked.connect(lambda: self.guard(lambda: doc.update_canvas({"background_image": None})))
        name = self.caption(lambda: _file_name(doc.config.canvas.background_image, "Немає"))
        section.add_row("Фонове зображення", name)
        section.add_full(hbox(QWidget(), choose, clear))

    def _choose_background(self) -> None:
        path = self.ctx.pick_image()
        if path is not None:
            relative = import_asset(self.doc.template_dir, path, "assets")
            self.doc.update_canvas({"background_image": relative})

    def _build_export(self) -> None:
        doc = self.doc
        section = self.section("Експорт")
        section.add_row(
            "Формат",
            self.segmented(
                [("jpg", "JPG"), ("png", "PNG"), ("pdf", "PDF")],
                lambda: doc.config.output.format,
                lambda v: doc.update_output({"format": v}),
            ),
        )
        section.add_row(
            "Якість JPG",
            self.slider(lambda: doc.config.output.quality, lambda v: doc.update_output({"quality": round(v)}), 1, 100),
        )
        section.add_row("DPI", self.spin(lambda: doc.config.output.dpi, lambda v: doc.update_output({"dpi": v}), 72, 1200))


# ---------------------------------------------------------------------- #
# Шари
# ---------------------------------------------------------------------- #


class LayerPanel(Panel):
    """Спільна частина для всіх шарів: назва, позиція, обертання, прозорість."""

    def __init__(self, ctx: InspectorContext, layer_id: str) -> None:
        super().__init__(ctx)
        self.layer_id = layer_id
        layer = self.layer
        self.body.addWidget(_header(TYPE_NAMES.get(layer.type, layer.type), layer.label or layer.id, layer.type))

        general = self.section("Загальне")
        general.add_row("Назва", self.line(lambda: self.layer.label, lambda v: self.update({"label": v or None}, "label"), layer.id))
        general.add_row("Видимий", self.switch(lambda: self.layer.visible, lambda v: self.update({"visible": v})))

        self.build_specific()

        placement = self.section("Розташування")
        x = self.spin(lambda: self.layer.x, lambda v: self.update({"x": v}, "x"), -MAX_COORD, MAX_COORD)
        y = self.spin(lambda: self.layer.y, lambda v: self.update({"y": v}, "y"), -MAX_COORD, MAX_COORD)
        placement.add_row("Позиція", hbox(_tiny("X"), x, _tiny("Y"), y, stretch_first=False))
        center_h = QPushButton("↔ По центру")
        center_h.setToolTip("Вирівняти по центру сторінки горизонтально")
        center_h.clicked.connect(lambda: self.guard(lambda: self.ctx.center_layer(self.layer_id, "horizontal")))
        center_v = QPushButton("↕ По центру")
        center_v.setToolTip("Вирівняти по центру сторінки вертикально")
        center_v.clicked.connect(lambda: self.guard(lambda: self.ctx.center_layer(self.layer_id, "vertical")))
        placement.add_row("Вирівняти", hbox(center_h, center_v, stretch_first=False))
        placement.add_row(
            "Прозорість",
            self.slider(lambda: self.layer.opacity, lambda v: self.update({"opacity": v}, "opacity"), 0, 1, 100, "%"),
        )
        placement.add_row(
            "Обертання",
            self.slider(lambda: self.layer.rotation, lambda v: self.update({"rotation": v}, "rotation"), -180, 180, 1, "°"),
        )
        placement.add_full(
            self.hint(
                "Перетягуйте шар мишею, тягніть за кути — щоб змінити розмір. "
                "Стрілки — зсув на 1 px, Shift+стрілки — на 10 px."
            )
        )
        self.finish()

    @property
    def layer(self):
        return self.doc.layer(self.layer_id)

    def update(self, changes: dict, prop: str | None = None) -> None:
        merge_key = f"{self.layer_id}:{prop}" if prop else None
        self.doc.update_layer(self.layer_id, changes, merge_key)

    def build_specific(self) -> None:
        raise NotImplementedError

    def import_image(self) -> str | None:
        path = self.ctx.pick_image()
        return import_asset(self.doc.template_dir, path, "assets") if path else None


class WatermarkPanel(LayerPanel):
    def build_specific(self) -> None:
        section = self.section("Водяний знак")
        replace = QPushButton("Замінити…")
        replace.clicked.connect(lambda: self.guard(self._replace))
        section.add_row("Файл", hbox(self.caption(lambda: _file_name(self.layer.path, "—")), replace))
        section.add_row(
            "Масштаб",
            self.slider(lambda: self.layer.scale, lambda v: self.update({"scale": max(v, 0.01)}, "scale"), 0.05, 3, 100, "%"),
        )
        section.add_full(self.hint("Прозорість водяного знака — у розділі «Розташування»."))

    def _replace(self) -> None:
        relative = self.import_image()
        if relative:
            self.update({"path": relative})


class ImagePanel(LayerPanel):
    def build_specific(self) -> None:
        doc = self.doc
        section = self.section("Зображення")
        section.add_row("Змінне поле", self.switch(lambda: self.layer.path is None, self._set_dynamic))

        choose = QPushButton("Обрати…")
        choose.clicked.connect(lambda: self.guard(self._choose))
        clear = QPushButton("Очистити")
        clear.clicked.connect(lambda: self.guard(lambda: doc.set_image_value(self.layer_id, None)))
        file_label = self.caption(self._file_caption)
        section.add_row("Файл", file_label)
        section.add_full(hbox(QWidget(), choose, clear))
        self.visible_when(lambda: self.layer.path is None, clear)

        required = self.switch(lambda: self.layer.required, lambda v: self.update({"required": v}))
        required_caption = section.add_row("Обов'язкове", required)
        self.visible_when(lambda: self.layer.path is None, required, required_caption)

        size = self.section("Розмір")
        width = self.spin(lambda: self.layer.width, lambda v: self.update({"width": v}, "width"), 1, MAX_COORD, "", "Авто")
        height = self.spin(lambda: self.layer.height, lambda v: self.update({"height": v}, "height"), 1, MAX_COORD, "", "Авто")
        size.add_row("Ш × В", hbox(width, QLabel("×"), height, stretch_first=False))
        size.add_row("Зберігати пропорції", self.switch(lambda: self.layer.keep_aspect, lambda v: self.update({"keep_aspect": v})))

    def _file_caption(self) -> str:
        if self.layer.path is not None:
            return _file_name(self.layer.path, "—")
        return _file_name(self.doc.state.image_values.get(self.layer_id), "Підставляється при генерації")

    def _set_dynamic(self, dynamic: bool) -> None:
        if dynamic:
            self.doc.set_image_mode(self.layer_id, True)
            return
        relative = self.import_image()
        if relative is None:
            self.bind()
            return
        self.doc.set_image_mode(self.layer_id, False, relative)

    def _choose(self) -> None:
        if self.layer.path is None:
            path = self.ctx.pick_image()
            if path:
                self.doc.set_image_value(self.layer_id, str(path))
            return
        relative = self.import_image()
        if relative:
            self.update({"path": relative})


class TextPanel(LayerPanel):
    def build_specific(self) -> None:
        doc = self.doc
        content = self.section("Вміст")
        content.add_row("Змінне поле", self.switch(lambda: self.layer.text is None, lambda v: doc.set_text_mode(self.layer_id, v)))
        self._text_edit = self.line(self._get_text, self._set_text, "Введіть текст")
        content.add_row("Текст", self._text_edit)
        required = self.switch(lambda: self.layer.required, lambda v: self.update({"required": v}))
        required_caption = content.add_row("Обов'язкове", required)
        self.visible_when(lambda: self.layer.text is None, required, required_caption)
        content.add_full(self.hint("Змінне поле заповнюється для кожного сертифіката. У тексті шаблону можна писати {certificate_id} і {issue_date}."))

        typography = self.section("Типографіка")
        typography.add_row("Шрифт", self._font_picker())
        typography.add_row("Розмір", self.spin(lambda: self.layer.font_size, lambda v: self.update({"font_size": v}, "font_size"), 1, 1000, " pt"))
        typography.add_row("Колір", self.color(lambda: self.layer.color, lambda v: self.update({"color": v})))
        typography.add_row(
            "Вирівнювання",
            self.segmented([("left", "Ліво"), ("center", "Центр"), ("right", "Право")], lambda: self.layer.align, lambda v: self.update({"align": v})),
        )
        typography.add_row("Великі літери", self.switch(lambda: self.layer.uppercase, lambda v: self.update({"uppercase": v})))

        layout = self.section("Перенесення")
        layout.add_row("Макс. ширина", self.spin(lambda: self.layer.max_width, lambda v: self.update({"max_width": v}, "max_width"), 1, MAX_COORD, " px", "Без обмеження"))
        layout.add_row(
            "Якщо не вміщується",
            self.segmented([("shrink", "Зменшити"), ("wrap", "Переносити")], lambda: self.layer.overflow, lambda v: self.update({"overflow": v})),
        )
        layout.add_row("Мін. розмір", self.spin(lambda: self.layer.min_font_size, lambda v: self.update({"min_font_size": v}, "min_font_size"), 1, 1000, " pt", "Авто"))
        layout.add_row(
            "Міжрядковий",
            self.slider(lambda: self.layer.line_spacing, lambda v: self.update({"line_spacing": v}, "line_spacing"), 0.5, 3, 100, "×", 2),
        )

    def focus_primary(self) -> None:
        self._text_edit.setFocus()
        self._text_edit.selectAll()

    def _get_text(self) -> str:
        if self.layer.text is None:
            return self.doc.state.field_values.get(self.layer_id, "")
        return self.layer.text

    def _set_text(self, value: str) -> None:
        if self.layer.text is None:
            self.doc.set_field_value(self.layer_id, value)
        elif value.strip():
            self.update({"text": value}, "text")

    def _font_picker(self) -> QWidget:
        combo = QComboBox()
        combo.currentIndexChanged.connect(
            lambda index: self.guard(lambda: self.update({"font": combo.itemData(index)})) if index >= 0 else None
        )
        add = QToolButton()
        add.setObjectName("Ghost")
        add.setIcon(line_icon("plus"))
        add.setToolTip("Додати шрифт (.ttf/.otf)")
        add.clicked.connect(lambda: self.guard(self._import_font))

        def binder() -> None:
            fonts = template_fonts(self.doc.template_dir)
            if self.layer.font not in fonts:
                fonts.append(self.layer.font)
            combo.blockSignals(True)
            combo.clear()
            for font in fonts:
                combo.addItem(Path(font).stem, font)
            combo.setCurrentIndex(fonts.index(self.layer.font))
            combo.blockSignals(False)

        self.on_bind(binder)
        return hbox(combo, add)

    def _import_font(self) -> None:
        path = self.ctx.pick_font()
        if path is not None:
            self.update({"font": import_asset(self.doc.template_dir, path, "fonts")})


class QrPanel(LayerPanel):
    def build_specific(self) -> None:
        section = self.section("QR-код")
        section.add_row("Розмір", self.spin(lambda: self.layer.size, lambda v: self.update({"size": v}, "size"), 20, MAX_COORD, " px"))
        section.add_row("Посилання", self.line(lambda: self.layer.url_template, lambda v: self.update({"url_template": v}, "url"), "https://…/{certificate_id}"))
        section.add_full(self.hint("Посилання має містити {certificate_id} — його буде замінено на ID сертифіката."))
        section.add_row("Колір модулів", self.color(lambda: self.layer.fill_color, lambda v: self.update({"fill_color": v})))
        section.add_row("Колір фону", self.color(lambda: self.layer.back_color, lambda v: self.update({"back_color": v})))
        section.add_row("Поля", self.spin(lambda: self.layer.border, lambda v: self.update({"border": v}, "border"), 0, 20, " мод."))
        section.add_row(
            "Корекція помилок",
            self.segmented([(level, level) for level in "LMQH"], lambda: self.layer.error_correction, lambda v: self.update({"error_correction": v})),
        )


PANEL_TYPES = {
    WatermarkLayer: WatermarkPanel,
    ImageLayer: ImagePanel,
    TextLayer: TextPanel,
    QrLayer: QrPanel,
}


def build_panel(ctx: InspectorContext, layer_id: str | None) -> Panel:
    if layer_id is None:
        return DocumentPanel(ctx)
    layer = ctx.doc.layer(layer_id)
    panel_type = PANEL_TYPES.get(type(layer))
    if panel_type is None:
        raise CertificateError(f"Немає панелі для шару типу {layer.type}")
    return panel_type(ctx, layer_id)


def _header(kind: str, title: str, icon_kind: str | None) -> QWidget:
    container = QWidget()
    row = QHBoxLayout(container)
    row.setContentsMargins(2, 0, 0, 0)
    row.setSpacing(10)
    if icon_kind:
        icon = QLabel()
        icon.setPixmap(type_icon(icon_kind).pixmap(QSize(30, 30)))
        row.addWidget(icon)
    texts = QWidget()
    column = QHBoxLayout(texts)
    column.setContentsMargins(0, 0, 0, 0)
    title_label = QLabel(title)
    title_label.setObjectName("PanelTitle")
    kind_label = QLabel(kind)
    kind_label.setObjectName("Hint")
    column.addWidget(title_label)
    column.addWidget(kind_label)
    column.addStretch(1)
    row.addWidget(texts, 1)
    return container


def _tiny(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Hint")
    return label
