"""Панелі інспектора для кожного типу шару та для документа в цілому."""

from collections.abc import Callable
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QComboBox, QDateEdit, QHBoxLayout, QLabel, QPushButton, QToolButton, QWidget

from core.exceptions import CertificateError
from core.models import FrameLayer, ImageLayer, QrLayer, ShapeLayer, TextLayer, WatermarkLayer
from core.frame_builder import CORNER_STYLES, FRAME_KINDS
from core.ornaments import honeycomb_background
from core.template_store import import_asset, save_generated_asset
from gui import theme
from gui.document import EditorDocument, new_certificate_id
from gui.page_size import CUSTOM_FORMAT, detect_format, format_by_key, px_to_mm
from gui.inspector_base import InspectorContext, Panel
from gui.qt_utils import TYPE_NAMES, line_icon, pil_to_pixmap, type_icon
from gui.widgets import hbox
from renderers.pillow_renderer import PillowRenderer

FONT_SUFFIXES = {".ttf", ".otf"}
MAX_COORD = 10_000
BACKGROUND_PREVIEW_HEIGHT = 150


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


def choose_background(doc: EditorDocument, pick_image: Callable[[], Path | None]) -> bool:
    """Діалог вибору → копія файлу в шаблон → новий фон. False — користувач скасував вибір."""
    path = pick_image()
    if path is None:
        return False
    doc.update_canvas({"background_image": import_asset(doc.template_dir, path, "assets")})
    return True


def apply_pattern_background(doc: EditorDocument) -> None:
    canvas = doc.config.canvas
    image = honeycomb_background(canvas.width, canvas.height, canvas.background_color)
    relative = save_generated_asset(doc.template_dir, "assets/pattern_honeycomb.png", image)
    doc.update_canvas({"background_image": relative, "background_fit": "stretch"})


def canvas_summary(doc: EditorDocument) -> str:
    """«A4 · горизонтально · 210 × 148 мм при 300 DPI»."""
    canvas, dpi = doc.config.canvas, doc.config.output.dpi
    key = detect_format(canvas.width, canvas.height, dpi)
    name = "Власний" if key == CUSTOM_FORMAT else format_by_key(key).title.split(" · ")[0]
    orientation = "горизонтально" if canvas.width > canvas.height else "вертикально" if canvas.width < canvas.height else "квадрат"
    size = f"{px_to_mm(canvas.width, dpi):.0f} × {px_to_mm(canvas.height, dpi):.0f} мм при {dpi} DPI"
    return f"{name} · {orientation}\n{size}"


def swap_orientation(doc: EditorDocument) -> None:
    canvas = doc.config.canvas
    doc.resize_canvas(canvas.height, canvas.width, scale_content=True)


def _background_thumbnail(doc: EditorDocument, width: int) -> QPixmap:
    """Мініатюра фону сторінки (з урахуванням способу вписування) для інспектора."""
    try:
        image = PillowRenderer().render_background(doc.config.canvas, doc.template_dir)
    except CertificateError:
        return QPixmap()
    image.thumbnail((width, BACKGROUND_PREVIEW_HEIGHT))
    return pil_to_pixmap(image)


# ---------------------------------------------------------------------- #
# Документ (нічого не виділено)
# ---------------------------------------------------------------------- #


class DocumentPanel(Panel):
    def __init__(self, ctx: InspectorContext) -> None:
        super().__init__(ctx)
        self.body.addWidget(_header("Документ", self.doc.config.name, None))
        self._build_background()
        self._build_certificate()
        self._build_canvas()
        self._build_export()
        self.finish()

    def _build_background(self) -> None:
        doc = self.doc
        section = self.section("Фон сторінки")

        preview = QLabel()
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setFixedHeight(BACKGROUND_PREVIEW_HEIGHT)
        preview.setStyleSheet(f"border-radius: 8px; background: {theme.CONTROL_FILL};")
        self.on_bind(lambda: preview.setPixmap(_background_thumbnail(doc, preview.width() or 300)))
        section.add_full(preview)
        section.add_full(self.caption(lambda: _file_name(doc.config.canvas.background_image, "Без зображення — лише колір")))

        choose = QPushButton("Обрати зображення…")
        choose.setObjectName("Accent")
        choose.clicked.connect(lambda: self.guard(lambda: choose_background(doc, self.ctx.pick_image)))
        clear = QPushButton("Прибрати")
        clear.clicked.connect(lambda: self.guard(lambda: doc.update_canvas({"background_image": None})))
        self.visible_when(lambda: doc.config.canvas.background_image is not None, clear)
        section.add_full(hbox(choose, clear, stretch_first=True))
        pattern = QPushButton("Візерунок «соти»")
        pattern.setToolTip("Ледь помітний візерунок, як на захищених бланках")
        pattern.clicked.connect(lambda: self.guard(lambda: apply_pattern_background(doc)))
        section.add_full(pattern)

        fit = self.segmented(
            [("cover", "Заповнити"), ("contain", "Вмістити"), ("stretch", "Розтягнути")],
            lambda: doc.config.canvas.background_fit,
            lambda v: doc.update_canvas({"background_fit": v}),
        )
        fit_caption = section.add_row("Як вписати", fit)
        self.visible_when(lambda: doc.config.canvas.background_image is not None, fit, fit_caption)
        section.add_row(
            "Колір фону",
            self.color(lambda: doc.config.canvas.background_color, lambda v: doc.update_canvas({"background_color": v})),
        )
        section.add_full(
            self.hint(
                "«Заповнити» — без порожніх країв, зайве обрізається; «Вмістити» — видно все зображення, "
                "краї заповнює колір фону. Підійде будь-який JPG/PNG; файл копіюється в шаблон."
            )
        )

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
        section.add_row("Формат", self.caption(lambda: canvas_summary(doc)))
        resize = QPushButton("Змінити розмір…")
        resize.setObjectName("Accent")
        resize.clicked.connect(lambda: self.guard(self.ctx.open_canvas_size))
        rotate = QPushButton("⟲ Повернути")
        rotate.setToolTip("Поміняти ширину й висоту місцями; вміст переноситься пропорційно")
        rotate.clicked.connect(lambda: self.guard(lambda: swap_orientation(doc)))
        section.add_full(hbox(resize, rotate, stretch_first=True))
        section.add_full(self.hint("У діалозі — формати A3, A4, A5, Letter, квадрат, DPI та пропорційне масштабування вмісту."))

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
        general.add_row("Заблоковано", self.switch(lambda: self.layer.locked, lambda v: self.update({"locked": v})))

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
        self._text_edit = self.text_area(self._get_text, self._set_text, "Введіть текст; Enter — новий рядок")
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
        typography.add_row("Підкреслення", self.switch(lambda: self.layer.underline, lambda v: self.update({"underline": v})))

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


class ShapePanel(LayerPanel):
    def build_specific(self) -> None:
        section = self.section("Фігура")
        section.add_row(
            "Форма",
            self.segmented(
                [("rectangle", "Прямокутник"), ("ellipse", "Еліпс"), ("line", "Лінія")],
                lambda: self.layer.shape,
                lambda v: self.update({"shape": v, "stroke_width": self.layer.stroke_width or 1}),
            ),
        )
        width = self.spin(lambda: self.layer.width, lambda v: self.update({"width": v}, "width"), 1, MAX_COORD, " px")
        height = self.spin(lambda: self.layer.height, lambda v: self.update({"height": v}, "height"), 1, MAX_COORD, " px")
        height_box = hbox(QLabel("×"), height, stretch_first=False)
        section.add_row("Розмір", hbox(width, height_box, stretch_first=False))
        self.visible_when(lambda: self.layer.shape != "line", height_box)

        fill = self.color(lambda: self.layer.fill_color or "#FFFFFF", lambda v: self.update({"fill_color": v}))
        fill_row = hbox(self.switch(lambda: self.layer.fill_color is not None, self._toggle_fill), fill, stretch_first=False)
        fill_caption = section.add_row("Заливка", fill_row)
        self.visible_when(lambda: self.layer.shape != "line", fill_caption, fill_row)
        self.visible_when(lambda: self.layer.fill_color is not None, fill)

        section.add_row("Колір лінії", self.color(lambda: self.layer.stroke_color, lambda v: self.update({"stroke_color": v})))
        section.add_row("Товщина", self.spin(lambda: self.layer.stroke_width, lambda v: self.update({"stroke_width": v}, "stroke"), 0, 500, " px"))
        radius = self.spin(lambda: self.layer.corner_radius, lambda v: self.update({"corner_radius": v}, "radius"), 0, MAX_COORD, " px")
        radius_caption = section.add_row("Заокруглення", radius)
        self.visible_when(lambda: self.layer.shape == "rectangle", radius, radius_caption)
        section.add_full(self.hint("Лінія підійде для місця підпису чи розділювача; поверніть її на 90°, щоб стала вертикальною."))

    def _toggle_fill(self, enabled: bool) -> None:
        self.update({"fill_color": "#F2F2F7" if enabled else None})


class FramePanel(LayerPanel):
    def build_specific(self) -> None:
        section = self.section("Рамка")
        section.add_row("Стиль", self.combo(FRAME_KINDS, lambda: self.layer.style, self._set_style))
        color = self.color(lambda: self.layer.color, lambda v: self.update({"color": v}))
        caption = section.add_row("Колір ліній", color)
        self.visible_when(lambda: self.layer.style not in ("gold", "image"), color, caption)
        section.add_full(self.hint("Рамка завжди займає всю сторінку й підлаштовується під її розмір."))
        self._build_constructor()
        self._build_image()

    def _set_style(self, style: str) -> None:
        if style == "image" and self.layer.path is None:
            relative = self.import_image()
            if relative is None:
                self.bind()
                return
            self.update({"style": "image", "path": relative})
            return
        self.update({"style": style})

    def _build_constructor(self) -> None:
        section = self.section("Конструктор")
        section.add_row("Лінії", self.segmented([("1", "Одна"), ("2", "Дві"), ("3", "Три")],
                                                lambda: str(self.layer.line_count),
                                                lambda v: self.update({"line_count": int(v)})))
        section.add_row("Другий колір", self.color(lambda: self.layer.accent_color,
                                                   lambda v: self.update({"accent_color": v})))
        section.add_row("Товщина", self._percent("thickness", 0.05, 3))
        section.add_row("Відступ від краю", self._percent("margin", 0, 12))
        section.add_row("Між лініями", self._percent("gap", 0.1, 5))
        section.add_row("Кути", self.combo(CORNER_STYLES, lambda: self.layer.corner, lambda v: self.update({"corner": v})))
        section.add_row("Розмір кутів", self._percent("corner_size", 0.5, 8))
        band = self.color(lambda: self.layer.band_color or "#F3E9D2", lambda v: self.update({"band_color": v}))
        band_row = hbox(self.switch(lambda: self.layer.band_color is not None,
                                    lambda on: self.update({"band_color": "#F3E9D2" if on else None})),
                        band, stretch_first=False)
        section.add_row("Смуга по краю", band_row)
        self.visible_when(lambda: self.layer.band_color is not None, band)
        self.visible_when(lambda: self.layer.style == "custom", section)
        section.add_full(self.hint("Розміри — у відсотках від коротшої сторони сторінки, тож рамка "
                                   "виглядає однаково на A4, A5 чи квадраті."))

    def _build_image(self) -> None:
        section = self.section("Зображення рамки")
        replace = QPushButton("Замінити…")
        replace.clicked.connect(lambda: self.guard(self._replace_image))
        section.add_row("Файл", hbox(self.caption(lambda: _file_name(self.layer.path, "—")), replace))
        section.add_row("Ширина рамки", self._percent("border", 1, 20))
        section.add_row("Кути й краї", self._percent("slice", 5, 49))
        section.add_full(self.hint(
            "Підійде PNG з прозорою серединою. Кути переносяться без спотворень, краї повторюються "
            "плитками. «Кути й краї» — яку частину картинки вважати рамкою."))
        self.visible_when(lambda: self.layer.style == "image", section)

    def _replace_image(self) -> None:
        relative = self.import_image()
        if relative:
            self.update({"path": relative, "style": "image"})

    def _percent(self, prop: str, minimum: float, maximum: float):
        return self.slider(lambda: getattr(self.layer, prop), lambda v: self.update({prop: v}, prop),
                           minimum, maximum, 100, " %", 1)  # значення вже у відсотках


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
    ShapeLayer: ShapePanel,
    FrameLayer: FramePanel,
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
