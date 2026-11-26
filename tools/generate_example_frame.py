"""Генерує приклад власної рамки-зображення: examples/frame_art_deco.png.

Запуск (з кореня проєкту):  python -m tools.generate_example_frame
PNG із прозорою серединою в стилі ар-деко — для пункту «+ Додати → Рамка → Зі свого зображення…».
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT = PROJECT_ROOT / "examples" / "frame_art_deco.png"
SIZE = 1200  # квадратне джерело: кути — 25% сторони
SCALE = 3  # малюємо збільшеним і зменшуємо — згладжені лінії
NAVY, GOLD, GOLD_LIGHT = (20, 33, 61, 255), (190, 146, 60, 255), (232, 200, 120, 255)


def _corner(draw: ImageDraw.ImageDraw, size: int) -> None:
    """Лівий верхній кут; решту отримуємо дзеркаленням."""
    u = size / 100
    for i in range(7):  # віяло променів
        angle = math.pi / 2 * (i + 0.5) / 7
        end = (6 * u + 17 * u * math.cos(angle), 6 * u + 17 * u * math.sin(angle))
        draw.line((6 * u, 6 * u, *end), fill=GOLD, width=round(0.5 * u))
    draw.pieslice((-6 * u, -6 * u, 18 * u, 18 * u), 0, 90, outline=GOLD, width=round(0.7 * u))
    for step, color in ((2.0, NAVY), (9.5, GOLD), (11.5, NAVY)):  # ступінчасті куточки
        draw.line((step * u, 22 * u, step * u, step * u, 22 * u, step * u), fill=color, width=round(0.9 * u), joint="curve")
    draw.rectangle((20 * u, 20 * u, 23.5 * u, 23.5 * u), fill=GOLD)


def _edges(draw: ImageDraw.ImageDraw, size: int) -> None:
    u = size / 100
    for offset, color in ((2.0, NAVY), (9.5, GOLD), (11.5, NAVY)):
        draw.line((22 * u, offset * u, 78 * u, offset * u), fill=color, width=round(0.9 * u))
        draw.line((offset * u, 22 * u, offset * u, 78 * u), fill=color, width=round(0.9 * u))
    for x in range(28, 76, 8):  # ритм ромбів на краях
        for cx, cy in ((x * u, 5.75 * u), (5.75 * u, x * u)):
            r = 1.6 * u
            draw.polygon(((cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)), fill=GOLD_LIGHT, outline=GOLD)


def build() -> Image.Image:
    big = SIZE * SCALE
    quarter = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(quarter)
    _corner(draw, big)
    _edges(draw, big)
    left_top = quarter.crop((0, 0, big // 2, big // 2))
    full = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    full.alpha_composite(left_top, (0, 0))
    full.alpha_composite(left_top.transpose(Image.Transpose.FLIP_LEFT_RIGHT), (big // 2, 0))
    full.alpha_composite(left_top.transpose(Image.Transpose.FLIP_TOP_BOTTOM), (0, big // 2))
    full.alpha_composite(left_top.transpose(Image.Transpose.ROTATE_180), (big // 2, big // 2))
    return full.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    build().save(OUTPUT, optimize=True)
    print(f"Збережено {OUTPUT.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
