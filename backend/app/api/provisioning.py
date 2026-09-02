"""Provisioning: create a tenant, seeded with its first account.

Multi-tenant only, and only the control plane calls it. It carries its own
key rather than a browser session because there is no browser and no tenant
yet — the request is *about* a tenant, not from one — and so it does not go
through get_session() or the tenant header at all.

Seeding the account is the point, not a convenience. The panel's normal
first run is "whoever arrives first creates the admin", which is right for a
box in somebody's cupboard and catastrophic for a database that just became
reachable from the internet. So a tenant never comes into being without its
account, and if the account cannot be written the database is taken back
out rather than left in that state.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from sqlalchemy import select

from ..config import settings
from ..database import (
    discard_tenant,
    provision_tenant,
    scoped_to,
    session_for,
    tenant_db_path,
)
from ..models import Account, AccountRole
from ..services import auth
from ..tenancy import validate_tenant_id
from .auth import _check_password, _clean_username

logger = logging.getLogger("cherubyte.provisioning")

router = APIRouter(prefix="/tenants", tags=["tenants"])


class TenantCreateIn(BaseModel):
    """Kept here rather than in schemas.py: nothing the SPA sends looks like
    this, and the whole provisioning contract reads better in one file."""

    tenant_id: str = Field(min_length=3, max_length=64)
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class TenantOut(BaseModel):
    tenant_id: str
    username: str


def _authorised(presented: str | None) -> bool:
    # An unset key admits nobody, never everybody — forgetting to set the
    # secret must lock provisioning, not open it. Same rule the edge applies
    # to its own Access secrets, for the same reason.
    expected = settings.provision_key
    if not expected or not presented:
        return False
    return hmac.compare_digest(presented.encode(), expected.encode())


@router.post("", response_model=TenantOut, status_code=201)
async def create_tenant(payload: TenantCreateIn, request: Request):
    if not settings.multi_tenant:
        # In single-tenant mode this route does not exist, and it answers the
        # way a route that never existed would.
        raise HTTPException(404, "Not Found")
    if not _authorised(request.headers.get(settings.provision_header)):
        raise HTTPException(403, "Not authorised")

    try:
        tenant_id = validate_tenant_id(payload.tenant_id)
    except ValueError:
        raise HTTPException(422, "Invalid tenant id") from None
    # The same rules the login flow applies, from the same functions, so a
    # username that provisioning accepts is one that login will too.
    username = _clean_username(payload.username)
    password = _check_password(payload.password)

    if tenant_db_path(tenant_id).exists():
        raise HTTPException(409, "Tenant exists")

    await provision_tenant(tenant_id)
    try:
        await _seed_account(tenant_id, username, password)
    except Exception:
        # Half a tenant is worse than none: a database with no account is
        # exactly the state the seed exists to prevent.
        logger.exception("Seeding tenant %s failed; removing its database", tenant_id)
        await discard_tenant(tenant_id)
        raise HTTPException(500, "Provisioning failed") from None

    logger.info("Provisioned tenant %s", tenant_id)
    return TenantOut(tenant_id=tenant_id, username=username)


class SessionOut(BaseModel):
    token: str
    username: str
    max_age: int


@router.post("/{tenant_id}/session", response_model=SessionOut, status_code=201)
async def mint_session(tenant_id: str, request: Request):
    """Mint a panel session for a tenant's owner, without a password.

    The login window has already established who this is — by email, against
    its own registry — and the panel has no way to check an email because its
    accounts are usernames. Rather than have the login window hold a password
    to replay, it asks for a session directly.

    This is a skeleton key, so it is guarded exactly like provisioning, and it
    is reachable only from the box: nothing outside can present the key.
    """
    if not settings.multi_tenant:
        raise HTTPException(404, "Not Found")
    if not _authorised(request.headers.get(settings.provision_header)):
        raise HTTPException(403, "Not authorised")
    try:
        tenant_id = validate_tenant_id(tenant_id)
    except ValueError:
        raise HTTPException(422, "Invalid tenant id") from None
    if not tenant_db_path(tenant_id).exists():
        raise HTTPException(404, "Unknown tenant")

    async with scoped_to(tenant_id) as session:
        account = (
            await session.execute(select(Account).where(Account.role == AccountRole.admin))
        ).scalars().first()
        if account is None:
            # A tenant with no account is the state provisioning exists to
            # prevent; if one is ever seen, it is not something to paper over.
            logger.error("Tenant %s has no admin account", tenant_id)
            raise HTTPException(409, "Tenant has no account")
        row = await auth.create_session(session, account, request.headers.get("user-agent"))
        await session.commit()
        return SessionOut(
            token=row.token,
            username=account.username,
            max_age=int(auth.SESSION_TTL.total_seconds()),
        )


async def _seed_account(tenant_id: str, username: str, password: str) -> None:
    session = await session_for(tenant_id)
    async with session:
        session.add(
            Account(
                username=username,
                password_hash=auth.hash_password(password),
                role=AccountRole.admin,
            )
        )
        await session.commit()
