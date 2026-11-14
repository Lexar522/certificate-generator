"""Головне вікно редактора: верхня панель, шари, полотно, інспектор."""

import logging
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core import about
from core.exceptions import CertificateError
from core.template_catalog import list_templates
from core.template_loader import load_template_config
from core.template_store import clone_template, save_config
from gui import theme
from gui.about import AboutDialog, app_logo
from gui.batch_dialog import BatchDialog
from gui.canvas import CanvasView, CertificateScene
from gui.document import EditorDocument
from gui.inspector_base import InspectorContext, Panel
from gui.layer_actions import layer_subtitle, new_layer_payload, scaled_layer_changes
from gui.layer_panels import build_panel
from gui.layers_panel import LayersPanel
from gui.qt_utils import line_icon, pil_to_pixmap, placeholder_pixmap
from gui.toast import Toast
from renderers.pillow_renderer import AnyLayer, PillowRenderer, RenderContext

logger = logging.getLogger(__name__)

IMAGE_FILTER = "Зображення (*.png *.jpg *.jpeg *.webp *.bmp)"
FONT_FILTER = "Шрифти (*.ttf *.otf)"
EXPORT_FILTERS = {"jpg": "JPEG (*.jpg)", "png": "PNG (*.png)", "pdf": "PDF (*.pdf)"}
SIDEBAR_WIDTH, INSPECTOR_WIDTH = 260, 380
PLACEHOLDER_SIZE = (360, 180)
ZOOM_FACTOR = 1.15


class MainWindow(QMainWindow):
    def __init__(self, templates_root: Path, output_dir: Path) -> None:
        super().__init__()
        self._templates_root = templates_root
        self._output_dir = output_dir
        self._renderer = PillowRenderer()
        self._selected: str | None = None
        self._panel: Panel | None = None
        self._panel_key: tuple | None = None

        templates = list_templates(templates_root)
        if not templates:
            raise CertificateError(f"У {templates_root} немає жодного шаблону з config.json")
        self._doc = EditorDocument(templates_root / templates[0])
        self._doc.subscribe(self._on_doc_changed)

        self._scene = CertificateScene()
        self._view = CanvasView(self._scene)
        self._layers = LayersPanel()
        self._inspector = QScrollArea()
        self._toast = Toast(self._view)

        self._build_ui(templates)
        self._connect()
        self._create_shortcuts()
        self.resize(1440, 880)
        self.setMinimumSize(1100, 680)
        self._full_sync()
        QTimer.singleShot(0, self._view.fit_page)

    # ------------------------------------------------------------------ #
    # Побудова інтерфейсу
    # ------------------------------------------------------------------ #

    def _build_ui(self, templates: tuple[str, ...]) -> None:
        root = QWidget()
        root.setObjectName("Root")
        column = QVBoxLayout(root)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._build_top_bar(templates))

        self._inspector.setObjectName("Inspector")
        self._inspector.setWidgetResizable(True)
        self._inspector.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._inspector.setMinimumWidth(INSPECTOR_WIDTH - 20)
        self._inspector.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.addWidget(self._layers)
        splitter.addWidget(self._view)
        splitter.addWidget(self._inspector)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([SIDEBAR_WIDTH, 900, INSPECTOR_WIDTH])
        splitter.setCollapsible(1, False)
        column.addWidget(splitter, 1)
        self.setCentralWidget(root)

        self.statusBar().setSizeGripEnabled(False)
        credit = QLabel(f"Розробник: {about.AUTHOR}, група {about.GROUP} · {about.UNIVERSITY}")
        credit.setObjectName("Hint")
        credit.setContentsMargins(0, 0, 10, 0)
        self.statusBar().addPermanentWidget(credit)
        self.setWindowIcon(QIcon(app_logo(64)))

    def _build_top_bar(self, templates: tuple[str, ...]) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TopBar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bar.setFixedHeight(56)
        row = QHBoxLayout(bar)
        row.setContentsMargins(18, 0, 14, 0)
        row.setSpacing(8)

        logo = QLabel()
        logo.setPixmap(app_logo(26))
        row.addWidget(logo)
        title = QLabel("Сертифікати")
        title.setObjectName("AppTitle")
        row.addWidget(title)
        row.addSpacing(14)

        self._template_box = QComboBox()
        for folder in templates:
            self._template_box.addItem(self._template_title(folder), folder)
        self._template_box.setMinimumWidth(200)
        self._template_box.setToolTip("Шаблон")
        row.addWidget(self._template_box)

        row.addSpacing(10)
        self._undo_button = self._icon_button("undo", "Скасувати (Ctrl+Z)", self._doc.undo)
        self._redo_button = self._icon_button("redo", "Повторити (Ctrl+Shift+Z)", self._doc.redo)
        row.addWidget(self._undo_button)
        row.addWidget(self._redo_button)
        row.addStretch(1)

        zoom_out = self._icon_button("minus", "Зменшити (Ctrl+−)", lambda: self._view.zoom_by(1 / ZOOM_FACTOR))
        zoom_in = self._icon_button("plus", "Збільшити (Ctrl+=)", lambda: self._view.zoom_by(ZOOM_FACTOR))
        fit = self._icon_button("fit", "Вмістити сторінку (Ctrl+0)", self._view.fit_page)
        self._zoom_label = QLabel("100%")
        self._zoom_label.setObjectName("ValueLabel")
        self._zoom_label.setMinimumWidth(44)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for widget in (zoom_out, self._zoom_label, zoom_in, fit):
            row.addWidget(widget)
        row.addStretch(1)

        self._save_button = QToolButton()
        self._save_button.setToolTip("Зберегти зміни в шаблоні (Ctrl+S)")
        self._save_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self._save_button.clicked.connect(self._save_template)
        save_menu = QMenu(self._save_button)
        save_menu.addAction("Зберегти як новий шаблон…", self._save_template_as)
        self._save_button.setMenu(save_menu)
        row.addWidget(self._save_button)

        batch = QPushButton("Для групи…")
        batch.setToolTip("Згенерувати сертифікати для всієї групи з Google Таблиці або CSV (Ctrl+G)")
        batch.clicked.connect(self._open_batch)
        row.addWidget(batch)

        export = QPushButton("Експорт")
        export.setObjectName("Accent")
        export.setToolTip("Зберегти сертифікат у JPG/PNG/PDF (Ctrl+E)")
        export.clicked.connect(self._export)
        row.addWidget(export)
        row.addWidget(self._icon_button("info", "Про програму", lambda: AboutDialog(self).exec()))
        return bar

    def _template_title(self, folder: str) -> str:
        try:
            return load_template_config(self._templates_root / folder).name
        except CertificateError:
            return folder

    @staticmethod
    def _icon_button(icon: str, tooltip: str, slot) -> QToolButton:
        button = QToolButton()
        button.setObjectName("Ghost")
        button.setIcon(line_icon(icon, theme.TEXT))
        button.setIconSize(QSize(18, 18))
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(slot)
        return button

    def _connect(self) -> None:
        doc = self._doc
        self._scene.layer_moved.connect(lambda lid, dx, dy: self._safely(lambda: doc.move_layer_by(lid, dx, dy)))
        self._scene.layer_resized.connect(self._resize_layer)
        self._scene.layer_activated.connect(self._activate_layer)
        self._scene.layer_selected.connect(self._select)
        self._layers.layer_selected.connect(self._select)
        self._layers.visibility_toggled.connect(
            lambda lid, visible: self._safely(lambda: doc.update_layer(lid, {"visible": visible}))
        )
        self._layers.add_requested.connect(lambda kind: self._safely(lambda: self._add_layer(kind)))
        self._layers.remove_requested.connect(self._remove_selected)
        self._layers.duplicate_requested.connect(self._duplicate_selected)
        self._layers.reorder_requested.connect(self._reorder_selected)
        self._layers.order_changed.connect(
            lambda ids: self._safely(lambda: doc.set_layer_order(list(reversed(ids))))
        )
        self._view.context_menu_requested.connect(self._show_layer_menu)
        self._layers.context_menu_requested.connect(self._show_layer_menu)
        self._view.zoom_changed.connect(lambda zoom: self._zoom_label.setText(f"{zoom * 100:.0f}%"))
        self._template_box.currentIndexChanged.connect(self._switch_template)

    def _create_shortcuts(self) -> None:
        bindings = [
            (QKeySequence.StandardKey.Undo, self._doc.undo),
            (QKeySequence.StandardKey.Redo, self._doc.redo),
            (QKeySequence("Ctrl+Shift+Z"), self._doc.redo),
            (QKeySequence.StandardKey.Save, self._save_template),
            (QKeySequence("Ctrl+E"), self._export),
            (QKeySequence("Ctrl+G"), self._open_batch),
            (QKeySequence("Ctrl+D"), self._duplicate_selected),
            # На рівні вікна, щоб працювало і з фокусом у списку шарів;
            # поля введення перехоплюють Delete/Backspace для себе (ShortcutOverride).
            (QKeySequence(Qt.Key.Key_Delete), self._remove_selected),
            (QKeySequence(Qt.Key.Key_Backspace), self._remove_selected),
            (QKeySequence("Ctrl+0"), self._view.fit_page),
            (QKeySequence("Ctrl+="), lambda: self._view.zoom_by(ZOOM_FACTOR)),
            (QKeySequence("Ctrl+-"), lambda: self._view.zoom_by(1 / ZOOM_FACTOR)),
        ]
        for sequence, slot in bindings:
            action = QAction(self)
            action.setShortcut(sequence)
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            action.triggered.connect(slot)
            self.addAction(action)

    # ------------------------------------------------------------------ #
    # Синхронізація з документом
    # ------------------------------------------------------------------ #

    def _on_doc_changed(self, kind: str, layer_id: str | None) -> None:
        if kind == "layer" and layer_id and self._doc.has_layer(layer_id):
            self._render_layer(self._doc.layer(layer_id), self._render_context(), self._z_index(layer_id))
            self._refresh_layer_list()
        else:
            if kind == "structure" and layer_id:
                self._selected = layer_id
            self._full_sync()
        self._refresh_inspector()
        self._update_chrome()

    def _full_sync(self) -> None:
        if self._selected and not self._doc.has_layer(self._selected):
            self._selected = None
        try:
            background = self._renderer.render_background(self._doc.config.canvas, self._doc.template_dir)
            self._scene.set_page(pil_to_pixmap(background))
        except CertificateError as exc:
            self._show_error(str(exc))
        context = self._render_context()
        for index, layer in enumerate(self._doc.config.layers):
            self._render_layer(layer, context, index)
        self._scene.retain_layers({layer.id for layer in self._doc.config.layers})
        self._scene.select_layer(self._selected)
        self._refresh_layer_list()
        self._refresh_inspector()
        self._update_chrome()

    def _refresh_layer_list(self) -> None:
        subtitles = {layer.id: layer_subtitle(layer, self._doc) for layer in self._doc.config.layers}
        self._layers.set_layers(self._doc.config.layers, subtitles, self._selected)

    def _render_context(self) -> RenderContext:
        return RenderContext(self._doc.preview_data(), self._doc.template_dir, self._doc.config)

    def _render_layer(self, layer: AnyLayer, context: RenderContext, z: int) -> None:
        name = layer.label or layer.id
        tooltip = f"{name}\nПодвійний клік — редагувати"
        try:
            sprite = self._renderer.render_layer(layer, context)
        except CertificateError as exc:
            self._show_error(str(exc))
            pixmap = placeholder_pixmap(*PLACEHOLDER_SIZE, f"⚠ {name}", theme.DANGER)
            self._scene.upsert_layer(layer.id, pixmap, layer.x, layer.y, z, layer.visible, str(exc))
            return
        if sprite is None:
            width = getattr(layer, "width", None) or PLACEHOLDER_SIZE[0]
            height = getattr(layer, "height", None) or PLACEHOLDER_SIZE[1]
            pixmap = placeholder_pixmap(width, height, name)
            self._scene.upsert_layer(layer.id, pixmap, layer.x, layer.y, z, layer.visible, tooltip)
            return
        pixmap = pil_to_pixmap(sprite.image)
        self._scene.upsert_layer(layer.id, pixmap, sprite.x, sprite.y, z, layer.visible, tooltip)

    def _z_index(self, layer_id: str) -> int:
        return next(i for i, layer in enumerate(self._doc.config.layers) if layer.id == layer_id)

    def _refresh_inspector(self) -> None:
        layer_type = type(self._doc.layer(self._selected)) if self._selected else None
        key = (self._doc.template_dir, self._selected, layer_type)
        if self._panel is not None and key == self._panel_key:
            self._panel.bind()
            return
        context = InspectorContext(
            self._doc, self._show_error, self._pick_image, self._pick_font, self._center_layer
        )
        self._panel = build_panel(context, self._selected)
        self._panel_key = key
        self._inspector.setWidget(self._panel)

    def _update_chrome(self) -> None:
        self._undo_button.setEnabled(self._doc.can_undo)
        self._redo_button.setEnabled(self._doc.can_redo)
        dirty = self._doc.is_dirty
        self._save_button.setText("Зберегти шаблон  •" if dirty else "Зберегти шаблон")
        self._save_button.setStyleSheet(f"color: {theme.ACCENT}; font-weight: 600;" if dirty else "")
        self.setWindowTitle(f"{self._doc.config.name}{' — змінено' if dirty else ''} · Сертифікати")

    def _select(self, layer_id: str | None) -> None:
        if layer_id == self._selected:
            return
        self._selected = layer_id
        self._scene.select_layer(layer_id)
        self._layers.select(layer_id)
        self._refresh_inspector()

    # ------------------------------------------------------------------ #
    # Дії над шарами
    # ------------------------------------------------------------------ #

    def _safely(self, action) -> None:
        try:
            action()
        except CertificateError as exc:
            self._show_error(str(exc))

    def _add_layer(self, kind: str) -> None:
        payload = new_layer_payload(kind, self._doc, self._pick_image, self._pick_font)
        if payload is not None:
            self._doc.add_layer(payload)
            self._toast.show_message(f"Додано: {payload['label']}. Перетягніть його на потрібне місце.", "success")

    def _resize_layer(self, layer_id: str, factor: float, left: int, top: int) -> None:
        self._safely(
            lambda: self._doc.update_layer(
                layer_id, scaled_layer_changes(self._renderer, self._doc, layer_id, factor, left, top)
            )
        )

    def _center_layer(self, layer_id: str, axis: str) -> None:
        rect = self._scene.layer_rect(layer_id)
        if rect is None:
            return
        page = self._scene.page_rect
        dx = round(page.center().x() - rect.center().x()) if axis == "horizontal" else 0
        dy = round(page.center().y() - rect.center().y()) if axis == "vertical" else 0
        self._doc.move_layer_by(layer_id, dx, dy)

    def _activate_layer(self, layer_id: str) -> None:
        self._select(layer_id)
        # Відкладено: після подвійного кліку Qt ще віддає фокус полотну.
        QTimer.singleShot(0, lambda: self._panel.focus_primary() if self._panel is not None else None)

    def _reorder_selected(self, step: int) -> None:
        if self._selected:
            self._safely(lambda: self._doc.reorder_layer(self._selected, step))

    def _remove_selected(self) -> None:
        if not self._selected:
            return
        name = self._doc.layer(self._selected).label or self._selected
        self._safely(lambda: self._doc.remove_layer(self._selected))
        self._toast.show_message(f"Видалено: {name}", "info", "Скасувати", self._doc.undo)

    def _duplicate_selected(self) -> None:
        if self._selected:
            self._safely(lambda: self._doc.duplicate_layer(self._selected))

    def _show_layer_menu(self, global_pos: QPoint) -> None:
        if not self._selected:
            return
        layer_id = self._selected
        doc = self._doc
        menu = QMenu(self)
        menu.addAction(line_icon("duplicate"), "Дублювати\tCtrl+D", self._duplicate_selected)
        menu.addAction("↔  По центру сторінки", lambda: self._safely(lambda: self._center_layer(layer_id, "horizontal")))
        menu.addAction("↕  По центру по вертикалі", lambda: self._safely(lambda: self._center_layer(layer_id, "vertical")))
        menu.addSeparator()
        menu.addAction(line_icon("up"), "Підняти вище", lambda: self._safely(lambda: doc.reorder_layer(layer_id, 1)))
        menu.addAction(line_icon("down"), "Опустити нижче", lambda: self._safely(lambda: doc.reorder_layer(layer_id, -1)))
        visible = doc.layer(layer_id).visible
        menu.addAction(
            line_icon("eye-off" if visible else "eye"),
            "Сховати" if visible else "Показати",
            lambda: self._safely(lambda: doc.update_layer(layer_id, {"visible": not visible})),
        )
        menu.addSeparator()
        menu.addAction(line_icon("minus", theme.DANGER), "Видалити\tDelete", self._remove_selected)
        menu.exec(global_pos)

    def _pick_image(self) -> Path | None:
        path, _ = QFileDialog.getOpenFileName(self, "Оберіть зображення", str(Path.home()), IMAGE_FILTER)
        return Path(path) if path else None

    def _pick_font(self) -> Path | None:
        path, _ = QFileDialog.getOpenFileName(self, "Оберіть шрифт", "/usr/share/fonts", FONT_FILTER)
        return Path(path) if path else None

    # ------------------------------------------------------------------ #
    # Шаблони, експорт
    # ------------------------------------------------------------------ #

    def _save_template(self) -> None:
        try:
            self._doc.save()
        except CertificateError as exc:
            self._show_error(str(exc))
            return
        self._update_chrome()
        self._toast.show_message("Шаблон збережено", "success")

    def _save_template_as(self) -> None:
        name, ok = QInputDialog.getText(self, "Новий шаблон", "Назва папки (латиниця, цифри, - _):")
        if not ok or not name.strip():
            return
        try:
            target = clone_template(self._templates_root, self._doc.template_dir, name.strip())
            save_config(target, self._doc.config)  # переносимо незбережені зміни в копію
            self._doc.load(target)
        except CertificateError as exc:
            self._show_error(str(exc))
            return
        self._template_box.blockSignals(True)
        self._template_box.addItem(self._template_title(target.name), target.name)
        self._template_box.setCurrentIndex(self._template_box.count() - 1)
        self._template_box.blockSignals(False)
        self._toast.show_message(f"Створено шаблон «{target.name}»", "success")

    def _switch_template(self, index: int) -> None:
        folder = self._template_box.itemData(index)
        if not folder or folder == self._doc.template_dir.name:
            return
        if not self._confirm_discard():
            self._template_box.blockSignals(True)
            self._template_box.setCurrentIndex(self._template_box.findData(self._doc.template_dir.name))
            self._template_box.blockSignals(False)
            return
        self._selected = None
        self._safely(lambda: self._doc.load(self._templates_root / folder))
        QTimer.singleShot(0, self._view.fit_page)

    def _open_batch(self) -> None:
        BatchDialog(self._doc, self._templates_root.parent, self).exec()

    def _export(self) -> None:
        try:
            data = self._doc.export_data()
        except CertificateError as exc:
            self._show_error(str(exc), dialog=True)
            return
        fmt = self._doc.config.output.format
        self._output_dir.mkdir(parents=True, exist_ok=True)
        default = self._output_dir / f"cert_{data.certificate_id}.{fmt}"
        filters = ";;".join([EXPORT_FILTERS[fmt]] + [f for key, f in EXPORT_FILTERS.items() if key != fmt])
        path, chosen = QFileDialog.getSaveFileName(self, "Експорт сертифіката", str(default), filters)
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() not in {".jpg", ".jpeg", ".png", ".pdf"}:
            suffix = next((key for key, f in EXPORT_FILTERS.items() if f == chosen), fmt)
            target = target.with_suffix(f".{suffix}")

        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = self._renderer.export(data, self._doc.template_dir, self._doc.config, target)
        except CertificateError as exc:
            self._show_error(str(exc), dialog=True)
            return
        finally:
            QGuiApplication.restoreOverrideCursor()
        self._toast.show_message(
            f"Збережено: {result.name}",
            "success",
            "Відкрити",
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(result))),
        )

    def _show_error(self, message: str, dialog: bool = False) -> None:
        logger.warning(message)
        if dialog:
            QMessageBox.warning(self, "Помилка", message)
        else:
            self._toast.show_message(message.splitlines()[0], "error")

    def _confirm_discard(self) -> bool:
        if not self._doc.is_dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Незбережені зміни",
            f"Зберегти зміни в шаблоні «{self._doc.config.name}»?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Save:
            self._save_template()
            return not self._doc.is_dirty
        return answer == QMessageBox.StandardButton.Discard

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt API
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()
