"""Auth dependencies shared by the protected API routers."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import Account, AccountRole
from ..services import auth

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_LEVEL = {AccountRole.viewer: 0, AccountRole.editor: 1, AccountRole.admin: 2}


async def current_account(
    request: Request, session: AsyncSession = Depends(get_session)
) -> Account:
    token = request.cookies.get(auth.COOKIE_NAME, "")
    account = await auth.account_for_token(session, token)
    if account is None:
        raise HTTPException(401, "Sessão inválida ou expirada")
    return account


def require(min_role: AccountRole):
    async def _dep(account: Account = Depends(current_account)) -> Account:
        if _LEVEL[account.role] < _LEVEL[min_role]:
            raise HTTPException(403, "Sem permissão para esta ação")
        return account

    return _dep


require_admin = require(AccountRole.admin)


async def enforce_access(
    request: Request, account: Account = Depends(current_account)
) -> Account:
    """Login for everything; writes need at least `editor`."""
    if request.method not in _SAFE_METHODS and account.role == AccountRole.viewer:
        raise HTTPException(403, "Conta só de leitura")
    return account
