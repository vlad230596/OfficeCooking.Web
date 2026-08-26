from uuid import UUID

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.contracts.auth import (
    AccountResponse,
    CurrentUserResponse,
    LoginRequest,
    UpdateAccountRequest,
)
from app.authentication import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    Principal,
    create_auth_session,
    hash_password,
    revoke_user_sessions,
    verify_password,
)
from app.models import AuthSession, User

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


def _error(request: Request, code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "fieldErrors": [],
                "details": {},
                "requestId": getattr(request.state, "request_id", "unavailable"),
            }
        },
    )


def _current(principal: Principal) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=principal.user_id, name=principal.name, username=principal.username, role=principal.role
    )


@router.post("/login", response_model=CurrentUserResponse)
async def login(
    payload: LoginRequest, request: Request, response: Response
) -> CurrentUserResponse | JSONResponse:
    async with request.app.state.session_factory() as session:
        result = await session.execute(
            select(User).where(func.lower(User.username) == payload.username.strip().lower())
        )
        user = result.scalar_one_or_none()
        if (
            user is None
            or not user.auth_enabled
            or not user.password_hash
            or not verify_password(payload.password, user.password_hash)
        ):
            return _error(
                request,
                "invalid_credentials",
                "Invalid username or password.",
                status.HTTP_401_UNAUTHORIZED,
            )
        token, csrf_token, _ = await create_auth_session(session, user, request.app.state.settings)
    cookie_options = dict(
        secure=request.app.state.settings.session_cookie_secure,
        samesite="strict",
        path="/",
    )
    response.set_cookie(SESSION_COOKIE, token, httponly=True, **cookie_options)
    response.set_cookie(CSRF_COOKIE, csrf_token, httponly=False, **cookie_options)
    return CurrentUserResponse(id=user.id, name=user.name, username=user.username, role=user.role)


@router.get("/me", response_model=CurrentUserResponse)
async def me(request: Request) -> CurrentUserResponse:
    return _current(request.state.principal)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> None:
    principal: Principal = request.state.principal
    async with request.app.state.session_factory() as session:
        stored = await session.get(AuthSession, principal.token_hash)
        if stored is not None:
            await session.delete(stored)
            await session.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


@router.get("/accounts", response_model=list[AccountResponse])
async def accounts(request: Request) -> list[AccountResponse]:
    async with request.app.state.session_factory() as session:
        users = (await session.execute(select(User).order_by(User.name, User.id))).scalars().all()
    return [
        AccountResponse(
            id=u.id,
            name=u.name,
            username=u.username or "",
            role=u.role,
            auth_enabled=u.auth_enabled,
        )
        for u in users
    ]


@router.put("/accounts/{user_id}", response_model=AccountResponse)
async def update_account(
    user_id: UUID, payload: UpdateAccountRequest, request: Request
) -> AccountResponse | JSONResponse:
    async with request.app.state.session_factory() as session:
        user = await session.get(User, user_id)
        if user is None:
            return _error(
                request, "user_not_found", "User was not found.", status.HTTP_404_NOT_FOUND
            )
        new_username = payload.username if payload.username is not None else user.username
        if payload.auth_enabled and not new_username:
            return _error(
                request,
                "username_required",
                "An enabled account requires a username.",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if payload.auth_enabled and not payload.password and not user.password_hash:
            return _error(
                request,
                "password_required",
                "An enabled account requires a password.",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        user.username = new_username if payload.auth_enabled else payload.username
        user.role = payload.role
        user.auth_enabled = payload.auth_enabled
        if payload.password:
            user.password_hash = hash_password(payload.password)
        await revoke_user_sessions(session, user_id)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return _error(
                request,
                "username_conflict",
                "This username is already in use.",
                status.HTTP_409_CONFLICT,
            )
        return AccountResponse(
            id=user.id,
            name=user.name,
            username=user.username or "",
            role=user.role,
            auth_enabled=user.auth_enabled,
        )
