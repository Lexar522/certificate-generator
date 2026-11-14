"""Пошук шаблонів, читання config.json та безпечне розв'язання шляхів до ресурсів."""

import json
from pathlib import Path

from pydantic import ValidationError

from core.exceptions import TemplateConfigError, TemplateNotFoundError
from core.models import TemplateConfig

CONFIG_FILENAME = "config.json"


def resolve_template_dir(templates_root: Path, template_name: str) -> Path:
    """Повертає папку шаблону або кидає TemplateNotFoundError."""
    template_dir = (templates_root / template_name).resolve()
    config_path = template_dir / CONFIG_FILENAME
    if not template_dir.is_relative_to(templates_root.resolve()) or not config_path.is_file():
        raise TemplateNotFoundError(template_name, config_path)
    return template_dir


def load_template_config(template_dir: Path) -> TemplateConfig:
    """Читає та валідує config.json; битий JSON чи схема → TemplateConfigError."""
    config_path = template_dir / CONFIG_FILENAME
    if not config_path.is_file():
        raise TemplateNotFoundError(template_dir.name, config_path)

    try:
        raw = config_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise TemplateConfigError(config_path, f"не вдалося прочитати файл: {exc}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TemplateConfigError(
            config_path, f"битий JSON — {exc.msg} (рядок {exc.lineno}, колонка {exc.colno})"
        ) from exc

    try:
        return TemplateConfig.model_validate(payload)
    except ValidationError as exc:
        raise TemplateConfigError(config_path, _format_validation_error(exc)) from exc


def resolve_template_asset(template_dir: Path, relative_path: str) -> Path:
    """Шлях до ресурсу шаблону; забороняє вихід за межі папки шаблону (path traversal)."""
    root = template_dir.resolve()
    candidate = (root / relative_path).resolve()
    if not candidate.is_relative_to(root):
        raise TemplateConfigError(
            root / CONFIG_FILENAME, f"шлях '{relative_path}' виходить за межі шаблону"
        )
    return candidate


def _format_validation_error(exc: ValidationError) -> str:
    lines = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "<root>"
        lines.append(f"  - {location}: {error['msg']}")
    return "\n".join(lines)
