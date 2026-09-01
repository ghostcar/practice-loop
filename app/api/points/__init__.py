"""Points economy, schedule, measurements, inventory, gamification config (REFACTORING.md step 4).

Sub-modules:
- helpers.py   — _get_progress (shared helper, no router)
- config.py    — gamification config (get/update)
- balance.py   — points balance + spend
- profiles.py  — profiles CRUD + assign
- redemptions.py — penalty redemptions (list/complete/skip)
- schedule.py  — today schedule + rules CRUD
- measurements.py — body measurements CRUD + charts
- inventory.py — inventory CRUD + reorder + images + shopping
- charts.py    — activity/points/XP/category/completion charts
- pages.py     — HTML pages (measurements/inventory/schedule/points)

The aggregated router is exposed here so ``from app.api.points import router``
(main.py) continues to work.
"""

from fastapi import APIRouter

from app.api.points.balance import router as _bal
from app.api.points.charts import router as _cht
from app.api.points.config import router as _cfg
from app.api.points.inventory import router as _inv
from app.api.points.measurements import router as _msr
from app.api.points.pages import page_router as _pages
from app.api.points.pages import router as _pgs
from app.api.points.profiles import router as _prf
from app.api.points.redemptions import router as _red
from app.api.points.schedule import router as _sch

router = APIRouter(prefix="/api/v2", tags=["v2"])
router.include_router(_bal)
router.include_router(_cht)
router.include_router(_cfg)
router.include_router(_inv)
router.include_router(_msr)
router.include_router(_pgs)

# HTML page routes are mounted separately by app.main without /api/v2.
page_router = _pages
router.include_router(_prf)
router.include_router(_red)
router.include_router(_sch)
