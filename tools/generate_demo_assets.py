"""Генерує демонстраційні ресурси для шаблону default_tech.

Запуск (з кореня проєкту):  python -m tools.generate_demo_assets
Створює фон, водяний знак, логотип і тестовий підпис, а також копіює шрифти
Noto Sans з системи (якщо їх ще немає в templates/default_tech/fonts).
"""

import math
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = PROJECT_ROOT / "templates" / "default_tech"
SIGNS_DIR = PROJECT_ROOT / "assets" / "signs"
CANVAS_SIZE = (2480, 1754)  # A4 landscape @ 300 DPI
FONT_NAMES = ("NotoSans-Regular.ttf", "NotoSans-Bold.ttf")
SYSTEM_FONT_DIRS = (
    Path("/usr/share/fonts/noto"),
    Path("/usr/share/fonts/truetype/noto"),
    Path("/usr/share/fonts/google-noto"),
)

NAVY = (11, 23, 54)
NAVY_LIGHT = (24, 44, 94)
GRID = (30, 55, 105)
TEAL = (0, 194, 203)
GOLD = (233, 184, 76)
INK = (230, 235, 245, 255)


def make_background(path: Path) -> None:
    width, height = CANVAS_SIZE
    gradient = Image.linear_gradient("L").rotate(90).resize(CANVAS_SIZE)
    image = Image.composite(
        Image.new("RGB", CANVAS_SIZE, NAVY_LIGHT), Image.new("RGB", CANVAS_SIZE, NAVY), gradient
    )
    draw = ImageDraw.Draw(image)

    step = 80
    for x in range(0, width, step):
        draw.line([(x, 0), (x, height)], fill=GRID, width=1)
    for y in range(0, height, step):
        draw.line([(0, y), (width, y)], fill=GRID, width=1)

    margin, inset = 70, 22
    draw.rectangle([margin, margin, width - margin, height - margin], outline=TEAL, width=6)
    draw.rectangle(
        [margin + inset, margin + inset, width - margin - inset, height - margin - inset],
        outline=GOLD,
        width=2,
    )
    image.save(path, optimize=True)


def make_hexagon(size: int, color: tuple[int, int, int], stroke: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    center, radius = size / 2, size / 2 - stroke
    points = [
        (
            center + radius * math.cos(math.radians(60 * i - 30)),
            center + radius * math.sin(math.radians(60 * i - 30)),
        )
        for i in range(6)
    ]
    draw.polygon(points, outline=color + (255,), width=stroke)
    inner = [(center + (px - center) * 0.55, center + (py - center) * 0.55) for px, py in points]
    draw.polygon(inner, fill=color + (255,))
    draw.text((center, center), "</>", fill=NAVY + (255,), anchor="mm", font_size=size // 6)
    return image


def make_signature(path: Path) -> None:
    image = Image.new("RGBA", (600, 220), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    points = [(40 + x * 5, 120 + 45 * math.sin(x / 7) * math.exp(-x / 120)) for x in range(104)]
    draw.line(points, fill=INK, width=6, joint="curve")
    draw.line([(60, 170), (540, 150)], fill=INK, width=4)
    image.filter(ImageFilter.SMOOTH).save(path)


def copy_fonts(target_dir: Path) -> None:
    for name in FONT_NAMES:
        destination = target_dir / name
        if destination.exists():
            continue
        source = next((d / name for d in SYSTEM_FONT_DIRS if (d / name).is_file()), None)
        if source is None:
            print(f"[!] {name} не знайдено в системі — покладіть .ttf у {target_dir}", file=sys.stderr)
            continue
        shutil.copy2(source, destination)


def main() -> None:
    assets_dir = TEMPLATE_DIR / "assets"
    fonts_dir = TEMPLATE_DIR / "fonts"
    for directory in (assets_dir, fonts_dir, SIGNS_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    make_background(assets_dir / "background.png")
    make_hexagon(900, TEAL, 40).save(assets_dir / "watermark.png")
    make_hexagon(320, GOLD, 18).save(assets_dir / "logo.png")
    make_signature(SIGNS_DIR / "sign1.png")
    copy_fonts(fonts_dir)
    print(f"Демо-ресурси створено: {assets_dir}, {fonts_dir}, {SIGNS_DIR}")


if __name__ == "__main__":
    main()
