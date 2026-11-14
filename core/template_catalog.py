"""Каталог шаблонів і опис полів, які треба заповнити для кожного сертифіката."""

import re
from dataclasses import dataclass
from pathlib import Path

from core.models import SAFE_NAME_PATTERN, ImageLayer, TemplateConfig, TextLayer
from core.template_loader import CONFIG_FILENAME

_SAFE_NAME_RE = re.compile(SAFE_NAME_PATTERN)
PLACEHOLDER_RE = re.compile(r"\{([A-Za-z][A-Za-z0-9_]{0,63})\}")
BUILTIN_PLACEHOLDERS = frozenset({"certificate_id", "issue_date"})


@dataclass(frozen=True)
class InputField:
    id: str
    label: str
    required: bool


@dataclass(frozen=True)
class TemplateInputs:
    text_fields: tuple[InputField, ...]
    image_fields: tuple[InputField, ...]


def list_templates(templates_root: Path) -> tuple[str, ...]:
    """Назви папок шаблонів, що містять config.json, в алфавітному порядку."""
    if not templates_root.is_dir():
        return ()
    return tuple(
        sorted(
            entry.name
            for entry in templates_root.iterdir()
            if entry.is_dir()
            and _SAFE_NAME_RE.match(entry.name)
            and (entry / CONFIG_FILENAME).is_file()
        )
    )


def placeholders_in(text: str) -> tuple[str, ...]:
    """Користувацькі плейсхолдери {key} у тексті (без вбудованих), у порядку появи."""
    keys = (match.group(1) for match in PLACEHOLDER_RE.finditer(text))
    return tuple(dict.fromkeys(key for key in keys if key not in BUILTIN_PLACEHOLDERS))


def describe_inputs(config: TemplateConfig) -> TemplateInputs:
    """Поля даних шаблону.

    Текстові: шари без статичного тексту + плейсхолдери {key} у статичних текстах
    (плейсхолдери обов'язкові — інакше в сертифікаті лишився б сирий «{key}»).
    Зображення: шари image без статичного path.
    """
    text_fields: dict[str, InputField] = {}
    for layer in config.layers:
        if not isinstance(layer, TextLayer):
            continue
        if layer.text is None:
            text_fields.setdefault(layer.id, _to_field(layer))
            continue
        for key in placeholders_in(layer.text):
            label = config.field_labels.get(key) or _humanize(key)
            text_fields.setdefault(key, InputField(id=key, label=label, required=True))

    image_fields = tuple(
        _to_field(layer)
        for layer in config.layers
        if isinstance(layer, ImageLayer) and layer.path is None
    )
    return TemplateInputs(text_fields=tuple(text_fields.values()), image_fields=image_fields)


def _to_field(layer: TextLayer | ImageLayer) -> InputField:
    return InputField(id=layer.id, label=layer.label or _humanize(layer.id), required=layer.required)


def _humanize(key: str) -> str:
    return key.replace("_", " ").capitalize()
