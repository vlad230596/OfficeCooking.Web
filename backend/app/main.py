from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.health import router as health_router
from app.api.routes.auth import router as auth_router
from app.api.routes.balances import router as balances_router
from app.api.routes.catalog import router as catalog_router
from app.api.routes.cooks import router as cooks_router
from app.auth_middleware import AuthenticationMiddleware
from app.config import Settings, get_settings
from app.database import create_engine, create_session_factory
from app.request_context import RequestIdMiddleware
from app.security import JsonMutationMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    engine = create_engine(resolved_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        yield
        await engine.dispose()

    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        lifespan=lifespan,
    )
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.settings = resolved_settings

    app.add_middleware(JsonMutationMiddleware)
    app.add_middleware(AuthenticationMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=resolved_settings.allowed_hosts)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(catalog_router)
    app.include_router(cooks_router)
    app.include_router(balances_router)
    return app


app = create_app()
