"""Shared Jinja2 templates instance — import from here, not from app.main."""

from datetime import datetime

from fastapi import Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from app.timeutils import as_utc


def _csrf_context(request: Request) -> dict:
    """Inject the CSRF token cookie into every template context.

    Templates rely on `csrf_token` for native form hidden inputs and the HTMX
    meta tag. Without this processor the token was only injected on the
    dashboard and home pages, so every other page sent an empty token and all
    state-changing requests failed CSRF verification with 403.
    """
    return {"csrf_token": request.cookies.get("csrf_token", "")}


def _composition_context(request: Request) -> dict:
    """Inject ProductComposition into every template for dynamic navigation.

    Makes `composition` available in base.html nav blocks so that disabled
    domain modules never appear in the header / bottom nav.
    """
    from app.platform.composition import composition

    return {"composition": composition}


def _prefs_context(request: Request) -> dict:
    """Inject customization/discretion state (Step 9e, DESIGN_V2 §16).

    Reads the request-scoped prefs ContextVar populated by ``prefs_middleware``
    (app/main.py) — no per-page handler changes needed. `discretion_active` is
    resolved at render time so the schedule window follows the client timezone.
    """
    from app.prefs import get_prefs

    prefs = get_prefs()
    return {
        "prefs": prefs,
        "discretion_active": prefs.discretion_active_at(),
    }


templates = Jinja2Templates(
    directory="app/templates",
    context_processors=[_csrf_context, _composition_context, _prefs_context],
)


def _localtime(value, fmt: str = "%Y-%m-%d %H:%M") -> Markup:
    """Render a datetime as a device-timezone-aware ``<time>`` element.

    The backend stores everything in UTC. Templates emit
    ``<time datetime="...(+00:00)" data-tz-fmt="...">fallback</time>`` and a
    small helper in app.js rewrites the text to the device's local timezone.
    Falls back to plain server rendering for ``date`` objects (no timezone)
    and for clients without JavaScript.
    """
    if value is None:
        return Markup("")
    if isinstance(value, datetime):
        iso = as_utc(value).isoformat()
        fallback = value.strftime(fmt)
        return Markup(f'<time datetime="{escape(iso)}" data-tz-fmt="{escape(fmt)}">{escape(fallback)}</time>')
    return Markup(escape(value.strftime(fmt)))


templates.env.globals["localtime"] = _localtime
