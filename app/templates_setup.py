"""Shared Jinja2 templates instance — import from here, not from app.main."""

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
