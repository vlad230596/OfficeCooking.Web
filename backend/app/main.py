import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.health import router as health_router
from app.api.routes.auth import router as auth_router
from app.api.routes.balances import router as balances_router
from app.api.routes.catalog import router as catalog_router
from app.api.routes.cooks import router as cooks_router
from app.api.routes.zenmoney import router as zenmoney_router
from app.auth_middleware import AuthenticationMiddleware
from app.config import Settings, get_settings
from app.database import create_engine, create_session_factory
from app.request_context import RequestIdMiddleware
from app.security import JsonMutationMiddleware
from app.services.zenmoney import ZenMoneyError
from app.services.zenmoney import sync as sync_zenmoney

logger = logging.getLogger(__name__)


async def _run_zenmoney_sync(app: FastAPI, interval_minutes: int) -> None:
    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            async with app.state.session_factory() as session:
                await sync_zenmoney(session, app.state.settings)
        except ZenMoneyError as error:
            if error.code != "not_configured":
                logger.warning("Scheduled ZenMoney sync failed: %s", error.code)
        except Exception:
            logger.exception("Scheduled ZenMoney sync failed unexpectedly")


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    engine = create_engine(resolved_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        sync_task = None
        encryption_key = resolved_settings.zenmoney_encryption_key
        if (
            encryption_key is not None and encryption_key.get_secret_value()
        ) or resolved_settings.environment.casefold() == "production":
            sync_task = asyncio.create_task(
                _run_zenmoney_sync(app, resolved_settings.zenmoney_sync_interval_minutes)
            )
        yield
        if sync_task is not None:
            sync_task.cancel()
            with suppress(asyncio.CancelledError):
                await sync_task
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
    app.include_router(zenmoney_router)
    return app


app = create_app()
