"""Auth dependencies shared by the protected API routers."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import Account, AccountRole
from ..services import api_tokens, auth

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_LEVEL = {AccountRole.viewer: 0, AccountRole.editor: 1, AccountRole.admin: 2}


async def current_account(
    request: Request, session: AsyncSession = Depends(get_session)
) -> Account:
    """The logged-in account behind the session cookie.

    Cookie only — an API token is not an account and cannot reach the routes
    that use this (account and agent management). Use `enforce_access` for the
    ordinary data routes, which a token may read.
    """
    token = request.cookies.get(auth.COOKIE_NAME, "")
    account = await auth.account_for_token(session, token)
    if account is None:
        raise HTTPException(401, "Invalid or expired session")
    return account


def require(min_role: AccountRole):
    async def _dep(account: Account = Depends(current_account)) -> Account:
        if _LEVEL[account.role] < _LEVEL[min_role]:
            raise HTTPException(403, "Not permitted to perform this action")
        return account

    return _dep


require_admin = require(AccountRole.admin)


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return ""


async def enforce_access(
    request: Request, session: AsyncSession = Depends(get_session)
) -> Account:
    """Login for the data routes; writes need at least `editor`.

    Accepts either a session cookie or an `nsk_` API token. A token is always
    treated as `viewer`, so it reads and nothing else — a write returns 403 just
    as it would for a read-only account.
    """
    presented = _bearer(request)
    if api_tokens.looks_like_token(presented):
        row = await api_tokens.authenticate(session, presented)
        if row is None:
            raise HTTPException(401, "Invalid API token")
        # a transient, unpersisted Account carrying only the token's role
        account = Account(username=f"token:{row.name}", role=AccountRole.viewer)
    else:
        account = await current_account(request, session)

    if request.method not in _SAFE_METHODS and account.role == AccountRole.viewer:
        raise HTTPException(403, "Read-only account")
    return account
