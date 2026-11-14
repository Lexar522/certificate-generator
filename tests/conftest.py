import json
import shutil
from datetime import date
from pathlib import Path

import pytest
from PIL import Image

from core import CertificateData, CertificateEngine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_FONT = PROJECT_ROOT / "templates" / "default_tech" / "fonts" / "NotoSans-Regular.ttf"


def write_config(template_dir: Path, config: dict) -> None:
    (template_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")


@pytest.fixture
def minimal_config() -> dict:
    return {
        "name": "Test",
        "canvas": {"width": 400, "height": 300, "background_color": "#FFFFFF"},
        "output": {"format": "png"},
        "layers": [
            {
                "id": "full_name",
                "type": "text",
                "required": True,
                "font": "fonts/font.ttf",
                "font_size": 32,
                "color": "#000000",
                "align": "center",
                "x": 200,
                "y": 100,
            }
        ],
    }


@pytest.fixture
def templates_root(tmp_path: Path, minimal_config: dict) -> Path:
    template_dir = tmp_path / "templates" / "test_tpl"
    (template_dir / "fonts").mkdir(parents=True)
    (template_dir / "assets").mkdir()
    shutil.copy(DEMO_FONT, template_dir / "fonts" / "font.ttf")
    Image.new("RGBA", (100, 50), (255, 0, 0, 255)).save(template_dir / "assets" / "red.png")
    write_config(template_dir, minimal_config)
    return tmp_path / "templates"


@pytest.fixture
def engine(templates_root: Path, tmp_path: Path) -> CertificateEngine:
    return CertificateEngine(templates_dir=templates_root, output_dir=tmp_path / "output")


@pytest.fixture
def certificate() -> CertificateData:
    return CertificateData(
        template_name="test_tpl",
        certificate_id="TEST-001",
        issue_date=date(2026, 1, 15),
        fields={"full_name": "Тест Тестович"},
    )
