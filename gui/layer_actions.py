"""Дії над шарами, які потребують рендерера чи діалогів: нові шари, масштабування, підписи."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image

from core.models import ImageLayer, QrLayer, TextLayer, WatermarkLayer
from core.template_store import import_asset
from gui.document import EditorDocument
from gui.layer_panels import template_fonts
from gui.layout_ops import resize_changes
from gui.qt_utils import TYPE_NAMES
from renderers.pillow_renderer import AnyLayer, PillowRenderer, RenderContext

WATERMARK_PAGE_FRACTION = 0.45
IMAGE_PAGE_FRACTION = 0.2
QR_PAGE_FRACTION = 1 / 8
TEXT_PAGE_FRACTION = 1 / 20
MIN_QR_SIZE, MIN_FONT_SIZE = 120, 24
DARK_BACKGROUND_SUM = 382  # сума R+G+B, нижче якої фон вважаємо темним

PathPicker = Callable[[], Path | None]


# ---------------------------------------------------------------------- #
# Нові шари
# ---------------------------------------------------------------------- #


def new_layer_payload(kind: str, doc: EditorDocument, pick_image: PathPicker, pick_font: PathPicker) -> dict | None:
    """Готовий до add_layer опис нового шару по центру сторінки; None — користувач скасував вибір файлу."""
    canvas = doc.config.canvas
    center_x, center_y = canvas.width // 2, canvas.height // 2
    label = _next_label(doc, kind)
    if kind == "text":
        payload = _text_payload(doc, center_x, center_y, pick_font)
    elif kind == "qr":
        size = max(MIN_QR_SIZE, round(canvas.width * QR_PAGE_FRACTION))
        payload = {"type": "qr", "size": size, "x": center_x - size // 2, "y": center_y - size // 2}
    else:
        payload = _picture_payload(kind, doc, center_x, center_y, pick_image)
    return None if payload is None else payload | {"label": label}


def _next_label(doc: EditorDocument, kind: str) -> str:
    base = TYPE_NAMES.get(kind, kind)
    existing = {layer.label for layer in doc.config.layers}
    if base not in existing:
        return base
    counter = 2
    while f"{base} {counter}" in existing:
        counter += 1
    return f"{base} {counter}"


def _text_payload(doc: EditorDocument, center_x: int, center_y: int, pick_font: PathPicker) -> dict | None:
    fonts = template_fonts(doc.template_dir)
    if not fonts:
        path = pick_font()
        if path is None:
            return None
        fonts = [import_asset(doc.template_dir, path, "fonts")]
    font_size = max(MIN_FONT_SIZE, round(doc.config.canvas.height * TEXT_PAGE_FRACTION))
    return {
        "type": "text",
        "text": "Новий текст",
        "font": fonts[0],
        "font_size": font_size,
        "color": "#FFFFFF" if _is_dark(doc.config.canvas.background_color) else "#1D1D1F",
        "align": "center",
        "x": center_x,
        "y": center_y - font_size // 2,
    }


def _picture_payload(
    kind: str, doc: EditorDocument, center_x: int, center_y: int, pick_image: PathPicker
) -> dict | None:
    path = pick_image()
    if path is None:
        return None
    relative = import_asset(doc.template_dir, path, "assets")
    with Image.open(doc.template_dir / relative) as image:
        width, height = image.size
    page_width = doc.config.canvas.width
    if kind == "watermark":
        scale = round(page_width * WATERMARK_PAGE_FRACTION / width, 3)
        return {
            "type": "watermark",
            "path": relative,
            "scale": scale,
            "opacity": 0.15,
            "x": round(center_x - width * scale / 2),
            "y": round(center_y - height * scale / 2),
        }
    target_width = round(page_width * IMAGE_PAGE_FRACTION)
    target_height = round(height * target_width / width)
    return {
        "type": "image",
        "path": relative,
        "width": target_width,
        "x": center_x - target_width // 2,
        "y": center_y - target_height // 2,
    }


def _is_dark(hex_color: str) -> bool:
    digits = hex_color.lstrip("#")
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    return sum(int(digits[i : i + 2], 16) for i in (0, 2, 4)) < DARK_BACKGROUND_SUM


# ---------------------------------------------------------------------- #
# Масштабування мишею
# ---------------------------------------------------------------------- #


def scaled_layer_changes(
    renderer: PillowRenderer, doc: EditorDocument, layer_id: str, factor: float, left: int, top: int
) -> dict[str, Any]:
    """Зміни розміру + позиції, щоб новий спрайт мав лівий верхній кут саме в (left, top)."""
    layer = doc.layer(layer_id)
    context = RenderContext(doc.preview_data(), doc.template_dir, doc.config)
    base = renderer.render_layer(layer.model_copy(update={"rotation": 0.0, "opacity": 1.0}), context)
    base_size = base.image.size if base else (getattr(layer, "width", None) or 300, 150)

    changes = resize_changes(layer, factor, base_size)
    candidate = type(layer).model_validate(layer.model_dump() | changes)
    sprite = renderer.render_layer(candidate, context)
    if sprite is None:  # змінне зображення без файлу: позиція шару = кут заглушки
        return changes | {"x": left, "y": top}
    return changes | {"x": candidate.x + left - sprite.x, "y": candidate.y + top - sprite.y}


# ---------------------------------------------------------------------- #
# Підписи для списку шарів
# ---------------------------------------------------------------------- #


def layer_subtitle(layer: AnyLayer, doc: EditorDocument) -> str:
    if isinstance(layer, TextLayer):
        if layer.text is None:
            value = doc.state.field_values.get(layer.id)
            return f"«{value}»" if value else "Змінне поле"
        return layer.text
    if isinstance(layer, ImageLayer):
        if layer.path is None:
            value = doc.state.image_values.get(layer.id)
            return Path(value).name if value else "Змінне зображення"
        return Path(layer.path).name
    if isinstance(layer, WatermarkLayer):
        return f"{Path(layer.path).name} · {round(layer.opacity * 100)}%"
    if isinstance(layer, QrLayer):
        return layer.url_template.replace("{certificate_id}", "…").removeprefix("https://")
    return ""
