"""Personal Contour — router registration.

All sub-handlers are imported here to register their handlers on the
shared ``personal_router``.  Import ``personal_router`` from this
package to include all personal contour routes in your bot.
"""

# Import all sub-modules to register their handlers on personal_router
from app.telegram.pc import (
    ai_gen,  # noqa: F401
    games,  # noqa: F401
    health,  # noqa: F401
    inventory,  # noqa: F401
    medications,  # noqa: F401
    nav,  # noqa: F401
    pillory,  # noqa: F401
    stats,  # noqa: F401
    status,  # noqa: F401
    tasks,  # noqa: F401
    training,  # noqa: F401
    wear,  # noqa: F401
)
from app.telegram.pc.helpers import personal_router  # noqa: F401
