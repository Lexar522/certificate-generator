"""Заготовка «Класичний двомовний»: рамка, логотип, дві колонки (укр / англ), печатка й підпис.

Розміри задано для A4 горизонтально (2480 × 1754) і масштабуються під розмір заготовки.
Логотип, печатка та підпис — пунктирні заглушки: їх замінюють власними файлами в редакторі.
"""

from pathlib import Path
from typing import Any

from PIL import Image

from core.ornaments import honeycomb_background, placeholder_badge

SERIF = "fonts/NotoSerif-Regular.ttf"
SERIF_BOLD = "fonts/NotoSerif-Bold.ttf"
REFERENCE_WIDTH, REFERENCE_HEIGHT = 2480, 1754
TEXT_COLOR = "#1A1A1A"
BODY, HEADING = 36, 40

PATTERN_ASSET = "assets/pattern_honeycomb.png"
LOGO_ASSET = "assets/logo_placeholder.png"
STAMP_ASSET = "assets/stamp_placeholder.png"
SIGNATURE_ASSET = "assets/signature_placeholder.png"
LOGO_SIZE, STAMP_SIZE, SIGNATURE_SIZE = 420, 340, (420, 220)

FIELD_LABELS = {
    "program": "Назва програми (укр.)",
    "program_en": "Назва програми (англ.)",
}

LEFT_COLUMN = {
    "heading": "СЕРТИФІКАТ",
    "intro": "про проходження навчання в рамках\nсертифікатної програми",
    "program": "«{program}»",
    "series": "серія СП № {certificate_id}\nвід {issue_date} р.",
    "body": "пройшов (-ла) навчання за середньостроковою\nсертифікатною програмою\n"
            "в обсязі 5 кредитів / 150 годин\nформа навчання – денна",
    "modules": "Змістові модулі:\nЗМ 1. Назва першого змістового модуля\nЗМ 2. Назва другого змістового модуля",
}
RIGHT_COLUMN = {
    "heading": "CERTIFICATE",
    "intro": "of certificate program completion",
    "program": "“{program_en}”",
    "series": "series SP № {certificate_id}\ndate of issue {issue_date}",
    "body": "has completed a medium-term\n150 hours / 5 credits certificate program\n\nmode of study – full-time",
    "modules": "Content modules:\nCM 1. Title of the first content module\nCM 2. Title of the second content module",
}


def classic_layers(width: int, height: int) -> list[dict[str, Any]]:
    sx, sy = width / REFERENCE_WIDTH, height / REFERENCE_HEIGHT
    unit = min(sx, sy)

    def px(value: float) -> int:
        return round(value * unit)

    def text(layer_id: str, label: str, x: float, y: float, value: str | None, **extra: Any) -> dict[str, Any]:
        return {
            "id": layer_id, "label": label, "type": "text", "text": value, "font": SERIF,
            "font_size": px(BODY), "color": TEXT_COLOR, "align": "center",
            "x": round(x * sx), "y": round(y * sy), "line_spacing": 1.25,
        } | extra

    column_width = px(1000)
    layers = [
        {"id": "frame", "label": "Рамка", "type": "frame", "style": "gold"},
        {"id": "logo", "label": "Логотип (замініть своїм)", "type": "image", "path": LOGO_ASSET,
         "x": round(150 * sx), "y": round(130 * sy), "width": px(LOGO_SIZE)},
        text("institution", "Назва закладу", 1450, 270, "НАЗВА ЗАКЛАДУ ОСВІТИ\nINSTITUTION NAME",
             font=SERIF_BOLD, font_size=px(HEADING), line_spacing=2.0),
    ]
    for side, x, content in (("uk", 670, LEFT_COLUMN), ("en", 1810, RIGHT_COLUMN)):
        lang = "укр." if side == "uk" else "англ."
        bold = {"font": SERIF_BOLD, "font_size": px(HEADING)}
        layers += [
            text(f"heading_{side}", f"Заголовок ({lang})", x, 540, content["heading"], **bold),
            text(f"intro_{side}", f"Вступ ({lang})", x, 595, content["intro"], max_width=column_width, overflow="wrap"),
            text(f"program_title_{side}", f"Програма ({lang})", x, 690, content["program"], font=SERIF_BOLD,
                 max_width=column_width, overflow="shrink"),
            text(f"series_{side}", f"Серія та дата ({lang})", x, 740, content["series"]),
            text(f"body_{side}", f"Опис навчання ({lang})", x, 905, content["body"], max_width=column_width, overflow="wrap"),
        ]
    layers += [
        text("full_name", "ПІБ (укр.)", 670, 845, None, font=SERIF_BOLD, uppercase=True, underline=True,
             required=True, max_width=column_width, overflow="shrink"),
        text("full_name_en", "ПІБ латиницею", 1810, 845, None, font=SERIF_BOLD, uppercase=True, underline=True,
             required=True, max_width=column_width, overflow="shrink"),
        text("modules_uk", "Змістові модулі (укр.)", 140, 1140, LEFT_COLUMN["modules"], align="left",
             max_width=px(1040), overflow="wrap"),
        text("modules_en", "Змістові модулі (англ.)", 1300, 1140, RIGHT_COLUMN["modules"], align="left",
             max_width=px(1040), overflow="wrap"),
        text("position", "Посада", 140, 1480, "Ректор / Rector", align="left"),
        {"id": "stamp", "label": "Печатка (замініть своєю)", "type": "image", "path": STAMP_ASSET,
         "x": round(930 * sx), "y": round(1330 * sy), "width": px(STAMP_SIZE)},
        {"id": "signature", "label": "Підпис (замініть своїм)", "type": "image", "path": SIGNATURE_ASSET,
         "x": round(1230 * sx), "y": round(1360 * sy), "width": px(SIGNATURE_SIZE[0])},
        text("signer", "Підписант", 2340, 1480, "Ім'я ПРІЗВИЩЕ / Name SURNAME", align="right"),
    ]
    return layers


def classic_assets(width: int, height: int, fonts_dir: Path) -> dict[str, Image.Image]:
    """Зображення, на які посилаються шари заготовки (шляхи відносно папки шаблону)."""
    unit = min(width / REFERENCE_WIDTH, height / REFERENCE_HEIGHT)
    font = fonts_dir / "NotoSans-Bold.ttf"

    def size(value: int) -> int:
        return max(16, round(value * unit))

    return {
        PATTERN_ASSET: honeycomb_background(width, height),
        LOGO_ASSET: placeholder_badge(size(LOGO_SIZE), size(LOGO_SIZE), "ЛОГОТИП", font),
        STAMP_ASSET: placeholder_badge(size(STAMP_SIZE), size(STAMP_SIZE), "М. П.", font),
        SIGNATURE_ASSET: placeholder_badge(size(SIGNATURE_SIZE[0]), size(SIGNATURE_SIZE[1]), "Підпис", font, round_shape=False),
    }
