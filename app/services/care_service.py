"""Backward-compatibility shim.

All code has been moved to ``app.services.care`` package (9 focused modules).
This module re-exports every public symbol so existing imports keep working.
"""

from __future__ import annotations

from app.services.care import *  # noqa: F401, F403
