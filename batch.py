"""Пакетна генерація з командного рядка (для автоматизації, cron, скриптів).

Приклади:
    python batch.py default_tech                       # усе з templates/default_tech/batch.json
    python batch.py default_tech --source examples/students.csv --format pdf --merge-pdf
    python batch.py default_tech --source "https://docs.google.com/spreadsheets/d/…/edit" --dry-run
"""

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from core import about
from core.batch import (
    BatchProfile,
    build_items,
    load_profile,
    parse_date,
    run_batch,
    suggest_columns,
)
from core.exceptions import CertificateError
from core.table_source import load_table
from core.template_catalog import describe_inputs
from core.template_loader import load_template_config, resolve_template_dir

PROJECT_ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"
EXIT_OK, EXIT_ROW_ERRORS, EXIT_FAILURE = 0, 1, 2


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"{about.APP_NAME}: сертифікати для всієї групи з Google Таблиці або CSV.",
        epilog=about.credits_text(),
    )
    parser.add_argument("template", help="назва шаблону (папка в templates/)")
    parser.add_argument("--source", help="посилання на Google Таблицю або шлях до CSV")
    parser.add_argument("--output", help="папка для результатів")
    parser.add_argument("--format", choices=("jpg", "png", "pdf"), help="формат файлів")
    parser.add_argument("--merge-pdf", action="store_true", help="також зібрати всі сертифікати в один PDF")
    parser.add_argument(
        "--map",
        action="append",
        default=[],
        metavar="ПОЛЕ=КОЛОНКА",
        help="відповідність поля колонці, напр. --map full_name=ПІБ (можна кілька)",
    )
    parser.add_argument("--issue-date", help="дата видачі (дд.мм.рррр), якщо не береться з таблиці")
    parser.add_argument("--dry-run", action="store_true", help="лише перевірити дані, без створення файлів")
    return parser.parse_args(argv)


def build_profile(args: argparse.Namespace, saved: BatchProfile) -> BatchProfile:
    """Профіль із batch.json шаблону, перевизначений аргументами командного рядка."""
    columns = dict(saved.columns)
    for item in args.map:
        field, separator, column = item.partition("=")
        if not separator or not field.strip() or not column.strip():
            raise CertificateError(f"Неправильний формат --map «{item}», очікується ПОЛЕ=КОЛОНКА")
        columns = columns | {field.strip(): column.strip()}
    changes = {
        "source": args.source or saved.source,
        "columns": columns,
        "output_dir": args.output or saved.output_dir,
        "output_format": args.format or saved.output_format,
        "merge_pdf": args.merge_pdf or saved.merge_pdf,
    }
    return BatchProfile.model_validate(saved.model_dump() | changes)


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    args = parse_args(argv)
    try:
        template_dir = resolve_template_dir(TEMPLATES_DIR, args.template)
        config = load_template_config(template_dir)
        profile = build_profile(args, load_profile(template_dir))
        if not profile.source:
            raise CertificateError("Не вказано джерело: додайте --source або налаштуйте «Для групи…» у програмі")

        table = load_table(profile.source, PROJECT_ROOT)
        inputs = describe_inputs(config)
        if not profile.columns:
            profile = profile.model_copy(update={"columns": suggest_columns(inputs, table.headers)})
            print(f"Автопідбір колонок: {profile.columns}")
        issue_date = parse_date(args.issue_date) if args.issue_date else date.today()
        items = build_items(table, profile, template_dir.name, inputs, issue_date)
    except CertificateError as exc:
        print(f"Помилка: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    ready = sum(1 for item in items if item.data is not None)
    print(f"Рядків: {len(items)} · готові: {ready} · з помилками: {len(items) - ready}")
    for item in items:
        if item.error:
            print(f"  рядок {item.row_number}: {item.error}")
    if args.dry_run:
        return EXIT_OK if ready == len(items) else EXIT_ROW_ERRORS

    output_dir = Path(profile.output_dir).expanduser()
    output_dir = output_dir if output_dir.is_absolute() else PROJECT_ROOT / output_dir
    try:
        report = run_batch(
            items,
            template_dir,
            config,
            output_dir,
            profile,
            on_progress=lambda done, total: print(f"\r  {done}/{total}", end="", flush=True),
        )
    except CertificateError as exc:
        print(f"\nПомилка: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    print(f"\nСтворено: {len(report.created)} у {output_dir}")
    if report.merged_pdf:
        print(f"Спільний PDF: {report.merged_pdf}")
    return EXIT_OK if not report.failed else EXIT_ROW_ERRORS


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
