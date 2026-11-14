"""Pydantic-моделі: вхідні дані сертифіката та схема config.json шаблону."""

import re
from collections import Counter
from datetime import date
from typing import Annotated, Literal, Union

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

SAFE_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
MAX_CANVAS_SIDE = 10_000
MAX_TEXT_LENGTH = 500
DEFAULT_MIN_FONT_SIZE = 12
CERTIFICATE_ID_PLACEHOLDER = "{certificate_id}"


def _validate_hex_color(value: str) -> str:
    if not HEX_COLOR_RE.match(value):
        raise ValueError(f"'{value}' не є HEX-кольором (#RGB, #RRGGBB або #RRGGBBAA)")
    return value


HexColor = Annotated[str, AfterValidator(_validate_hex_color)]
SafeName = Annotated[str, Field(pattern=SAFE_NAME_PATTERN)]
Coordinate = Annotated[int, Field(ge=-MAX_CANVAS_SIDE, le=MAX_CANVAS_SIDE)]
Dimension = Annotated[int, Field(gt=0, le=MAX_CANVAS_SIDE)]
RelativePath = Annotated[str, Field(min_length=1, max_length=255)]


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")


# --------------------------------------------------------------------------- #
# Вхідні дані
# --------------------------------------------------------------------------- #


class CertificateData(_FrozenModel):
    """Дані одного сертифіката."""

    template_name: SafeName = Field(description="Назва папки шаблону в templates/")
    certificate_id: SafeName = Field(description="Унікальний ID для верифікації та QR")
    issue_date: date
    fields: dict[SafeName, Annotated[str, Field(max_length=MAX_TEXT_LENGTH)]] = Field(
        default_factory=dict
    )
    images: dict[SafeName, RelativePath] = Field(default_factory=dict)

    @field_validator("fields")
    @classmethod
    def _strip_and_reject_blank(cls, value: dict[str, str]) -> dict[str, str]:
        stripped = {key: text.strip() for key, text in value.items()}
        blank = [key for key, text in stripped.items() if not text]
        if blank:
            raise ValueError(f"порожні значення для полів: {', '.join(blank)}")
        return stripped


# --------------------------------------------------------------------------- #
# Конфігурація шаблону
# --------------------------------------------------------------------------- #


class CanvasConfig(_FrozenModel):
    width: Dimension
    height: Dimension
    background_color: HexColor = "#FFFFFF"
    background_image: RelativePath | None = None
    background_fit: Literal["cover", "contain", "stretch"] = Field(
        default="cover",
        description="cover — заповнити з обрізанням; contain — вмістити повністю; stretch — розтягнути",
    )


class OutputConfig(_FrozenModel):
    format: Literal["jpg", "png", "pdf"] = "jpg"
    quality: int = Field(default=95, ge=1, le=100)
    dpi: int = Field(default=300, ge=72, le=1200)


class _BaseLayer(_FrozenModel):
    id: SafeName
    label: str | None = Field(default=None, max_length=100, description="Підпис поля в інтерфейсі")
    x: Coordinate = 0
    y: Coordinate = 0
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    rotation: float = Field(default=0.0, ge=-360, le=360, description="Градуси, проти годинникової")
    visible: bool = True


class WatermarkLayer(_BaseLayer):
    type: Literal["watermark"]
    path: RelativePath
    scale: float = Field(default=1.0, gt=0, le=20)
    opacity: float = Field(default=0.15, ge=0.0, le=1.0)


class ImageLayer(_BaseLayer):
    type: Literal["image"]
    path: RelativePath | None = Field(
        default=None, description="Статичний шлях відносно шаблону; images[id] має пріоритет"
    )
    width: Dimension | None = None
    height: Dimension | None = None
    keep_aspect: bool = True
    required: bool = False


class TextLayer(_BaseLayer):
    type: Literal["text"]
    text: str | None = Field(
        default=None,
        max_length=MAX_TEXT_LENGTH,
        description="Статичний текст; fields[id] має пріоритет. Плейсхолдери: "
        "{certificate_id}, {issue_date}",
    )
    font: RelativePath
    font_size: int = Field(gt=0, le=1000)
    color: HexColor = "#000000"
    align: Literal["left", "center", "right"] = "left"
    max_width: Dimension | None = None
    overflow: Literal["shrink", "wrap"] = "shrink"
    min_font_size: int | None = Field(
        default=None, gt=0, le=1000, description=f"За замовчуванням min({DEFAULT_MIN_FONT_SIZE}, font_size)"
    )
    line_spacing: float = Field(default=1.2, ge=0.5, le=5.0)
    uppercase: bool = False
    required: bool = False

    @model_validator(mode="after")
    def _check_font_sizes(self) -> "TextLayer":
        if self.min_font_size is not None and self.min_font_size > self.font_size:
            raise ValueError("min_font_size не може перевищувати font_size")
        return self

    @property
    def effective_min_font_size(self) -> int:
        if self.min_font_size is not None:
            return self.min_font_size
        return min(DEFAULT_MIN_FONT_SIZE, self.font_size)


class QrLayer(_BaseLayer):
    type: Literal["qr"]
    size: Dimension
    url_template: str = Field(
        default="https://verify.example.com/certificates/{certificate_id}",
        max_length=500,
    )
    fill_color: HexColor = "#000000"
    back_color: HexColor = "#FFFFFF"
    border: int = Field(default=2, ge=0, le=20)
    error_correction: Literal["L", "M", "Q", "H"] = "M"

    @field_validator("url_template")
    @classmethod
    def _require_placeholder(cls, value: str) -> str:
        if CERTIFICATE_ID_PLACEHOLDER not in value:
            raise ValueError(f"url_template має містити {CERTIFICATE_ID_PLACEHOLDER}")
        return value


Layer = Annotated[
    Union[WatermarkLayer, ImageLayer, TextLayer, QrLayer],
    Field(discriminator="type"),
]


class TemplateConfig(_FrozenModel):
    name: str = Field(min_length=1, max_length=100)
    date_format: str = Field(default="%d.%m.%Y", min_length=1, max_length=50)
    canvas: CanvasConfig
    output: OutputConfig = OutputConfig()
    field_labels: dict[SafeName, Annotated[str, Field(max_length=100)]] = Field(
        default_factory=dict, description="Назви полів-плейсхолдерів {key} для інтерфейсу"
    )
    layers: tuple[Layer, ...] = Field(min_length=1)

    @field_validator("layers")
    @classmethod
    def _unique_layer_ids(cls, layers: tuple[_BaseLayer, ...]) -> tuple[_BaseLayer, ...]:
        counts = Counter(layer.id for layer in layers)
        duplicates = [layer_id for layer_id, count in counts.items() if count > 1]
        if duplicates:
            raise ValueError(f"дубльовані id шарів: {', '.join(sorted(duplicates))}")
        return layers
