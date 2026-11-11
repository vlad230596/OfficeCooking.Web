from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.contracts.settlements import ReplaceSettlementsRequest, SettlementsResponse
from app.api.routes.balances import get_session
from app.services.cooks import CookServiceError
from app.services.settlements import get_settlements, replace_settlements

router = APIRouter(prefix="/api/v1/cooks", tags=["settlements"])


def error_response(request: Request, exc: CookServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": str(exc),
                "details": exc.details,
                "fieldErrors": [],
                "requestId": getattr(request.state, "request_id", "unavailable"),
            }
        },
    )


@router.get("/{cook_id}/settlements", response_model=SettlementsResponse)
async def read_settlements(
    request: Request, cook_id: UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> SettlementsResponse | JSONResponse:
    try:
        return await get_settlements(session, cook_id)
    except CookServiceError as exc:
        return error_response(request, exc)


@router.put("/{cook_id}/settlements", response_model=SettlementsResponse)
async def write_settlements(
    request: Request,
    cook_id: UUID,
    body: ReplaceSettlementsRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SettlementsResponse | JSONResponse:
    try:
        return await replace_settlements(session, cook_id, body)
    except CookServiceError as exc:
        return error_response(request, exc)
