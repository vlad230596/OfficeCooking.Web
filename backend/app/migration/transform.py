from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.domain.legacy_calculation import MemberInput, ProductInput, calculate_cook, float32
from app.models import (
    Cook,
    CookMember,
    CookMemberVote,
    CookProductPrice,
    CookTemplate,
    CookVoteVariant,
    Payment,
    PaymentType,
    TemplateIngredient,
    TemplateVoteVariant,
    User,
    UserContact,
)

from .json_reader import read_json
from .manifest import Manifest, build_manifest

UUID_NAMESPACE = uuid.UUID("88068a58-3ad9-5c31-8f8c-f9ba70968f19")
MIGRATOR_VERSION = "1"
CALCULATION_VERSION = 1


class MigrationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MigrationIssue:
    source_path: str
    json_path: str
    reason: str
    kind: str = "validation"


@dataclass(slots=True)
class MigrationBundle:
    manifest: Manifest
    entities: dict[str, list[Any]] = field(default_factory=dict)
    issues: list[MigrationIssue] = field(default_factory=list)
    user_ids: dict[int, uuid.UUID] = field(default_factory=dict)
    payment_type_ids: dict[int, uuid.UUID] = field(default_factory=dict)

    @property
    def counts(self) -> dict[str, int]:
        return {name: len(items) for name, items in self.entities.items()}

    def report(self, *, status: str = "validated") -> dict[str, object]:
        was_imported = status == "imported"
        was_skipped = status == "already_imported"
        has_durable_run = was_imported or was_skipped
        return {
            "schema_version": "office-cook-migration-report/v1",
            "run_id": str(uuid.uuid4()),
            "generated_at": datetime.now(UTC).isoformat(),
            "status": status,
            "durable_import_run": has_durable_run,
            "durable_status": "published" if has_durable_run else None,
            "manifest_checksum": self.manifest.checksum,
            "migrator_version": MIGRATOR_VERSION,
            "alembic_revision": "0001_initial_schema",
            "calculation_version": CALCULATION_VERSION,
            "files_read": len(self.manifest.files),
            "entities": {
                name: {
                    "read": len(items),
                    "written": len(items) if was_imported else 0,
                    "skipped": len(items) if was_skipped else 0,
                    "errors": 0,
                }
                for name, items in self.entities.items()
            },
            "legacy_mappings": {
                "users": {str(key): str(value) for key, value in self.user_ids.items()},
                "payment_types": {
                    str(key): str(value) for key, value in self.payment_type_ids.items()
                },
            },
            "issues": [
                {
                    "source_path": issue.source_path,
                    "json_path": issue.json_path,
                    "reason": issue.reason,
                    "kind": issue.kind,
                }
                for issue in self.issues
            ],
        }


def stable_uuid(key: str) -> uuid.UUID:
    return uuid.uuid5(UUID_NAMESPACE, key)


def child_uuid(parent_key: str, collection: str, position: int) -> uuid.UUID:
    return stable_uuid(f"{parent_key}:{collection}:{position}")


def _object(value: Any, source: str, json_path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MigrationError(f"{source} {json_path}: expected object")
    return value


def _list(value: Any, source: str, json_path: str) -> list[Any]:
    if not isinstance(value, list):
        raise MigrationError(f"{source} {json_path}: expected array")
    return value


def _required(item: dict[str, Any], key: str, source: str, json_path: str) -> Any:
    if key not in item:
        raise MigrationError(f"{source} {json_path}: missing {key!r}")
    return item[key]


def _parse_date(value: Any, source: str, json_path: str) -> datetime:
    if not isinstance(value, str):
        raise MigrationError(f"{source} {json_path}: expected date string")
    try:
        return datetime.strptime(value, "%d.%m.%Y")
    except ValueError as exc:
        raise MigrationError(f"{source} {json_path}: invalid dd.MM.yyyy date {value!r}") from exc


def _parse_registration_date(value: Any, source: str, json_path: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise MigrationError(f"{source} {json_path}: expected string or null")
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        try:
            return datetime.strptime(value, "%d.%m.%Y %I:%M:%S %p")
        except ValueError as exc:
            raise MigrationError(f"{source} {json_path}: unsupported timestamp {value!r}") from exc


def _new_entities() -> dict[str, list[Any]]:
    return {
        "users": [],
        "user_contacts": [],
        "payment_types": [],
        "cook_templates": [],
        "template_vote_variants": [],
        "template_ingredients": [],
        "cooks": [],
        "cook_vote_variants": [],
        "cook_members": [],
        "cook_member_votes": [],
        "cook_product_prices": [],
        "payments": [],
    }


def transform_snapshot(data_root: Path, *, manifest: Manifest | None = None) -> MigrationBundle:
    root = data_root.resolve(strict=True)
    actual_manifest = build_manifest(root)
    if manifest is not None and manifest != actual_manifest:
        raise MigrationError("source changed after manifest verification")
    bundle = MigrationBundle(actual_manifest, _new_entities())
    _transform_users(root, bundle)
    _transform_payment_types(root, bundle)
    templates = _transform_templates(root, bundle)
    _transform_cooks(root, bundle, templates)
    _transform_payments(root, bundle)
    _validate_unique_cook_dates(bundle)
    if build_manifest(root) != actual_manifest:
        raise MigrationError("source changed while the read-only snapshot was being transformed")
    return bundle


def _transform_users(root: Path, bundle: MigrationBundle) -> None:
    source = "Users.json"
    values = _list(read_json(root / source), source, "$")
    for position, raw in enumerate(values):
        path = f"$[{position}]"
        item = _object(raw, source, path)
        name = _required(item, "name", source, path)
        key = f"users:{position}"
        identifier = stable_uuid(key)
        bundle.user_ids[position] = identifier
        bundle.entities["users"].append(
            User(
                id=identifier,
                legacy_id=position,
                source_key=key,
                name=name,
                permanent_sale=float32(item.get("permanentSale", 1.0)),
                enabled=item.get("enabled", True),
            )
        )
        for contact_position, contact in enumerate(item.get("contacts", [])):
            bundle.entities["user_contacts"].append(
                UserContact(
                    id=child_uuid(key, "contacts", contact_position),
                    user_id=identifier,
                    position=contact_position,
                    value=contact,
                )
            )


def _transform_payment_types(root: Path, bundle: MigrationBundle) -> None:
    source = "PaymentsType.json"
    values = _list(read_json(root / source), source, "$")
    for position, raw in enumerate(values):
        path = f"$[{position}]"
        item = _object(raw, source, path)
        key = f"payment-types:{position}"
        identifier = stable_uuid(key)
        bundle.payment_type_ids[position] = identifier
        bundle.entities["payment_types"].append(
            PaymentType(
                id=identifier,
                legacy_id=position,
                source_key=key,
                name=_required(item, "name", source, path),
                enabled=item.get("enabled", True),
            )
        )


def _transform_templates(root: Path, bundle: MigrationBundle) -> dict[str, uuid.UUID]:
    by_name: dict[str, uuid.UUID] = {}
    for path in sorted((root / "Templates").glob("*.json"), key=lambda value: value.name):
        source = path.relative_to(root).as_posix()
        item = _object(read_json(path, allow_trailing_commas=True), source, "$")
        identifier = stable_uuid(source)
        name = path.stem
        if name in by_name:
            raise MigrationError(f"{source}: duplicate template name {name!r}")
        by_name[name] = identifier
        bundle.entities["cook_templates"].append(
            CookTemplate(
                id=identifier,
                legacy_name=name,
                source_key=source,
                is_multivote=item.get("isMultivote", False),
            )
        )
        votes = _list(_required(item, "voteVariants", source, "$"), source, "$.voteVariants")
        for position, raw_vote in enumerate(votes):
            vote = _object(raw_vote, source, f"$.voteVariants[{position}]")
            bundle.entities["template_vote_variants"].append(
                TemplateVoteVariant(
                    id=child_uuid(source, "voteVariants", position),
                    template_id=identifier,
                    position=position,
                    name=_required(vote, "name", source, f"$.voteVariants[{position}]"),
                    value=float32(_required(vote, "value", source, f"$.voteVariants[{position}]")),
                )
            )
        ingredients = _list(_required(item, "ingredients", source, "$"), source, "$.ingredients")
        for position, raw_ingredient in enumerate(ingredients):
            ingredient = _object(raw_ingredient, source, f"$.ingredients[{position}]")
            bundle.entities["template_ingredients"].append(
                TemplateIngredient(
                    id=child_uuid(source, "ingredients", position),
                    template_id=identifier,
                    position=position,
                    name=_required(ingredient, "name", source, f"$.ingredients[{position}]"),
                    enabled=ingredient.get("enabled", True),
                )
            )
    return by_name


def _transform_cooks(root: Path, bundle: MigrationBundle, templates: dict[str, uuid.UUID]) -> None:
    for path in sorted((root / "Cooks").glob("*.json"), key=lambda value: value.name):
        source = path.relative_to(root).as_posix()
        item = _object(read_json(path), source, "$")
        identifier = stable_uuid(source)
        type_name = _required(item, "type", source, "$")
        raw_votes = _list(_required(item, "votes", source, "$"), source, "$.votes")
        raw_members = _list(_required(item, "members", source, "$"), source, "$.members")
        raw_products = _list(
            _required(item, "productPrices", source, "$"), source, "$.productPrices"
        )
        vote_values: list[float] = []
        for position, raw_vote in enumerate(raw_votes):
            vote = _object(raw_vote, source, f"$.votes[{position}]")
            value = float32(_required(vote, "value", source, f"$.votes[{position}]"))
            vote_values.append(value)
            bundle.entities["cook_vote_variants"].append(
                CookVoteVariant(
                    id=child_uuid(source, "votes", position),
                    cook_id=identifier,
                    position=position,
                    name=_required(vote, "name", source, f"$.votes[{position}]"),
                    value=value,
                )
            )
        member_inputs: list[MemberInput] = []
        seen_users: set[int] = set()
        for position, raw_member in enumerate(raw_members):
            member_path = f"$.members[{position}]"
            member = _object(raw_member, source, member_path)
            legacy_user_id = _required(member, "userId", source, member_path)
            if legacy_user_id not in bundle.user_ids:
                raise MigrationError(f"{source} {member_path}: unknown userId {legacy_user_id}")
            if legacy_user_id in seen_users:
                raise MigrationError(f"{source} {member_path}: duplicate userId {legacy_user_id}")
            seen_users.add(legacy_user_id)
            votes = _list(_required(member, "votes", source, member_path), source, member_path)
            member_id = child_uuid(source, "members", position)
            bundle.entities["cook_members"].append(
                CookMember(
                    id=member_id,
                    cook_id=identifier,
                    user_id=bundle.user_ids[legacy_user_id],
                    position=position,
                    active=_required(member, "active", source, member_path),
                    permanent_sale_snapshot=bundle.entities["users"][
                        legacy_user_id
                    ].permanent_sale,
                )
            )
            for vote_position, vote_index in enumerate(votes):
                if not isinstance(vote_index, int) or not 0 <= vote_index < len(raw_votes):
                    reason = (
                        f"{source} {member_path}.votes[{vote_position}]: "
                        f"invalid index {vote_index!r}"
                    )
                    raise MigrationError(reason)
                bundle.entities["cook_member_votes"].append(
                    CookMemberVote(
                        cook_id=identifier,
                        cook_member_id=member_id,
                        cook_vote_variant_id=child_uuid(source, "votes", vote_index),
                        position=vote_position,
                    )
                )
            user = bundle.entities["users"][legacy_user_id]
            member_inputs.append(
                MemberInput(
                    user_id=legacy_user_id,
                    active=member["active"],
                    vote_indexes=tuple(votes),
                    permanent_sale=user.permanent_sale,
                )
            )
        product_inputs: list[ProductInput] = []
        product_items: list[dict[str, Any]] = []
        for position, raw_product in enumerate(raw_products):
            product = _object(raw_product, source, f"$.productPrices[{position}]")
            product_items.append(product)
            product_inputs.append(
                ProductInput(
                    product_name=_required(
                        product, "productName", source, f"$.productPrices[{position}]"
                    ),
                    expression=_required(product, "price", source, f"$.productPrices[{position}]"),
                )
            )
        sale = float32(_required(item, "sale", source, "$"))
        calculation = calculate_cook(product_inputs, vote_values, member_inputs, sale)
        for position, (product, result) in enumerate(
            zip(product_items, calculation.products, strict=True)
        ):
            if result.result.error is not None:
                bundle.issues.append(
                    MigrationIssue(
                        source,
                        f"$.productPrices[{position}].price",
                        result.result.error,
                        "invalid_expression",
                    )
                )
            bundle.entities["cook_product_prices"].append(
                CookProductPrice(
                    id=child_uuid(source, "productPrices", position),
                    cook_id=identifier,
                    position=position,
                    product_name=product["productName"],
                    expression=product["price"],
                    computed_value=result.result.value,
                    calculation_status=result.result.status.value,
                    calculation_error=result.result.error,
                    calculation_version=CALCULATION_VERSION,
                )
            )
        cook_date = _parse_date(path.stem, source, "$filename").date()
        template_id = templates.get(type_name)
        if template_id is None:
            bundle.issues.append(
                MigrationIssue(
                    source,
                    "$.type",
                    f"template snapshot not found for {type_name!r}",
                    "unresolved_reference",
                )
            )
        bundle.entities["cooks"].append(
            Cook(
                id=identifier,
                cook_date=cook_date,
                legacy_filename=path.name,
                source_key=source,
                template_id=template_id,
                type_snapshot=type_name,
                sale=sale,
                total_price_cached=calculation.total_price,
                calculation_version=CALCULATION_VERSION,
                row_version=1,
            )
        )


def _transform_payments(root: Path, bundle: MigrationBundle) -> None:
    source = "Payments.json"
    values = _list(read_json(root / source), source, "$")
    for position, raw in enumerate(values):
        path = f"$[{position}]"
        item = _object(raw, source, path)
        user_id = _required(item, "userId", source, path)
        type_id = _required(item, "typeId", source, path)
        if user_id not in bundle.user_ids:
            raise MigrationError(f"{source} {path}: unknown userId {user_id}")
        if type_id not in bundle.payment_type_ids:
            raise MigrationError(f"{source} {path}: unknown typeId {type_id}")
        payment_date_raw = _required(item, "paymentDate", source, path)
        registration_raw = _required(item, "registrationDate", source, path)
        key = f"payments:{position}"
        bundle.entities["payments"].append(
            Payment(
                id=stable_uuid(key),
                legacy_position=position,
                user_id=bundle.user_ids[user_id],
                payment_type_id=bundle.payment_type_ids[type_id],
                payment_date=_parse_date(payment_date_raw, source, f"{path}.paymentDate").date(),
                payment_date_raw=payment_date_raw,
                registration_date_raw=registration_raw,
                registration_date_parsed=_parse_registration_date(
                    registration_raw, source, f"{path}.registrationDate"
                ),
                sum=_required(item, "sum", source, path),
                comment=item.get("comment", ""),
                source_key=key,
            )
        )


def _validate_unique_cook_dates(bundle: MigrationBundle) -> None:
    counts = Counter(cook.cook_date for cook in bundle.entities["cooks"])
    duplicates = [date.isoformat() for date, count in counts.items() if count > 1]
    if duplicates:
        raise MigrationError(f"duplicate cook dates: {', '.join(sorted(duplicates))}")
