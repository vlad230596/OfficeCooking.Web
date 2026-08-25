from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class JsonMutationMiddleware(BaseHTTPMiddleware):
    """Reject browser-simple content types on methods intended to mutate state."""

    _guarded_methods = frozenset({"POST", "PUT", "PATCH"})

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method == "DELETE":
            return JSONResponse(
                status_code=405,
                content={"detail": "DELETE is not available in the current API version."},
                headers={"Allow": "GET, POST, PUT, PATCH, OPTIONS"},
            )
        if request.method in self._guarded_methods:
            media_type = request.headers.get("content-type", "").split(";", 1)[0].lower().strip()
            if media_type != "application/json" and not media_type.endswith("+json"):
                return JSONResponse(
                    status_code=415,
                    content={
                        "detail": "Mutating requests must use an application/json content type."
                    },
                )
        return await call_next(request)
