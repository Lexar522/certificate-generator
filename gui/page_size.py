"""Формати сторінки та зміна розміру полотна з пропорційним масштабуванням вмісту."""

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from core.exceptions import CertificateError
from core.models import MAX_CANVAS_SIDE, FrameLayer, ImageLayer, ShapeLayer, TemplateConfig
from core.template_loader import resolve_template_asset
from gui.layout_ops import resize_changes
from renderers.pillow_renderer import AnyLayer

MM_PER_INCH = 25.4
FALLBACK_SIZE = (300, 150)
SIZE_TOLERANCE = 2  # px: округлення мм → px дає розбіжність у кілька пікселів


@dataclass(frozen=True)
class PageFormat:
    key: str
    title: str
    short: float  # коротша сторона
    long: float  # довша сторона
    unit: str  # "mm" — залежить від DPI; "px" — фіксований розмір екрана


PAGE_FORMATS: tuple[PageFormat, ...] = (
    PageFormat("a4", "A4 · 210 × 297 мм", 210, 297, "mm"),
    PageFormat("a5", "A5 · 148 × 210 мм", 148, 210, "mm"),
    PageFormat("a3", "A3 · 297 × 420 мм", 297, 420, "mm"),
    PageFormat("letter", "Letter · 216 × 279 мм", 215.9, 279.4, "mm"),
    PageFormat("square", "Квадрат · 2000 × 2000 px", 2000, 2000, "px"),
    PageFormat("full_hd", "Екран 16:9 · 1920 × 1080 px", 1080, 1920, "px"),
)
CUSTOM_FORMAT = "custom"


def format_by_key(key: str) -> PageFormat:
    for page in PAGE_FORMATS:
        if page.key == key:
            return page
    raise KeyError(key)


def mm_to_px(mm: float, dpi: int) -> int:
    return round(mm / MM_PER_INCH * dpi)


def px_to_mm(px: int, dpi: int) -> float:
    return px / dpi * MM_PER_INCH


def format_pixels(page: PageFormat, dpi: int, landscape: bool) -> tuple[int, int]:
    """(ширина, висота) у пікселях; для мм-форматів — з урахуванням DPI."""
    if page.unit == "mm":
        short, long = mm_to_px(page.short, dpi), mm_to_px(page.long, dpi)
    else:
        short, long = round(page.short), round(page.long)
    width, height = (long, short) if landscape else (short, long)
    return min(width, MAX_CANVAS_SIDE), min(height, MAX_CANVAS_SIDE)


def detect_format(width: int, height: int, dpi: int) -> str:
    """Ключ формату, якому відповідає розмір, або CUSTOM_FORMAT."""
    for page in PAGE_FORMATS:
        for landscape in (True, False):
            w, h = format_pixels(page, dpi, landscape)
            if abs(w - width) <= SIZE_TOLERANCE and abs(h - height) <= SIZE_TOLERANCE:
                return page.key
    return CUSTOM_FORMAT


# ---------------------------------------------------------------------- #
# Масштабування вмісту
# ---------------------------------------------------------------------- #


def resized_layers(config: TemplateConfig, template_dir: Path, width: int, height: int) -> tuple[AnyLayer, ...]:
    """Шари, пропорційно перенесені на полотно нового розміру.

    Вміст масштабується однаково по обох осях і центрується (нічого не спотворюється);
    шари на всю сторінку — рамки, підкладки — розтягуються під новий розмір.
    """
    old_w, old_h = config.canvas.width, config.canvas.height
    factor = min(width / old_w, height / old_h)
    dx, dy = (width - old_w * factor) / 2, (height - old_h * factor) / 2
    result = []
    for layer in config.layers:
        if isinstance(layer, FrameLayer):
            result.append(layer)  # сама підлаштовується під нову сторінку
            continue
        if _covers_page(layer, old_w, old_h):
            changes = {"x": 0, "y": 0, "width": width, "height": height}
        else:
            changes = _scaled_size(layer, factor, template_dir) | {
                "x": round(layer.x * factor + dx),
                "y": round(layer.y * factor + dy),
            }
        result.append(type(layer).model_validate(layer.model_dump() | changes))
    return tuple(result)


def _covers_page(layer: AnyLayer, width: int, height: int) -> bool:
    if isinstance(layer, ShapeLayer):
        if layer.shape == "line":
            return False
    elif not isinstance(layer, ImageLayer) or layer.width is None or layer.height is None:
        return False
    return layer.x <= 0 and layer.y <= 0 and layer.x + layer.width >= width and layer.y + layer.height >= height


def _scaled_size(layer: AnyLayer, factor: float, template_dir: Path) -> dict:
    if isinstance(layer, ImageLayer) and layer.width is None and layer.height is None and layer.path is None:
        return {}  # змінне зображення без розміру: підлаштується під файл при генерації
    return resize_changes(layer, factor, _image_size(layer, template_dir))


def _image_size(layer: AnyLayer, template_dir: Path) -> tuple[int, int]:
    if not isinstance(layer, ImageLayer) or layer.path is None:
        return FALLBACK_SIZE
    try:
        with Image.open(resolve_template_asset(template_dir, layer.path)) as image:
            return image.size
    except (CertificateError, OSError, UnidentifiedImageError):
        return FALLBACK_SIZE
