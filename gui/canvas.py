"""Полотно редактора: сторінка сертифіката та шари, що перетягуються й масштабуються мишею."""

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPainterPath, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QStyle,
    QStyleOptionGraphicsItem,
)

from gui import theme

SNAP_DISTANCE_PX = 7
SELECTION_PEN_PX = 2.0
HANDLE_PX = 9
HANDLE_HIT_PX = 12
MIN_RESIZE_FACTOR = 0.05
NUDGE_SMALL, NUDGE_LARGE = 1, 10
ZOOM_STEP = 1.15
MIN_ZOOM, MAX_ZOOM = 0.05, 4.0
PAGE_MARGIN_PX = 48
GUIDE_COLOR = "#FF2D55"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
DROPPABLE_SUFFIXES = IMAGE_SUFFIXES | {".csv", ".tsv"}

# Кути: 0 — лівий верхній, 1 — правий верхній, 2 — лівий нижній, 3 — правий нижній.
_OPPOSITE = {0: 3, 1: 2, 2: 1, 3: 0}
_CURSORS = {
    0: Qt.CursorShape.SizeFDiagCursor,
    3: Qt.CursorShape.SizeFDiagCursor,
    1: Qt.CursorShape.SizeBDiagCursor,
    2: Qt.CursorShape.SizeBDiagCursor,
}


def _corners(rect: QRectF) -> tuple[QPointF, QPointF, QPointF, QPointF]:
    return rect.topLeft(), rect.topRight(), rect.bottomLeft(), rect.bottomRight()


@dataclass(frozen=True)
class _ResizeState:
    anchor_scene: QPointF
    anchor_item: QPointF
    start_rect: QRectF  # у координатах сцени


class LayerItem(QGraphicsPixmapItem):
    def __init__(self, layer_id: str, scene: "CertificateScene") -> None:
        super().__init__()
        self.layer_id = layer_id
        self._scene_ref = scene
        self._press_pos: QPointF | None = None
        self._resize: _ResizeState | None = None
        self._hovered = False
        self.locked = False
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    # ------------------------------------------------------------------ #
    # Малювання
    # ------------------------------------------------------------------ #

    def content_rect(self) -> QRectF:
        return QRectF(self.pixmap().rect())

    def boundingRect(self) -> QRectF:  # noqa: N802 — Qt API
        pad = HANDLE_HIT_PX / self._scene_ref.view_scale
        return self.content_rect().adjusted(-pad, -pad, pad, pad)

    def shape(self) -> QPainterPath:
        # Клік по всьому прямокутнику шару, а не лише по непрозорих пікселях —
        # інакше по тонкому тексту чи напівпрозорому водяному знаку важко влучити.
        path = QPainterPath()
        path.addRect(self.boundingRect() if self.isSelected() else self.content_rect())
        return path

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None) -> None:
        clean = QStyleOptionGraphicsItem(option)
        clean.state &= ~QStyle.StateFlag.State_Selected  # власна рамка замість пунктиру Qt
        super().paint(painter, clean, widget)
        if not (self.isSelected() or self._hovered):
            return

        scale = (painter.transform().m11() or 1.0)
        rect = self.content_rect()
        accent = QColor(theme.ACCENT)
        if not self.isSelected():
            accent.setAlpha(150)
        pen = QPen(accent, (SELECTION_PEN_PX if self.isSelected() else 1.0) / scale)
        if self.locked:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)
        if not self.isSelected() or self.locked:
            return
        handle = HANDLE_PX / scale
        painter.setBrush(QColor("white"))
        painter.setPen(QPen(QColor(theme.ACCENT), 1.5 / scale))
        for corner in _corners(rect):
            painter.drawRoundedRect(
                QRectF(corner.x() - handle / 2, corner.y() - handle / 2, handle, handle), handle / 4, handle / 4
            )

    # ------------------------------------------------------------------ #
    # Взаємодія
    # ------------------------------------------------------------------ #

    def set_locked(self, locked: bool) -> None:
        self.locked = locked
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not locked)
        self.setCursor(Qt.CursorShape.ArrowCursor if locked else Qt.CursorShape.OpenHandCursor)

    def _handle_at(self, item_pos: QPointF) -> int | None:
        if not self.isSelected() or self.locked:
            return None
        tolerance = HANDLE_HIT_PX / self._scene_ref.view_scale
        for index, corner in enumerate(_corners(self.content_rect())):
            if abs(item_pos.x() - corner.x()) <= tolerance and abs(item_pos.y() - corner.y()) <= tolerance:
                return index
        return None

    def hoverEnterEvent(self, event) -> None:  # noqa: N802 — Qt API
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverMoveEvent(self, event) -> None:  # noqa: N802 — Qt API
        handle = self._handle_at(event.pos())
        idle = Qt.CursorShape.ArrowCursor if self.locked else Qt.CursorShape.OpenHandCursor
        self.setCursor(_CURSORS[handle] if handle is not None else idle)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event) -> None:  # noqa: N802 — Qt API
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 — Qt API
        handle = self._handle_at(event.pos()) if event.button() == Qt.MouseButton.LeftButton else None
        if handle is not None:
            anchor_item = _corners(self.content_rect())[_OPPOSITE[handle]]
            self._resize = _ResizeState(
                anchor_scene=self.mapToScene(anchor_item),
                anchor_item=anchor_item,
                start_rect=self.mapRectToScene(self.content_rect()),
            )
            self.setTransformOriginPoint(anchor_item)
            event.accept()
            return
        self._press_pos = None if self.locked else self.pos()
        if not self.locked:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 — Qt API
        if self._resize is None:
            super().mouseMoveEvent(event)
            return
        state, point = self._resize, event.scenePos()
        width = abs(point.x() - state.anchor_scene.x()) / max(1.0, state.start_rect.width())
        height = abs(point.y() - state.anchor_scene.y()) / max(1.0, state.start_rect.height())
        self.setScale(max(MIN_RESIZE_FACTOR, width, height))
        self._scene_ref.show_size_hint(self)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 — Qt API
        if self._resize is not None:
            self._finish_resize()
            return
        super().mouseReleaseEvent(event)
        self.setCursor(Qt.CursorShape.ArrowCursor if self.locked else Qt.CursorShape.OpenHandCursor)
        self._scene_ref.hide_guides()
        if self._press_pos is None:
            return
        delta = self.pos() - self._press_pos
        self._press_pos = None
        dx, dy = round(delta.x()), round(delta.y())
        if dx or dy:
            self._scene_ref.layer_moved.emit(self.layer_id, dx, dy)

    def _finish_resize(self) -> None:
        state, factor = self._resize, self.scale()
        self._resize = None
        self.setScale(1.0)
        self._scene_ref.hide_guides()
        if abs(factor - 1.0) < 0.005:
            return
        anchor, rect = state.anchor_scene, state.start_rect
        left = anchor.x() + (rect.left() - anchor.x()) * factor
        top = anchor.y() + (rect.top() - anchor.y()) * factor
        self._scene_ref.layer_resized.emit(self.layer_id, factor, round(left), round(top))

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 — Qt API
        self._scene_ref.layer_activated.emit(self.layer_id)
        event.accept()

    def itemChange(self, change, value):  # noqa: N802 — Qt API
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self._press_pos is not None:
            return self._scene_ref.snap(self, value)
        return super().itemChange(change, value)


class CertificateScene(QGraphicsScene):
    layer_moved = Signal(str, int, int)
    layer_resized = Signal(str, float, int, int)  # id, множник, новий лівий-верхній кут
    layer_activated = Signal(str)
    layer_selected = Signal(object)  # str | None

    def __init__(self) -> None:
        super().__init__()
        self._page = QGraphicsPixmapItem()
        self._page.setZValue(-1000)
        self._page.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._shadow = QGraphicsDropShadowEffect()
        self._shadow.setBlurRadius(60)
        self._shadow.setOffset(0, 12)
        self._page.setGraphicsEffect(self._shadow)
        self.addItem(self._page)
        self._items: dict[str, LayerItem] = {}
        self.view_scale = 1.0

        guide_pen = QPen(QColor(GUIDE_COLOR), 0)
        guide_pen.setCosmetic(True)
        self._v_guide = QGraphicsLineItem()
        self._h_guide = QGraphicsLineItem()
        for guide in (self._v_guide, self._h_guide):
            guide.setPen(guide_pen)
            guide.setZValue(10_000)
            guide.hide()
            self.addItem(guide)

        self.selectionChanged.connect(self._emit_selection)

    def refresh_theme(self) -> None:
        # У темній темі тінь сильніша, інакше сторінка зливається з фоном.
        self._shadow.setColor(QColor(0, 0, 0, 140 if theme.palette().is_dark else 55))
        self.update()

    @property
    def page_rect(self) -> QRectF:
        return self._page.boundingRect()

    @property
    def page_item(self) -> QGraphicsPixmapItem:
        return self._page

    def layer_rect(self, layer_id: str) -> QRectF | None:
        item = self._items.get(layer_id)
        return item.mapRectToScene(item.content_rect()) if item else None

    def set_view_scale(self, scale: float) -> None:
        self.view_scale = scale or 1.0
        for item in self._items.values():
            item.prepareGeometryChange()

    def set_page(self, pixmap: QPixmap) -> None:
        self._page.setPixmap(pixmap)
        margin = PAGE_MARGIN_PX * 40
        self.setSceneRect(self.page_rect.adjusted(-margin, -margin, margin, margin))

    def upsert_layer(
        self,
        layer_id: str,
        pixmap: QPixmap,
        x: int,
        y: int,
        z: int,
        visible: bool,
        tooltip: str,
        locked: bool = False,
    ) -> None:
        item = self._items.get(layer_id)
        if item is None:
            item = LayerItem(layer_id, self)
            self._items[layer_id] = item
            self.addItem(item)
        item.prepareGeometryChange()
        item.setPixmap(pixmap)
        item.setPos(x, y)
        item.setZValue(z)
        item.setVisible(visible)
        item.setToolTip(tooltip)
        item.set_locked(locked)

    def retain_layers(self, layer_ids: set[str]) -> None:
        for layer_id in set(self._items) - layer_ids:
            self.removeItem(self._items.pop(layer_id))

    def select_layer(self, layer_id: str | None) -> None:
        self.blockSignals(True)
        self.clearSelection()
        item = self._items.get(layer_id) if layer_id else None
        if item is not None:
            item.setSelected(True)
        self.blockSignals(False)

    def selected_layer(self) -> str | None:
        selected = [item for item in self.selectedItems() if isinstance(item, LayerItem)]
        return selected[0].layer_id if selected else None

    # ------------------------------------------------------------------ #
    # Розумні напрямні
    # ------------------------------------------------------------------ #

    def snap(self, item: LayerItem, proposed: QPointF) -> QPointF:
        """Прилипання країв і центру шару до країв/центру сторінки та інших шарів."""
        threshold = SNAP_DISTANCE_PX / self.view_scale
        rect = item.content_rect()
        others = [
            other.mapRectToScene(other.content_rect())
            for other in self._items.values()
            if other is not item and other.isVisible()
        ]
        targets = [self.page_rect] + others
        x_targets = [value for r in targets for value in (r.left(), r.center().x(), r.right())]
        y_targets = [value for r in targets for value in (r.top(), r.center().y(), r.bottom())]

        own_x = (0.0, rect.width() / 2, rect.width())
        own_y = (0.0, rect.height() / 2, rect.height())
        dx, guide_x = _best_snap([proposed.x() + offset for offset in own_x], x_targets, threshold)
        dy, guide_y = _best_snap([proposed.y() + offset for offset in own_y], y_targets, threshold)

        page = self.page_rect
        self._show_guide(self._v_guide, guide_x, lambda v: (v, page.top(), v, page.bottom()))
        self._show_guide(self._h_guide, guide_y, lambda v: (page.left(), v, page.right(), v))
        return QPointF(round(proposed.x() + dx), round(proposed.y() + dy))

    def show_size_hint(self, item: LayerItem) -> None:
        """Під час масштабування показує напрямні по краях нового розміру."""
        rect = item.mapRectToScene(item.content_rect())
        page = self.page_rect
        self._show_guide(self._v_guide, rect.right(), lambda v: (v, page.top(), v, page.bottom()))
        self._show_guide(self._h_guide, rect.bottom(), lambda v: (page.left(), v, page.right(), v))

    @staticmethod
    def _show_guide(guide: QGraphicsLineItem, value: float | None, line) -> None:
        if value is None:
            guide.hide()
            return
        guide.setLine(*line(value))
        guide.show()

    def hide_guides(self) -> None:
        self._v_guide.hide()
        self._h_guide.hide()

    def _emit_selection(self) -> None:
        self.layer_selected.emit(self.selected_layer())


def _best_snap(edges: list[float], targets: list[float], threshold: float) -> tuple[float, float | None]:
    """Найменший зсув, що суміщає будь-який край/центр з будь-якою ціллю; (0, None) — без прилипання."""
    best_delta, best_target = 0.0, None
    for edge in edges:
        for target in targets:
            delta = target - edge
            if abs(delta) < threshold and (best_target is None or abs(delta) < abs(best_delta)):
                best_delta, best_target = delta, target
    return best_delta, best_target


class CanvasView(QGraphicsView):
    zoom_changed = Signal(float)
    context_menu_requested = Signal(QPoint)
    files_dropped = Signal(list, QPointF, bool)  # шляхи, точка на сцені, затиснутий Shift

    def __init__(self, scene: CertificateScene) -> None:
        super().__init__(scene)
        self._scene = scene
        self._fit_mode = True
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
            | QPainter.RenderHint.TextAntialiasing
        )
        self.refresh_theme()
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._pan_anchor: QPointF | None = None
        self._space_held = False
        self.setAcceptDrops(True)

    def refresh_theme(self) -> None:
        self.setBackgroundBrush(QColor(theme.CANVAS))
        self._scene.refresh_theme()

    @property
    def zoom(self) -> float:
        return self.transform().m11()

    def fit_page(self) -> None:
        self._fit_mode = True
        page = self._scene.page_rect
        if page.isEmpty():
            return
        margin = PAGE_MARGIN_PX
        available_w = max(1, self.viewport().width() - 2 * margin)
        available_h = max(1, self.viewport().height() - 2 * margin)
        scale = min(available_w / page.width(), available_h / page.height())
        self._apply_zoom(scale)
        self.centerOn(page.center())

    def zoom_by(self, factor: float) -> None:
        self._fit_mode = False
        self._apply_zoom(self.zoom * factor)

    def _apply_zoom(self, scale: float) -> None:
        scale = max(MIN_ZOOM, min(MAX_ZOOM, scale))
        self.resetTransform()
        self.scale(scale, scale)
        self._scene.set_view_scale(scale)
        self.zoom_changed.emit(scale)

    def resizeEvent(self, event) -> None:  # noqa: N802 — Qt API
        super().resizeEvent(event)
        if self._fit_mode:
            self.fit_page()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 — Qt API
        if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
            self.zoom_by(ZOOM_STEP if event.angleDelta().y() > 0 else 1 / ZOOM_STEP)
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 — Qt API
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = True
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            return
        layer_id = self._scene.selected_layer()
        step = NUDGE_LARGE if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else NUDGE_SMALL
        moves = {
            Qt.Key.Key_Left: (-step, 0),
            Qt.Key.Key_Right: (step, 0),
            Qt.Key.Key_Up: (0, -step),
            Qt.Key.Key_Down: (0, step),
        }
        if layer_id and event.key() in moves:
            self._scene.layer_moved.emit(layer_id, *moves[event.key()])
            return
        if layer_id and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._scene.layer_activated.emit(layer_id)
            return
        if event.key() == Qt.Key.Key_Escape:
            self._scene.clearSelection()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------ #
    # Перетягування файлів із файлового менеджера
    # ------------------------------------------------------------------ #

    @staticmethod
    def _dropped_paths(event) -> list[str]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        return [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]

    def dragEnterEvent(self, event) -> None:  # noqa: N802 — Qt API
        if any(Path(path).suffix.lower() in DROPPABLE_SUFFIXES for path in self._dropped_paths(event)):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 — Qt API
        event.acceptProposedAction()  # не віддаємо подію шарам — вони файлів не приймають

    def dropEvent(self, event) -> None:  # noqa: N802 — Qt API
        paths = [p for p in self._dropped_paths(event) if Path(p).suffix.lower() in DROPPABLE_SUFFIXES]
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        self.files_dropped.emit(paths, self.mapToScene(event.position().toPoint()), shift)

    def contextMenuEvent(self, event) -> None:  # noqa: N802 — Qt API
        item = self.itemAt(event.pos())
        if isinstance(item, LayerItem):
            self._scene.clearSelection()
            item.setSelected(True)
            self.context_menu_requested.emit(event.globalPos())

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # noqa: N802 — Qt API
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = False
            self.viewport().unsetCursor()
            return
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 — Qt API
        self.setFocus()
        # Панорамування: середня кнопка або затиснутий пробіл.
        if event.button() == Qt.MouseButton.MiddleButton or self._space_held:
            self._fit_mode = False
            self._pan_anchor = event.position()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if self.itemAt(event.position().toPoint()) in (None, self._scene.page_item):
            self._scene.clearSelection()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 — Qt API
        if self._pan_anchor is not None:
            delta = event.position() - self._pan_anchor
            self._pan_anchor = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - round(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - round(delta.y()))
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 — Qt API
        if self._pan_anchor is not None:
            self._pan_anchor = None
            if self._space_held:
                self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.viewport().unsetCursor()
            return
        super().mouseReleaseEvent(event)
