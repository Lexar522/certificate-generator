from datetime import date

import pytest
from pydantic import ValidationError

from core.models import CertificateData, QrLayer, TemplateConfig, TextLayer

TEXT_LAYER = {"type": "text", "font": "f.ttf", "font_size": 20}


def make_data(**overrides) -> dict:
    return {"template_name": "default_tech", "certificate_id": "ID-1", "issue_date": date(2026, 1, 1)} | overrides


def test_certificate_data_strips_field_values():
    data = CertificateData(**make_data(fields={"full_name": "  Іван  "}))
    assert data.fields["full_name"] == "Іван"


@pytest.mark.parametrize("template_name", ["../etc", "a/b", "", "with space"])
def test_rejects_unsafe_template_name(template_name):
    with pytest.raises(ValidationError):
        CertificateData(**make_data(template_name=template_name))


def test_rejects_blank_field_value():
    with pytest.raises(ValidationError, match="порожні значення"):
        CertificateData(**make_data(fields={"full_name": "   "}))


def test_certificate_data_is_immutable():
    data = CertificateData(**make_data())
    with pytest.raises(ValidationError):
        data.certificate_id = "OTHER"


@pytest.mark.parametrize("color", ["red", "#12", "#GGGGGG", "123456"])
def test_rejects_invalid_hex_color(color):
    with pytest.raises(ValidationError, match="HEX"):
        TextLayer(id="t", color=color, **TEXT_LAYER)


def test_rejects_min_font_size_above_font_size():
    with pytest.raises(ValidationError, match="min_font_size"):
        TextLayer(id="t", min_font_size=30, **TEXT_LAYER)


def test_qr_url_template_requires_placeholder():
    with pytest.raises(ValidationError, match="certificate_id"):
        QrLayer(id="qr", type="qr", size=100, url_template="https://example.com")


def test_opacity_must_be_between_zero_and_one():
    layer = {"id": "w", "type": "watermark", "path": "w.png", "opacity": 1.5}
    with pytest.raises(ValidationError):
        TemplateConfig(name="t", canvas={"width": 10, "height": 10}, layers=[layer])


def test_rejects_duplicate_layer_ids():
    layers = [{"id": "t", **TEXT_LAYER}, {"id": "t", **TEXT_LAYER}]
    with pytest.raises(ValidationError, match="дубльовані"):
        TemplateConfig(name="t", canvas={"width": 10, "height": 10}, layers=layers)


def test_unknown_layer_type_is_rejected():
    with pytest.raises(ValidationError):
        TemplateConfig(name="t", canvas={"width": 10, "height": 10}, layers=[{"id": "x", "type": "video"}])
