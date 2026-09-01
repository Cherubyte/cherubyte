from fastapi import APIRouter, Depends

from . import (
    actions,
    agents,
    auth,
    brands,
    devices,
    events,
    hoststats,
    metrics,
    os_logos,
    provisioning,
    scan,
    settings,
    stats,
    stream,
    topology,
    users,
    wan,
)
from .deps import enforce_access

api_router = APIRouter(prefix="/api")

# Open: the auth flow itself, the notification-button endpoints, the agent
# enrol/report routes, and the Prometheus scrape — the last three carry their
# own token (or none) rather than a browser session. (Agent *management* routes
# guard themselves, see agents.py.)
api_router.include_router(auth.router)
api_router.include_router(actions.router)
api_router.include_router(agents.router)
api_router.include_router(metrics.router)
# Provisioning carries its own key and is about a tenant rather than from one;
# it refuses outright in single-tenant mode, so mounting it always is safe and
# keeps the hosted configuration testable.
api_router.include_router(provisioning.router)

# Everything else requires a login; writes require at least an `editor`.
_protected = APIRouter(dependencies=[Depends(enforce_access)])
for _module in (devices, events, users, brands, os_logos, stats, settings, scan, stream, topology, wan, hoststats):
    _protected.include_router(_module.router)
api_router.include_router(_protected)
