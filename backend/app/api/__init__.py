from fastapi import APIRouter, Depends

from . import (
    actions,
    agents,
    auth,
    brands,
    devices,
    events,
    os_logos,
    scan,
    settings,
    stats,
    stream,
    users,
    wan,
)
from .deps import enforce_access

api_router = APIRouter(prefix="/api")

# Open: the auth flow itself, the notification-button endpoints, and the agent
# enrol/report routes — those last two carry their own token rather than a
# browser session. (Agent *management* routes guard themselves, see agents.py.)
api_router.include_router(auth.router)
api_router.include_router(actions.router)
api_router.include_router(agents.router)

# Everything else requires a login; writes require at least an `editor`.
_protected = APIRouter(dependencies=[Depends(enforce_access)])
for _module in (devices, events, users, brands, os_logos, stats, settings, scan, stream, wan):
    _protected.include_router(_module.router)
api_router.include_router(_protected)
