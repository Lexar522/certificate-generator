"""Заготовки для нового шаблону: розмір сторінки, кольори й стартові шари."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from core.classic_preset import FIELD_LABELS, PATTERN_ASSET, classic_assets, classic_layers
from core.models import TemplateConfig

TITLE_FONT = "fonts/NotoSans-Bold.ttf"
BODY_FONT = "fonts/NotoSans-Regular.ttf"
REFERENCE_SIDE = 1754  # коротша сторона A4 при 300 DPI — від неї масштабуються розміри


@dataclass(frozen=True)
class Preset:
    key: str
    title: str
    description: str
    width: int
    height: int
    background: str
    text: str
    muted: str
    accent: str
    style: str = "modern"  # "modern" — мінімалістичний; "classic" — рамка й дві колонки


PRESETS: tuple[Preset, ...] = (
    Preset("landscape_light", "A4 горизонтально · світлий", "2480 × 1754, білий фон",
           2480, 1754, "#FFFFFF", "#1D1D1F", "#6E6E73", "#0071E3"),
    Preset("landscape_dark", "A4 горизонтально · темний", "2480 × 1754, темно-синій фон",
           2480, 1754, "#0B1736", "#FFFFFF", "#FFFFFFB3", "#E9B84C"),
    Preset("portrait_light", "A4 вертикально · світлий", "1754 × 2480, білий фон",
           1754, 2480, "#FFFFFF", "#1D1D1F", "#6E6E73", "#0071E3"),
    Preset("classic_bilingual", "Класичний двомовний · з рамкою",
           "A4 горизонтально: золота рамка, логотип, укр. та англ. колонки, печатка й підпис",
           2480, 1754, "#FFFFFF", "#1A1A1A", "#4A4A4A", "#1F4E9A", style="classic"),
    Preset("square_light", "Квадрат · світлий", "2000 × 2000 — для соцмереж",
           2000, 2000, "#F5F5F7", "#1D1D1F", "#6E6E73", "#0071E3"),
)


def preset_by_key(key: str) -> Preset:
    for preset in PRESETS:
        if preset.key == key:
            return preset
    raise KeyError(key)


def starter_config(preset: Preset, name: str) -> TemplateConfig:
    """Робочий шаблон для заготовки (класичний або мінімальний)."""
    if preset.style == "classic":
        return _classic_config(preset, name)
    return _modern_config(preset, name)


def starter_assets(preset: Preset, fonts_dir: Path) -> dict[str, Image.Image]:
    """Згенеровані зображення, які потрібні заготовці (відносний шлях → зображення)."""
    if preset.style == "classic":
        return classic_assets(preset.width, preset.height, fonts_dir)
    return {}


def _classic_config(preset: Preset, name: str) -> TemplateConfig:
    return TemplateConfig.model_validate(
        {
            "name": name,
            "canvas": {
                "width": preset.width, "height": preset.height, "background_color": preset.background,
                "background_image": PATTERN_ASSET, "background_fit": "stretch",
            },
            "output": {"format": "pdf"},
            "field_labels": FIELD_LABELS,
            "layers": classic_layers(preset.width, preset.height),
        }
    )


def _modern_config(preset: Preset, name: str) -> TemplateConfig:
    """Мінімальний робочий шаблон: заголовок, ПІБ, курс, дата, номер і QR-код."""
    w, h = preset.width, preset.height
    unit = min(w, h) / REFERENCE_SIDE
    margin = round(180 * unit)
    qr_size = round(260 * unit)

    def text(layer_id: str, label: str, y: float, size: int, color: str, **extra: Any) -> dict[str, Any]:
        return {
            "id": layer_id, "label": label, "type": "text", "font": BODY_FONT,
            "font_size": round(size * unit), "color": color, "align": "center", "x": w // 2, "y": round(y),
        } | extra

    wide = {"max_width": round(w * 0.8)}
    layers = [
        text("title", "Заголовок", h * 0.16, 120, preset.accent, text="Сертифікат", font=TITLE_FONT, uppercase=True),
        text("subtitle", "Підзаголовок", h * 0.30, 50, preset.muted, text="цим засвідчується, що"),
        text("full_name", "ПІБ отримувача", h * 0.37, 120, preset.text, font=TITLE_FONT, required=True,
             overflow="shrink", min_font_size=round(60 * unit), **wide),
        text("course_intro", "Текст перед курсом", h * 0.52, 46, preset.muted, text="успішно завершив(-ла) курс"),
        text("course_name", "Назва курсу", h * 0.58, 80, preset.text, font=TITLE_FONT, required=True,
             overflow="wrap", **wide),
        text("issue_date", "Дата видачі", h - margin - 60 * unit, 38, preset.muted,
             text="Дата видачі: {issue_date}", align="left", x=margin),
        text("certificate_number", "Номер сертифіката", h - margin, 32, preset.muted,
             text="№ {certificate_id}", align="left", x=margin),
        {
            "id": "verify_qr", "label": "QR-код перевірки", "type": "qr", "size": qr_size,
            "x": w - margin - qr_size, "y": h - margin - qr_size + round(40 * unit),
        },
    ]
    return TemplateConfig.model_validate(
        {
            "name": name,
            "canvas": {"width": w, "height": h, "background_color": preset.background},
            "output": {"format": "pdf"},
            "layers": layers,
        }
    )
