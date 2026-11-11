from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.api.contracts.preparation import (
    CookPreparationResponse,
    SaveCookPreparation,
    SaveTemplatePreparation,
    TemplatePreparationResponse,
)
from app.api.routes.cooks import _error_response
from app.services.cooks import CookServiceError
from app.services.preparation import PreparationService

router = APIRouter(prefix="/api/v1", tags=["preparation"])


async def get_preparation_service(request: Request) -> AsyncIterator[PreparationService]:
    async with request.app.state.session_factory() as session:
        yield PreparationService(session)


Service = Annotated[PreparationService, Depends(get_preparation_service)]


@router.get("/templates/{template_id}/preparation", response_model=TemplatePreparationResponse)
async def get_template(template_id: UUID, service: Service):
    try:
        return await service.template(template_id)
    except CookServiceError as error:
        return _error_response(error)


@router.put("/templates/{template_id}/preparation", response_model=TemplatePreparationResponse)
async def put_template(template_id: UUID, request: SaveTemplatePreparation, service: Service):
    try:
        return await service.save_template(template_id, request)
    except CookServiceError as error:
        return _error_response(error)


@router.get("/cooks/{cook_id}/preparation", response_model=CookPreparationResponse)
async def get_cook(cook_id: UUID, service: Service):
    try:
        return await service.cook(cook_id)
    except CookServiceError as error:
        return _error_response(error)


@router.put("/cooks/{cook_id}/preparation", response_model=CookPreparationResponse)
async def put_cook(cook_id: UUID, request: SaveCookPreparation, service: Service):
    try:
        return await service.save_cook(cook_id, request)
    except CookServiceError as error:
        return _error_response(error)
