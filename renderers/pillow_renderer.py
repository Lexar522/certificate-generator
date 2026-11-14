"""Рендерер на Pillow: кожен шар рендериться в окремий спрайт і накладається на холст.

Спрайтова модель дозволяє редактору перемальовувати лише змінений шар, а фінальний
файл збирається тим самим кодом — перегляд і результат завжди ідентичні.
"""

import logging
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import qrcode
from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError
from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q
from qrcode.exceptions import DataOverflowError

from core.exceptions import AssetNotFoundError, FontLoadError, MissingFieldError, RenderError
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
from core.template_catalog import PLACEHOLDER_RE
from core.template_loader import load_template_config, resolve_template_asset
from renderers.base import BaseRenderer
from renderers.text_layout import aligned_x, layout_text

logger = logging.getLogger(__name__)

AnyLayer = WatermarkLayer | ImageLayer | TextLayer | QrLayer

TRANSPARENT = (0, 0, 0, 0)
QR_BOX_SIZE = 10
PIL_FORMATS = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".pdf": "PDF"}
QR_ERROR_LEVELS = {
    "L": ERROR_CORRECT_L,
    "M": ERROR_CORRECT_M,
    "Q": ERROR_CORRECT_Q,
    "H": ERROR_CORRECT_H,
}


@dataclass(frozen=True)
class RenderContext:
    data: CertificateData
    template_dir: Path
    config: TemplateConfig


@dataclass(frozen=True)
class LayerSprite:
    """Відрендерений шар: RGBA-зображення та позиція його лівого верхнього кута на холсті."""

    image: Image.Image
    x: int
    y: int


class PillowRenderer(BaseRenderer):
    """Кожен крок повертає нове зображення — вхідні дані ніколи не мутуються."""

    def render(self, data: CertificateData, template_dir: Path, output_path: Path) -> Path:
        config = load_template_config(template_dir)
        return self.export(data, template_dir, config, output_path)

    def export(
        self, data: CertificateData, template_dir: Path, config: TemplateConfig, output_path: Path
    ) -> Path:
        """Рендер за конфігом у пам'яті (наприклад, незбереженим у редакторі)."""
        return save_image(self.compose(data, template_dir, config), output_path, config.output)

    def compose(
        self, data: CertificateData, template_dir: Path, config: TemplateConfig | None = None
    ) -> Image.Image:
        """Збирає сертифікат у пам'яті без збереження."""
        config = config or load_template_config(template_dir)
        context = RenderContext(data=data, template_dir=template_dir, config=config)
        canvas = self.render_background(config.canvas, template_dir)
        for layer in config.layers:
            if not layer.visible:
                continue
            sprite = self.render_layer(layer, context)
            if sprite is not None:
                canvas = composite_at(canvas, sprite)
        return canvas

    # ------------------------------------------------------------------ #
    # Публічні будівельні блоки (використовуються редактором)
    # ------------------------------------------------------------------ #

    def render_background(self, canvas_config: CanvasConfig, template_dir: Path) -> Image.Image:
        size = (canvas_config.width, canvas_config.height)
        base = Image.new("RGBA", size, ImageColor.getrgb(canvas_config.background_color))
        if canvas_config.background_image is None:
            return base

        path = resolve_template_asset(template_dir, canvas_config.background_image)
        background = ImageOps.fit(open_rgba(path, "canvas.background_image"), size)
        return Image.alpha_composite(base, background)

    def render_layer(self, layer: AnyLayer, context: RenderContext) -> LayerSprite | None:
        """Спрайт шару з урахуванням opacity та rotation; None — якщо шару нема що показати."""
        handlers = {
            WatermarkLayer: self._watermark_sprite,
            ImageLayer: self._image_sprite,
            TextLayer: self._text_sprite,
            QrLayer: self._qr_sprite,
        }
        sprite = handlers[type(layer)](layer, context)
        if sprite is None:
            return None
        return _apply_rotation(_apply_opacity(sprite, layer.opacity), layer.rotation)

    # ------------------------------------------------------------------ #
    # Шари
    # ------------------------------------------------------------------ #

    def _watermark_sprite(self, layer: WatermarkLayer, context: RenderContext) -> LayerSprite:
        path = resolve_template_asset(context.template_dir, layer.path)
        return LayerSprite(_scale(open_rgba(path, layer.id), layer.scale), layer.x, layer.y)

    def _image_sprite(self, layer: ImageLayer, context: RenderContext) -> LayerSprite | None:
        path = image_source(layer, context)
        if path is None:
            return None
        return LayerSprite(_fit_size(open_rgba(path, layer.id), layer), layer.x, layer.y)

    def _text_sprite(self, layer: TextLayer, context: RenderContext) -> LayerSprite | None:
        text = text_value(layer, context)
        if text is None:
            return None

        font_path = resolve_template_asset(context.template_dir, layer.font)
        measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        block = layout_text(
            measure,
            text,
            font_factory=lambda size: load_font(font_path, size, layer.id),
            font_size=layer.font_size,
            max_width=layer.max_width,
            overflow=layer.overflow,
            min_font_size=layer.effective_min_font_size,
        )

        line_height = block.font.size * layer.line_spacing
        positions = [
            (aligned_x(measure, line, block.font, layer.x, layer.align), layer.y + i * line_height)
            for i, line in enumerate(block.lines)
        ]
        boxes = [measure.textbbox(pos, line, font=block.font) for pos, line in zip(positions, block.lines)]
        left = int(min(box[0] for box in boxes))
        top = int(min(box[1] for box in boxes))
        right = int(max(box[2] for box in boxes)) + 1
        bottom = int(max(box[3] for box in boxes)) + 1

        sprite = Image.new("RGBA", (max(1, right - left), max(1, bottom - top)), TRANSPARENT)
        draw = ImageDraw.Draw(sprite)
        fill = ImageColor.getrgb(layer.color)
        for (px, py), line in zip(positions, block.lines):
            draw.text((px - left, py - top), line, font=block.font, fill=fill)
        return LayerSprite(sprite, left, top)

    def _qr_sprite(self, layer: QrLayer, context: RenderContext) -> LayerSprite:
        url = layer.url_template.replace("{certificate_id}", context.data.certificate_id)
        try:
            qr = qrcode.QRCode(
                error_correction=QR_ERROR_LEVELS[layer.error_correction],
                box_size=QR_BOX_SIZE,
                border=layer.border,
            )
            qr.add_data(url)
            qr.make(fit=True)
            image = qr.make_image(fill_color=layer.fill_color, back_color=layer.back_color)
            code = image.get_image().convert("RGBA")
        except (ValueError, DataOverflowError) as exc:
            raise RenderError(f"Шар '{layer.id}': не вдалося згенерувати QR-код: {exc}") from exc

        code = code.resize((layer.size, layer.size), Image.Resampling.NEAREST)
        return LayerSprite(code, layer.x, layer.y)


# ---------------------------------------------------------------------- #
# Джерела значень
# ---------------------------------------------------------------------- #


def image_source(layer: ImageLayer, context: RenderContext) -> Path | None:
    dynamic = context.data.images.get(layer.id)
    if dynamic is not None:
        return Path(dynamic)
    if layer.path is not None:
        return resolve_template_asset(context.template_dir, layer.path)
    if layer.required:
        raise MissingFieldError(layer.id, "images")
    logger.debug("Шар '%s' пропущено: зображення не передано", layer.id)
    return None


def text_value(layer: TextLayer, context: RenderContext) -> str | None:
    value = context.data.fields.get(layer.id)
    if value is None and layer.text is not None:
        value = fill_placeholders(layer.text, context)
    if value is None:
        if layer.required:
            raise MissingFieldError(layer.id, "fields")
        logger.debug("Шар '%s' пропущено: текст не передано", layer.id)
        return None
    return value.upper() if layer.uppercase else value


def fill_placeholders(template: str, context: RenderContext) -> str:
    """Підставляє {certificate_id}, {issue_date} і поля даних {key}; невідомий ключ — помилка."""
    builtins = {
        "certificate_id": context.data.certificate_id,
        "issue_date": context.data.issue_date.strftime(context.config.date_format),
    }

    def substitute(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in builtins:
            return builtins[key]
        value = context.data.fields.get(key)
        if value is None:
            raise MissingFieldError(key, "fields")
        return value

    return PLACEHOLDER_RE.sub(substitute, template)


# ---------------------------------------------------------------------- #
# Робота із зображеннями
# ---------------------------------------------------------------------- #


def composite_at(canvas: Image.Image, sprite: LayerSprite) -> Image.Image:
    """Накладає спрайт на копію холста; частини за межами холста обрізаються."""
    src_left, src_top = max(0, -sprite.x), max(0, -sprite.y)
    src_right = min(sprite.image.width, canvas.width - sprite.x)
    src_bottom = min(sprite.image.height, canvas.height - sprite.y)
    if src_right <= src_left or src_bottom <= src_top:
        return canvas

    visible = sprite.image.crop((src_left, src_top, src_right, src_bottom))
    result = canvas.copy()
    result.alpha_composite(visible, (max(0, sprite.x), max(0, sprite.y)))
    return result


def save_image(canvas: Image.Image, output_path: Path, output: OutputConfig) -> Path:
    pil_format = PIL_FORMATS.get(output_path.suffix.lower())
    if pil_format is None:
        raise RenderError(
            f"Непідтримуване розширення '{output_path.suffix}'. Доступні: {', '.join(PIL_FORMATS)}"
        )

    image = canvas if pil_format == "PNG" else canvas.convert("RGB")
    options = {
        "JPEG": {"quality": output.quality, "dpi": (output.dpi, output.dpi), "optimize": True},
        "PNG": {"dpi": (output.dpi, output.dpi), "optimize": True},
        "PDF": {"resolution": float(output.dpi)},
    }[pil_format]

    # Атомарний запис: при збої не залишиться напівзаписаного файлу.
    temp_path = output_path.with_name(f".{output_path.name}.tmp")
    try:
        image.save(temp_path, format=pil_format, **options)
        os.replace(temp_path, output_path)
    except OSError as exc:
        temp_path.unlink(missing_ok=True)
        raise RenderError(f"Не вдалося зберегти сертифікат у {output_path}: {exc}") from exc
    return output_path


def open_rgba(path: Path, layer_id: str) -> Image.Image:
    if not path.is_file():
        raise AssetNotFoundError(layer_id, path)
    try:
        with Image.open(path) as image:
            return image.convert("RGBA")
    except UnidentifiedImageError as exc:
        raise AssetNotFoundError(layer_id, path, "файл не є підтримуваним зображенням") from exc
    except OSError as exc:
        raise AssetNotFoundError(layer_id, path, f"помилка читання: {exc}") from exc


@lru_cache(maxsize=128)
def load_font(font_path: Path, size: int, layer_id: str) -> ImageFont.FreeTypeFont:
    if not font_path.is_file():
        raise FontLoadError(layer_id, font_path, "файл не існує")
    try:
        return ImageFont.truetype(str(font_path), size)
    except OSError as exc:
        raise FontLoadError(layer_id, font_path, f"пошкоджений або непідтримуваний шрифт: {exc}") from exc


def _apply_opacity(sprite: LayerSprite, opacity: float) -> LayerSprite:
    """Множить альфа-канал на opacity (0.0 — невидимо, 1.0 — без змін)."""
    if opacity >= 1.0:
        return sprite
    alpha = sprite.image.getchannel("A").point(lambda value: round(value * opacity))
    image = sprite.image.copy()
    image.putalpha(alpha)
    return LayerSprite(image, sprite.x, sprite.y)


def _apply_rotation(sprite: LayerSprite, degrees: float) -> LayerSprite:
    """Обертає навколо центру спрайта, зберігаючи положення центру."""
    if not degrees % 360:
        return sprite
    rotated = sprite.image.rotate(degrees, expand=True, resample=Image.Resampling.BICUBIC)
    center_x = sprite.x + sprite.image.width / 2
    center_y = sprite.y + sprite.image.height / 2
    return LayerSprite(
        rotated, round(center_x - rotated.width / 2), round(center_y - rotated.height / 2)
    )


def _scale(image: Image.Image, factor: float) -> Image.Image:
    if factor == 1.0:
        return image
    size = (max(1, round(image.width * factor)), max(1, round(image.height * factor)))
    return image.resize(size, Image.Resampling.LANCZOS)


def _fit_size(image: Image.Image, layer: ImageLayer) -> Image.Image:
    width, height = layer.width, layer.height
    if width is None and height is None:
        return image
    if width is not None and height is not None:
        if layer.keep_aspect:
            return ImageOps.contain(image, (width, height), Image.Resampling.LANCZOS)
        return image.resize((width, height), Image.Resampling.LANCZOS)
    if width is not None:
        height = max(1, round(image.height * width / image.width))
    else:
        width = max(1, round(image.width * height / image.height))
    return image.resize((width, height), Image.Resampling.LANCZOS)
