"""Абстрактний контракт рендерера: дозволяє замінити Pillow на інший рушій."""

from abc import ABC, abstractmethod
from pathlib import Path

from core.models import CertificateData


class BaseRenderer(ABC):
    """Перетворює дані сертифіката + шаблон на готовий файл."""

    @abstractmethod
    def render(self, data: CertificateData, template_dir: Path, output_path: Path) -> Path:
        """Рендерить сертифікат у output_path і повертає фактичний шлях до файлу.

        Реалізація має кидати винятки з core.exceptions, а не сирі помилки бібліотек.
        """
