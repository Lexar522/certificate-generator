"""Відомості про програму та автора (використовуються в GUI, CLI та README)."""

APP_NAME = "Генератор сертифікатів"
APP_VERSION = "1.1"
AUTHOR = "Чорней Олексій"
AUTHOR_INSTRUMENTAL = "Чорнеєм Олексієм"  # «розроблено студентом …»
GROUP: str | None = "51-371с"  # академічна група автора
UNIVERSITY = "Херсонський державний університет"
ORIGIN = "Програму розроблено під час виробничої практики"
YEAR = 2026


def credits_text() -> str:
    group = f", група {GROUP}" if GROUP else ""
    return f"{ORIGIN} студентом {AUTHOR_INSTRUMENTAL}{group}.\n{UNIVERSITY}, {YEAR}."
