"""Можливості версії 1.2: фігури, багаторядковий і підкреслений текст, рамки,
класична двомовна заготовка та зміна розміру полотна."""

import shutil
from datetime import date
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont
from pydantic import ValidationError

from core.classic_preset import FIELD_LABELS
from core.exceptions import CertificateError
from core.models import CertificateData, FrameLayer, ShapeLayer, TemplateConfig, TextLayer
from core.ornaments import FRAME_STYLES, frame_image, honeycomb_background, placeholder_badge
from core.presets import preset_by_key, starter_assets, starter_config
from core.template_catalog import PLACEHOLDER_RE, describe_inputs
from core.template_loader import load_template_config
from core.template_store import create_template
from gui.document import EditorDocument
from gui.layer_actions import frame_payload, layer_subtitle, new_layer_payload
from gui.layout_ops import resize_changes
from gui.page_size import CUSTOM_FORMAT, detect_format, format_by_key, format_pixels, px_to_mm, resized_layers
from renderers.pillow_renderer import PillowRenderer, RenderContext
from renderers.text_layout import layout_text
from tests.conftest import DEMO_FONT, PROJECT_ROOT

FONTS = PROJECT_ROOT / "templates" / "default_tech" / "fonts"
DATA = CertificateData(template_name="t", certificate_id="T-1", issue_date=date(2026, 6, 30))


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(DEMO_FONT), size)


def _measure() -> ImageDraw.ImageDraw:
    return ImageDraw.Draw(Image.new("RGBA", (1, 1)))


def _context(tmp_path: Path) -> RenderContext:
    fonts = tmp_path / "fonts"
    fonts.mkdir(exist_ok=True)
    shutil.copy(DEMO_FONT, fonts / "font.ttf")
    config = TemplateConfig(
        name="t",
        canvas={"width": 400, "height": 300},
        layers=[ShapeLayer(id="s", type="shape", width=10, height=10, stroke_width=1)],
    )
    return RenderContext(DATA, tmp_path, config)


def _text(**extra) -> TextLayer:
    return TextLayer.model_validate(
        {"id": "t", "type": "text", "text": "ABC", "font": "fonts/font.ttf", "font_size": 40} | extra
    )


# ------------------------------- текст ------------------------------- #


def test_explicit_newlines_become_separate_lines():
    block = layout_text(_measure(), "перший\n\nтретій", _font, 30, None, "wrap", 12)
    assert block.lines == ("перший", "", "третій")


def test_each_paragraph_wraps_separately():
    block = layout_text(_measure(), "один два три чотири\nп'ять", _font, 30, 150, "wrap", 12)
    assert len(block.lines) > 2 and block.lines[-1] == "п'ять"


def test_shrink_fits_widest_paragraph():
    block = layout_text(_measure(), "коротко\nдуже довгий рядок тексту", _font, 60, 300, "shrink", 8)
    assert block.font.size < 60 and len(block.lines) == 2


def test_underline_extends_text_sprite(tmp_path: Path):
    context, renderer = _context(tmp_path), PillowRenderer()
    plain = renderer.render_layer(_text(), context)
    underlined = renderer.render_layer(_text(underline=True), context)
    assert underlined.image.height > plain.image.height
    assert underlined.image.getchannel("A").getbbox()[3] == underlined.image.height


def test_layer_text_may_be_longer_than_field_values():
    assert _text(text="а" * 1500).text
    with pytest.raises(ValidationError):
        _text(text="а" * 2001)


# ------------------------------- фігури ------------------------------- #


@pytest.mark.parametrize("shape, size", [("rectangle", (200, 80)), ("ellipse", (200, 80)), ("line", (200, 6))])
def test_shape_sprite_size(tmp_path: Path, shape, size):
    layer = ShapeLayer(id="s", type="shape", shape=shape, width=200, height=80, stroke_width=6, x=5, y=7)
    sprite = PillowRenderer().render_layer(layer, _context(tmp_path))
    assert sprite.image.size == size and (sprite.x, sprite.y) == (5, 7)


def test_filled_rectangle_paints_fill_color(tmp_path: Path):
    layer = ShapeLayer(id="s", type="shape", width=100, height=50, fill_color="#FF0000", stroke_width=0)
    sprite = PillowRenderer().render_layer(layer, _context(tmp_path))
    assert sprite.image.getpixel((50, 25)) == (255, 0, 0, 255)


def test_invisible_shape_is_rejected():
    with pytest.raises(ValidationError, match="невидимою"):
        ShapeLayer(id="s", type="shape", width=10, height=10, stroke_width=0)


def test_shape_resize_scales_size_and_stroke():
    layer = ShapeLayer(id="s", type="shape", width=100, height=40, stroke_width=4, corner_radius=10)
    assert resize_changes(layer, 2.0, (0, 0)) == {"width": 200, "height": 80, "stroke_width": 8, "corner_radius": 20}


# ------------------------------- прикраси ------------------------------- #


@pytest.mark.parametrize("style", FRAME_STYLES)
def test_frame_matches_page_and_leaves_center_transparent(style):
    frame = frame_image(600, 400, style)
    assert frame.size == (600, 400)
    assert frame.getpixel((300, 200))[3] == 0
    assert frame.getchannel("A").getbbox() is not None


def test_unknown_frame_style_is_rejected():
    with pytest.raises(ValueError):
        frame_image(100, 100, "neon")


def test_honeycomb_and_placeholder_sizes(tmp_path: Path):
    assert honeycomb_background(300, 200).size == (300, 200)
    badge = placeholder_badge(120, 60, "Підпис", tmp_path / "missing.ttf", round_shape=False)
    assert badge.size == (120, 60)  # без шрифту — запасний вбудований


# --------------------------- класична заготовка --------------------------- #


@pytest.fixture
def classic_dir(tmp_path: Path) -> Path:
    preset = preset_by_key("classic_bilingual")
    return create_template(tmp_path, "classic", starter_config(preset, "Класичний"), FONTS, starter_assets(preset, FONTS))


def test_classic_template_asks_for_names_and_program(classic_dir: Path):
    config = load_template_config(classic_dir)
    keys = {field.id for field in describe_inputs(config).text_fields}
    assert {"full_name", "full_name_en", *FIELD_LABELS} <= keys


def test_classic_layer_ids_do_not_shadow_placeholders(classic_dir: Path):
    config = load_template_config(classic_dir)
    placeholders = {
        key
        for layer in config.layers
        if isinstance(layer, TextLayer) and layer.text
        for key in PLACEHOLDER_RE.findall(layer.text)
    }
    assert not placeholders & {layer.id for layer in config.layers}


def test_classic_template_renders_with_all_assets(classic_dir: Path):
    data = CertificateData(
        template_name="classic",
        certificate_id="2026-1",
        issue_date=date(2026, 6, 30),
        fields={
            "full_name": "Петренко Іванна",
            "full_name_en": "Petrenko Ivanna",
            "program": "Основи танцю",
            "program_en": "Dance Basics",
        },
    )
    assert PillowRenderer().compose(data, classic_dir).size == (2480, 1754)


def test_create_template_reports_missing_fonts(tmp_path: Path):
    empty_fonts = tmp_path / "no_fonts"
    empty_fonts.mkdir()
    preset = preset_by_key("classic_bilingual")
    with pytest.raises(CertificateError, match="шрифтів"):
        create_template(tmp_path / "out", "x", starter_config(preset, "X"), empty_fonts)
    assert not (tmp_path / "out" / "x").exists()


# ------------------------------ розмір полотна ------------------------------ #


def test_a4_pixels_depend_on_dpi_and_orientation():
    a4 = format_by_key("a4")
    assert format_pixels(a4, 300, landscape=True) == (3508, 2480)
    assert format_pixels(a4, 150, landscape=False) == (1240, 1754)
    assert format_pixels(format_by_key("full_hd"), 300, landscape=True) == (1920, 1080)


def test_detect_format_and_mm():
    assert detect_format(3508, 2480, 300) == "a4"
    assert detect_format(1234, 567, 300) == CUSTOM_FORMAT
    assert round(px_to_mm(2480, 300)) == 210


def test_resize_scales_uniformly_centers_and_stretches_frames(classic_dir: Path):
    config = load_template_config(classic_dir)
    layers = {layer.id: layer for layer in resized_layers(config, classic_dir, 1754, 2480)}
    old = {layer.id: layer for layer in config.layers}
    factor = 1754 / 2480

    assert layers["frame"] == old["frame"]  # рамка сама малюється під розмір сторінки
    assert layers["heading_uk"].font_size == round(old["heading_uk"].font_size * factor)
    assert layers["logo"].x == round(old["logo"].x * factor)
    assert layers["logo"].y > old["logo"].y * factor  # зсув до центру по вертикалі


def test_document_resize_is_one_undo_step(classic_dir: Path):
    doc = EditorDocument(classic_dir)
    before = doc.config
    doc.resize_canvas(1754, 2480, scale_content=True)
    assert (doc.config.canvas.width, doc.config.canvas.height) == (1754, 2480)
    doc.undo()
    assert doc.config == before


def test_resize_without_scaling_keeps_layers(classic_dir: Path):
    doc = EditorDocument(classic_dir)
    layers = doc.config.layers
    doc.resize_canvas(3000, 2000, scale_content=False)
    assert doc.config.layers == layers and doc.config.canvas.width == 3000


# ------------------------------ шари в редакторі ------------------------------ #


def test_frame_layer_goes_to_bottom_locked(classic_dir: Path):
    doc = EditorDocument(classic_dir)
    layer_id = doc.add_layer(frame_payload(doc, "classic"), 0)
    layer = doc.config.layers[0]
    assert layer.id == layer_id and layer.locked and layer.style == "classic"
    with pytest.raises(CertificateError):
        frame_payload(doc, "neon")


@pytest.mark.parametrize("size", [(600, 400), (400, 600)])
def test_frame_layer_always_matches_canvas(tmp_path: Path, size):
    context = _context(tmp_path)
    context = RenderContext(DATA, tmp_path, context.config.model_copy(
        update={"canvas": context.config.canvas.model_copy(update={"width": size[0], "height": size[1]})}
    ))
    sprite = PillowRenderer().render_layer(FrameLayer(id="f", type="frame", style="minimal"), context)
    assert sprite.image.size == size and (sprite.x, sprite.y) == (0, 0)


def test_new_shape_layer_is_centered(classic_dir: Path):
    doc = EditorDocument(classic_dir)
    payload = new_layer_payload("shape", doc, lambda: None, lambda: None)
    layer = doc.layer(doc.add_layer(payload))
    assert abs(layer.x + layer.width / 2 - doc.config.canvas.width / 2) <= 1
    assert layer_subtitle(layer, doc).startswith("Прямокутник")
