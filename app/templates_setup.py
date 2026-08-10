"""Shared Jinja2 templates instance — import from here, not from app.main."""

from fastapi import Request
from fastapi.templating import Jinja2Templates


def _csrf_context(request: Request) -> dict:
    """Inject the CSRF token cookie into every template context.

    Templates rely on `csrf_token` for native form hidden inputs and the HTMX
    meta tag. Without this processor the token was only injected on the
    dashboard and home pages, so every other page sent an empty token and all
    state-changing requests failed CSRF verification with 403.
    """
    return {"csrf_token": request.cookies.get("csrf_token", "")}


templates = Jinja2Templates(
    directory="app/templates",
    context_processors=[_csrf_context],
)
