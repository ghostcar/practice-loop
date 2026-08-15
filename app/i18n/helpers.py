"""Shared i18n helpers: locale and theme detection."""

from fastapi import Request

from app.i18n import FALLBACK_LOCALE, get_supported_locales


def detect_locale(request: Request, user_locale: str | None = None) -> str:
    """Detect locale: user preference → Accept-Language → fallback."""
    if user_locale and user_locale in get_supported_locales():
        return user_locale

    accept_lang = request.headers.get("accept-language", "")
    for lang in get_supported_locales():
        if lang in accept_lang:
            return lang

    return FALLBACK_LOCALE


def detect_theme(user_theme: str | None = None) -> str:
    """Resolve theme for SSR: user preference → default dark.

    ``system`` (Step 9e) is resolved to a concrete value for the server render;
    the raw choice is kept in ``prefs.theme_choice`` so app.js can re-resolve
    it against the OS ``prefers-color-scheme`` on the client.
    """
    if user_theme in ("dark", "light"):
        return user_theme
    return "dark"
