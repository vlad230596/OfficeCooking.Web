from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import text

router = APIRouter(tags=["health"])


@router.get("/health", summary="Process liveness")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/version", summary="Backend build information")
async def version(request: Request) -> dict[str, str]:
    settings = request.app.state.settings
    return {
        "component": "backend",
        "version": settings.app_version,
        "buildDate": settings.build_date,
    }


@router.get("/ready", summary="Database readiness")
async def ready(request: Request) -> dict[str, str]:
    try:
        async with request.app.state.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc
    return {"status": "ready"}
