from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.contracts.preparation import PreparationPlan, SaveCookPreparation
from app.models.preparation import CookPreparation
from app.services.cooks import InvalidSnapshotError, VersionConflictError
from app.services.preparation import (
    PreparationService,
    batch_warnings,
    initialize_preparation,
    prune_preparation_members,
)


def option(key="doneness", batch=5):
    return {"key": key, "name": key, "values": ["medium", "well"], "batchSize": batch}


def test_batch_constraint_aggregates_across_members_and_other_choices():
    plan = PreparationPlan.model_validate({
        "options": [option(), option("tomato", 1)],
        "groups": [
            {"userId": uuid4(), "quantity": 2, "choices": {"doneness": "medium"}},
            {"userId": uuid4(), "quantity": 3,
             "choices": {"doneness": "medium", "tomato": "well"}},
        ],
    })
    assert batch_warnings(plan) == []
    plan.groups[0].quantity = 1
    warnings = batch_warnings(plan)
    assert [(item.option_key, item.value, item.quantity, item.batch_size) for item in warnings] == [
        ("doneness", "medium", 4, 5)
    ]


def test_combinations_remain_independent_for_one_participant():
    user = uuid4()
    plan = PreparationPlan.model_validate({
        "options": [option()], "groups": [
            {"userId": user, "quantity": 1, "choices": {"doneness": "medium"}},
            {"userId": user, "quantity": 1, "choices": {"doneness": "well"}},
        ],
    })
    assert len(plan.groups) == 2
    assert len(batch_warnings(plan)) == 2  # Warnings do not reject a valid plan.


@pytest.mark.parametrize("choices", [{"unknown": "medium"}, {"doneness": "rare"}])
def test_choices_must_reference_snapshot(choices):
    with pytest.raises(ValidationError):
        PreparationPlan.model_validate({
            "options": [option()],
            "groups": [{"userId": uuid4(), "quantity": 1, "choices": choices}],
        })


def test_missing_choices_use_first_value_and_duplicate_option_keys_rejected():
    plan = PreparationPlan.model_validate({
        "options": [option()], "groups": [{"userId": uuid4(), "quantity": 1}],
    })
    assert plan.groups[0].choices == {"doneness": "medium"}
    with pytest.raises(ValidationError):
        PreparationPlan(options=[option(), option()])


@pytest.mark.asyncio
async def test_version_conflict_is_checked_before_any_write():
    session = SimpleNamespace(scalar=AsyncMock(return_value=SimpleNamespace(row_version=8)),
                              commit=AsyncMock(), add=Mock())
    request = SaveCookPreparation(expected_version=7)
    with pytest.raises(VersionConflictError):
        await PreparationService(session).save_cook(uuid4(), request)
    session.commit.assert_not_called()
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_nonmember_cannot_receive_preparation_groups():
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=SimpleNamespace(row_version=7)),
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [uuid4()])),
        commit=AsyncMock(),
    )
    request = SaveCookPreparation(expected_version=7, groups=[{
        "userId": uuid4(), "quantity": 1,
    }])
    with pytest.raises(InvalidSnapshotError):
        await PreparationService(session).save_cook(uuid4(), request)
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_save_with_incomplete_batch_increments_shared_version_without_billing_changes():
    user = uuid4()
    cook = SimpleNamespace(row_version=7, total_price_cached=500)
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=cook),
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [user])),
        get=AsyncMock(return_value=None), add=Mock(), commit=AsyncMock(),
    )
    request = SaveCookPreparation(expected_version=7, options=[option()], groups=[{
        "userId": user, "quantity": 2,
    }])
    result = await PreparationService(session).save_cook(uuid4(), request)
    assert cook.row_version == 8
    assert cook.total_price_cached == 500
    assert result.row_version == 8
    assert result.warnings[0].quantity == 2
    assert result.groups[0].choices == {"doneness": "medium"}
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_historical_cook_without_snapshot_never_reads_current_template_presets():
    cook_id = uuid4()
    session = SimpleNamespace(get=AsyncMock(side_effect=[SimpleNamespace(row_version=3), None]))
    result = await PreparationService(session).cook(cook_id)
    assert result.options == []
    assert result.groups == []
    assert session.get.await_count == 2


@pytest.mark.asyncio
async def test_initialization_copies_template_presets_and_removal_prunes_groups():
    session = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(options=[option()])), add=Mock(),
    )
    await initialize_preparation(session, uuid4(), uuid4())
    stored = session.add.call_args.args[0]
    assert isinstance(stored, CookPreparation)
    assert stored.options == [option()]
    keep, remove = uuid4(), uuid4()
    stored.groups = [{"userId": str(keep), "quantity": 1},
                     {"userId": str(remove), "quantity": 2}]
    session.get.return_value = stored
    await prune_preparation_members(session, stored.cook_id, {keep})
    assert stored.groups == [{"userId": str(keep), "quantity": 1}]
