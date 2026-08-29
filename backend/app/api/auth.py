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
    AuthStatusOut,
    LoginIn,
    ProfileUpdateIn,
)
from ..services import auth
from .deps import current_account, require_admin

router = APIRouter(prefix="/auth", tags=["auth"])

_MIN_PASSWORD = 8


def _clean_username(raw: str) -> str:
    name = (raw or "").strip().lower()
    if not (2 <= len(name) <= 64) or not all(
        c.isalnum() or c in "._-" for c in name
    ):
        raise HTTPException(422, "Nome de utilizador inválido")
    return name


def _check_password(raw: str) -> str:
    if len(raw or "") < _MIN_PASSWORD:
        raise HTTPException(422, f"A palavra-passe precisa de {_MIN_PASSWORD}+ caracteres")
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
        raise HTTPException(409, "A configuração inicial já foi feita")
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
        raise HTTPException(429, "Demasiadas tentativas; tenta novamente daqui a pouco")
    account = (
        await session.execute(select(Account).where(Account.username == username))
    ).scalars().first()
    if account is None or not auth.verify_password(payload.password, account.password_hash):
        auth.note_failure(username)
        raise HTTPException(401, "Credenciais inválidas")
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
        raise HTTPException(403, "Palavra-passe atual errada")
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
                raise HTTPException(409, "Esse nome de utilizador já existe")
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
        raise HTTPException(409, "Esse nome de utilizador já existe")
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
        raise HTTPException(404, "Conta não encontrada")
    if (
        payload.role is not None
        and payload.role != AccountRole.admin
        and account.role == AccountRole.admin
        and await _last_admin(session, account.id)
    ):
        raise HTTPException(409, "Tem de existir pelo menos um admin")
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
        raise HTTPException(404, "Conta não encontrada")
    if account.id == me.id:
        raise HTTPException(409, "Não podes apagar a tua própria conta")
    if account.role == AccountRole.admin and await _last_admin(session, account.id):
        raise HTTPException(409, "Tem de existir pelo menos um admin")
    await session.delete(account)
    await session.commit()
