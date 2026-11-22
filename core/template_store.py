"""Запис шаблонів: збереження config.json, імпорт ресурсів, клонування шаблону."""

import json
import os
import re
import shutil
from pathlib import Path

from core.exceptions import CertificateError
from core.models import SAFE_NAME_PATTERN, TemplateConfig
from core.template_loader import CONFIG_FILENAME

_SAFE_NAME_RE = re.compile(SAFE_NAME_PATTERN)
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
MAX_ASSET_BYTES = 50 * 1024 * 1024


def serialize_config(config: TemplateConfig) -> str:
    payload = config.model_dump(mode="json", exclude_none=True)
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def save_config(template_dir: Path, config: TemplateConfig) -> Path:
    """Атомарно записує config.json у папку шаблону."""
    config_path = template_dir / CONFIG_FILENAME
    temp_path = template_dir / f".{CONFIG_FILENAME}.tmp"
    try:
        temp_path.write_text(serialize_config(config), encoding="utf-8")
        os.replace(temp_path, config_path)
    except OSError as exc:
        temp_path.unlink(missing_ok=True)
        raise CertificateError(f"Не вдалося зберегти шаблон у {config_path}: {exc}") from exc
    return config_path


def import_asset(template_dir: Path, source: Path, subdir: str) -> str:
    """Копіює файл у <шаблон>/<subdir>/ і повертає шлях відносно шаблону.

    Якщо файл уже лежить усередині шаблону — повертає його відносний шлях без копіювання.
    """
    source = source.resolve()
    root = template_dir.resolve()
    if not source.is_file():
        raise CertificateError(f"Файл не знайдено: {source}")
    if source.is_relative_to(root):
        return source.relative_to(root).as_posix()
    if source.stat().st_size > MAX_ASSET_BYTES:
        raise CertificateError(f"Файл завеликий (> {MAX_ASSET_BYTES // 1024 // 1024} МБ): {source}")

    target_dir = root / subdir
    target = _unique_path(target_dir, _safe_filename(source.name))
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    except OSError as exc:
        raise CertificateError(f"Не вдалося скопіювати {source} у шаблон: {exc}") from exc
    return target.relative_to(root).as_posix()


def create_template(templates_root: Path, folder: str, config: TemplateConfig, fonts_source: Path) -> Path:
    """Новий шаблон: папка з fonts/ (копія шрифтів із fonts_source) та config.json."""
    target = _new_template_dir(templates_root, folder)
    try:
        target.mkdir(parents=True)
        if fonts_source.is_dir():
            shutil.copytree(fonts_source, target / "fonts")
    except OSError as exc:
        shutil.rmtree(target, ignore_errors=True)
        raise CertificateError(f"Не вдалося створити шаблон '{folder}': {exc}") from exc
    save_config(target, config)
    return target


def clone_template(templates_root: Path, source_dir: Path, new_name: str) -> Path:
    """Копіює всю папку шаблону під новою назвою."""
    target = _new_template_dir(templates_root, new_name)
    try:
        shutil.copytree(source_dir, target)
    except OSError as exc:
        raise CertificateError(f"Не вдалося створити шаблон '{new_name}': {exc}") from exc
    return target


def _new_template_dir(templates_root: Path, folder: str) -> Path:
    if not _SAFE_NAME_RE.match(folder):
        raise CertificateError("Назва папки шаблону: латиниця, цифри, «-» і «_», до 64 символів")
    target = templates_root / folder
    if target.exists():
        raise CertificateError(f"Шаблон '{folder}' уже існує")
    return target


def _safe_filename(name: str) -> str:
    stem, dot, suffix = name.rpartition(".")
    if not dot:
        stem, suffix = name, ""
    clean_stem = _UNSAFE_FILENAME_CHARS.sub("_", stem).strip("._") or "file"
    clean_suffix = _UNSAFE_FILENAME_CHARS.sub("", suffix).lower()
    return f"{clean_stem}.{clean_suffix}" if clean_suffix else clean_stem


def _unique_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    stem, suffix = candidate.stem, candidate.suffix
    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem}_{counter}{suffix}"
        counter += 1
    return candidate
