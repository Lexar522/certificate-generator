"""Пакетна генерація: рядки таблиці → дані сертифікатів → файли.

Налаштування групи зберігаються у профілі `batch.json` у папці шаблону, тож повторна
генерація (з GUI або командою `python batch.py <шаблон>`) не потребує жодних кліків.
"""

import json
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from core.exceptions import CertificateError
from core.models import SAFE_NAME_PATTERN, CertificateData, TemplateConfig
from core.table_source import TableData
from core.template_catalog import InputField, TemplateInputs
from renderers.pillow_renderer import PillowRenderer, save_image

logger = logging.getLogger(__name__)

PROFILE_FILENAME = "batch.json"
MERGED_PDF_NAME = "all_certificates.pdf"
MAX_FILENAME_LENGTH = 120
DATE_FORMATS = ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%y", "%d-%m-%Y")
_FORBIDDEN_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
_SAFE_ID_RE = re.compile(SAFE_NAME_PATTERN)

FIELD_SYNONYMS: dict[str, tuple[str, ...]] = {
    "full_name": ("піб", "прізвище", "ім'я", "імʼя", "name", "студент", "учасник", "фіо"),
    "birth_date": ("народж", "birth", "д.н."),
    "course_name": ("курс", "course", "дисциплін", "предмет", "програм"),
    "instructor_name": ("викладач", "instructor", "teacher", "керівник"),
}
ISSUE_DATE_SYNONYMS = ("дата видачі", "issue")


class BatchProfile(BaseModel):
    """Збережені налаштування пакетної генерації для шаблону."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str = Field(default="", max_length=2000)
    columns: dict[str, str] = Field(default_factory=dict, description="id поля → назва колонки")
    certificate_id_column: str | None = None
    id_prefix: str = Field(default="CERT", pattern=r"^[A-Za-z0-9_-]{1,20}$")
    issue_date_column: str | None = None
    output_dir: str = Field(default="output/batch", min_length=1, max_length=500)
    output_format: Literal["jpg", "png", "pdf"] = "pdf"
    filename_pattern: str = Field(default="{full_name}", max_length=200)
    merge_pdf: bool = False


@dataclass(frozen=True)
class BatchItem:
    row_number: int  # номер рядка в таблиці (1 — заголовок)
    data: CertificateData | None
    error: str | None


@dataclass(frozen=True)
class BatchReport:
    created: tuple[Path, ...]
    failed: tuple[tuple[int, str], ...]
    merged_pdf: Path | None
    cancelled: bool


# ---------------------------------------------------------------------- #
# Профіль
# ---------------------------------------------------------------------- #


def load_profile(template_dir: Path) -> BatchProfile:
    path = template_dir / PROFILE_FILENAME
    if not path.is_file():
        return BatchProfile()
    try:
        return BatchProfile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise CertificateError(f"Пошкоджений профіль пакетної генерації {path}: {exc}") from exc


def save_profile(template_dir: Path, profile: BatchProfile) -> Path:
    path = template_dir / PROFILE_FILENAME
    payload = json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    try:
        path.write_text(payload, encoding="utf-8")
    except OSError as exc:
        raise CertificateError(f"Не вдалося зберегти профіль {path}: {exc}") from exc
    return path


# ---------------------------------------------------------------------- #
# Відповідність колонок
# ---------------------------------------------------------------------- #


def suggest_columns(inputs: TemplateInputs, headers: tuple[str, ...]) -> dict[str, str]:
    """Автопідбір колонок за назвами полів і синонімами («ПІБ» → full_name тощо)."""
    normalized = {header: _normalize(header) for header in headers}
    used: set[str] = set()
    result: dict[str, str] = {}
    for field in inputs.text_fields + inputs.image_fields:
        keys = (_normalize(field.label), _normalize(field.id)) + FIELD_SYNONYMS.get(field.id, ())
        match = next(
            (h for h in headers if h not in used and _matches(normalized[h], keys)),
            None,
        )
        if match is not None:
            result[field.id] = match
            used.add(match)
    return result


def suggest_special_column(headers: tuple[str, ...], synonyms: tuple[str, ...]) -> str | None:
    return next((h for h in headers if _matches(_normalize(h), synonyms)), None)


def _matches(header: str, keys: tuple[str, ...]) -> bool:
    return any(key and (header == key or (len(key) >= 3 and key in header)) for key in keys)


def _normalize(text: str) -> str:
    return " ".join(text.lower().replace("’", "'").split())


# ---------------------------------------------------------------------- #
# Рядки → дані сертифікатів
# ---------------------------------------------------------------------- #


def build_items(
    table: TableData,
    profile: BatchProfile,
    template_name: str,
    inputs: TemplateInputs,
    default_issue_date: date,
) -> tuple[BatchItem, ...]:
    """Перетворює кожен непорожній рядок на CertificateData або пояснення помилки."""
    plan = _RowPlan(
        columns={fid: table.column(header) for fid, header in profile.columns.items() if header},
        id_column=table.column(profile.certificate_id_column) if profile.certificate_id_column else None,
        date_column=table.column(profile.issue_date_column) if profile.issue_date_column else None,
        image_ids=frozenset(field.id for field in inputs.image_fields),
        required=tuple(field for field in inputs.text_fields + inputs.image_fields if field.required),
        id_prefix=profile.id_prefix,
        template_name=template_name,
        default_issue_date=default_issue_date,
    )
    items = []
    for index, row in enumerate(table.rows):
        if not any(row):
            continue
        row_number = index + 2
        try:
            items.append(BatchItem(row_number, _row_to_data(row, row_number, plan), None))
        except CertificateError as exc:
            items.append(BatchItem(row_number, None, str(exc)))
    return tuple(items)


@dataclass(frozen=True)
class _RowPlan:
    columns: dict[str, int]
    id_column: int | None
    date_column: int | None
    image_ids: frozenset[str]
    required: tuple[InputField, ...]
    id_prefix: str
    template_name: str
    default_issue_date: date


def _row_to_data(row: tuple[str, ...], row_number: int, plan: _RowPlan) -> CertificateData:
    values = {fid: row[col].strip() for fid, col in plan.columns.items() if row[col].strip()}
    missing = [field.label for field in plan.required if field.id not in values]
    if missing:
        raise CertificateError(f"не заповнено: {', '.join(missing)}")

    issue_date = parse_date(row[plan.date_column]) if plan.date_column is not None else plan.default_issue_date
    if plan.id_column is not None:
        certificate_id = row[plan.id_column].strip()
        if not _SAFE_ID_RE.match(certificate_id):
            raise CertificateError(f"некоректний ID «{certificate_id}» (латиниця, цифри, - _)")
    else:
        certificate_id = f"{plan.id_prefix}-{issue_date:%Y}-{row_number - 1:04d}"

    try:
        return CertificateData(
            template_name=plan.template_name,
            certificate_id=certificate_id,
            issue_date=issue_date,
            fields={key: value for key, value in values.items() if key not in plan.image_ids},
            images={key: value for key, value in values.items() if key in plan.image_ids},
        )
    except ValidationError as exc:
        details = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        raise CertificateError(details) from exc


def parse_date(value: str) -> date:
    text = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise CertificateError(f"не вдалося розпізнати дату «{text}» (очікується дд.мм.рррр)")


# ---------------------------------------------------------------------- #
# Генерація
# ---------------------------------------------------------------------- #

ProgressCallback = Callable[[int, int], None]


def run_batch(
    items: tuple[BatchItem, ...],
    template_dir: Path,
    config: TemplateConfig,
    output_dir: Path,
    profile: BatchProfile,
    on_progress: ProgressCallback | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    renderer: PillowRenderer | None = None,
) -> BatchReport:
    renderer = renderer or PillowRenderer()
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CertificateError(f"Не вдалося створити папку {output_dir}: {exc}") from exc

    merged_temp = output_dir / f".{MERGED_PDF_NAME}.tmp"
    merged_temp.unlink(missing_ok=True)
    created: list[Path] = []
    failed: list[tuple[int, str]] = []
    used_names: set[str] = set()
    cancelled = False

    for position, item in enumerate(items, start=1):
        if is_cancelled is not None and is_cancelled():
            cancelled = True
            break
        if item.data is None:
            failed.append((item.row_number, item.error or "невідома помилка"))
        else:
            try:
                image = renderer.compose(item.data, template_dir, config)
                name = unique_filename(render_filename(profile.filename_pattern, item.data), used_names)
                created.append(save_image(image, output_dir / f"{name}.{profile.output_format}", config.output))
                if profile.merge_pdf:
                    _append_pdf_page(image, merged_temp, config.output.dpi)
            except CertificateError as exc:
                failed.append((item.row_number, str(exc)))
        if on_progress is not None:
            on_progress(position, len(items))

    merged = None
    if profile.merge_pdf and merged_temp.exists():
        merged = output_dir / MERGED_PDF_NAME
        os.replace(merged_temp, merged)
    logger.info("Пакет: створено %d, помилок %d", len(created), len(failed))
    return BatchReport(tuple(created), tuple(failed), merged, cancelled)


def _append_pdf_page(image, pdf_path: Path, dpi: int) -> None:
    try:
        image.convert("RGB").save(pdf_path, format="PDF", resolution=float(dpi), append=pdf_path.exists())
    except OSError as exc:
        raise CertificateError(f"Не вдалося додати сторінку до спільного PDF: {exc}") from exc


def render_filename(pattern: str, data: CertificateData) -> str:
    values = data.fields | {"certificate_id": data.certificate_id, "issue_date": data.issue_date.isoformat()}
    filled = re.sub(r"\{([A-Za-z][A-Za-z0-9_]*)\}", lambda m: values.get(m.group(1), ""), pattern)
    cleaned = _FORBIDDEN_FILENAME_CHARS.sub("", filled)
    cleaned = "_".join(cleaned.split()).strip("._")[:MAX_FILENAME_LENGTH]
    return cleaned or f"cert_{data.certificate_id}"


def unique_filename(name: str, used: set[str]) -> str:
    """Додає _2, _3… для однакових імен; запам'ятовує видане ім'я у used."""
    candidate, counter = name, 2
    while candidate.lower() in used:
        candidate = f"{name}_{counter}"
        counter += 1
    used.add(candidate.lower())
    return candidate
