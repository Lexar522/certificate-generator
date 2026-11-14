import io
import re
import urllib.error
from datetime import date
from pathlib import Path

import pytest
from PIL import Image

from core.batch import (
    BatchProfile,
    build_items,
    load_profile,
    parse_date,
    render_filename,
    run_batch,
    save_profile,
    suggest_columns,
    suggest_special_column,
    unique_filename,
)
from core.exceptions import CertificateError
from core.table_source import (
    TableData,
    TableSourceError,
    fetch_google_sheet,
    google_sheet_csv_url,
    load_table,
    parse_csv_text,
)
from core.template_catalog import describe_inputs
from core.template_loader import load_template_config
from tests.conftest import PROJECT_ROOT

TEMPLATE_DIR = PROJECT_ROOT / "templates" / "default_tech"
STUDENTS_CSV = PROJECT_ROOT / "examples" / "students.csv"
SHEET_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
PDF_COUNT_RE = re.compile(rb"/Count (\d+)")


@pytest.fixture
def config():
    return load_template_config(TEMPLATE_DIR)


@pytest.fixture
def table():
    return load_table(str(STUDENTS_CSV))


def _profile(**overrides) -> BatchProfile:
    columns = {"full_name": "ПІБ студента", "birth_date": "Дата народження", "course_name": "Курс"}
    return BatchProfile(columns=columns, **overrides)


# --------------------------- джерела даних --------------------------- #


def test_parse_csv_detects_semicolon_and_pads_rows():
    table = parse_csv_text("ПІБ;Дата\nІван;01.01.2000\nОля\n")
    assert table.headers == ("ПІБ", "Дата")
    assert table.rows == (("Іван", "01.01.2000"), ("Оля", ""))


def test_parse_csv_names_empty_and_duplicate_headers():
    table = parse_csv_text("Ім'я,,Ім'я\na,b,c\n")
    assert table.headers == ("Ім'я", "Колонка 2", "Ім'я (2)")


@pytest.mark.parametrize("text", ["", "ПІБ,Дата\n"])
def test_parse_csv_rejects_empty_tables(text):
    with pytest.raises(TableSourceError):
        parse_csv_text(text)


def test_load_csv_supports_windows_1251(tmp_path: Path):
    path = tmp_path / "group.csv"
    path.write_bytes("ПІБ\nПетренко\n".encode("cp1251"))
    assert load_table(str(path)).rows == (("Петренко",),)


def test_google_url_is_converted_to_csv_export_with_sheet_gid():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid=123"
    assert google_sheet_csv_url(url) == (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=123"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example.com/spreadsheets/d/x",
        f"http://docs.google.com/spreadsheets/d/{SHEET_ID}",
        "https://docs.google.com/document/d/abc",
    ],
)
def test_google_url_validation(url):
    with pytest.raises(TableSourceError):
        google_sheet_csv_url(url)


class _FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, content_type: str) -> None:
        super().__init__(body)
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_fetch_google_sheet_parses_csv(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: _FakeResponse("ПІБ\nІван\n".encode(), "text/csv"),
    )
    table = fetch_google_sheet(f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")
    assert table.rows == (("Іван",),)


def test_private_google_sheet_gives_sharing_hint(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: _FakeResponse(b"<html>login</html>", "text/html"),
    )
    with pytest.raises(TableSourceError, match="Усі, хто має посилання"):
        fetch_google_sheet(f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")


def test_network_error_is_reported(monkeypatch):
    def fail(request, timeout):
        raise urllib.error.URLError("no network")

    monkeypatch.setattr("urllib.request.urlopen", fail)
    with pytest.raises(TableSourceError, match="Не вдалося завантажити"):
        fetch_google_sheet(f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")


# --------------------------- відповідність --------------------------- #


def test_suggest_columns_matches_by_synonyms(config, table):
    mapping = suggest_columns(describe_inputs(config), table.headers)
    assert mapping["full_name"] == "ПІБ студента"
    assert mapping["birth_date"] == "Дата народження"
    assert mapping["course_name"] == "Курс"
    assert mapping["instructor_name"] == "Викладач"
    assert suggest_special_column(table.headers, ("номер", "№")) == "№"


@pytest.mark.parametrize(
    "text, expected", [("14.02.2005", date(2005, 2, 14)), ("2005-02-14", date(2005, 2, 14))]
)
def test_parse_date_formats(text, expected):
    assert parse_date(text) == expected


def test_parse_date_rejects_garbage():
    with pytest.raises(CertificateError, match="дату"):
        parse_date("вчора")


# --------------------------- побудова рядків --------------------------- #


def test_build_items_creates_data_with_auto_ids(config, table):
    inputs = describe_inputs(config)
    items = build_items(table, _profile(id_prefix="PY"), "default_tech", inputs, date(2026, 6, 30))

    assert len(items) == 6 and all(item.error is None for item in items)
    first = items[0].data
    assert first.certificate_id == "PY-2026-0001"
    assert first.fields["full_name"] == "Андрієнко Марія Олегівна"
    assert first.fields["birth_date"] == "14.02.2005"


def test_build_items_reports_missing_required_values(config):
    table = parse_csv_text("ПІБ студента,Дата народження,Курс\n,01.01.2000,Python\n")
    items = build_items(table, _profile(), "default_tech", describe_inputs(config), date.today())
    assert items[0].data is None and "ПІБ отримувача" in items[0].error
    assert items[0].row_number == 2


def test_build_items_validates_id_column(config):
    table = parse_csv_text("ID,ПІБ студента,Дата народження,Курс\nкирилиця,Іван,01.01.2000,Python\n")
    profile = _profile(certificate_id_column="ID")
    items = build_items(table, profile, "default_tech", describe_inputs(config), date.today())
    assert "некоректний ID" in items[0].error


def test_unknown_mapped_column_is_an_error(config, table):
    profile = BatchProfile(columns={"full_name": "Немає"})
    with pytest.raises(TableSourceError, match="Немає"):
        build_items(table, profile, "default_tech", describe_inputs(config), date.today())


# --------------------------- файли --------------------------- #


def test_render_filename_sanitizes_and_deduplicates(config, table):
    items = build_items(table, _profile(), "default_tech", describe_inputs(config), date(2026, 1, 1))
    name = render_filename("{full_name}: {birth_date}/x", items[0].data)
    assert name == "Андрієнко_Марія_Олегівна_14.02.2005x"
    used: set[str] = set()
    assert [unique_filename("a", used) for _ in range(3)] == ["a", "a_2", "a_3"]


def test_run_batch_creates_files_merged_pdf_and_reports_failures(config, table, tmp_path):
    small = TableData(table.headers, table.rows[:2] + (("7", "", "01.01.2000", "Python", ""),))
    items = build_items(small, _profile(), "default_tech", describe_inputs(config), date(2026, 1, 1))
    progress = []

    report = run_batch(
        items,
        TEMPLATE_DIR,
        config,
        tmp_path,
        _profile(output_format="png", merge_pdf=True),
        on_progress=lambda done, total: progress.append((done, total)),
    )

    assert [path.name for path in report.created] == [
        "Андрієнко_Марія_Олегівна.png",
        "Бондар_Ігор_Васильович.png",
    ]
    assert report.failed[0][0] == 4
    # Pillow дописує PDF інкрементально: актуальна кількість сторінок — в останньому /Count
    assert int(PDF_COUNT_RE.findall(report.merged_pdf.read_bytes())[-1]) == 2
    assert progress[-1] == (3, 3)
    with Image.open(report.created[0]) as image:
        assert image.size == (2480, 1754)


def test_run_batch_can_be_cancelled(config, table, tmp_path):
    items = build_items(table, _profile(), "default_tech", describe_inputs(config), date(2026, 1, 1))
    report = run_batch(
        items, TEMPLATE_DIR, config, tmp_path, _profile(output_format="jpg"), is_cancelled=lambda: True
    )
    assert report.cancelled and report.created == ()


def test_profile_roundtrip_and_corruption(tmp_path):
    profile = _profile(source="https://docs.google.com/spreadsheets/d/x", merge_pdf=True)
    save_profile(tmp_path, profile)
    assert load_profile(tmp_path) == profile

    (tmp_path / "batch.json").write_text("{ broken", encoding="utf-8")
    with pytest.raises(CertificateError, match="Пошкоджений профіль"):
        load_profile(tmp_path)


def test_missing_profile_returns_defaults(tmp_path):
    assert load_profile(tmp_path) == BatchProfile()


def test_placeholder_field_is_required_and_rendered(config, tmp_path):
    inputs = describe_inputs(config)
    birth = next(field for field in inputs.text_fields if field.id == "birth_date")
    assert birth.label == "Дата народження" and birth.required
