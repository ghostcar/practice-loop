"""Medication Organizer API — router registration.

Split from monolithic medication.py (1047 lines → 2 focused modules).
"""

from app.api.medication.forms import router  # noqa: F401
from app.api.medication.json_api import json_router  # noqa: F401

# Re-export schedule_summary for cross-module imports (dashboard, today)
from app.services.med_service import schedule_summary as _schedule_summary  # noqa: F401
