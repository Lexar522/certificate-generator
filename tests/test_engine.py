from pathlib import Path

import pytest
from PIL import Image

from core import (
    AssetNotFoundError,
    CertificateEngine,
    CertificateError,
    FontLoadError,
    MissingFieldError,
    TemplateConfigError,
    TemplateNotFoundError,
)
from tests.conftest import PROJECT_ROOT, write_config


def test_generates_png_with_expected_name_and_size(engine, certificate):
    result = engine.generate(certificate)

    assert result.name == "cert_TEST-001.png"
    with Image.open(result) as image:
        assert image.size == (400, 300)


@pytest.mark.parametrize("output_format", ["jpg", "pdf"])
def test_output_format_override(engine, certificate, output_format):
    result = engine.generate(certificate, output_format=output_format)
    assert result.suffix == f".{output_format}"
    assert result.stat().st_size > 0


def test_accepts_plain_dict_and_validates_it(engine, certificate):
    result = engine.generate(certificate.model_dump())
    assert result.exists()


def test_invalid_input_raises_certificate_error(engine):
    with pytest.raises(CertificateError, match="Некоректні дані"):
        engine.generate({"template_name": "test_tpl"})


def test_missing_template_raises(engine, certificate):
    with pytest.raises(TemplateNotFoundError):
        engine.generate(certificate.model_copy(update={"template_name": "nope"}))


def test_broken_json_raises_config_error(engine, certificate, templates_root):
    (templates_root / "test_tpl" / "config.json").write_text("{ broken", encoding="utf-8")
    with pytest.raises(TemplateConfigError, match="битий JSON"):
        engine.generate(certificate)


def test_schema_violation_reports_location(engine, certificate, templates_root, minimal_config):
    write_config(templates_root / "test_tpl", minimal_config | {"canvas": {"width": -1, "height": 10}})
    with pytest.raises(TemplateConfigError, match="canvas.width"):
        engine.generate(certificate)


def test_missing_font_raises(engine, certificate, templates_root):
    (templates_root / "test_tpl" / "fonts" / "font.ttf").unlink()
    with pytest.raises(FontLoadError, match="не існує"):
        engine.generate(certificate)


def test_corrupted_font_raises(engine, certificate, templates_root):
    (templates_root / "test_tpl" / "fonts" / "font.ttf").write_bytes(b"not a font")
    with pytest.raises(FontLoadError, match="пошкоджений"):
        engine.generate(certificate)


def test_required_field_missing_raises(engine, certificate):
    with pytest.raises(MissingFieldError, match="full_name"):
        engine.generate(certificate.model_copy(update={"fields": {}}))


def test_missing_dynamic_image_raises(engine, certificate, templates_root, minimal_config):
    layers = minimal_config["layers"] + [{"id": "sign", "type": "image", "x": 0, "y": 0}]
    write_config(templates_root / "test_tpl", minimal_config | {"layers": layers})
    data = certificate.model_copy(update={"images": {"sign": "/no/such/file.png"}})
    with pytest.raises(AssetNotFoundError, match="sign"):
        engine.generate(data)


def test_path_traversal_in_config_is_rejected(engine, certificate, templates_root, minimal_config):
    canvas = minimal_config["canvas"] | {"background_image": "../../secret.png"}
    write_config(templates_root / "test_tpl", minimal_config | {"canvas": canvas})
    with pytest.raises(TemplateConfigError, match="виходить за межі"):
        engine.generate(certificate)


def test_image_layer_keeps_aspect_ratio(engine, certificate, templates_root, minimal_config):
    layer = {"id": "logo", "type": "image", "path": "assets/red.png", "x": 0, "y": 0, "width": 200, "height": 200}
    write_config(templates_root / "test_tpl", minimal_config | {"layers": [layer]})

    with Image.open(engine.generate(certificate)) as image:
        rgb = image.convert("RGB")
        assert rgb.getpixel((199, 99)) == (255, 0, 0)  # 200x100: ширина вписана
        assert rgb.getpixel((10, 150)) == (255, 255, 255)  # нижче — фон


def test_watermark_opacity_blends_with_background(engine, certificate, templates_root, minimal_config):
    layer = {"id": "wm", "type": "watermark", "path": "assets/red.png", "x": 0, "y": 0, "opacity": 0.5}
    write_config(templates_root / "test_tpl", minimal_config | {"layers": [layer]})

    with Image.open(engine.generate(certificate)) as image:
        red, green, _ = image.convert("RGB").getpixel((10, 10))
        assert red == 255 and 120 <= green <= 135


def test_qr_layer_is_rendered(engine, certificate, templates_root, minimal_config):
    layer = {"id": "qr", "type": "qr", "x": 10, "y": 10, "size": 150}
    write_config(templates_root / "test_tpl", minimal_config | {"layers": [layer]})

    with Image.open(engine.generate(certificate)) as image:
        colors = {color for _, color in image.convert("L").crop((10, 10, 160, 160)).getcolors()}
        assert colors == {0, 255}


def test_shrink_keeps_text_within_max_width(engine, certificate, templates_root, minimal_config):
    layer = minimal_config["layers"][0] | {"x": 10, "align": "left", "max_width": 150, "min_font_size": 8}
    write_config(templates_root / "test_tpl", minimal_config | {"layers": [layer]})
    data = certificate.model_copy(update={"fields": {"full_name": "Дуже довге ім'я учасника курсу"}})

    with Image.open(engine.generate(data)) as image:
        bbox = Image.eval(image.convert("L"), lambda v: 255 - v).getbbox()
        assert bbox[2] <= 10 + 150 + 2


def test_missing_templates_dir_raises(tmp_path: Path):
    with pytest.raises(CertificateError, match="Директорію шаблонів"):
        CertificateEngine(templates_dir=tmp_path / "missing")


def test_bundled_default_template_renders(tmp_path, certificate):
    engine = CertificateEngine(templates_dir=PROJECT_ROOT / "templates", output_dir=tmp_path)
    data = certificate.model_copy(
        update={"template_name": "default_tech", "fields": {"full_name": "А", "course_name": "Б", "birth_date": "01.01.2000"}}
    )
    with Image.open(engine.generate(data)) as image:
        assert image.size == (2480, 1754)


def test_wrap_splits_long_text_into_lines(engine, certificate, templates_root, minimal_config):
    layer = minimal_config["layers"][0] | {"max_width": 200, "overflow": "wrap"}
    write_config(templates_root / "test_tpl", minimal_config | {"layers": [layer]})
    data = certificate.model_copy(update={"fields": {"full_name": "Перше Друге Третє Четверте"}})

    with Image.open(engine.generate(data)) as image:
        bbox = Image.eval(image.convert("L"), lambda v: 255 - v).getbbox()
        assert bbox[3] - bbox[1] > 32 * 2  # щонайменше два рядки
        assert bbox[2] - bbox[0] <= 200 + 2


def test_static_text_placeholders_are_filled(certificate):
    from core.models import TemplateConfig
    from renderers.pillow_renderer import RenderContext, text_value

    config = TemplateConfig(
        name="t",
        date_format="%Y/%m/%d",
        canvas={"width": 10, "height": 10},
        layers=[{"id": "info", "type": "text", "font": "f.ttf", "font_size": 10,
                 "text": "{certificate_id} від {issue_date}"}],
    )
    context = RenderContext(data=certificate, template_dir=Path("."), config=config)
    assert text_value(config.layers[0], context) == "TEST-001 від 2026/01/15"
