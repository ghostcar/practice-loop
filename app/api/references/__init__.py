"""Reference data and task-link API aggregator (REFACTORING.md step 3).

Route implementations moved to:
- body_parts.py  (BodyPart catalog)
- locations.py   (TaskLocation catalog + user CRUD)
- categories.py  (InventoryCategory reference)
- task_targets.py (task body/location/inventory links + search + available inventory)

The aggregated router is exposed here so ``from app.api.references import router``
(main.py) continues to work unchanged.
"""

from fastapi import APIRouter

from app.api.references.body_parts import router as _bp
from app.api.references.categories import router as _cat
from app.api.references.locations import router as _loc
from app.api.references.task_targets import router as _tt

router = APIRouter(prefix="/api/v2", tags=["references"])
router.include_router(_bp)
router.include_router(_cat)
router.include_router(_loc)
router.include_router(_tt)
