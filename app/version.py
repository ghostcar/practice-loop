"""Single source of truth for the application version (audit P1-7).

FastAPI metadata, the full-data export header and any CLI/docs that need a
version must import ``__version__`` from here instead of hardcoding their own.
Keep in sync with ``pyproject.toml`` / ``README.md``.
"""

__version__ = "0.8.0"
