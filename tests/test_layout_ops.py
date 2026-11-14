import shutil
from pathlib import Path

import pytest

from core.exceptions import CertificateError
from core.models import ImageLayer, QrLayer, TextLayer, WatermarkLayer
from gui.canvas import _best_snap
from gui.document import EditorDocument
from gui.layer_actions import layer_subtitle, scaled_layer_changes
from gui.layout_ops import resize_changes
from renderers.pillow_renderer import PillowRenderer, RenderContext
from tests.conftest import PROJECT_ROOT

TEXT = {"type": "text", "font": "f.ttf"}


def test_watermark_scale_multiplies():
    layer = WatermarkLayer(id="w", type="watermark", path="w.png", scale=0.5)
    assert resize_changes(layer, 2.0, (100, 100)) == {"scale": 1.0}


def test_qr_size_has_minimum():
    layer = QrLayer(id="q", type="qr", size=100)
    assert resize_changes(layer, 0.01, (100, 100)) == {"size": 20}


def test_image_without_size_gets_width_from_rendered_sprite():
    layer = ImageLayer(id="i", type="image", path="a.png")
    assert resize_changes(layer, 1.5, (200, 100)) == {"width": 300}


def test_image_scales_only_given_dimensions():
    layer = ImageLayer(id="i", type="image", path="a.png", height=80)
    assert resize_changes(layer, 0.5, (999, 999)) == {"width": None, "height": 40}


def test_text_scales_font_and_wrap_width():
    layer = TextLayer(id="t", font_size=40, max_width=500, min_font_size=30, **TEXT)
    assert resize_changes(layer, 0.5, (0, 0)) == {"font_size": 20, "max_width": 250, "min_font_size": 20}


def test_non_positive_factor_is_rejected():
    with pytest.raises(ValueError):
        resize_changes(QrLayer(id="q", type="qr", size=100), 0, (1, 1))


@pytest.mark.parametrize(
    "edges, targets, expected",
    [
        ([100.0, 150.0, 200.0], [148.0], (-2.0, 148.0)),  # центр прилипає
        ([100.0, 150.0, 200.0], [300.0], (0.0, None)),  # задалеко
        ([10.0, 50.0], [12.0, 49.0], (-1.0, 49.0)),  # найближча ціль
    ],
)
def test_best_snap(edges, targets, expected):
    assert _best_snap(edges, targets, threshold=5) == expected


@pytest.fixture
def doc(tmp_path: Path) -> EditorDocument:
    target = tmp_path / "templates" / "default_tech"
    shutil.copytree(PROJECT_ROOT / "templates" / "default_tech", target)
    return EditorDocument(target)


def _sprite(doc: EditorDocument, layer_id: str):
    context = RenderContext(doc.preview_data(), doc.template_dir, doc.config)
    return PillowRenderer().render_layer(doc.layer(layer_id), context)


def test_set_layer_order_and_validation(doc):
    ids = [layer.id for layer in doc.config.layers]
    doc.set_layer_order(list(reversed(ids)))
    assert [layer.id for layer in doc.config.layers] == list(reversed(ids))
    with pytest.raises(CertificateError):
        doc.set_layer_order(ids[:-1])


def test_scaled_layer_keeps_requested_corner(doc):
    changes = scaled_layer_changes(PillowRenderer(), doc, "verify_qr", 0.5, 2000, 1300)
    doc.update_layer("verify_qr", changes)

    sprite = _sprite(doc, "verify_qr")
    assert (sprite.x, sprite.y) == (2000, 1300)
    assert sprite.image.size == (150, 150)


def test_scaled_centered_text_keeps_requested_corner(doc):
    doc.set_field_value("full_name", "Олексій Чорней")
    changes = scaled_layer_changes(PillowRenderer(), doc, "full_name", 0.5, 700, 650)
    doc.update_layer("full_name", changes)

    sprite = _sprite(doc, "full_name")
    assert (sprite.x, sprite.y) == (700, 650)
    assert doc.layer("full_name").font_size == 65


def test_layer_subtitles_describe_content(doc):
    assert layer_subtitle(doc.layer("title"), doc) == "Сертифікат"
    assert layer_subtitle(doc.layer("full_name"), doc) == "Змінне поле"
    doc.set_field_value("full_name", "Іван")
    assert layer_subtitle(doc.layer("full_name"), doc) == "«Іван»"
    assert layer_subtitle(doc.layer("brand_watermark"), doc).startswith("watermark.png")
