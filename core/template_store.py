"""Запис шаблонів: збереження config.json, імпорт ресурсів, клонування шаблону."""

import json
import os
import re
import shutil
from collections.abc import Mapping
from pathlib import Path

from PIL import Image

from core.exceptions import CertificateError
from core.models import SAFE_NAME_PATTERN, TemplateConfig, TextLayer
from core.template_loader import CONFIG_FILENAME, resolve_template_asset

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


def create_template(
    templates_root: Path,
    folder: str,
    config: TemplateConfig,
    fonts_source: Path,
    assets: Mapping[str, Image.Image] | None = None,
) -> Path:
    """Новий шаблон: папка з fonts/ (копія шрифтів із fonts_source), згенерованими assets і config.json."""
    target = _new_template_dir(templates_root, folder)
    try:
        target.mkdir(parents=True)
        if fonts_source.is_dir():
            shutil.copytree(fonts_source, target / "fonts")
        _require_fonts(target, config)
        for relative, image in (assets or {}).items():
            save_generated_asset(target, relative, image)
        save_config(target, config)
    except (OSError, CertificateError) as exc:
        shutil.rmtree(target, ignore_errors=True)
        if isinstance(exc, CertificateError):
            raise
        raise CertificateError(f"Не вдалося створити шаблон '{folder}': {exc}") from exc
    return target


def save_generated_asset(template_dir: Path, relative: str, image: Image.Image) -> str:
    """Зберігає згенероване зображення як PNG у шаблон; повертає фактичний відносний шлях."""
    destination = resolve_template_asset(template_dir, relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination = _unique_path(destination.parent, _safe_filename(destination.name))
    try:
        image.save(destination, format="PNG", optimize=True)
    except OSError as exc:
        raise CertificateError(f"Не вдалося зберегти зображення {relative}: {exc}") from exc
    return destination.relative_to(template_dir).as_posix()


def _require_fonts(template_dir: Path, config: TemplateConfig) -> None:
    fonts = {layer.font for layer in config.layers if isinstance(layer, TextLayer)}
    missing = sorted(font for font in fonts if not (template_dir / font).is_file())
    if missing:
        raise CertificateError(f"Для цієї заготовки бракує шрифтів: {', '.join(missing)}")


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
