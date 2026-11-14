from pathlib import Path

from core.models import TemplateConfig
from core.template_catalog import describe_inputs, list_templates
from tests.conftest import PROJECT_ROOT

TEXT = {"type": "text", "font": "f.ttf", "font_size": 20}


def test_list_templates_returns_only_dirs_with_config(tmp_path: Path):
    (tmp_path / "good").mkdir()
    (tmp_path / "good" / "config.json").write_text("{}", encoding="utf-8")
    (tmp_path / "empty").mkdir()
    (tmp_path / "bad name").mkdir()
    (tmp_path / "bad name" / "config.json").write_text("{}", encoding="utf-8")

    assert list_templates(tmp_path) == ("good",)


def test_list_templates_missing_root_is_empty(tmp_path: Path):
    assert list_templates(tmp_path / "nope") == ()


def test_describe_inputs_skips_static_layers_and_uses_labels():
    config = TemplateConfig(
        name="t",
        canvas={"width": 10, "height": 10},
        layers=[
            {"id": "title", "text": "Static", **TEXT},
            {"id": "full_name", "label": "ПІБ", "required": True, **TEXT},
            {"id": "course_name", **TEXT},
            {"id": "logo", "type": "image", "path": "logo.png"},
            {"id": "sign", "type": "image"},
        ],
    )

    inputs = describe_inputs(config)

    assert [(f.id, f.label, f.required) for f in inputs.text_fields] == [
        ("full_name", "ПІБ", True),
        ("course_name", "Course name", False),
    ]
    assert [f.id for f in inputs.image_fields] == ["sign"]


def test_bundled_template_is_listed():
    assert "default_tech" in list_templates(PROJECT_ROOT / "templates")
