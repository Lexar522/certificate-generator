"""Додаткові можливості головного вікна (домішка до MainWindow).

Вигляд (тема, колір акценту), буфер обміну для шарів, замок шару, перетягування файлів
на полотно, новий шаблон, довідка гарячих клавіш і збереження налаштувань між запусками.
Методи спираються на атрибути MainWindow: _doc, _scene, _view, _layers, _toast, _selected тощо.
"""

from pathlib import Path

from PySide6.QtCore import QMimeData, QPointF
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QToolButton

from core.exceptions import CertificateError
from core.template_store import import_asset
from gui import theme
from gui.about import AboutDialog
from gui.batch_dialog import BatchDialog
from gui.canvas import IMAGE_SUFFIXES
from gui.canvas_size_dialog import CanvasSizeDialog
from gui.layer_actions import CLIPBOARD_MIME, layer_to_clipboard, paste_payload, picture_payload_from_file
from gui.new_template_dialog import NewTemplateDialog
from gui.qt_utils import line_icon
from gui.settings import UserSettings, save_settings, updated
from gui.shortcuts_dialog import ShortcutsDialog

THEME_LABELS = {"system": "Як у системі", "light": "Світла", "dark": "Темна"}
SWATCH_SIZE = 14
BUNDLED_TEMPLATE = "default_tech"


def _swatch(color: str) -> QIcon:
    pixmap = QPixmap(SWATCH_SIZE * 2, SWATCH_SIZE * 2)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor(0, 0, 0, 40))
    painter.setBrush(QColor(color))
    painter.drawEllipse(1, 1, SWATCH_SIZE * 2 - 2, SWATCH_SIZE * 2 - 2)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


class WindowExtrasMixin:
    _settings: UserSettings

    # ------------------------------------------------------------------ #
    # Вигляд: тема й колір акценту
    # ------------------------------------------------------------------ #

    def _build_appearance_buttons(self) -> list[QToolButton]:
        self._theme_button = self._icon_button("moon", "Перемкнути світлу / темну тему", self._toggle_theme)
        menu_button = self._icon_button("sliders", "Вигляд, довідка, про програму", lambda: None)
        menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu_button.setMenu(self._build_app_menu(menu_button))
        return [self._theme_button, menu_button]

    def _build_app_menu(self, parent) -> QMenu:
        menu = QMenu(parent)
        theme_menu = menu.addMenu("Тема")
        group = QActionGroup(theme_menu)
        self._theme_actions: dict[str, QAction] = {}
        for mode, label in THEME_LABELS.items():
            action = theme_menu.addAction(label, lambda m=mode: self._set_appearance(mode=m))
            action.setCheckable(True)
            group.addAction(action)
            self._theme_actions[mode] = action

        accent_menu = menu.addMenu("Колір акценту")
        accent_group = QActionGroup(accent_menu)
        self._accent_actions: dict[str, QAction] = {}
        for key, (label, light, _dark) in theme.ACCENTS.items():
            action = accent_menu.addAction(_swatch(light), label, lambda k=key: self._set_appearance(accent=k))
            action.setCheckable(True)
            accent_group.addAction(action)
            self._accent_actions[key] = action

        menu.addSeparator()
        menu.addAction("Новий шаблон…\tCtrl+N", self._new_template)
        menu.addAction("Розмір полотна…\tCtrl+Shift+R", self._open_canvas_size)
        menu.addAction("Гарячі клавіші\tCtrl+/", lambda: ShortcutsDialog(self).exec())
        menu.addSeparator()
        menu.addAction("Про програму", lambda: AboutDialog(self).exec())
        return menu

    def _toggle_theme(self) -> None:
        self._set_appearance(mode="light" if theme.palette().is_dark else "dark")

    def _set_appearance(self, mode: str | None = None, accent: str | None = None) -> None:
        self._settings = updated(
            self._settings,
            theme_mode=mode or self._settings.theme_mode,
            accent=accent or self._settings.accent,
        )
        self._apply_appearance()
        save_settings(self._settings)

    def _apply_appearance(self) -> None:
        theme.apply_theme(QApplication.instance(), self._settings.theme_mode, self._settings.accent)
        dark = theme.palette().is_dark
        self._theme_button.setProperty("icon_name", "sun" if dark else "moon")
        self._theme_button.setToolTip("Світла тема" if dark else "Темна тема")
        for mode, action in getattr(self, "_theme_actions", {}).items():
            action.setChecked(mode == self._settings.theme_mode)
        for key, action in getattr(self, "_accent_actions", {}).items():
            action.setChecked(key == self._settings.accent)
        self._refresh_icons()
        self._view.refresh_theme()
        self._panel_key = None  # інспектор перебудується з новими кольорами
        self._full_sync()

    def _on_system_scheme_changed(self, *_args) -> None:
        if self._settings.theme_mode == "system":
            self._apply_appearance()

    def _refresh_icons(self) -> None:
        for button in self.findChildren(QToolButton):
            name = button.property("icon_name")
            if name and not self._layers.isAncestorOf(button):  # іконки панелі шарів — окремо, іншим кольором
                button.setIcon(line_icon(name, theme.TEXT))
        self._layers.refresh_icons()

    # ------------------------------------------------------------------ #
    # Буфер обміну та замок
    # ------------------------------------------------------------------ #

    def _copy_selected(self) -> None:
        if not self._selected:
            return
        layer = self._doc.layer(self._selected)
        mime = QMimeData()
        mime.setData(CLIPBOARD_MIME, layer_to_clipboard(layer, self._doc))
        QApplication.clipboard().setMimeData(mime)
        self._toast.show_message(f"Скопійовано: {layer.label or layer.id}", "info")

    def _paste(self) -> None:
        mime = QApplication.clipboard().mimeData()
        if mime is None or not mime.hasFormat(CLIPBOARD_MIME):
            self._toast.show_message("У буфері немає шару — спершу скопіюйте його (Ctrl+C)", "info")
            return
        try:
            self._doc.add_layer(paste_payload(bytes(mime.data(CLIPBOARD_MIME)), self._doc))
        except CertificateError as exc:
            self._show_error(str(exc))

    def _toggle_lock(self, layer_id: str | None = None, locked: bool | None = None) -> None:
        layer_id = layer_id or self._selected
        if not layer_id:
            return
        layer = self._doc.layer(layer_id)
        target = (not layer.locked) if locked is None else locked
        self._safely(lambda: self._doc.update_layer(layer_id, {"locked": target}))
        name = layer.label or layer.id
        self._toast.show_message(f"{'Заблоковано' if target else 'Розблоковано'}: {name}", "info")

    def _move_layer(self, layer_id: str, dx: int, dy: int) -> None:
        if self._doc.layer(layer_id).locked:
            self._toast.show_message("Шар заблоковано — Ctrl+L, щоб розблокувати", "info")
            return
        self._safely(lambda: self._doc.move_layer_by(layer_id, dx, dy))

    # ------------------------------------------------------------------ #
    # Перетягування файлів на полотно
    # ------------------------------------------------------------------ #

    def _on_files_dropped(self, paths: list[str], scene_pos: QPointF, as_background: bool) -> None:
        tables = [p for p in paths if Path(p).suffix.lower() in {".csv", ".tsv"}]
        if tables:
            BatchDialog(self._doc, self._templates_root.parent, self, initial_source=tables[0]).exec()
            return
        images = [Path(p) for p in paths if Path(p).suffix.lower() in IMAGE_SUFFIXES]
        if not images:
            return
        try:
            if as_background:
                self._doc.update_canvas({"background_image": self._import_background(images[0])})
                self._show_background_settings()
                self._toast.show_message("Фон оновлено", "success", "Скасувати", self._doc.undo)
                return
            for offset, image in enumerate(images):
                shift = offset * 40
                payload = picture_payload_from_file(
                    "image", self._doc, image, round(scene_pos.x()) + shift, round(scene_pos.y()) + shift
                )
                self._doc.add_layer(payload | {"label": image.stem[:60]})
        except CertificateError as exc:
            self._show_error(str(exc))
            return
        count = len(images)
        self._toast.show_message(
            f"Додано зображень: {count}. Утримуйте Shift під час перетягування, щоб зробити фоном.", "success"
        )

    def _import_background(self, path: Path) -> str:
        return import_asset(self._doc.template_dir, path, "assets")

    # ------------------------------------------------------------------ #
    # Шаблони та налаштування
    # ------------------------------------------------------------------ #

    def _new_template(self) -> None:
        if not self._confirm_discard():
            return
        dialog = NewTemplateDialog(self._templates_root, self._fonts_source(), self)
        if not dialog.exec() or dialog.created_dir is None:
            return
        folder = dialog.created_dir.name
        self._template_box.blockSignals(True)
        self._template_box.addItem(self._template_title(folder), folder)
        self._template_box.setCurrentIndex(self._template_box.count() - 1)
        self._template_box.blockSignals(False)
        self._selected = None
        self._safely(lambda: self._doc.load(dialog.created_dir))
        self._view.fit_page()
        self._toast.show_message(f"Створено шаблон «{self._doc.config.name}»", "success")

    def _fonts_source(self) -> Path:
        """Шрифти для нового шаблону: з комплектного шаблону (там є і серифні), інакше — з поточного."""
        bundled = self._templates_root / BUNDLED_TEMPLATE / "fonts"
        return bundled if bundled.is_dir() else self._doc.template_dir / "fonts"

    def _open_canvas_size(self) -> None:
        dialog = CanvasSizeDialog(self._doc, self)
        if not dialog.exec():
            return
        try:
            if dialog.dpi != self._doc.config.output.dpi:
                self._doc.update_output({"dpi": dialog.dpi})
            self._doc.resize_canvas(dialog.width, dialog.height, dialog.scale_content)
        except CertificateError as exc:
            self._show_error(str(exc))
            return
        self._view.fit_page()
        self._toast.show_message(f"Розмір полотна: {dialog.width} × {dialog.height} px", "success")

    def _remember_session(self) -> None:
        self._settings = updated(
            self._settings, geometry=self.saveGeometry(), last_template=self._doc.template_dir.name
        )
        save_settings(self._settings)
