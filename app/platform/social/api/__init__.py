"""Platform Social — API routes (REFACTORING.md step 6).

Sub-routers:
- profile.py      — profile + consent + privacy (S0)
- subjects.py     — subject registry (S1)
- relationships.py — invites, blocks, grants (S2)
- feed.py         — publications & feed (S3)
- verification.py — verification requests & votes (S4)
- comments.py     — comments & encouragements (S4)
- moderation.py   — reports & actions (S5)

Aggregated router exposed as ``from app.platform.social.api import router``
(main.py continues to work unchanged).
"""

from fastapi import APIRouter

from app.platform.social.api.comments import router as _com
from app.platform.social.api.feed import router as _feed
from app.platform.social.api.leaderboard import router as _ldr
from app.platform.social.api.moderation import router as _mod
from app.platform.social.api.pillory import router as _pil
from app.platform.social.api.profile import router as _prf
from app.platform.social.api.relationships import router as _rel
from app.platform.social.api.subjects import router as _sub
from app.platform.social.api.verification import router as _ver

router = APIRouter(prefix="/social", tags=["social"])
router.include_router(_com)
router.include_router(_feed)
router.include_router(_ldr)
router.include_router(_mod)
router.include_router(_pil)
router.include_router(_prf)
router.include_router(_rel)
router.include_router(_sub)
router.include_router(_ver)
