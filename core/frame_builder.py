"""Власні рамки: конструктор з параметрів і рамка з власного зображення («дев'ять частин»).

Готові стилі (gold / classic / minimal) малює core.ornaments; тут — усе, що налаштовує користувач.
"""

from PIL import Image, ImageColor, ImageDraw

from core.models import FrameLayer
from core.ornaments import FRAME_STYLES, TRANSPARENT, frame_image

FRAME_KINDS: dict[str, str] = FRAME_STYLES | {
    "custom": "Власна (конструктор)",
    "image": "Зі свого зображення",
}
CORNER_STYLES: dict[str, str] = {
    "none": "Без прикрас",
    "diamond": "Ромб",
    "circle": "Коло",
    "square": "Квадрат",
    "bracket": "Куточки",
}
SUPERSAMPLE = 2  # конструктор малює вдвічі більшим і зменшує — згладжені ромби й кола
INNER_LINE_RATIO = 0.45  # друга (внутрішня) лінія тонша за основну


def build_frame(width: int, height: int, layer: FrameLayer, source: Image.Image | None = None) -> Image.Image:
    """Прозоре зображення рамки розміром із сторінку для будь-якого стилю шару."""
    if layer.style == "custom":
        return custom_frame(width, height, layer)
    if layer.style == "image":
        if source is None:
            raise ValueError("Для рамки із зображення потрібне саме зображення")
        return nine_slice_frame(source, width, height, layer.border, layer.slice)
    return frame_image(width, height, layer.style, layer.color)


# ---------------------------------------------------------------------- #
# Конструктор
# ---------------------------------------------------------------------- #


def custom_frame(width: int, height: int, layer: FrameLayer) -> Image.Image:
    k = SUPERSAMPLE
    w, h = width * k, height * k
    unit = min(w, h) / 100  # 1% коротшої сторони
    frame = Image.new("RGBA", (w, h), TRANSPARENT)
    draw = ImageDraw.Draw(frame)
    main, accent = ImageColor.getrgb(layer.color), ImageColor.getrgb(layer.accent_color)
    margin = layer.margin * unit
    thickness = max(1.0, layer.thickness * unit)

    if layer.band_color is not None and margin > 0:
        draw.rectangle((0, 0, w - 1, h - 1), fill=ImageColor.getrgb(layer.band_color))
        draw.rectangle((margin, margin, w - 1 - margin, h - 1 - margin), fill=TRANSPARENT)  # без змішування

    insets = _line_insets(layer, margin, thickness, unit)
    for index, (inset, line_width) in enumerate(insets):
        color = accent if index == 1 else main
        draw.rectangle((inset, inset, w - 1 - inset, h - 1 - inset), outline=color, width=max(1, round(line_width)))

    _draw_corners(draw, layer, (w, h), insets, unit, main, accent)
    return frame.resize((width, height), Image.Resampling.LANCZOS)


def _line_insets(layer: FrameLayer, margin: float, thickness: float, unit: float) -> list[tuple[float, float]]:
    """(відступ, товщина) для кожної лінії: основна, тонша акцентна, знову основна."""
    widths = [thickness, max(1.0, thickness * INNER_LINE_RATIO), thickness][: layer.line_count]
    result, inset = [], margin
    for line_width in widths:
        result.append((inset, line_width))
        inset += line_width + layer.gap * unit
    return result


def _draw_corners(draw, layer: FrameLayer, size, insets, unit, main, accent) -> None:
    if layer.corner == "none":
        return
    w, h = size
    radius = layer.corner_size * unit / 2
    outer = insets[0][0] + insets[0][1] / 2
    inner = insets[-1][0] + insets[-1][1] / 2
    for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        def at(d: float) -> tuple[float, float]:
            return (d if sx > 0 else w - 1 - d, d if sy > 0 else h - 1 - d)

        if layer.corner == "bracket":
            _bracket(draw, at(inner), sx, sy, radius * 3, max(2.0, insets[0][1] * 2.2), accent)
            continue
        cx, cy = at(outer)
        if layer.corner == "diamond":
            draw.polygon(_diamond(cx, cy, radius), fill=main)
            draw.polygon(_diamond(cx, cy, radius * 0.45), fill=accent)
        elif layer.corner == "circle":
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=main)
            r = radius * 0.5
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=accent)
        else:  # square
            draw.rectangle((cx - radius, cy - radius, cx + radius, cy + radius), fill=main)
            r = radius * 0.5
            draw.rectangle((cx - r, cy - r, cx + r, cy + r), fill=accent)


def _diamond(cx: float, cy: float, r: float) -> list[tuple[float, float]]:
    return [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]


def _bracket(draw, corner: tuple[float, float], sx: int, sy: int, length: float, width: float, color) -> None:
    """Г-подібний куточок усередині кута рамки."""
    x, y = corner
    draw.line((x, y, x + sx * length, y), fill=color, width=round(width))
    draw.line((x, y, x, y + sy * length), fill=color, width=round(width))


# ---------------------------------------------------------------------- #
# Рамка з власного зображення
# ---------------------------------------------------------------------- #


def nine_slice_frame(source: Image.Image, width: int, height: int, border_pct: float, slice_pct: float) -> Image.Image:
    """Кути зображення переносяться без спотворень, краї розкладаються плитками, середина прозора.

    border_pct — ширина рамки на сторінці (% коротшої сторони сторінки);
    slice_pct — яка частина вихідного зображення вважається кутом/краєм (% його коротшої сторони).
    """
    src = source.convert("RGBA")
    sw, sh = src.size
    cut = max(1, min(round(min(sw, sh) * slice_pct / 100), sw // 2 - 1, sh // 2 - 1))
    band = max(1, min(round(min(width, height) * border_pct / 100), width // 2, height // 2))
    frame = Image.new("RGBA", (width, height), TRANSPARENT)

    corners = {
        (0, 0): (0, 0, cut, cut),
        (width - band, 0): (sw - cut, 0, sw, cut),
        (0, height - band): (0, sh - cut, cut, sh),
        (width - band, height - band): (sw - cut, sh - cut, sw, sh),
    }
    for position, box in corners.items():
        frame.alpha_composite(src.crop(box).resize((band, band), Image.Resampling.LANCZOS), position)

    edges = (
        ((cut, 0, sw - cut, cut), True, (band, 0)),
        ((cut, sh - cut, sw - cut, sh), True, (band, height - band)),
        ((0, cut, cut, sh - cut), False, (0, band)),
        ((sw - cut, cut, sw, sh - cut), False, (width - band, band)),
    )
    for box, horizontal, origin in edges:
        length = (width if horizontal else height) - 2 * band
        _tile_edge(frame, src.crop(box), horizontal, band, length, origin)
    return frame


def _tile_edge(frame: Image.Image, strip: Image.Image, horizontal: bool, band: int, length: int, origin) -> None:
    """Плитки краю в натуральних пропорціях, трохи розтягнуті, щоб лягти без залишку."""
    if length <= 0 or strip.width == 0 or strip.height == 0:
        return
    natural = strip.width * band / strip.height if horizontal else strip.height * band / strip.width
    count = max(1, round(length / max(1.0, natural)))
    edges = [round(i * length / count) for i in range(count + 1)]
    x, y = origin
    for start, end in zip(edges, edges[1:]):
        size = (end - start, band) if horizontal else (band, end - start)
        piece = strip.resize(size, Image.Resampling.LANCZOS)
        frame.alpha_composite(piece, (x + start, y) if horizontal else (x, y + start))
