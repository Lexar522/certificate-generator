"""Джерела табличних даних: локальний CSV або Google Таблиця (через експорт у CSV).

Google Таблиця має бути доступна за посиланням («Усі, хто має посилання — читач»),
тоді авторизація не потрібна.
"""

import csv
import io
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from core.exceptions import CertificateError

GOOGLE_HOSTS = {"docs.google.com"}
SHEET_ID_RE = re.compile(r"/spreadsheets/d/([A-Za-z0-9_-]{20,})")
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 20
CSV_ENCODINGS = ("utf-8-sig", "cp1251")
DELIMITERS = ",;\t"


class TableSourceError(CertificateError):
    """Таблицю не вдалося прочитати або завантажити."""


@dataclass(frozen=True)
class TableData:
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]

    def column(self, header: str) -> int:
        try:
            return self.headers.index(header)
        except ValueError as exc:
            raise TableSourceError(f"У таблиці немає колонки «{header}»") from exc


def is_google_sheet_url(source: str) -> bool:
    parsed = urlparse(source.strip())
    return parsed.scheme in ("http", "https") and parsed.netloc in GOOGLE_HOSTS


def google_sheet_csv_url(url: str) -> str:
    """Перетворює посилання на Google Таблицю на посилання експорту CSV (з урахуванням аркуша gid)."""
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or parsed.netloc not in GOOGLE_HOSTS:
        raise TableSourceError("Потрібне посилання виду https://docs.google.com/spreadsheets/d/…")
    match = SHEET_ID_RE.search(parsed.path)
    if match is None:
        raise TableSourceError("Не вдалося знайти ID таблиці в посиланні")
    gid = parse_qs(parsed.query).get("gid", [None])[0] or parse_qs(parsed.fragment).get("gid", [None])[0]
    export = f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=csv"
    return f"{export}&gid={gid}" if gid and gid.isdigit() else export


def fetch_google_sheet(url: str) -> TableData:
    export_url = google_sheet_csv_url(url)
    request = urllib.request.Request(export_url, headers={"User-Agent": "certificate-generator"})
    try:
        # noqa: S310 — URL зібрано вище і він завжди веде на docs.google.com
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:  # noqa: S310
            content_type = response.headers.get("Content-Type", "")
            payload = response.read(MAX_DOWNLOAD_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 404):
            raise TableSourceError(NOT_SHARED_MESSAGE) from exc
        raise TableSourceError(f"Google повернув помилку {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TableSourceError(f"Не вдалося завантажити таблицю: {exc}") from exc

    if len(payload) > MAX_DOWNLOAD_BYTES:
        raise TableSourceError("Таблиця завелика (понад 10 МБ)")
    if "text/html" in content_type:
        raise TableSourceError(NOT_SHARED_MESSAGE)
    return parse_csv_text(payload.decode("utf-8-sig", errors="replace"))


def load_csv(path: Path) -> TableData:
    if not path.is_file():
        raise TableSourceError(f"Файл не знайдено: {path}")
    raw = path.read_bytes()
    for encoding in CSV_ENCODINGS:
        try:
            return parse_csv_text(raw.decode(encoding))
        except UnicodeDecodeError:
            continue
    raise TableSourceError(f"Невідоме кодування файлу {path.name} (очікується UTF-8 або Windows-1251)")


def load_table(source: str, base_dir: Path | None = None) -> TableData:
    """Посилання на Google Таблицю або шлях до CSV (відносний — від base_dir)."""
    if not source.strip():
        raise TableSourceError("Не вказано джерело даних")
    if is_google_sheet_url(source):
        return fetch_google_sheet(source)
    path = Path(source).expanduser()
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    return load_csv(path)


def parse_csv_text(text: str) -> TableData:
    if not text.strip():
        raise TableSourceError("Таблиця порожня")
    records = [
        [cell.strip() for cell in row]
        for row in csv.reader(io.StringIO(text), delimiter=_detect_delimiter(text))
        if any(cell.strip() for cell in row)
    ]
    if not records:
        raise TableSourceError("Таблиця порожня")

    headers = _unique_headers(records[0])
    width = len(headers)
    rows = tuple(tuple((record + [""] * width)[:width]) for record in records[1:])
    if not rows:
        raise TableSourceError("У таблиці є лише заголовки — додайте рядки з даними")
    return TableData(headers=headers, rows=rows)


def _detect_delimiter(text: str) -> str:
    """Sniffer, а якщо він не впорався (нерівні рядки) — найчастіший роздільник у заголовку."""
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=DELIMITERS).delimiter
    except csv.Error:
        header = text.splitlines()[0]
        return max(DELIMITERS, key=header.count)


def _unique_headers(headers: list[str]) -> tuple[str, ...]:
    result: list[str] = []
    for index, header in enumerate(headers):
        name = header or f"Колонка {index + 1}"
        duplicates = sum(1 for existing in result if existing == name or existing.startswith(f"{name} ("))
        result.append(f"{name} ({duplicates + 1})" if duplicates else name)
    return tuple(result)


NOT_SHARED_MESSAGE = (
    "Таблиця недоступна. Відкрийте доступ: «Поділитися» → «Загальний доступ» → "
    "«Усі, хто має посилання» (Читач), і спробуйте ще раз."
)
