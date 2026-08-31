"""Login, logout, first-run setup, and account management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import Account, AccountRole
from ..schemas import (
    AccountCreateIn,
    AccountOut,
    AccountPatchIn,
    ApiTokenCreatedOut,
    ApiTokenCreateIn,
    ApiTokenOut,
    AuthStatusOut,
    LoginIn,
    ProfileUpdateIn,
)
from ..services import api_tokens, auth
from .deps import current_account, require_admin

router = APIRouter(prefix="/auth", tags=["auth"])

_MIN_PASSWORD = 8


def _clean_username(raw: str) -> str:
    name = (raw or "").strip().lower()
    if not (2 <= len(name) <= 64) or not all(
        c.isalnum() or c in "._-" for c in name
    ):
        raise HTTPException(422, "Invalid username")
    return name


def _check_password(raw: str) -> str:
    if len(raw or "") < _MIN_PASSWORD:
        raise HTTPException(422, f"Password needs to be {_MIN_PASSWORD}+ characters")
    return raw


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        auth.COOKIE_NAME,
        token,
        max_age=int(auth.SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        path="/",
    )


async def _last_admin(session: AsyncSession, exclude_id: int) -> bool:
    others = (
        await session.execute(
            select(Account.id).where(
                Account.role == AccountRole.admin, Account.id != exclude_id
            )
        )
    ).first()
    return others is None


@router.get("/status", response_model=AuthStatusOut)
async def status(request: Request, session: AsyncSession = Depends(get_session)):
    if await auth.count_accounts(session) == 0:
        return AuthStatusOut(setup_required=True)
    token = request.cookies.get(auth.COOKIE_NAME, "")
    account = await auth.account_for_token(session, token)
    await session.commit()  # persist a slid expiry
    return AuthStatusOut(
        setup_required=False,
        account=AccountOut.model_validate(account) if account else None,
    )


@router.post("/setup", response_model=AccountOut, status_code=201)
async def setup(
    payload: LoginIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    if await auth.count_accounts(session) > 0:
        raise HTTPException(409, "Initial setup is already done")
    account = Account(
        username=_clean_username(payload.username),
        password_hash=auth.hash_password(_check_password(payload.password)),
        role=AccountRole.admin,
    )
    session.add(account)
    await session.flush()
    row = await auth.create_session(session, account, request.headers.get("user-agent"))
    await session.commit()
    _set_cookie(response, row.token)
    return AccountOut.model_validate(account)


@router.post("/login", response_model=AccountOut)
async def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    username = (payload.username or "").strip().lower()
    if auth.is_locked_out(username):
        raise HTTPException(429, "Too many attempts; try again shortly")
    account = (
        await session.execute(select(Account).where(Account.username == username))
    ).scalars().first()
    if account is None or not auth.verify_password(payload.password, account.password_hash):
        auth.note_failure(username)
        raise HTTPException(401, "Invalid credentials")
    auth.clear_failures(username)
    row = await auth.create_session(session, account, request.headers.get("user-agent"))
    await session.commit()
    _set_cookie(response, row.token)
    return AccountOut.model_validate(account)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    _: Account = Depends(current_account),
):
    await auth.destroy_session(session, request.cookies.get(auth.COOKIE_NAME, ""))
    await session.commit()
    response.delete_cookie(auth.COOKIE_NAME, path="/")


@router.patch("/me", response_model=AccountOut)
async def update_me(
    payload: ProfileUpdateIn,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
):
    """Change your own username and/or password. The current password is the
    gate for both — a hijacked session then can't lock the real owner out."""
    if not auth.verify_password(payload.current, account.password_hash):
        raise HTTPException(403, "Current password is wrong")
    if payload.username is not None:
        new_name = _clean_username(payload.username)
        if new_name != account.username:
            taken = (
                await session.execute(
                    select(Account.id).where(
                        Account.username == new_name, Account.id != account.id
                    )
                )
            ).first()
            if taken is not None:
                raise HTTPException(409, "That username is already taken")
            account.username = new_name
    if payload.new_password is not None:
        account.password_hash = auth.hash_password(_check_password(payload.new_password))
    await session.commit()
    return AccountOut.model_validate(account)


@router.get("/accounts", response_model=list[AccountOut])
async def list_accounts(
    session: AsyncSession = Depends(get_session), _: Account = Depends(require_admin)
):
    res = await session.execute(select(Account).order_by(Account.username))
    return [AccountOut.model_validate(a) for a in res.scalars()]


@router.post("/accounts", response_model=AccountOut, status_code=201)
async def create_account(
    payload: AccountCreateIn,
    session: AsyncSession = Depends(get_session),
    _: Account = Depends(require_admin),
):
    username = _clean_username(payload.username)
    exists = (
        await session.execute(select(Account.id).where(Account.username == username))
    ).first()
    if exists is not None:
        raise HTTPException(409, "That username is already taken")
    account = Account(
        username=username,
        password_hash=auth.hash_password(_check_password(payload.password)),
        role=payload.role,
    )
    session.add(account)
    await session.commit()
    return AccountOut.model_validate(account)


@router.patch("/accounts/{account_id}", response_model=AccountOut)
async def update_account(
    account_id: int,
    payload: AccountPatchIn,
    session: AsyncSession = Depends(get_session),
    _: Account = Depends(require_admin),
):
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(404, "Account not found")
    if (
        payload.role is not None
        and payload.role != AccountRole.admin
        and account.role == AccountRole.admin
        and await _last_admin(session, account.id)
    ):
        raise HTTPException(409, "There has to be at least one admin")
    if payload.role is not None:
        account.role = payload.role
    if payload.password is not None:
        account.password_hash = auth.hash_password(_check_password(payload.password))
    await session.commit()
    return AccountOut.model_validate(account)


@router.delete("/accounts/{account_id}", status_code=204)
async def delete_account(
    account_id: int,
    session: AsyncSession = Depends(get_session),
    me: Account = Depends(require_admin),
):
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(404, "Account not found")
    if account.id == me.id:
        raise HTTPException(409, "You can't delete your own account")
    if account.role == AccountRole.admin and await _last_admin(session, account.id):
        raise HTTPException(409, "There has to be at least one admin")
    await session.delete(account)
    await session.commit()


# --- API tokens (admin-managed) ------------------------------------------

@router.get("/tokens", response_model=list[ApiTokenOut])
async def list_tokens(
    session: AsyncSession = Depends(get_session), _: Account = Depends(require_admin)
):
    rows = await api_tokens.list_all(session)
    return [ApiTokenOut.model_validate(r) for r in rows]


@router.post("/tokens", response_model=ApiTokenCreatedOut, status_code=201)
async def create_token(
    payload: ApiTokenCreateIn,
    session: AsyncSession = Depends(get_session),
    me: Account = Depends(require_admin),
):
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(422, "Give the token a name")
    row, secret = await api_tokens.create(session, name=name, created_by=me.id)
    await session.commit()
    out = ApiTokenCreatedOut.model_validate(row)
    out.token = secret  # shown exactly once
    return out


@router.delete("/tokens/{token_id}", status_code=204)
async def revoke_token(
    token_id: int,
    session: AsyncSession = Depends(get_session),
    _: Account = Depends(require_admin),
):
    if not await api_tokens.revoke(session, token_id):
        raise HTTPException(404, "Token not found")
    await session.commit()
