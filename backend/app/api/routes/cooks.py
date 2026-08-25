from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.api.contracts.calculations import (
    ExpressionPreviewRequest,
    ExpressionPreviewResponse,
)
from app.api.contracts.cooks import (
    CalculateSelectionRequest,
    CalculateSelectionResponse,
    CookDetailResponse,
    CooksPageResponse,
    CooksQuery,
    CreateCookRequest,
    DraftCookPreviewRequest,
    DraftCookPreviewResponse,
    UpdateCookRequest,
)
from app.services.cooks import (
    CookServiceError,
    CooksService,
    InvalidSnapshotError,
    preview_expression,
)

router = APIRouter(prefix="/api/v1", tags=["cooks"])


async def get_cooks_service(request: Request) -> AsyncIterator[CooksService]:
    async with request.app.state.session_factory() as session:
        yield CooksService(session)


CooksServiceDependency = Annotated[CooksService, Depends(get_cooks_service)]


def _error_response(error: CookServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={
            "error": {
                "code": error.code,
                "message": str(error),
                "fieldErrors": [],
                "details": error.details,
                "requestId": str(uuid4()),
            }
        },
    )


@router.post(
    "/cooks/calculate-selection",
    response_model=CalculateSelectionResponse,
)
async def calculate_selection(
    request: CalculateSelectionRequest,
    service: CooksServiceDependency,
) -> CalculateSelectionResponse | JSONResponse:
    try:
        return await service.calculate_selection(request)
    except CookServiceError as error:
        return _error_response(error)


@router.post("/cooks/preview", response_model=DraftCookPreviewResponse)
async def preview_cook(
    request: DraftCookPreviewRequest,
    service: CooksServiceDependency,
) -> DraftCookPreviewResponse | JSONResponse:
    try:
        return await service.preview_cook(request)
    except CookServiceError as error:
        return _error_response(error)


@router.get("/cooks", response_model=CooksPageResponse)
async def list_cooks(
    date_from: Annotated[date, Query(alias="dateFrom")],
    date_to: Annotated[date, Query(alias="dateTo")],
    service: CooksServiceDependency,
    template_id: Annotated[UUID | None, Query(alias="templateId")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, alias="pageSize")] = 50,
) -> CooksPageResponse | JSONResponse:
    if date_from > date_to:
        return _error_response(InvalidSnapshotError("dateFrom must be on or before dateTo"))
    query = CooksQuery(
        date_from=date_from,
        date_to=date_to,
        template_id=template_id,
        page=page,
        page_size=page_size,
    )
    return await service.list_cooks(query)


@router.get("/cooks/{cook_id}", response_model=CookDetailResponse)
async def get_cook(
    cook_id: UUID,
    service: CooksServiceDependency,
) -> CookDetailResponse | JSONResponse:
    try:
        return await service.get_cook(cook_id)
    except CookServiceError as error:
        return _error_response(error)


@router.post("/cooks", response_model=CookDetailResponse, status_code=201)
async def create_cook(
    request: CreateCookRequest,
    service: CooksServiceDependency,
) -> CookDetailResponse | JSONResponse:
    try:
        return await service.create_cook(request)
    except CookServiceError as error:
        return _error_response(error)


@router.put("/cooks/{cook_id}", response_model=CookDetailResponse)
async def update_cook(
    cook_id: UUID,
    request: UpdateCookRequest,
    service: CooksServiceDependency,
) -> CookDetailResponse | JSONResponse:
    try:
        return await service.update_cook(cook_id, request)
    except CookServiceError as error:
        return _error_response(error)


@router.post(
    "/calculations/expressions/preview",
    response_model=ExpressionPreviewResponse,
)
async def expression_preview(
    request: ExpressionPreviewRequest,
) -> ExpressionPreviewResponse:
    return preview_expression(request)
