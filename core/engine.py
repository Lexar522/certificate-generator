"""CertificateEngine — оркестратор: валідація → пошук шаблону → рендер → збереження."""

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from core.exceptions import CertificateError, RenderError
from core.models import CertificateData
from core.template_loader import load_template_config, resolve_template_dir
from renderers.base import BaseRenderer
from renderers.pillow_renderer import PillowRenderer

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATES_DIR = Path("templates")
DEFAULT_OUTPUT_DIR = Path("output")
OutputFormat = Literal["jpg", "png", "pdf"]


class CertificateEngine:
    """Головна точка входу для генерації сертифікатів."""

    def __init__(
        self,
        templates_dir: str | Path = DEFAULT_TEMPLATES_DIR,
        output_dir: str | Path = DEFAULT_OUTPUT_DIR,
        renderer: BaseRenderer | None = None,
    ) -> None:
        self._templates_dir = Path(templates_dir)
        self._output_dir = Path(output_dir)
        self._renderer = renderer or PillowRenderer()

        if not self._templates_dir.is_dir():
            raise CertificateError(f"Директорію шаблонів не знайдено: {self._templates_dir}")

    @property
    def templates_dir(self) -> Path:
        return self._templates_dir

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    def generate(
        self,
        data: CertificateData | Mapping[str, Any],
        output_format: OutputFormat | None = None,
    ) -> Path:
        """Генерує сертифікат і повертає шлях до файлу в output_dir.

        output_format перекриває `output.format` з config.json шаблону.
        """
        certificate = self._validate(data)
        template_dir = resolve_template_dir(self._templates_dir, certificate.template_name)
        config = load_template_config(template_dir)

        extension = output_format or config.output.format
        output_path = self._output_dir / f"cert_{certificate.certificate_id}.{extension}"
        self._prepare_output_dir()

        logger.info(
            "Генерація сертифіката %s за шаблоном '%s' → %s",
            certificate.certificate_id,
            certificate.template_name,
            output_path,
        )
        result = self._renderer.render(certificate, template_dir, output_path)
        logger.info("Сертифікат збережено: %s", result)
        return result

    @staticmethod
    def _validate(data: CertificateData | Mapping[str, Any]) -> CertificateData:
        try:
            return CertificateData.model_validate(data)
        except ValidationError as exc:
            raise CertificateError(f"Некоректні дані сертифіката:\n{exc}") from exc

    def _prepare_output_dir(self) -> None:
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RenderError(
                f"Не вдалося створити директорію результатів {self._output_dir}: {exc}"
            ) from exc
