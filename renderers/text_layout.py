"""Вимірювання та компонування тексту: підгонка під max_width і вирівнювання."""

import logging
from collections.abc import Callable
from dataclasses import dataclass

from PIL import ImageDraw, ImageFont

logger = logging.getLogger(__name__)

FontFactory = Callable[[int], ImageFont.FreeTypeFont]


@dataclass(frozen=True)
class TextBlock:
    font: ImageFont.FreeTypeFont
    lines: tuple[str, ...]


def measure_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    return right - left


def layout_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_factory: FontFactory,
    font_size: int,
    max_width: int | None,
    overflow: str,
    min_font_size: int,
) -> TextBlock:
    """Підбирає шрифт і розбиття на рядки так, щоб текст вмістився в max_width.

    «\\n» у тексті — примусовий новий рядок (абзац); кожен абзац переноситься окремо.
    overflow="shrink": зменшує кегль до min_font_size, далі — перенос рядків.
    overflow="wrap": перенос рядків за словами при початковому кеглі.
    """
    paragraphs = tuple(text.splitlines()) or ("",)
    font = font_factory(font_size)
    if max_width is None or _widest(draw, paragraphs, font) <= max_width:
        return TextBlock(font, paragraphs)

    if overflow == "shrink":
        fitted = _shrink_to_fit(draw, paragraphs, font_factory, font_size, max_width, min_font_size)
        if fitted is not None:
            return TextBlock(fitted, paragraphs)
        font = font_factory(min_font_size)

    lines = tuple(line for paragraph in paragraphs for line in _wrap_words(draw, paragraph, font, max_width))
    return TextBlock(font, lines)


def _widest(draw: ImageDraw.ImageDraw, lines: tuple[str, ...], font: ImageFont.FreeTypeFont) -> int:
    return max(measure_width(draw, line, font) for line in lines)


def _shrink_to_fit(
    draw: ImageDraw.ImageDraw,
    lines: tuple[str, ...],
    font_factory: FontFactory,
    font_size: int,
    max_width: int,
    min_font_size: int,
) -> ImageFont.FreeTypeFont | None:
    """Бінарний пошук найбільшого кеглю, що вміщується; None — якщо не вміщується навіть min."""
    low, high = min_font_size, font_size - 1
    best: ImageFont.FreeTypeFont | None = None
    while low <= high:
        middle = (low + high) // 2
        candidate = font_factory(middle)
        if _widest(draw, lines, candidate) <= max_width:
            best, low = candidate, middle + 1
        else:
            high = middle - 1
    return best


def _wrap_words(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int
) -> tuple[str, ...]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and measure_width(draw, candidate, font) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current or not lines:  # порожній абзац лишається порожнім рядком
        lines.append(current)

    too_wide = [line for line in lines if measure_width(draw, line, font) > max_width]
    if too_wide:
        logger.warning("Слово ширше за max_width=%d, рядок виходить за межі: %s", max_width, too_wide)
    return tuple(lines)


def aligned_x(
    draw: ImageDraw.ImageDraw, line: str, font: ImageFont.FreeTypeFont, x: int, align: str
) -> float:
    """X-координата початку рядка, щоб `x` був лівим краєм, центром чи правим краєм."""
    left, _, right, _ = draw.textbbox((0, 0), line, font=font)
    width = right - left
    offsets = {"left": 0.0, "center": width / 2, "right": float(width)}
    return x - left - offsets[align]
