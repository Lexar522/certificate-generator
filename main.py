"""Приклад використання: генерує тестовий сертифікат за шаблоном default_tech."""

import logging
import sys
from datetime import date
from pathlib import Path

from core import CertificateData, CertificateEngine, CertificateError

PROJECT_ROOT = Path(__file__).resolve().parent


def build_sample_certificate() -> CertificateData:
    return CertificateData(
        template_name="default_tech",
        certificate_id="PY-ADV-2026-000123",
        issue_date=date.today(),
        fields={
            "full_name": "Олексій Чорней",
            "birth_date": "12.03.2004",
            "course_name": "Python Advanced: архітектура, тестування та продуктивність",
            "instructor_name": "Марія Коваленко",
        },
        images={
            "instructor_sign": str(PROJECT_ROOT / "assets" / "signs" / "sign1.png"),
        },
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    try:
        engine = CertificateEngine(
            templates_dir=PROJECT_ROOT / "templates",
            output_dir=PROJECT_ROOT / "output",
        )
        certificate = build_sample_certificate()
        jpg_path = engine.generate(certificate)
        pdf_path = engine.generate(certificate, output_format="pdf")
    except CertificateError as exc:
        logging.error("Генерацію перервано: %s", exc)
        return 1

    print(f"Готово:\n  {jpg_path}\n  {pdf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
