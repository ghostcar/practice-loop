"""Response helpers for the dual-mode JSON-first contract (ADR-065, M4).

Action endpoints that historically returned an HTML redirect (for HTMX forms)
now also serve JSON to API/mobile clients: when the request carries an
``Authorization: Bearer`` header the response is JSON, otherwise the original
redirect is kept so the browser frontend is unaffected.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse


def is_bearer_request(request: Request) -> bool:
    """True when the request authenticates via the Authorization header.

    Cookie-authenticated (browser/HTMX) requests return False, so they keep
    the redirect behaviour they rely on.
    """
    auth = request.headers.get("authorization", "")
    return auth.lower().startswith("bearer ")


def is_json_requested(request: Request) -> bool:
    """True when client explicitly requests JSON via Bearer, Accept or AJAX header."""
    if is_bearer_request(request):
        return True
    accept = request.headers.get("accept", "").lower()
    if "application/json" in accept:
        return True
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def action_response(
    request: Request,
    *,
    json_body: dict,
    redirect_url: str,
    status_code: int = 303,
):
    """Return JSON for bearer/API clients and AJAX, redirect for HTML forms."""
    if is_json_requested(request):
        return JSONResponse(json_body)
    return RedirectResponse(redirect_url, status_code=status_code)

