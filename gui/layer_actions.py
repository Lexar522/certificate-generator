"""Дії над шарами, які потребують рендерера чи діалогів: нові шари, масштабування, підписи."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image

from core.exceptions import CertificateError
from core.models import FrameLayer, ImageLayer, QrLayer, ShapeLayer, TextLayer, WatermarkLayer
from core.ornaments import FRAME_STYLES
from core.template_loader import resolve_template_asset
from core.template_store import import_asset
from gui.document import LAYER_TYPES, EditorDocument
from gui.layer_panels import template_fonts
from gui.layout_ops import resize_changes
from gui.qt_utils import TYPE_NAMES
from renderers.pillow_renderer import AnyLayer, PillowRenderer, RenderContext

WATERMARK_PAGE_FRACTION = 0.45
IMAGE_PAGE_FRACTION = 0.2
QR_PAGE_FRACTION = 1 / 8
TEXT_PAGE_FRACTION = 1 / 20
MIN_QR_SIZE, MIN_FONT_SIZE = 120, 24
SHAPE_PAGE_FRACTION = 0.3
SHAPE_STROKE_FRACTION = 1 / 400
FRAME_PREFIX = "frame:"  # "frame:gold" — згенерована рамка на всю сторінку
DARK_BACKGROUND_SUM = 382  # сума R+G+B, нижче якої фон вважаємо темним

PathPicker = Callable[[], Path | None]


# ---------------------------------------------------------------------- #
# Нові шари
# ---------------------------------------------------------------------- #


def new_layer_payload(kind: str, doc: EditorDocument, pick_image: PathPicker, pick_font: PathPicker) -> dict | None:
    """Готовий до add_layer опис нового шару по центру сторінки; None — користувач скасував вибір файлу."""
    canvas = doc.config.canvas
    center_x, center_y = canvas.width // 2, canvas.height // 2
    if kind.startswith(FRAME_PREFIX):
        return frame_payload(doc, kind.removeprefix(FRAME_PREFIX)) | {"label": _next_label(doc, "frame")}
    label = _next_label(doc, kind)
    if kind == "text":
        payload = _text_payload(doc, center_x, center_y, pick_font)
    elif kind == "shape":
        payload = _shape_payload(doc, center_x, center_y)
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


def frame_payload(doc: EditorDocument, style: str) -> dict:
    """Рамка на всю сторінку (одразу заблокована, щоб не зсунути випадково)."""
    if style not in FRAME_STYLES:
        raise CertificateError(f"Невідомий стиль рамки: {style}")
    color = "#FFFFFF" if _is_dark(doc.config.canvas.background_color) else "#1F3A5F"
    return {"type": "frame", "style": style, "color": color, "locked": True}


def _shape_payload(doc: EditorDocument, center_x: int, center_y: int) -> dict:
    canvas = doc.config.canvas
    width = round(canvas.width * SHAPE_PAGE_FRACTION)
    height = width // 2
    return {
        "type": "shape",
        "shape": "rectangle",
        "width": width,
        "height": height,
        "stroke_color": "#FFFFFF" if _is_dark(canvas.background_color) else "#1D1D1F",
        "stroke_width": max(2, round(canvas.width * SHAPE_STROKE_FRACTION)),
        "x": center_x - width // 2,
        "y": center_y - height // 2,
    }


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
    return None if path is None else picture_payload_from_file(kind, doc, path, center_x, center_y)


def picture_payload_from_file(kind: str, doc: EditorDocument, path: Path, center_x: int, center_y: int) -> dict:
    """Шар image/watermark з файлу, центрований у точці (center_x, center_y); файл копіюється в шаблон."""
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
    if isinstance(layer, FrameLayer):
        return FRAME_STYLES[layer.style]
    if isinstance(layer, ShapeLayer):
        names = {"rectangle": "Прямокутник", "ellipse": "Еліпс", "line": "Лінія"}
        size = f"{layer.width} px" if layer.shape == "line" else f"{layer.width} × {layer.height}"
        return f"{names[layer.shape]} · {size}"
    if isinstance(layer, QrLayer):
        return layer.url_template.replace("{certificate_id}", "…").removeprefix("https://")
    return ""


# ---------------------------------------------------------------------- #
# Копіювання / вставка шарів (у т. ч. між шаблонами)
# ---------------------------------------------------------------------- #

CLIPBOARD_MIME = "application/x-certificate-layer"
PASTE_OFFSET = 40
MAX_CLIPBOARD_BYTES = 256 * 1024
_ASSET_FIELDS = {"image": ("path", "assets"), "watermark": ("path", "assets"), "text": ("font", "fonts")}


def layer_to_clipboard(layer: AnyLayer, doc: EditorDocument) -> bytes:
    payload = {"layer": layer.model_dump(mode="json"), "template_dir": str(doc.template_dir.resolve())}
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def paste_payload(raw: bytes, doc: EditorDocument) -> dict:
    """Опис шару з буфера обміну, готовий до add_layer; файли з іншого шаблону копіюються в поточний.

    Буфер міг заповнити будь-який застосунок, тож дані перевіряються як зовнішні.
    """
    if len(raw) > MAX_CLIPBOARD_BYTES:
        raise CertificateError("У буфері обміну завеликий фрагмент")
    try:
        clip = json.loads(raw.decode("utf-8"))
        layer = dict(clip["layer"])
        source_dir = Path(clip["template_dir"])
    except (ValueError, KeyError, TypeError) as exc:
        raise CertificateError("У буфері обміну немає шару сертифіката") from exc
    kind = layer.get("type")
    if kind not in LAYER_TYPES:
        raise CertificateError(f"Невідомий тип шару в буфері: {kind}")

    asset = _ASSET_FIELDS.get(kind)
    relative = layer.get(asset[0]) if asset else None
    if relative and source_dir.resolve() != doc.template_dir.resolve():
        source_file = resolve_template_asset(source_dir, relative)  # без виходу за межі шаблону-джерела
        layer[asset[0]] = import_asset(doc.template_dir, source_file, asset[1])

    layer.pop("id", None)
    return layer | {"x": int(layer.get("x", 0)) + PASTE_OFFSET, "y": int(layer.get("y", 0)) + PASTE_OFFSET}
