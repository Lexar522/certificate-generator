"""Згенеровані кодом прикраси: рамки, візерунковий фон і заглушки для логотипа, печатки, підпису.

Усе малюється з нуля примітивами Pillow, тож не потребує сторонніх зображень і ліцензій.
"""

import math
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont

FRAME_STYLES: dict[str, str] = {
    "gold": "Золота орнаментальна",
    "classic": "Класична подвійна",
    "minimal": "Тонка лінія",
}

TRANSPARENT = (0, 0, 0, 0)
SUPERSAMPLE = 3  # дрібні елементи малюємо збільшеними й зменшуємо — згладжені краї
BAND_FRACTION = 0.045  # ширина орнаментальної смуги від коротшої сторони
GOLD_DARK, GOLD_MID, GOLD_LIGHT = (92, 62, 18), (176, 132, 52), (238, 206, 120)
INNER_LINE_COLOR = "#1F4E9A"


def frame_image(width: int, height: int, style: str, color: str = "#1F3A5F") -> Image.Image:
    """Прозоре зображення розміром із сторінку: рамка по краях, усередині порожньо."""
    builders = {"gold": _gold_frame, "classic": _classic_frame, "minimal": _minimal_frame}
    if style not in builders:
        raise ValueError(f"Невідомий стиль рамки: {style}")
    return builders[style](width, height, ImageColor.getrgb(color))


# ---------------------------------------------------------------------- #
# Золота орнаментальна рамка
# ---------------------------------------------------------------------- #


def _gold_frame(width: int, height: int, _color: tuple[int, ...]) -> Image.Image:
    band = max(12, round(min(width, height) * BAND_FRACTION))
    frame = Image.new("RGBA", (width, height), TRANSPARENT)
    _paste_band(frame, _shell_tile(band), band)
    corner = _rosette_tile(band)
    for x, y in ((0, 0), (width - band, 0), (0, height - band), (width - band, height - band)):
        frame.alpha_composite(corner, (x, y))

    draw = ImageDraw.Draw(frame)
    unit = max(1, band // 16)
    draw.rectangle((band, band, width - band - 1, height - band - 1), outline=GOLD_DARK, width=unit * 2)
    inset = band + unit * 5
    draw.rectangle((inset, inset, width - inset - 1, height - inset - 1), outline=INNER_LINE_COLOR, width=unit * 2)
    draw.rectangle((0, 0, width - 1, height - 1), outline=GOLD_DARK, width=unit)
    return frame


def _paste_band(frame: Image.Image, tile: Image.Image, band: int) -> None:
    """Розкладає плитку вздовж чотирьох сторін; плитки трохи розтягуються, щоб лягти без залишку."""
    width, height = frame.size
    for start, length in _tile_spans(width - 2 * band, band):
        piece = tile.resize((length, band), Image.Resampling.LANCZOS)
        frame.alpha_composite(piece, (band + start, 0))
        frame.alpha_composite(piece.rotate(180), (band + start, height - band))
    for start, length in _tile_spans(height - 2 * band, band):
        piece = tile.resize((length, band), Image.Resampling.LANCZOS)
        frame.alpha_composite(piece.rotate(90, expand=True), (0, band + start))
        frame.alpha_composite(piece.rotate(-90, expand=True), (width - band, band + start))


def _tile_spans(length: int, band: int) -> list[tuple[int, int]]:
    """(початок, довжина) плиток, що рівно заповнюють відрізок."""
    if length <= 0:
        return []
    count = max(1, round(length / band))
    edges = [round(i * length / count) for i in range(count + 1)]
    return [(start, end - start) for start, end in zip(edges, edges[1:])]


def _gold_gradient(size: int) -> Image.Image:
    """Вертикальний «металевий» градієнт: темне — світле — темне."""
    column = Image.new("RGBA", (1, size))
    for y in range(size):
        t = y / max(1, size - 1)
        shine = 1 - abs(t - 0.4) / 0.6  # найсвітліше трохи вище середини
        column.putpixel((0, y), _mix(GOLD_DARK, GOLD_LIGHT, max(0.0, shine)) + (255,))
    return column.resize((size, size))


def _shell_tile(band: int) -> Image.Image:
    """Плитка смуги: мушля-пальмета з променями на золотому тлі."""
    s = band * SUPERSAMPLE
    tile = _gold_gradient(s)
    draw = ImageDraw.Draw(tile)
    line = max(1, s // 40)
    cx, base = s / 2, s * 0.86
    for radius, shade in ((0.44, GOLD_DARK), (0.38, GOLD_LIGHT), (0.3, GOLD_MID), (0.2, GOLD_LIGHT), (0.1, GOLD_DARK)):
        r = s * radius
        draw.pieslice((cx - r, base - r, cx + r, base + r), 180, 360, fill=shade, outline=GOLD_DARK, width=line)
    for i in range(1, 8):  # промені мушлі
        angle = math.pi + math.pi * i / 8
        r = s * 0.38
        draw.line((cx, base, cx + r * math.cos(angle), base + r * math.sin(angle)), fill=GOLD_DARK, width=line)
    draw.line((0, base, s, base), fill=GOLD_DARK, width=line * 2)
    for x in (s * 0.06, s * 0.94):  # перлини між мушлями
        r = s * 0.05
        draw.ellipse((x - r, s * 0.5 - r, x + r, s * 0.5 + r), fill=GOLD_LIGHT, outline=GOLD_DARK, width=line)
    draw.rectangle((0, 0, s - 1, s - 1), outline=GOLD_DARK, width=line)
    return tile.resize((band, band), Image.Resampling.LANCZOS)


def _rosette_tile(band: int) -> Image.Image:
    """Кутова плитка: розетка з вісьмома пелюстками."""
    s = band * SUPERSAMPLE
    tile = _gold_gradient(s)
    line = max(1, s // 40)
    c = s / 2
    petal = Image.new("RGBA", (s, s), TRANSPARENT)
    ImageDraw.Draw(petal).ellipse((c - s * 0.09, c - s * 0.44, c + s * 0.09, c), fill=GOLD_LIGHT, outline=GOLD_DARK, width=line)
    for angle in range(0, 360, 45):
        tile.alpha_composite(petal.rotate(angle, resample=Image.Resampling.BICUBIC, center=(c, c)))
    draw = ImageDraw.Draw(tile)
    for radius, fill in ((0.16, GOLD_MID), (0.08, GOLD_LIGHT)):
        r = s * radius
        draw.ellipse((c - r, c - r, c + r, c + r), fill=fill, outline=GOLD_DARK, width=line)
    draw.rectangle((0, 0, s - 1, s - 1), outline=GOLD_DARK, width=line)
    return tile.resize((band, band), Image.Resampling.LANCZOS)


# ---------------------------------------------------------------------- #
# Прості рамки
# ---------------------------------------------------------------------- #


def _classic_frame(width: int, height: int, color: tuple[int, ...]) -> Image.Image:
    """Подвійна лінія з ромбами в кутах."""
    short = min(width, height)
    frame = Image.new("RGBA", (width * 2, height * 2), TRANSPARENT)  # 2× для згладжених ромбів
    draw = ImageDraw.Draw(frame)
    outer, inner = round(short * 0.03) * 2, round(short * 0.045) * 2
    right, bottom = width * 2 - outer, height * 2 - outer
    draw.rectangle((outer, outer, right, bottom), outline=color, width=max(2, round(short * 0.008)))
    draw.rectangle((inner, inner, width * 2 - inner, height * 2 - inner), outline=color, width=max(2, round(short * 0.0025)))
    size = round(short * 0.022) * 2
    for x, y in ((outer, outer), (right, outer), (outer, bottom), (right, bottom)):
        draw.polygon(((x, y - size), (x + size, y), (x, y + size), (x - size, y)), fill=color)
    return frame.resize((width, height), Image.Resampling.LANCZOS)


def _minimal_frame(width: int, height: int, color: tuple[int, ...]) -> Image.Image:
    short = min(width, height)
    frame = Image.new("RGBA", (width, height), TRANSPARENT)
    margin = round(short * 0.035)
    ImageDraw.Draw(frame).rectangle(
        (margin, margin, width - margin - 1, height - margin - 1), outline=color, width=max(1, round(short * 0.003))
    )
    return frame


# ---------------------------------------------------------------------- #
# Візерунковий фон і заглушки
# ---------------------------------------------------------------------- #


def honeycomb_background(width: int, height: int, base: str = "#FFFFFF", line: str = "#EBEEF3") -> Image.Image:
    """Ледь помітні «соти» на світлому тлі, як на захищених бланках."""
    image = Image.new("RGBA", (width, height), ImageColor.getrgb(base))
    draw = ImageDraw.Draw(image)
    radius = max(6, min(width, height) / 70)
    step_x, step_y = radius * 1.5, radius * math.sqrt(3)
    stroke = ImageColor.getrgb(line)
    for col in range(int(width / step_x) + 2):
        for row in range(int(height / step_y) + 2):
            cx = col * step_x
            cy = row * step_y + (step_y / 2 if col % 2 else 0)
            points = [(cx + radius * math.cos(math.pi / 3 * k), cy + radius * math.sin(math.pi / 3 * k)) for k in range(7)]
            draw.line(points, fill=stroke, width=max(1, round(radius / 12)))
    return image


def placeholder_badge(
    width: int, height: int, caption: str, font_path: Path, round_shape: bool = True, color: str = "#8E8E93"
) -> Image.Image:
    """Пунктирна заглушка з підписом: показує, де буде логотип, печатка чи підпис."""
    s = SUPERSAMPLE
    image = Image.new("RGBA", (width * s, height * s), TRANSPARENT)
    draw = ImageDraw.Draw(image)
    rgb = ImageColor.getrgb(color)
    stroke = max(2, round(min(width, height) * 0.015)) * s
    box = (stroke, stroke, width * s - stroke, height * s - stroke)
    if round_shape:
        dashes = 48
        for i in range(0, dashes, 2):
            draw.arc(box, 360 * i / dashes, 360 * (i + 1) / dashes, fill=rgb, width=stroke)
    else:
        _dashed_rect(draw, box, rgb, stroke)

    longest = max(len(part) for part in caption.splitlines())
    font_size = round(min(height * 0.12, width * 1.1 / max(4, longest))) * s
    font_size = max(8, font_size)
    font = ImageFont.truetype(str(font_path), font_size) if font_path.is_file() else ImageFont.load_default(font_size)
    draw.multiline_text(
        (width * s / 2, height * s / 2), caption, font=font, fill=rgb, anchor="mm", align="center", spacing=stroke
    )
    return image.resize((width, height), Image.Resampling.LANCZOS)


def _dashed_rect(draw: ImageDraw.ImageDraw, box: tuple[float, float, float, float], color, stroke: int) -> None:
    left, top, right, bottom = box
    dash = stroke * 4
    for start, end, fixed, horizontal in (
        (left, right, top, True), (left, right, bottom, True), (top, bottom, left, False), (top, bottom, right, False)
    ):
        position = start
        while position < end:
            stop = min(end, position + dash)
            draw.line((position, fixed, stop, fixed) if horizontal else (fixed, position, fixed, stop), fill=color, width=stroke)
            position += dash * 2


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))
