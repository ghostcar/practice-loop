"""Backward-compatibility shim.

All code has been moved to ``app.api.medication`` package (2 focused modules).
This module re-exports routers so existing registrations keep working.
"""

from __future__ import annotations

from app.api.medication import router, json_router  # noqa: F401
from app.api.medication import _schedule_summary  # noqa: F401
