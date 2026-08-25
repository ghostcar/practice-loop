"""Import/Export module: CSV/JSON templates, upload, API for external services, full export.

Per-type import handlers live in app/api/importers/* (imported from there).
Template/export metadata and export logic live in app/services/import_data_service.py.
This module keeps only thin HTTP handlers.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.api.importers.base import _import_csv, _import_json
from app.auth import get_optional_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.user import User
from app.schemas.points_v2 import ImportPayload
from app.services.import_data_service import (
    export_data_by_type,
    export_full_data,
    get_import_page_context,
    get_template_download,
    list_templates_meta,
)
from app.templates_setup import templates

router = APIRouter(prefix="/import", tags=["import"])


@router.get("/templates")
async def list_templates():
    """List all available import templates with labels."""
    return list_templates_meta()


@router.get("/template/{template_type}")
async def get_template(
    template_type: str,
    format: str = Query(default="csv"),
):
    """Download a template for external services (CSV or JSON)."""
    try:
        return get_template_download(template_type, format)
    except ValueError as e:
        code = 400 if "Format" in str(e) else 404
        raise HTTPException(code, str(e))


@router.get("", response_class=HTMLResponse)
async def import_page(
    request: Request,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Import/Export management page."""
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    ctx = get_import_page_context(str(request.base_url).rstrip("/"))
    return templates.TemplateResponse(
        request=request,
        name="import_data.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "import",
            **ctx,
        },
    )


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload a CSV or JSON file for import. Auto-detects type from headers."""
    content = await file.read()
    filename = file.filename or ""

    if filename.endswith(".csv"):
        return await _import_csv(content.decode("utf-8"), db, user)
    elif filename.endswith(".json"):
        return await _import_json(json.loads(content.decode("utf-8")), db, user)
    else:
        raise HTTPException(400, "Unsupported file format. Use .csv or .json")


@router.post("/api")
async def api_push(
    payload: ImportPayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """API endpoint for external services to push data (JSON)."""
    return await _import_json(
        {"import_type": payload.import_type, "data": payload.data},
        db,
        user,
        mode=payload.mode,
    )


# ═══════════════════════════════════════════════════════════
# Export endpoints
# ═══════════════════════════════════════════════════════════


@router.get("/export/full")
async def export_full(
    format: str = Query(default="json"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Full backup: export ALL user data as a single JSON."""
    try:
        return await export_full_data(db, user, format)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/export/{export_type}")
async def export_type(
    export_type: str,
    format: str = Query(default="json"),
    limit: int = Query(default=10000, ge=1, le=100000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Export user data by type as JSON or CSV."""
    try:
        return await export_data_by_type(db, user, export_type, format, limit)
    except ValueError as e:
        code = 400 if "format" in str(e).lower() or "limit" in str(e).lower() else 404
        raise HTTPException(code, str(e))
