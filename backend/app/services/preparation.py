from collections import Counter
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.contracts.preparation import (
    CookPreparationResponse,
    PreparationPlan,
    PreparationWarning,
    SaveCookPreparation,
    SaveTemplatePreparation,
    TemplatePreparationResponse,
)
from app.models.entities import Cook, CookMember, CookTemplate
from app.models.preparation import CookPreparation, TemplatePreparation
from app.services.cooks import CookNotFoundError, InvalidSnapshotError, VersionConflictError


def batch_warnings(plan: PreparationPlan) -> list[PreparationWarning]:
    result = []
    for option in plan.options:
        totals: Counter[str] = Counter()
        for group in plan.groups:
            totals[group.choices.get(option.key, option.values[0])] += group.quantity
        for value in option.values:
            quantity = totals[value]
            if quantity % option.batch_size:
                result.append(PreparationWarning(
                    option_key=option.key, option_name=option.name, value=value,
                    quantity=quantity, batch_size=option.batch_size,
                ))
    return result


async def initialize_preparation(session: AsyncSession, cook_id: UUID, template_id: UUID) -> None:
    """Copy presets once at creation; old cooks never inherit current presets."""
    preset = await session.get(TemplatePreparation, template_id)
    session.add(CookPreparation(
        cook_id=cook_id, options=preset.options if preset else [], groups=[]
    ))


async def prune_preparation_members(
    session: AsyncSession, cook_id: UUID, user_ids: set[UUID]
) -> None:
    plan = await session.get(CookPreparation, cook_id)
    if plan:
        plan.groups = [group for group in plan.groups if UUID(group["userId"]) in user_ids]


class PreparationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def template(self, template_id: UUID) -> TemplatePreparationResponse:
        if await self.session.get(CookTemplate, template_id) is None:
            raise CookNotFoundError("Блюдо не найдено.")
        preset = await self.session.get(TemplatePreparation, template_id)
        return TemplatePreparationResponse(
            version=preset.version if preset else 0, options=preset.options if preset else []
        )

    async def save_template(
        self, template_id: UUID, request: SaveTemplatePreparation
    ) -> TemplatePreparationResponse:
        template = await self.session.scalar(
            select(CookTemplate).where(CookTemplate.id == template_id).with_for_update()
        )
        if template is None:
            raise CookNotFoundError("Блюдо не найдено.")
        preset = await self.session.get(TemplatePreparation, template_id, populate_existing=True)
        version = preset.version if preset else 0
        if version != request.expected_version:
            raise VersionConflictError("Настройки блюда изменены. Обновите страницу.")
        options = [option.model_dump(mode="json") for option in request.options]
        if preset is None:
            preset = TemplatePreparation(template_id=template_id, version=1, options=options)
            self.session.add(preset)
        else:
            preset.options = options
            preset.version += 1
        await self.session.commit()
        return TemplatePreparationResponse(version=preset.version, options=options)

    async def cook(self, cook_id: UUID) -> CookPreparationResponse:
        cook = await self.session.get(Cook, cook_id)
        if cook is None:
            raise CookNotFoundError("Готовка не найдена.")
        stored = await self.session.get(CookPreparation, cook_id)
        plan = PreparationPlan.model_validate({
            "options": stored.options if stored else [], "groups": stored.groups if stored else []
        })
        return CookPreparationResponse(
            **plan.model_dump(), row_version=cook.row_version, warnings=batch_warnings(plan)
        )

    async def save_cook(
        self, cook_id: UUID, request: SaveCookPreparation
    ) -> CookPreparationResponse:
        cook = await self.session.scalar(
            select(Cook)
            .where(Cook.id == cook_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if cook is None:
            raise CookNotFoundError("Готовка не найдена.")
        if cook.row_version != request.expected_version:
            raise VersionConflictError("Готовка изменена. Обновите данные перед сохранением.")
        member_ids = set((await self.session.scalars(
            select(CookMember.user_id).where(CookMember.cook_id == cook_id)
        )).all())
        if any(group.user_id not in member_ids for group in request.groups):
            raise InvalidSnapshotError("Пожелания можно задать только участникам этой готовки.")
        stored = await self.session.get(CookPreparation, cook_id)
        data = request.model_dump(mode="json", exclude={"expected_version"})
        if stored is None:
            self.session.add(CookPreparation(cook_id=cook_id, **data))
        else:
            stored.options = data["options"]
            stored.groups = data["groups"]
        cook.row_version += 1
        await self.session.commit()
        return CookPreparationResponse(
            **data, row_version=cook.row_version, warnings=batch_warnings(request)
        )
