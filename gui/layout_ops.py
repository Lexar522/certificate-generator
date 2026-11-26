"""Чисті функції геометрії шарів: як змінити властивості шару при масштабуванні мишею."""

from typing import Any

from core.models import FrameLayer, ImageLayer, QrLayer, ShapeLayer, TextLayer, WatermarkLayer
from renderers.pillow_renderer import AnyLayer

MIN_SCALE, MAX_SCALE = 0.01, 20.0
MAX_DIMENSION = 10_000
MIN_QR_SIZE = 20
MAX_FONT_SIZE = 1000
MAX_STROKE = 500


def resize_changes(layer: AnyLayer, factor: float, base_size: tuple[int, int]) -> dict[str, Any]:
    """Зміни властивостей, що масштабують шар у factor разів.

    base_size — поточний розмір спрайта без обертання (потрібен зображенням без явних width/height).
    """
    if factor <= 0:
        raise ValueError("factor має бути додатним")

    def scaled(value: int) -> int:
        return max(1, min(MAX_DIMENSION, round(value * factor)))

    if isinstance(layer, WatermarkLayer):
        return {"scale": round(min(MAX_SCALE, max(MIN_SCALE, layer.scale * factor)), 4)}
    if isinstance(layer, QrLayer):
        return {"size": max(MIN_QR_SIZE, scaled(layer.size))}
    if isinstance(layer, ImageLayer):
        if layer.width is None and layer.height is None:
            return {"width": scaled(base_size[0])}
        return {
            "width": scaled(layer.width) if layer.width is not None else None,
            "height": scaled(layer.height) if layer.height is not None else None,
        }
    if isinstance(layer, TextLayer):
        font_size = max(1, min(MAX_FONT_SIZE, round(layer.font_size * factor)))
        changes: dict[str, Any] = {"font_size": font_size}
        if layer.max_width is not None:
            changes["max_width"] = scaled(layer.max_width)
        if layer.min_font_size is not None:
            changes["min_font_size"] = min(layer.min_font_size, font_size)
        return changes
    if isinstance(layer, FrameLayer):
        return {}  # розмір рамки завжди дорівнює розміру сторінки
    if isinstance(layer, ShapeLayer):
        stroke = min(MAX_STROKE, max(1, round(layer.stroke_width * factor))) if layer.stroke_width else 0
        return {
            "width": scaled(layer.width),
            "height": scaled(layer.height),
            "stroke_width": stroke,
            "corner_radius": round(layer.corner_radius * factor),
        }
    raise TypeError(f"Невідомий тип шару: {type(layer).__name__}")
