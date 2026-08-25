from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.contracts.templates import (
    SaveTemplateRequest,
    TemplateDetailResponse,
    TemplateIngredientResponse,
    TemplateSummaryResponse,
    TemplateVoteVariantResponse,
)
from app.api.contracts.users import (
    EnabledFilter,
    SaveUserRequest,
    UserContactResponse,
    UserResponse,
)
from app.models import (
    CookTemplate,
    TemplateIngredient,
    TemplateVoteVariant,
    User,
    UserContact,
)


class CatalogServiceError(Exception):
    status_code = 400
    code = "catalog_error"

    def __init__(self, message: str, *, details: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class CatalogItemNotFoundError(CatalogServiceError):
    status_code = 404
    code = "catalog_item_not_found"


class CatalogConflictError(CatalogServiceError):
    status_code = 409
    code = "catalog_conflict"


_USER_SEQUENCE_LOCK = 7_612_684_032


async def list_users(session: AsyncSession, enabled: EnabledFilter = "all") -> list[UserResponse]:
    statement = select(User)
    if enabled != "all":
        statement = statement.where(User.enabled.is_(enabled == "true"))
    statement = statement.order_by(User.legacy_id, User.name, User.id)
    users = list((await session.execute(statement)).scalars().all())

    contacts_by_user: dict[UUID, list[UserContactResponse]] = {user.id: [] for user in users}
    if users:
        contacts_statement = (
            select(UserContact)
            .where(UserContact.user_id.in_(contacts_by_user))
            .order_by(UserContact.user_id, UserContact.position, UserContact.id)
        )
        contacts = (await session.execute(contacts_statement)).scalars().all()
        for contact in contacts:
            contacts_by_user[contact.user_id].append(
                UserContactResponse(position=contact.position, value=contact.value)
            )

    return [
        UserResponse(
            id=user.id,
            legacy_id=user.legacy_id,
            name=user.name,
            permanent_sale=user.permanent_sale,
            enabled=user.enabled,
            contacts=contacts_by_user[user.id],
        )
        for user in users
    ]


async def list_templates(session: AsyncSession) -> list[TemplateSummaryResponse]:
    statement = select(CookTemplate).order_by(CookTemplate.legacy_name, CookTemplate.id)
    templates = (await session.execute(statement)).scalars().all()
    return [
        TemplateSummaryResponse(
            id=template.id,
            name=template.legacy_name,
            is_multivote=template.is_multivote,
        )
        for template in templates
    ]


async def get_template(session: AsyncSession, template_id: UUID) -> TemplateDetailResponse | None:
    template_statement = select(CookTemplate).where(CookTemplate.id == template_id)
    template = (await session.execute(template_statement)).scalar_one_or_none()
    if template is None:
        return None

    variants_statement = (
        select(TemplateVoteVariant)
        .where(TemplateVoteVariant.template_id == template_id)
        .order_by(TemplateVoteVariant.position, TemplateVoteVariant.id)
    )
    ingredients_statement = (
        select(TemplateIngredient)
        .where(TemplateIngredient.template_id == template_id)
        .order_by(TemplateIngredient.position, TemplateIngredient.id)
    )
    variants = (await session.execute(variants_statement)).scalars().all()
    ingredients = (await session.execute(ingredients_statement)).scalars().all()

    return TemplateDetailResponse(
        id=template.id,
        name=template.legacy_name,
        is_multivote=template.is_multivote,
        vote_variants=[
            TemplateVoteVariantResponse(
                id=variant.id,
                position=variant.position,
                name=variant.name,
                value=variant.value,
            )
            for variant in variants
        ],
        ingredients=[
            TemplateIngredientResponse(
                id=ingredient.id,
                position=ingredient.position,
                name=ingredient.name,
                enabled=ingredient.enabled,
            )
            for ingredient in ingredients
        ],
    )


async def create_user(session: AsyncSession, request: SaveUserRequest) -> UserResponse:
    await session.execute(select(func.pg_advisory_xact_lock(_USER_SEQUENCE_LOCK)))
    max_legacy_id = await session.scalar(select(func.max(User.legacy_id)))
    user_id = uuid4()
    user = User(
        id=user_id,
        legacy_id=(max_legacy_id if max_legacy_id is not None else -1) + 1,
        source_key=f"web:users:{user_id}",
        name=request.name,
        permanent_sale=request.permanent_sale,
        enabled=request.enabled,
    )
    session.add(user)
    _add_contacts(session, user_id, request)
    await _commit_or_conflict(session, "Не удалось добавить пользователя.")
    return _user_response(user, request)


async def update_user(
    session: AsyncSession, user_id: UUID, request: SaveUserRequest
) -> UserResponse:
    user = await session.get(User, user_id)
    if user is None:
        raise CatalogItemNotFoundError(
            "Пользователь не найден.", details={"userId": str(user_id)}
        )
    user.name = request.name
    user.permanent_sale = request.permanent_sale
    user.enabled = request.enabled
    await session.execute(delete(UserContact).where(UserContact.user_id == user_id))
    _add_contacts(session, user_id, request)
    await _commit_or_conflict(session, "Не удалось сохранить пользователя.")
    return _user_response(user, request)


async def create_template(
    session: AsyncSession, request: SaveTemplateRequest
) -> TemplateDetailResponse:
    template_id = uuid4()
    template = CookTemplate(
        id=template_id,
        legacy_name=request.name,
        source_key=f"web:templates:{template_id}",
        is_multivote=request.is_multivote,
    )
    session.add(template)
    variants, ingredients = _add_template_children(session, template_id, request)
    await _commit_or_conflict(session, "Блюдо с таким названием уже существует.")
    return _template_response(template, variants, ingredients)


async def update_template(
    session: AsyncSession, template_id: UUID, request: SaveTemplateRequest
) -> TemplateDetailResponse:
    template = await session.get(CookTemplate, template_id)
    if template is None:
        raise CatalogItemNotFoundError(
            "Блюдо не найдено.", details={"dishId": str(template_id)}
        )
    template.legacy_name = request.name
    template.is_multivote = request.is_multivote
    await session.execute(
        delete(TemplateVoteVariant).where(TemplateVoteVariant.template_id == template_id)
    )
    await session.execute(
        delete(TemplateIngredient).where(TemplateIngredient.template_id == template_id)
    )
    variants, ingredients = _add_template_children(session, template_id, request)
    await _commit_or_conflict(session, "Блюдо с таким названием уже существует.")
    return _template_response(template, variants, ingredients)


def _add_contacts(session: AsyncSession, user_id: UUID, request: SaveUserRequest) -> None:
    session.add_all(
        [
            UserContact(id=uuid4(), user_id=user_id, position=position, value=contact.value)
            for position, contact in enumerate(request.contacts)
        ]
    )


def _user_response(user: User, request: SaveUserRequest) -> UserResponse:
    return UserResponse(
        id=user.id,
        legacy_id=user.legacy_id,
        name=user.name,
        permanent_sale=user.permanent_sale,
        enabled=user.enabled,
        contacts=[
            UserContactResponse(position=position, value=contact.value)
            for position, contact in enumerate(request.contacts)
        ],
    )


def _add_template_children(
    session: AsyncSession, template_id: UUID, request: SaveTemplateRequest
) -> tuple[list[TemplateVoteVariant], list[TemplateIngredient]]:
    variants = [
        TemplateVoteVariant(
            id=uuid4(),
            template_id=template_id,
            position=position,
            name=variant.name,
            value=variant.value,
        )
        for position, variant in enumerate(request.vote_variants)
    ]
    ingredients = [
        TemplateIngredient(
            id=uuid4(),
            template_id=template_id,
            position=position,
            name=ingredient.name,
            enabled=ingredient.enabled,
        )
        for position, ingredient in enumerate(request.ingredients)
    ]
    session.add_all([*variants, *ingredients])
    return variants, ingredients


def _template_response(
    template: CookTemplate,
    variants: list[TemplateVoteVariant],
    ingredients: list[TemplateIngredient],
) -> TemplateDetailResponse:
    return TemplateDetailResponse(
        id=template.id,
        name=template.legacy_name,
        is_multivote=template.is_multivote,
        vote_variants=[
            TemplateVoteVariantResponse(
                id=item.id, position=item.position, name=item.name, value=item.value
            )
            for item in variants
        ],
        ingredients=[
            TemplateIngredientResponse(
                id=item.id, position=item.position, name=item.name, enabled=item.enabled
            )
            for item in ingredients
        ],
    )


async def _commit_or_conflict(session: AsyncSession, message: str) -> None:
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise CatalogConflictError(message) from error
