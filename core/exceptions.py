"""Ієрархія винятків модуля генерації сертифікатів.

Усі винятки успадковуються від CertificateError, тож клієнтський код може
перехоплювати їх одним `except CertificateError`.
"""

from pathlib import Path


class CertificateError(Exception):
    """Базовий виняток модуля."""


class TemplateNotFoundError(CertificateError):
    """Папку шаблону або її config.json не знайдено."""

    def __init__(self, template_name: str, searched_path: Path) -> None:
        self.template_name = template_name
        self.searched_path = searched_path
        super().__init__(
            f"Шаблон '{template_name}' не знайдено: очікувався файл {searched_path}"
        )


class TemplateConfigError(CertificateError):
    """config.json пошкоджений (битий JSON) або не відповідає схемі."""

    def __init__(self, config_path: Path, details: str) -> None:
        self.config_path = config_path
        self.details = details
        super().__init__(f"Некоректна конфігурація шаблону {config_path}:\n{details}")


class AssetNotFoundError(CertificateError):
    """Файл зображення (фон, логотип, підпис, водяний знак) недоступний."""

    def __init__(self, layer_id: str, asset_path: Path, reason: str = "файл не існує") -> None:
        self.layer_id = layer_id
        self.asset_path = asset_path
        super().__init__(f"Шар '{layer_id}': не вдалося відкрити {asset_path} ({reason})")


class FontLoadError(CertificateError):
    """Шрифт .ttf відсутній або пошкоджений."""

    def __init__(self, layer_id: str, font_path: Path, reason: str) -> None:
        self.layer_id = layer_id
        self.font_path = font_path
        super().__init__(f"Шар '{layer_id}': не вдалося завантажити шрифт {font_path} ({reason})")


class MissingFieldError(CertificateError):
    """Для обов'язкового шару не передано значення в fields/images."""

    def __init__(self, layer_id: str, source: str) -> None:
        self.layer_id = layer_id
        self.source = source
        super().__init__(
            f"Обов'язковий шар '{layer_id}' не має значення: додайте ключ '{layer_id}' у `{source}`"
        )


class RenderError(CertificateError):
    """Будь-яка інша помилка під час рендерингу чи збереження."""
