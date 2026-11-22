"""Можливості версії 1.1: тема, заготовки шаблонів, буфер обміну шарів, замок."""

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from core.exceptions import CertificateError
from core.models import CertificateData
from core.presets import PRESETS, preset_by_key, starter_config
from core.template_loader import load_template_config
from core.template_store import create_template
from gui import theme
from gui.document import EditorDocument
from gui.layer_actions import layer_to_clipboard, paste_payload
from gui.new_template_dialog import folder_from_title
from renderers.pillow_renderer import PillowRenderer
from tests.conftest import PROJECT_ROOT

FONTS = PROJECT_ROOT / "templates" / "default_tech" / "fonts"


# ------------------------------- тема ------------------------------- #


def test_dark_and_light_palettes_differ_and_use_accent():
    light = theme.build_palette(dark=False, accent="green")
    dark = theme.build_palette(dark=True, accent="green")
    assert not light.is_dark and dark.is_dark
    assert light.window != dark.window and light.text != dark.text
    assert light.accent == theme.ACCENTS["green"][1].lower()
    assert dark.accent == theme.ACCENTS["green"][2].lower()


def test_unknown_accent_falls_back_to_default():
    assert theme.build_palette(False, "rainbow").accent == theme.ACCENTS[theme.DEFAULT_ACCENT][1].lower()


def test_module_attributes_follow_current_palette():
    assert theme.ACCENT == theme.palette().accent
    assert theme.TEXT_SECONDARY == theme.palette().text_secondary
    with pytest.raises(AttributeError):
        theme.NOT_A_COLOR  # noqa: B018


def test_stylesheet_contains_palette_colors():
    dark = theme.build_palette(True)
    css = theme.stylesheet(dark)
    assert dark.window in css and dark.accent in css


# ------------------------------ заготовки ------------------------------ #


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.key)
def test_every_preset_creates_renderable_template(tmp_path: Path, preset):
    template_dir = create_template(tmp_path, preset.key, starter_config(preset, preset.title), FONTS)
    config = load_template_config(template_dir)
    assert (config.canvas.width, config.canvas.height) == (preset.width, preset.height)

    data = CertificateData(
        template_name=preset.key,
        certificate_id="T-1",
        issue_date=date(2026, 6, 30),
        fields={"full_name": "Іван Петренко", "course_name": "Python"},
    )
    image = PillowRenderer().compose(data, template_dir, config)
    assert image.size == (preset.width, preset.height)


def test_create_template_rejects_bad_or_existing_folder(tmp_path: Path):
    config = starter_config(preset_by_key("landscape_light"), "Тест")
    create_template(tmp_path, "one", config, FONTS)
    with pytest.raises(CertificateError, match="уже існує"):
        create_template(tmp_path, "one", config, FONTS)
    with pytest.raises(CertificateError):
        create_template(tmp_path, "../evil", config, FONTS)


@pytest.mark.parametrize(
    "title, folder",
    [("Курс Python 2026", "kurs_python_2026"), ("Щасливий ювілей!", "shchaslyvyi_iuvilei"), ("", "new_template")],
)
def test_folder_from_title_transliterates(title, folder):
    assert folder_from_title(title) == folder


# --------------------------- буфер обміну --------------------------- #


@pytest.fixture
def docs(tmp_path: Path) -> tuple[EditorDocument, EditorDocument]:
    source = tmp_path / "templates" / "default_tech"
    shutil.copytree(PROJECT_ROOT / "templates" / "default_tech", source)
    target = create_template(
        tmp_path / "templates", "blank", starter_config(preset_by_key("landscape_light"), "Порожній"), FONTS
    )
    return EditorDocument(source), EditorDocument(target)


def test_paste_within_template_offsets_and_gets_new_id(docs):
    source, _ = docs
    payload = paste_payload(layer_to_clipboard(source.layer("title"), source), source)
    new_id = source.add_layer(payload)

    assert new_id != "title"
    assert source.layer(new_id).x == source.layer("title").x + 40
    assert source.layer(new_id).text == source.layer("title").text


def test_paste_into_other_template_copies_asset(docs):
    source, target = docs
    raw = layer_to_clipboard(source.layer("brand_watermark"), source)

    new_id = target.add_layer(paste_payload(raw, target))

    copied = target.template_dir / target.layer(new_id).path
    assert copied.is_file() and copied.is_relative_to(target.template_dir)


@pytest.mark.parametrize(
    "raw", [b"not json", json.dumps({"layer": {"type": "video"}, "template_dir": "/"}).encode()]
)
def test_paste_rejects_foreign_clipboard(docs, raw):
    _, target = docs
    with pytest.raises(CertificateError):
        paste_payload(raw, target)


def test_paste_blocks_path_traversal_from_clipboard(docs):
    source, target = docs
    clip = json.loads(layer_to_clipboard(source.layer("brand_watermark"), source))
    clip["layer"]["path"] = "../../../etc/passwd"
    with pytest.raises(CertificateError, match="за межі"):
        paste_payload(json.dumps(clip).encode(), target)


# -------------------------------- замок -------------------------------- #


def test_lock_flag_roundtrips_through_save(docs):
    source, _ = docs
    source.update_layer("title", {"locked": True})
    source.save()
    saved = {layer.id: layer for layer in load_template_config(source.template_dir).layers}
    assert saved["title"].locked is True
