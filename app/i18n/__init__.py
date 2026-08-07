from typing import Any

from app.i18n.en import EN
from app.i18n.ru import RU

TRANSLATIONS: dict[str, dict[str, Any]] = {
    "en": EN,
    "ru": RU,
}

FALLBACK_LOCALE = "en"
SUPPORTED_LOCALES = frozenset(TRANSLATIONS.keys())


def get_translations(locale: str) -> dict[str, Any]:
    """Return translation dict for the requested locale, falling back to EN."""
    if locale in TRANSLATIONS:
        return TRANSLATIONS[locale]
    return TRANSLATIONS[FALLBACK_LOCALE]


def get_supported_locales() -> frozenset[str]:
    return SUPPORTED_LOCALES
