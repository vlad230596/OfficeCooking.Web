from collections.abc import Awaitable, Callable

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.authentication import (
    CSRF_HEADER,
    SESSION_COOKIE,
    authenticate_session,
    digest_token,
    has_role,
    required_role,
)
from app.models import AuthSession


def _error(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
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


class AuthenticationMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        if (
            request.method == "OPTIONS"
            or not path.startswith("/api/v1")
            or path == "/api/v1/auth/login"
        ):
            return await call_next(request)

        token = request.cookies.get(SESSION_COOKIE)
        if not token:
            return _error(
                request,
                status.HTTP_401_UNAUTHORIZED,
                "authentication_required",
                "Sign in is required.",
            )
        async with request.app.state.session_factory() as session:
            principal = await authenticate_session(session, token)
            if principal is None:
                return _error(
                    request,
                    status.HTTP_401_UNAUTHORIZED,
                    "invalid_session",
                    "The session is invalid or expired.",
                )
            if not has_role(principal, required_role(request)):
                return _error(
                    request,
                    status.HTTP_403_FORBIDDEN,
                    "insufficient_permissions",
                    "Your role does not permit this action.",
                )
            if request.method in {"POST", "PUT", "PATCH"}:
                stored = await session.get(AuthSession, principal.token_hash)
                supplied = request.headers.get(CSRF_HEADER, "")
                if (
                    stored is None
                    or not supplied
                    or digest_token(supplied) != stored.csrf_token_hash
                ):
                    return _error(
                        request,
                        status.HTTP_403_FORBIDDEN,
                        "csrf_validation_failed",
                        "The request security token is missing or invalid.",
                    )
        request.state.principal = principal
        return await call_next(request)
