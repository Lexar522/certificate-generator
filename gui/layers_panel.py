"""Ліва панель: список шарів (верхній — найближчий до глядача) та дії над ними."""

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gui import theme
from gui.qt_utils import TYPE_NAMES, line_icon, type_icon
from renderers.pillow_renderer import AnyLayer

ROW_HEIGHT = 46
ADD_ORDER = ("text", "image", "watermark", "qr")
SUBTITLE_MAX_CHARS = 27
NAME_MAX_CHARS = 21


class _LayerRow(QWidget):
    def __init__(self, layer: AnyLayer, subtitle: str, on_toggle) -> None:
        super().__init__()
        self.setToolTip(f"{layer.label or layer.id}\n{subtitle}")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 6, 4)
        layout.setSpacing(10)

        icon = QLabel()
        icon.setPixmap(type_icon(layer.type).pixmap(QSize(26, 26)))
        icon.setEnabled(layer.visible)  # прихований шар — приглушена іконка
        layout.addWidget(icon)

        text_box = QVBoxLayout()
        text_box.setSpacing(1)
        full_name = layer.label or TYPE_NAMES.get(layer.type, layer.id)
        name = QLabel(_elide(full_name, NAME_MAX_CHARS))
        muted = "" if layer.visible else f"color: {theme.TEXT_TERTIARY};"
        name.setStyleSheet(f"font-weight: 600; {muted}")
        detail = QLabel(_elide(subtitle, SUBTITLE_MAX_CHARS))
        detail.setObjectName("Hint")
        text_box.addWidget(name)
        text_box.addWidget(detail)
        layout.addLayout(text_box, 1)

        eye = QToolButton()
        eye.setObjectName("Ghost")
        eye.setIcon(line_icon("eye" if layer.visible else "eye-off"))
        eye.setToolTip("Сховати" if layer.visible else "Показати")
        eye.setCursor(Qt.CursorShape.PointingHandCursor)
        eye.clicked.connect(lambda: on_toggle(layer.id, not layer.visible))
        layout.addWidget(eye)


class _ReorderList(QListWidget):
    """Список із перетягуванням рядків; після скидання повідомляє новий порядок id."""

    order_changed = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragEnabled(True)

    def dropEvent(self, event) -> None:  # noqa: N802 — Qt API
        super().dropEvent(event)
        ids = [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]
        # Відкладено: обробник перебудовує список, а ми ще всередині події самого списку.
        QTimer.singleShot(0, lambda: self.order_changed.emit(ids))


class LayersPanel(QWidget):
    layer_selected = Signal(object)  # str | None
    visibility_toggled = Signal(str, bool)
    add_requested = Signal(str)
    remove_requested = Signal()
    duplicate_requested = Signal()
    reorder_requested = Signal(int)
    order_changed = Signal(list)  # id згори донизу, як у списку
    context_menu_requested = Signal(QPoint)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 14, 10, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("ШАРИ")
        title.setObjectName("SectionTitle")
        self._count = QLabel()
        self._count.setObjectName("Hint")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self._count)
        layout.addLayout(header)

        self._list = _ReorderList()
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.currentItemChanged.connect(self._on_current_changed)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        self._list.order_changed.connect(self.order_changed)
        layout.addWidget(self._list, 1)

        hint = QLabel("Перетягніть рядок, щоб змінити порядок")
        hint.setObjectName("Hint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)
        layout.addWidget(self._build_toolbar())

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)

        add = self._tool("plus", "Додати шар")
        add.setText("Додати")
        add.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        menu = QMenu(add)
        for kind in ADD_ORDER:
            action = menu.addAction(type_icon(kind), TYPE_NAMES[kind])
            action.triggered.connect(lambda _=False, k=kind: self.add_requested.emit(k))
        add.setMenu(menu)
        add.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        row.addWidget(add)
        row.addStretch(1)

        self._up = self._tool("up", "Підняти вище")
        self._up.clicked.connect(lambda: self.reorder_requested.emit(1))
        self._down = self._tool("down", "Опустити нижче")
        self._down.clicked.connect(lambda: self.reorder_requested.emit(-1))
        self._duplicate = self._tool("duplicate", "Дублювати (Ctrl+D)")
        self._duplicate.clicked.connect(self.duplicate_requested.emit)
        self._remove = self._tool("minus", "Видалити шар (Delete)")
        self._remove.clicked.connect(self.remove_requested.emit)
        for button in (self._up, self._down, self._duplicate, self._remove):
            row.addWidget(button)
        return bar

    @staticmethod
    def _tool(icon: str, tooltip: str) -> QToolButton:
        button = QToolButton()
        button.setObjectName("Ghost")
        button.setIcon(line_icon(icon))
        button.setIconSize(QSize(18, 18))
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def set_layers(self, layers: tuple[AnyLayer, ...], subtitles: dict[str, str], selected: str | None) -> None:
        scroll = self._list.verticalScrollBar().value()
        self._list.blockSignals(True)
        self._list.clear()
        for layer in reversed(layers):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, layer.id)
            item.setSizeHint(QSize(0, ROW_HEIGHT))
            self._list.addItem(item)
            row = _LayerRow(layer, subtitles.get(layer.id, ""), self.visibility_toggled.emit)
            self._list.setItemWidget(item, row)
            if layer.id == selected:
                self._list.setCurrentItem(item)
        self._list.blockSignals(False)
        self._list.verticalScrollBar().setValue(scroll)
        self._count.setText(str(len(layers)))
        self._update_buttons(selected)

    def select(self, layer_id: str | None) -> None:
        self._list.blockSignals(True)
        self._list.setCurrentItem(None)
        for index in range(self._list.count()):
            item = self._list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == layer_id:
                self._list.setCurrentItem(item)
                self._list.scrollToItem(item)
        self._list.blockSignals(False)
        self._update_buttons(layer_id)

    def _on_current_changed(self, current: QListWidgetItem | None, _previous) -> None:
        layer_id = current.data(Qt.ItemDataRole.UserRole) if current else None
        self._update_buttons(layer_id)
        self.layer_selected.emit(layer_id)

    def _on_context_menu(self, pos: QPoint) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return
        self._list.setCurrentItem(item)
        self.context_menu_requested.emit(self._list.viewport().mapToGlobal(pos))

    def _update_buttons(self, layer_id: str | None) -> None:
        for button in (self._remove, self._up, self._down, self._duplicate):
            button.setEnabled(layer_id is not None)


def _elide(text: str, limit: int) -> str:
    single_line = " ".join(text.split())
    return single_line if len(single_line) <= limit else single_line[: limit - 1] + "…"
