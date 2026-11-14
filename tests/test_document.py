import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from core.exceptions import CertificateError
from core.template_loader import load_template_config
from core.template_store import clone_template, import_asset
from gui.document import EditorDocument
from tests.conftest import PROJECT_ROOT


@pytest.fixture
def template_dir(tmp_path: Path) -> Path:
    target = tmp_path / "templates" / "default_tech"
    shutil.copytree(PROJECT_ROOT / "templates" / "default_tech", target)
    return target


@pytest.fixture
def doc(template_dir: Path) -> EditorDocument:
    return EditorDocument(template_dir)


def test_update_layer_returns_new_config_and_notifies(doc):
    events = []
    doc.subscribe(lambda kind, layer_id: events.append((kind, layer_id)))
    before = doc.config

    doc.update_layer("brand_watermark", {"opacity": 0.5})

    assert doc.layer("brand_watermark").opacity == 0.5
    assert before.layers[0].opacity == pytest.approx(0.1)  # старий знімок не змінено
    assert events == [("layer", "brand_watermark")]
    assert doc.is_dirty


def test_invalid_change_is_rejected_without_side_effects(doc):
    before = doc.config
    with pytest.raises(CertificateError):
        doc.update_layer("brand_watermark", {"opacity": 2})
    assert doc.config is before
    assert not doc.can_undo


def test_undo_redo_roundtrip(doc):
    doc.move_layer_by("title", 15, -5)
    moved = doc.layer("title")

    doc.undo()
    assert (doc.layer("title").x, doc.layer("title").y) == (moved.x - 15, moved.y + 5)
    doc.redo()
    assert doc.layer("title") == moved


def test_slider_changes_with_same_merge_key_form_one_undo_step(doc):
    for value in (0.2, 0.3, 0.4):
        doc.update_layer("brand_watermark", {"opacity": value}, merge_key="wm:opacity")
    doc.undo()
    assert doc.layer("brand_watermark").opacity == pytest.approx(0.1)


def test_add_duplicate_remove_and_reorder(doc):
    new_id = doc.add_layer({"type": "watermark", "path": "assets/logo.png", "opacity": 0.3})
    assert doc.config.layers[-1].id == new_id == "watermark_1"

    copy_id = doc.duplicate_layer(new_id)
    assert doc.layer(copy_id).x == doc.layer(new_id).x + 40

    doc.reorder_layer(copy_id, -100)
    assert doc.config.layers[0].id == copy_id

    doc.remove_layer(copy_id)
    assert not doc.has_layer(copy_id)


def test_text_mode_toggle_keeps_content(doc):
    doc.set_field_value("full_name", "Ірина")
    doc.set_text_mode("full_name", dynamic=False)
    assert doc.layer("full_name").text == "Ірина"

    doc.set_text_mode("full_name", dynamic=True)
    assert doc.layer("full_name").text is None
    assert doc.state.field_values["full_name"] == "Ірина"


def test_preview_data_uses_placeholders_but_export_does_not(doc):
    assert doc.preview_data().fields["course_name"] == "«Назва курсу»"
    assert "course_name" not in doc.export_data().fields


def test_invalid_certificate_id_falls_back_in_preview_only(doc):
    doc.set_certificate_id("кирилиця")
    assert doc.preview_data().certificate_id == "PREVIEW"
    with pytest.raises(CertificateError, match="ID сертифіката"):
        doc.export_data()


def test_save_writes_loadable_config(doc, template_dir):
    doc.update_layer("title", {"x": 100, "color": "#FF0000"})
    doc.save()

    reloaded = load_template_config(template_dir)
    assert reloaded.layers[2].x == 100 and reloaded.layers[2].color == "#FF0000"
    assert not doc.is_dirty
    json.loads((template_dir / "config.json").read_text(encoding="utf-8"))


def test_import_asset_copies_with_safe_unique_name(template_dir, tmp_path):
    source = tmp_path / "Мій логотип!.PNG"
    Image.new("RGBA", (4, 4)).save(source, format="PNG")

    first = import_asset(template_dir, source, "assets")
    second = import_asset(template_dir, source, "assets")

    assert first.startswith("assets/") and first.endswith(".png")
    assert first != second
    assert (template_dir / first).is_file()
    assert import_asset(template_dir, template_dir / first, "assets") == first


def test_clone_template_validates_name(template_dir):
    root = template_dir.parent
    assert (clone_template(root, template_dir, "my_copy") / "config.json").is_file()
    with pytest.raises(CertificateError):
        clone_template(root, template_dir, "../evil")
    with pytest.raises(CertificateError, match="уже існує"):
        clone_template(root, template_dir, "my_copy")
