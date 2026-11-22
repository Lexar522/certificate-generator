"""Налаштування користувача між запусками: тема, акцент, останній шаблон, розмір вікна."""

from dataclasses import dataclass, replace

from PySide6.QtCore import QByteArray, QSettings

from gui.theme import ACCENTS, DEFAULT_ACCENT, ThemeMode

ORGANIZATION = "KSU"
APPLICATION = "CertificateGenerator"
THEME_MODES: tuple[ThemeMode, ...] = ("system", "light", "dark")


@dataclass(frozen=True)
class UserSettings:
    theme_mode: ThemeMode = "system"
    accent: str = DEFAULT_ACCENT
    last_template: str | None = None
    geometry: QByteArray | None = None


def _store() -> QSettings:
    return QSettings(ORGANIZATION, APPLICATION)


def load_settings() -> UserSettings:
    store = _store()
    mode = store.value("appearance/theme", "system")
    accent = store.value("appearance/accent", DEFAULT_ACCENT)
    geometry = store.value("window/geometry")
    return UserSettings(
        theme_mode=mode if mode in THEME_MODES else "system",
        accent=accent if accent in ACCENTS else DEFAULT_ACCENT,
        last_template=store.value("editor/last_template") or None,
        geometry=geometry if isinstance(geometry, QByteArray) else None,
    )


def save_settings(settings: UserSettings) -> None:
    store = _store()
    store.setValue("appearance/theme", settings.theme_mode)
    store.setValue("appearance/accent", settings.accent)
    store.setValue("editor/last_template", settings.last_template or "")
    if settings.geometry is not None:
        store.setValue("window/geometry", settings.geometry)
    store.sync()


def updated(settings: UserSettings, **changes) -> UserSettings:
    return replace(settings, **changes)
