"""Balance API routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.contracts import (
    ApiError,
    BalanceAdjustmentResponse,
    BalancesQuery,
    BalancesResponse,
    CloseBalanceAdjustmentRequest,
    CloseBalancePreviewResponse,
    CreateBalanceAdjustmentRequest,
    CreateBalancePaymentRequest,
    DateRangeQuery,
    ErrorEnvelope,
    UserBalanceDetailResponse,
)
from app.services.balances import (
    BalanceChangedError,
    BalanceDataError,
    BalanceService,
    PaymentNotFoundError,
    PaymentTypeNotFoundError,
    UserNotFoundError,
    ZeroBalanceError,
)

router = APIRouter(prefix="/api/v1/balances", tags=["balances"])


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


def get_balance_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BalanceService:
    return BalanceService(session)


def _error_response(
    request: Request, status_code: int, code: str, message: str, **details: str
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) or request.headers.get(
        "x-request-id", "unavailable"
    )
    envelope = ErrorEnvelope(
        error=ApiError(
            code=code,
            message=message,
            details=details,
            request_id=request_id,
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json", by_alias=True),
    )


@router.get(
    "",
    response_model=BalancesResponse,
    responses={500: {"model": ErrorEnvelope}},
)
async def list_balances(
    request: Request,
    query: Annotated[BalancesQuery, Query()],
    service: Annotated[BalanceService, Depends(get_balance_service)],
) -> BalancesResponse | JSONResponse:
    try:
        return await service.list_balances(
            query.date_from, query.date_to, non_zero_only=query.non_zero_only
        )
    except BalanceDataError as exc:
        return _error_response(
            request,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "balance_calculation_failed",
            "Stored data cannot produce balances.",
            reason=str(exc),
        )


@router.get(
    "/users/{userId}",
    response_model=UserBalanceDetailResponse,
    responses={404: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}},
)
async def get_user_balance(
    request: Request,
    user_id: Annotated[UUID, Path(alias="userId")],
    query: Annotated[DateRangeQuery, Query()],
    service: Annotated[BalanceService, Depends(get_balance_service)],
) -> UserBalanceDetailResponse | JSONResponse:
    try:
        return await service.get_user_balance(user_id, query.date_from, query.date_to)
    except UserNotFoundError:
        return _error_response(
            request,
            status.HTTP_404_NOT_FOUND,
            "user_not_found",
            "User was not found.",
            userId=str(user_id),
        )
    except BalanceDataError as exc:
        return _error_response(
            request,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "balance_calculation_failed",
            "Stored data cannot produce balances.",
            reason=str(exc),
        )


@router.post(
    "/users/{userId}/payments",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    responses={404: {"model": ErrorEnvelope}},
)
async def create_user_payment(
    request: Request,
    user_id: Annotated[UUID, Path(alias="userId")],
    body: CreateBalancePaymentRequest,
    service: Annotated[BalanceService, Depends(get_balance_service)],
) -> Response | JSONResponse:
    try:
        await service.create_payment(user_id, body)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except UserNotFoundError:
        return _error_response(
            request,
            status.HTTP_404_NOT_FOUND,
            "user_not_found",
            "User was not found.",
            userId=str(user_id),
        )
    except PaymentTypeNotFoundError:
        return _error_response(
            request,
            status.HTTP_404_NOT_FOUND,
            "payment_type_not_found",
            "Payment type was not found.",
            paymentTypeId=str(body.payment_type_id),
        )


@router.get(
    "/users/{userId}/adjustments/close-preview",
    response_model=CloseBalancePreviewResponse,
    responses={404: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}},
)
async def close_balance_preview(
    request: Request,
    user_id: Annotated[UUID, Path(alias="userId")],
    adjustment_date: Annotated[date, Query(alias="adjustmentDate")],
    service: Annotated[BalanceService, Depends(get_balance_service)],
) -> CloseBalancePreviewResponse | JSONResponse:
    try:
        return await service.close_balance_preview(user_id, adjustment_date)
    except UserNotFoundError:
        return _error_response(request, 404, "user_not_found", "User was not found.")


@router.post(
    "/users/{userId}/adjustments",
    response_model=BalanceAdjustmentResponse,
    responses={404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}},
)
async def create_adjustment(
    request: Request,
    user_id: Annotated[UUID, Path(alias="userId")],
    body: CreateBalanceAdjustmentRequest,
    service: Annotated[BalanceService, Depends(get_balance_service)],
) -> BalanceAdjustmentResponse | JSONResponse:
    try:
        return await service.create_adjustment(
            user_id,
            body,
            getattr(getattr(request.state, "principal", None), "user_id", None),
        )
    except UserNotFoundError:
        return _error_response(request, 404, "user_not_found", "User was not found.")
    except BalanceChangedError:
        return _error_response(
            request, 409, "balance_changed", "Balance changed; refresh and retry."
        )


@router.post(
    "/users/{userId}/adjustments/close",
    response_model=BalanceAdjustmentResponse,
    responses={404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}},
)
async def close_balance(
    request: Request,
    user_id: Annotated[UUID, Path(alias="userId")],
    body: CloseBalanceAdjustmentRequest,
    service: Annotated[BalanceService, Depends(get_balance_service)],
) -> BalanceAdjustmentResponse | JSONResponse:
    try:
        return await service.close_balance(
            user_id,
            body,
            getattr(getattr(request.state, "principal", None), "user_id", None),
        )
    except UserNotFoundError:
        return _error_response(request, 404, "user_not_found", "User was not found.")
    except BalanceChangedError:
        return _error_response(
            request, 409, "balance_changed", "Balance changed; refresh the preview and retry."
        )
    except ZeroBalanceError:
        return _error_response(request, 409, "balance_already_zero", "Balance is already zero.")


@router.post(
    "/users/{userId}/payments/{paymentId}/delete",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    responses={404: {"model": ErrorEnvelope}},
)
async def delete_user_payment(
    request: Request,
    user_id: Annotated[UUID, Path(alias="userId")],
    payment_id: Annotated[UUID, Path(alias="paymentId")],
    service: Annotated[BalanceService, Depends(get_balance_service)],
) -> Response | JSONResponse:
    try:
        await service.delete_payment(user_id, payment_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except PaymentNotFoundError:
        return _error_response(
            request,
            status.HTTP_404_NOT_FOUND,
            "payment_not_found",
            "Payment was not found.",
            userId=str(user_id),
            paymentId=str(payment_id),
        )


__all__ = ["get_balance_service", "router"]
