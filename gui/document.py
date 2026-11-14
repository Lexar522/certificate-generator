"""Модель документа редактора: шаблон + значення полів, з undo/redo.

Без залежностей від Qt — логіку редагування можна тестувати окремо.
Кожна зміна створює новий незмінний знімок стану; історія — це список знімків.
"""

import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from core.exceptions import CertificateError
from core.models import (
    CanvasConfig,
    CertificateData,
    ImageLayer,
    OutputConfig,
    QrLayer,
    TemplateConfig,
    TextLayer,
    WatermarkLayer,
)
from core.template_catalog import describe_inputs
from core.template_loader import load_template_config
from core.template_store import save_config
from renderers.pillow_renderer import AnyLayer

ChangeKind = Literal["reset", "structure", "layer", "canvas", "data"]
Listener = Callable[[ChangeKind, str | None], None]

HISTORY_LIMIT = 200
MERGE_WINDOW_SECONDS = 1.5
DUPLICATE_OFFSET = 40
LAYER_TYPES: dict[str, type[BaseModel]] = {
    "watermark": WatermarkLayer,
    "image": ImageLayer,
    "text": TextLayer,
    "qr": QrLayer,
}


@dataclass(frozen=True)
class DocState:
    config: TemplateConfig
    field_values: dict[str, str] = field(default_factory=dict)
    image_values: dict[str, str] = field(default_factory=dict)
    certificate_id: str = ""
    issue_date: date = field(default_factory=date.today)


@dataclass(frozen=True)
class _HistoryEntry:
    state: DocState
    merge_key: str | None
    timestamp: float


def new_certificate_id(issue_date: date) -> str:
    return f"CERT-{issue_date:%Y%m%d}-{secrets.token_hex(3).upper()}"


class EditorDocument:
    def __init__(self, template_dir: Path) -> None:
        self._listeners: list[Listener] = []
        self._template_dir = template_dir
        self._state = self._initial_state(template_dir)
        self._undo: list[_HistoryEntry] = []
        self._redo: list[DocState] = []
        self._saved_config = self._state.config

    # ------------------------------------------------------------------ #
    # Доступ до стану
    # ------------------------------------------------------------------ #

    @property
    def template_dir(self) -> Path:
        return self._template_dir

    @property
    def state(self) -> DocState:
        return self._state

    @property
    def config(self) -> TemplateConfig:
        return self._state.config

    @property
    def is_dirty(self) -> bool:
        return self._state.config != self._saved_config

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def layer(self, layer_id: str) -> AnyLayer:
        return self.config.layers[self._index(layer_id)]

    def has_layer(self, layer_id: str | None) -> bool:
        return any(layer.id == layer_id for layer in self.config.layers)

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    # ------------------------------------------------------------------ #
    # Завантаження / збереження
    # ------------------------------------------------------------------ #

    def load(self, template_dir: Path) -> None:
        state = self._initial_state(template_dir)
        self._template_dir = template_dir
        self._state = state
        self._undo, self._redo = [], []
        self._saved_config = state.config
        self._emit("reset", None)

    def save(self) -> Path:
        path = save_config(self._template_dir, self.config)
        self._saved_config = self.config
        return path

    @staticmethod
    def _initial_state(template_dir: Path) -> DocState:
        config = load_template_config(template_dir)
        today = date.today()
        return DocState(config=config, certificate_id=new_certificate_id(today), issue_date=today)

    # ------------------------------------------------------------------ #
    # Редагування шарів
    # ------------------------------------------------------------------ #

    def update_layer(
        self, layer_id: str, changes: dict[str, Any], merge_key: str | None = None
    ) -> None:
        current = self.layer(layer_id)
        updated = _validated(type(current), current.model_dump() | changes)
        state = replace(self._state, config=self._replace_layer(updated))
        self._commit(state, "layer", layer_id, merge_key)

    def move_layer_by(self, layer_id: str, dx: int, dy: int) -> None:
        if dx or dy:
            layer = self.layer(layer_id)
            self.update_layer(layer_id, {"x": layer.x + dx, "y": layer.y + dy})

    def add_layer(self, payload: dict[str, Any]) -> str:
        layer_type = LAYER_TYPES.get(payload.get("type", ""))
        if layer_type is None:
            raise CertificateError(f"Невідомий тип шару: {payload.get('type')}")
        layer_id = self._unique_id(payload["type"])
        layer = _validated(layer_type, payload | {"id": layer_id})
        state = replace(self._state, config=self._with_layers(self.config.layers + (layer,)))
        self._commit(state, "structure", layer_id)
        return layer_id

    def duplicate_layer(self, layer_id: str) -> str:
        source = self.layer(layer_id)
        new_id = self._unique_id(source.type)
        payload = source.model_dump() | {
            "id": new_id,
            "x": source.x + DUPLICATE_OFFSET,
            "y": source.y + DUPLICATE_OFFSET,
        }
        copy = _validated(type(source), payload)
        index = self._index(layer_id)
        layers = self.config.layers[: index + 1] + (copy,) + self.config.layers[index + 1 :]

        field_values = self._state.field_values
        if layer_id in field_values:
            field_values = field_values | {new_id: field_values[layer_id]}
        image_values = self._state.image_values
        if layer_id in image_values:
            image_values = image_values | {new_id: image_values[layer_id]}

        state = replace(
            self._state,
            config=self._with_layers(layers),
            field_values=field_values,
            image_values=image_values,
        )
        self._commit(state, "structure", new_id)
        return new_id

    def remove_layer(self, layer_id: str) -> None:
        layers = tuple(layer for layer in self.config.layers if layer.id != layer_id)
        if not layers:
            raise CertificateError("У шаблоні має лишитися хоча б один шар")
        self._commit(replace(self._state, config=self._with_layers(layers)), "structure", None)

    def reorder_layer(self, layer_id: str, step: int) -> None:
        """step > 0 — вище (ближче до глядача), step < 0 — нижче."""
        index = self._index(layer_id)
        target = max(0, min(len(self.config.layers) - 1, index + step))
        if target == index:
            return
        layers = list(self.config.layers)
        layers.insert(target, layers.pop(index))
        state = replace(self._state, config=self._with_layers(tuple(layers)))
        self._commit(state, "structure", layer_id)

    def set_layer_order(self, layer_ids: list[str]) -> None:
        """Новий порядок шарів знизу вгору (як у config.json); має містити ті самі id."""
        by_id = {layer.id: layer for layer in self.config.layers}
        if sorted(layer_ids) != sorted(by_id):
            raise CertificateError("Новий порядок не збігається зі складом шарів")
        layers = tuple(by_id[layer_id] for layer_id in layer_ids)
        self._commit(replace(self._state, config=self._with_layers(layers)), "structure", None)

    def set_text_mode(self, layer_id: str, dynamic: bool) -> None:
        """Перемикає текстовий шар між статичним текстом і змінним полем, зберігаючи вміст."""
        layer = self.layer(layer_id)
        if not isinstance(layer, TextLayer) or (layer.text is None) == dynamic:
            return
        values = self._state.field_values
        if dynamic:
            changes = {"text": None, "label": layer.label or layer.id}
            values = values | {layer_id: layer.text or ""} if layer.text else values
        else:
            changes = {"text": values.get(layer_id) or layer.label or layer.id, "required": False}
            values = {key: value for key, value in values.items() if key != layer_id}
        updated = _validated(TextLayer, layer.model_dump() | changes)
        state = replace(self._state, config=self._replace_layer(updated), field_values=values)
        self._commit(state, "layer", layer_id)

    def set_image_mode(self, layer_id: str, dynamic: bool, static_path: str | None = None) -> None:
        """Змінне зображення (підставляється при генерації) або файл шаблону."""
        layer = self.layer(layer_id)
        if not isinstance(layer, ImageLayer):
            return
        if not dynamic and static_path is None:
            raise CertificateError("Оберіть файл зображення для шаблону")
        changes = {"path": None} if dynamic else {"path": static_path, "required": False}
        self.update_layer(layer_id, changes)

    # ------------------------------------------------------------------ #
    # Полотно та дані
    # ------------------------------------------------------------------ #

    def update_canvas(self, changes: dict[str, Any], merge_key: str | None = None) -> None:
        canvas = _validated(CanvasConfig, self.config.canvas.model_dump() | changes)
        config = self.config.model_copy(update={"canvas": canvas})
        self._commit(replace(self._state, config=config), "canvas", None, merge_key)

    def update_output(self, changes: dict[str, Any]) -> None:
        output = _validated(OutputConfig, self.config.output.model_dump() | changes)
        config = self.config.model_copy(update={"output": output})
        self._commit(replace(self._state, config=config), "data", None, "output")

    def set_date_format(self, date_format: str) -> None:
        if not date_format.strip():
            raise CertificateError("Формат дати не може бути порожнім")
        config = self.config.model_copy(update={"date_format": date_format})
        self._commit(replace(self._state, config=config), "data", None, "date_format")

    def set_field_value(self, layer_id: str, value: str) -> None:
        values = {key: text for key, text in self._state.field_values.items() if key != layer_id}
        if value.strip():
            values = values | {layer_id: value}
        state = replace(self._state, field_values=values)
        self._commit(state, "layer", layer_id, f"field:{layer_id}")

    def set_image_value(self, layer_id: str, path: str | None) -> None:
        values = {key: item for key, item in self._state.image_values.items() if key != layer_id}
        if path:
            values = values | {layer_id: path}
        self._commit(replace(self._state, image_values=values), "layer", layer_id)

    def set_certificate_id(self, certificate_id: str) -> None:
        state = replace(self._state, certificate_id=certificate_id.strip())
        self._commit(state, "data", None, "certificate_id")

    def set_issue_date(self, issue_date: date) -> None:
        self._commit(replace(self._state, issue_date=issue_date), "data", None, "issue_date")

    # ------------------------------------------------------------------ #
    # Дані для рендеру
    # ------------------------------------------------------------------ #

    def preview_data(self) -> CertificateData:
        """Дані для перегляду: порожні змінні текстові поля показуються як «Назва поля»."""
        placeholders = {
            field.id: f"«{field.label}»" for field in describe_inputs(self.config).text_fields
        }
        try:
            return self._build_data(placeholders | self._state.field_values, self._state.certificate_id)
        except CertificateError:
            return self._build_data(placeholders | self._state.field_values, "PREVIEW")

    def export_data(self) -> CertificateData:
        return self._build_data(dict(self._state.field_values), self._state.certificate_id)

    def _build_data(self, fields: dict[str, str], certificate_id: str) -> CertificateData:
        try:
            return CertificateData(
                template_name=self._template_dir.name,
                certificate_id=certificate_id,
                issue_date=self._state.issue_date,
                fields=fields,
                images=dict(self._state.image_values),
            )
        except ValidationError as exc:
            raise CertificateError(_humanize(exc)) from exc

    # ------------------------------------------------------------------ #
    # Історія
    # ------------------------------------------------------------------ #

    def undo(self) -> None:
        if not self._undo:
            return
        entry = self._undo.pop()
        self._redo.append(self._state)
        self._state = entry.state
        self._emit("reset", None)

    def redo(self) -> None:
        if not self._redo:
            return
        self._undo.append(_HistoryEntry(self._state, None, 0.0))
        self._state = self._redo.pop()
        self._emit("reset", None)

    def _commit(
        self,
        new_state: DocState,
        kind: ChangeKind,
        layer_id: str | None,
        merge_key: str | None = None,
    ) -> None:
        if new_state == self._state:
            return
        now = time.monotonic()
        last = self._undo[-1] if self._undo else None
        mergeable = (
            merge_key is not None
            and last is not None
            and last.merge_key == merge_key
            and now - last.timestamp < MERGE_WINDOW_SECONDS
        )
        if mergeable:
            self._undo = self._undo[:-1] + [replace(last, timestamp=now)]
        else:
            self._undo = (self._undo + [_HistoryEntry(self._state, merge_key, now)])[-HISTORY_LIMIT:]
        self._redo = []
        self._state = new_state
        self._emit(kind, layer_id)

    def _emit(self, kind: ChangeKind, layer_id: str | None) -> None:
        for listener in self._listeners:
            listener(kind, layer_id)

    # ------------------------------------------------------------------ #
    # Допоміжне
    # ------------------------------------------------------------------ #

    def _with_layers(self, layers: tuple[AnyLayer, ...]) -> TemplateConfig:
        return self.config.model_copy(update={"layers": layers})

    def _replace_layer(self, updated: AnyLayer) -> TemplateConfig:
        layers = tuple(updated if layer.id == updated.id else layer for layer in self.config.layers)
        return self._with_layers(layers)

    def _index(self, layer_id: str) -> int:
        for index, layer in enumerate(self.config.layers):
            if layer.id == layer_id:
                return index
        raise KeyError(layer_id)

    def _unique_id(self, prefix: str) -> str:
        existing = {layer.id for layer in self.config.layers}
        counter = 1
        while f"{prefix}_{counter}" in existing:
            counter += 1
        return f"{prefix}_{counter}"


def _validated(model: type[BaseModel], payload: dict[str, Any]) -> Any:
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise CertificateError(_humanize(exc)) from exc


def _humanize(exc: ValidationError) -> str:
    messages = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        if location == "certificate_id":
            messages.append("ID сертифіката: лише латиниця, цифри, «-» і «_» (до 64 символів)")
        else:
            messages.append(f"{location}: {error['msg']}" if location else error["msg"])
    return "\n".join(messages)
