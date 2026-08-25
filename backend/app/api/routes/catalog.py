from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.contracts.errors import ApiError, ErrorEnvelope
from app.api.contracts.templates import (
    SaveTemplateRequest,
    TemplateDetailResponse,
    TemplateSummaryResponse,
)
from app.api.contracts.users import EnabledFilter, SaveUserRequest, UserResponse
from app.services import catalog

router = APIRouter(prefix="/api/v1", tags=["catalog"])


async def get_catalog_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


CatalogSession = Annotated[AsyncSession, Depends(get_catalog_session)]


def _error_response(error: catalog.CatalogServiceError) -> JSONResponse:
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


@router.get("/users", response_model=list[UserResponse])
async def users(
    session: CatalogSession,
    enabled: EnabledFilter = "all",
) -> list[UserResponse]:
    return await catalog.list_users(session, enabled)


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: SaveUserRequest, session: CatalogSession
) -> UserResponse | JSONResponse:
    try:
        return await catalog.create_user(session, request)
    except catalog.CatalogServiceError as error:
        return _error_response(error)


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID, request: SaveUserRequest, session: CatalogSession
) -> UserResponse | JSONResponse:
    try:
        return await catalog.update_user(session, user_id, request)
    except catalog.CatalogServiceError as error:
        return _error_response(error)


@router.get("/templates", response_model=list[TemplateSummaryResponse])
async def templates(
    session: CatalogSession,
) -> list[TemplateSummaryResponse]:
    return await catalog.list_templates(session)


@router.post(
    "/templates", response_model=TemplateDetailResponse, status_code=status.HTTP_201_CREATED
)
async def create_template(
    request: SaveTemplateRequest, session: CatalogSession
) -> TemplateDetailResponse | JSONResponse:
    try:
        return await catalog.create_template(session, request)
    except catalog.CatalogServiceError as error:
        return _error_response(error)


@router.put("/templates/{template_id}", response_model=TemplateDetailResponse)
async def update_template(
    template_id: UUID, request: SaveTemplateRequest, session: CatalogSession
) -> TemplateDetailResponse | JSONResponse:
    try:
        return await catalog.update_template(session, template_id, request)
    except catalog.CatalogServiceError as error:
        return _error_response(error)


@router.get(
    "/templates/{template_id}",
    response_model=TemplateDetailResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope}},
)
async def template(
    template_id: UUID,
    request: Request,
    session: CatalogSession,
) -> TemplateDetailResponse | JSONResponse:
    result = await catalog.get_template(session, template_id)
    if result is not None:
        return result

    request_id = getattr(request.state, "request_id", None) or request.headers.get(
        "x-request-id", "unavailable"
    )
    error = ErrorEnvelope(
        error=ApiError(
            code="template_not_found",
            message="Template was not found.",
            details={"templateId": str(template_id)},
            request_id=request_id,
        )
    )
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=error.model_dump(mode="json", by_alias=True),
    )
