from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.contracts.zenmoney import (
    DecideZenMoneyTransactionRequest,
    SaveZenMoneySettingsRequest,
    ZenMoneyAccountResponse,
    ZenMoneyAccountsRequest,
    ZenMoneyBulkApproveResponse,
    ZenMoneySettingsResponse,
    ZenMoneySyncResponse,
    ZenMoneyTransactionResponse,
)
from app.services import zenmoney

router = APIRouter(prefix="/api/v1/zenmoney", tags=["zenmoney"])


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


Session = Annotated[AsyncSession, Depends(get_session)]


def error_response(error: zenmoney.ZenMoneyError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={
            "error": {
                "code": error.code,
                "message": str(error),
                "fieldErrors": [],
                "details": {},
                "requestId": str(uuid4()),
            }
        },
    )


@router.get("/settings", response_model=ZenMoneySettingsResponse)
async def settings(session: Session) -> ZenMoneySettingsResponse:
    return await zenmoney.get_settings_response(session)


@router.post("/settings/accounts", response_model=list[ZenMoneyAccountResponse])
async def accounts(
    body: ZenMoneyAccountsRequest, request: Request, session: Session
) -> list[ZenMoneyAccountResponse] | JSONResponse:
    try:
        token = body.access_token.get_secret_value() if body.access_token else None
        if token is None:
            configured = await session.get(zenmoney.ZenMoneySettings, 1)
            if configured is None:
                raise zenmoney.ZenMoneyError("Access token is required.", code="token_required")
            token = zenmoney.decrypt_token(
                configured.access_token_ciphertext, request.app.state.settings
            )
        return zenmoney.accounts_from_diff(await zenmoney.request_diff(token, 0))
    except zenmoney.ZenMoneyError as error:
        return error_response(error)


@router.put("/settings", response_model=ZenMoneySettingsResponse)
async def save_settings(
    body: SaveZenMoneySettingsRequest, request: Request, session: Session
) -> ZenMoneySettingsResponse | JSONResponse:
    try:
        return await zenmoney.save_settings(session, body, request.app.state.settings)
    except zenmoney.ZenMoneyError as error:
        return error_response(error)


@router.post("/sync", response_model=ZenMoneySyncResponse)
async def sync(request: Request, session: Session) -> ZenMoneySyncResponse | JSONResponse:
    try:
        return await zenmoney.sync(session, request.app.state.settings)
    except zenmoney.ZenMoneyError as error:
        return error_response(error)


@router.get("/transactions", response_model=list[ZenMoneyTransactionResponse])
async def transactions(
    session: Session,
    include_blacklisted: bool = Query(False),
    status: str | None = Query(None, pattern="^(matched|review|blacklisted|rejected)$"),
) -> list[ZenMoneyTransactionResponse]:
    return await zenmoney.list_transactions(
        session, include_blacklisted=include_blacklisted, status=status
    )


@router.post("/transactions/approve-matched", response_model=ZenMoneyBulkApproveResponse)
async def approve_matched(
    session: Session,
) -> ZenMoneyBulkApproveResponse | JSONResponse:
    try:
        return await zenmoney.approve_all_matched(session)
    except zenmoney.ZenMoneyError as error:
        return error_response(error)


@router.patch("/transactions/{transaction_id}", response_model=ZenMoneyTransactionResponse)
async def decide(
    transaction_id: UUID,
    body: DecideZenMoneyTransactionRequest,
    session: Session,
) -> ZenMoneyTransactionResponse | JSONResponse:
    try:
        return await zenmoney.decide(session, transaction_id, body.action, body.user_id)
    except zenmoney.ZenMoneyError as error:
        return error_response(error)
