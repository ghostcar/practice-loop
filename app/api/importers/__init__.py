"""Import handlers package — one module per import type (REFACTORING.md step 2).

Split from app/api/import_data.py: measurements, inventory, entities, schedule,
points, training, activity_logs, body_parts, locations, categories — plus
base.py (CSV/JSON dispatch + shared helpers). The FastAPI router stays in
app/api/import_data.py.
"""
