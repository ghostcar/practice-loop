"""Backward-compatibility shim.

All code has been moved to ``app.services.med`` package (12 focused modules).
This module re-exports every public symbol so existing imports keep working.

Preferred new import::

    from app.services.med import schedule_summary, med_dict, ...
"""

from __future__ import annotations

# Re-export everything from the new package
from app.services.med import *  # noqa: F401, F403
