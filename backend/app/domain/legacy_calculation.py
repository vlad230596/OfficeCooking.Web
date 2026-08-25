"""Legacy-compatible cook price and participant charge calculations.

The old application evaluates price expressions through ``DataTable.Compute`` and
then converts that result to a C# ``float``.  All subsequent arithmetic is C#
single-precision arithmetic.  This module deliberately makes those float32
rounding points explicit and never evaluates user input as Python code.
"""

from __future__ import annotations

import math
import re
import struct
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal, DecimalException, localcontext
from enum import StrEnum

INT32_MIN = -(2**31)
INT32_MAX = 2**31 - 1
FLOAT32_MAX = float.fromhex("0x1.fffffep+127")
MAX_EXPRESSION_LENGTH = 4096
MAX_EXPRESSION_TOKENS = 2048
MAX_NESTING_DEPTH = 64


class CalculationStatus(StrEnum):
    VALID = "valid"
    EMPTY = "empty"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ExpressionResult:
    status: CalculationStatus
    value: float | None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ProductInput:
    product_name: str | None
    expression: str | None


@dataclass(frozen=True, slots=True)
class MemberInput:
    user_id: int
    active: bool
    vote_indexes: Sequence[int]
    permanent_sale: float


@dataclass(frozen=True, slots=True)
class ProductCalculation:
    index: int
    included_in_total: bool
    result: ExpressionResult


@dataclass(frozen=True, slots=True)
class MemberCalculation:
    index: int
    user_id: int
    vote_weight: float
    effective_weight: float
    charge: int | None


@dataclass(frozen=True, slots=True)
class CookCalculation:
    status: CalculationStatus
    products: tuple[ProductCalculation, ...]
    total_price: float | None
    members: tuple[MemberCalculation, ...]
    total_effective_weight: float | None
    total_rounded_charges: int | None
    error: str | None = None


class LegacyCalculationError(ValueError):
    """A controlled invalid/non-numeric state in the legacy calculation."""


def float32(value: float | Decimal | int) -> float:
    """Round *value* to IEEE-754 binary32, rejecting non-finite/overflow values."""

    try:
        number = float(value)
        if not math.isfinite(number) or abs(number) > FLOAT32_MAX:
            raise LegacyCalculationError("value is outside the finite float32 range")
        result = struct.unpack("<f", struct.pack("<f", number))[0]
    except (OverflowError, ValueError) as exc:
        raise LegacyCalculationError("value is outside the finite float32 range") from exc
    if not math.isfinite(result):
        raise LegacyCalculationError("value is outside the finite float32 range")
    return result


def float32_bits(value: float) -> str:
    """Return the same lowercase bit representation as the C# oracle."""

    return struct.pack(">f", float32(value)).hex()


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    text: str
    offset: int


_NUMBER = re.compile(
    r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?",
    re.ASCII,
)


class _NumericKind(StrEnum):
    INT32 = "int32"
    INT64 = "int64"
    DECIMAL = "decimal"
    DOUBLE = "double"


DECIMAL_MAX = Decimal("79228162514264337593543950335")


@dataclass(frozen=True, slots=True)
class _Numeric:
    kind: _NumericKind
    value: int | float | Decimal

    @classmethod
    def literal(cls, text: str) -> _Numeric:
        if "e" in text.lower():
            try:
                return cls(_NumericKind.DOUBLE, float(text))
            except ValueError as exc:
                raise LegacyCalculationError("invalid scientific literal") from exc
        if "." in text:
            return cls(_NumericKind.DECIMAL, _checked_decimal(Decimal(text)))
        integer = int(text)
        if integer <= INT32_MAX:
            return cls(_NumericKind.INT32, integer)
        if integer <= 2**63 - 1:
            return cls(_NumericKind.INT64, integer)
        # DataTable promotes an out-of-Int64 integer literal to System.Double.
        return cls(_NumericKind.DOUBLE, float(text))

    def unary(self, operator: str) -> _Numeric:
        if operator == "+":
            return self
        if self.kind is _NumericKind.INT32:
            return _checked_integer(-int(self.value), _NumericKind.INT32)
        if self.kind is _NumericKind.INT64:
            return _checked_integer(-int(self.value), _NumericKind.INT64)
        if self.kind is _NumericKind.DECIMAL:
            return _Numeric(self.kind, _checked_decimal(-Decimal(self.value)))
        return _Numeric(self.kind, -float(self.value))

    def binary(self, operator: str, right: _Numeric) -> _Numeric:
        if operator == "/":
            return self._divide(right)
        kind = _common_arithmetic_kind(self.kind, right.kind)
        if kind is _NumericKind.DOUBLE:
            left_value, right_value = float(self.value), float(right.value)
            if operator == "+":
                result = left_value + right_value
            elif operator == "-":
                result = left_value - right_value
            else:
                result = left_value * right_value
            return _Numeric(kind, result)
        if kind is _NumericKind.DECIMAL:
            left_value, right_value = Decimal(self.value), Decimal(right.value)
            if operator == "+":
                result = left_value + right_value
            elif operator == "-":
                result = left_value - right_value
            else:
                result = left_value * right_value
            return _Numeric(kind, _checked_decimal(result))
        left_value, right_value = int(self.value), int(right.value)
        if operator == "+":
            result = left_value + right_value
        elif operator == "-":
            result = left_value - right_value
        else:
            result = left_value * right_value
        return _checked_integer(result, kind)

    def _divide(self, right: _Numeric) -> _Numeric:
        kind = _common_arithmetic_kind(self.kind, right.kind)
        if kind in (_NumericKind.INT32, _NumericKind.INT64, _NumericKind.DOUBLE):
            left_value, right_value = float(self.value), float(right.value)
            if right_value == 0.0:
                if left_value == 0.0:
                    return _Numeric(_NumericKind.DOUBLE, math.nan)
                signs_differ = math.copysign(1.0, left_value) != math.copysign(
                    1.0, right_value
                )
                sign = -1.0 if signs_differ else 1.0
                return _Numeric(_NumericKind.DOUBLE, math.copysign(math.inf, sign))
            return _Numeric(_NumericKind.DOUBLE, left_value / right_value)
        left_value, right_value = Decimal(self.value), Decimal(right.value)
        if right_value == 0:
            raise LegacyCalculationError("decimal division by zero")
        return _Numeric(_NumericKind.DECIMAL, _checked_decimal(left_value / right_value))


def _checked_integer(value: int, kind: _NumericKind) -> _Numeric:
    minimum, maximum = (
        (INT32_MIN, INT32_MAX)
        if kind is _NumericKind.INT32
        else (-(2**63), 2**63 - 1)
    )
    if value < minimum or value > maximum:
        raise LegacyCalculationError(f"{kind.value} arithmetic overflow")
    return _Numeric(kind, value)


def _checked_decimal(value: Decimal) -> Decimal:
    if not value.is_finite() or abs(value) > DECIMAL_MAX:
        raise LegacyCalculationError("decimal arithmetic overflow")
    return value


def _common_arithmetic_kind(left: _NumericKind, right: _NumericKind) -> _NumericKind:
    if _NumericKind.DOUBLE in (left, right):
        return _NumericKind.DOUBLE
    if _NumericKind.DECIMAL in (left, right):
        return _NumericKind.DECIMAL
    if _NumericKind.INT64 in (left, right):
        return _NumericKind.INT64
    return _NumericKind.INT32


def _tokenize(expression: str) -> list[_Token]:
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise LegacyCalculationError("expression is too long")
    tokens: list[_Token] = []
    offset = 0
    while offset < len(expression):
        character = expression[offset]
        if character.isspace():
            offset += 1
            continue
        match = _NUMBER.match(expression, offset)
        if match:
            tokens.append(_Token("number", match.group(), offset))
            if len(tokens) > MAX_EXPRESSION_TOKENS:
                raise LegacyCalculationError("expression has too many tokens")
            offset = match.end()
            continue
        if character in "+-*/()":
            tokens.append(_Token(character, character, offset))
            if len(tokens) > MAX_EXPRESSION_TOKENS:
                raise LegacyCalculationError("expression has too many tokens")
            offset += 1
            continue
        raise LegacyCalculationError(f"unsupported character at offset {offset}")
    tokens.append(_Token("eof", "", len(expression)))
    return tokens


class _Parser:
    """Recursive-descent parser for the approved DataTable-like subset."""

    def __init__(self, expression: str) -> None:
        # This is the exact normalization performed by the legacy application.
        self._tokens = _tokenize(expression.replace(",", "."))
        self._position = 0
        self._depth = 0

    @property
    def current(self) -> _Token:
        return self._tokens[self._position]

    def consume(self, kind: str) -> _Token:
        token = self.current
        if token.kind != kind:
            raise LegacyCalculationError(
                f"expected {kind!r} at offset {token.offset}, got {token.kind!r}"
            )
        self._position += 1
        return token

    def parse(self) -> _Numeric:
        value = self._additive()
        self.consume("eof")
        return value

    def _additive(self) -> _Numeric:
        value = self._multiplicative()
        while self.current.kind in ("+", "-"):
            operator = self.current.kind
            self._position += 1
            right = self._multiplicative()
            value = value.binary(operator, right)
        return value

    def _multiplicative(self) -> _Numeric:
        value = self._unary()
        while self.current.kind in ("*", "/"):
            operator = self.current.kind
            self._position += 1
            right = self._unary()
            value = value.binary(operator, right)
        return value

    def _unary(self) -> _Numeric:
        if self.current.kind in ("+", "-"):
            operator = self.current.kind
            self._position += 1
            value = self._nested(self._unary)
            return value.unary(operator)
        return self._primary()

    def _primary(self) -> _Numeric:
        if self.current.kind == "number":
            return _Numeric.literal(self.consume("number").text)
        if self.current.kind == "(":
            self.consume("(")
            value = self._nested(self._additive)
            self.consume(")")
            return value
        token = self.current
        raise LegacyCalculationError(f"expected a number or '(' at offset {token.offset}")

    def _nested(self, parser: Callable[[], _Numeric]) -> _Numeric:
        if self._depth >= MAX_NESTING_DEPTH:
            raise LegacyCalculationError("expression nesting is too deep")
        self._depth += 1
        try:
            return parser()
        finally:
            self._depth -= 1


def evaluate_expression(expression: str | None) -> ExpressionResult:
    """Safely evaluate an approved legacy expression and return float32 output."""

    if expression is None or expression.strip() == "":
        return ExpressionResult(CalculationStatus.EMPTY, 0.0)
    try:
        # System.Decimal/DataTable arithmetic has about 29 significant digits.
        with localcontext() as context:
            context.prec = 29
            value = _Parser(expression).parse()
        return ExpressionResult(CalculationStatus.VALID, float32(value.value))
    except (LegacyCalculationError, DecimalException) as exc:
        return ExpressionResult(CalculationStatus.ERROR, None, str(exc))


def _f32_add(left: float, right: float) -> float:
    return float32(float32(left) + float32(right))


def _f32_multiply(left: float, right: float) -> float:
    return float32(float32(left) * float32(right))


def _f32_divide(left: float, right: float) -> float:
    left32, right32 = float32(left), float32(right)
    if right32 == 0.0:
        raise LegacyCalculationError("total effective weight is zero")
    return float32(left32 / right32)


def truncating_integer_division(dividend: int, divisor: int) -> int:
    """Integer division truncated toward zero, matching C# (unlike Python ``//``)."""

    if divisor == 0:
        raise LegacyCalculationError("integer division by zero")
    quotient = abs(dividend) // abs(divisor)
    return -quotient if (dividend < 0) != (divisor < 0) else quotient


def ceil_to_5(price: float) -> int:
    """Legacy misnamed rounding: float-to-int truncation, then C# integer math."""

    price = float32(price)
    if price < INT32_MIN or price > INT32_MAX:
        raise LegacyCalculationError("charge input is outside the Int32 range")
    price_as_int = math.trunc(price)
    result = truncating_integer_division(price_as_int + 4, 5) * 5
    if result < INT32_MIN or result > INT32_MAX:
        raise LegacyCalculationError("charge result is outside the Int32 range")
    return result


def calculate_cook(
    products: Sequence[ProductInput],
    vote_values: Sequence[float],
    members: Sequence[MemberInput],
    cook_sale: float,
) -> CookCalculation:
    """Calculate one cook in the exact legacy product/member/vote order.

    Invalid expressions and invalid distribution states are protective errors:
    source rows remain representable, while totals and charges are unavailable.
    """

    product_results: list[ProductCalculation] = []
    total = 0.0
    product_error: str | None = None
    for index, product in enumerate(products):
        included = product.product_name is not None and product.expression is not None
        result = (
            evaluate_expression(product.expression)
            if included
            else ExpressionResult(CalculationStatus.EMPTY, 0.0)
        )
        product_results.append(ProductCalculation(index, included, result))
        if result.status is CalculationStatus.ERROR:
            product_error = product_error or f"product {index}: {result.error}"
        elif included:
            total = _f32_add(total, result.value or 0.0)

    if product_error is not None:
        return CookCalculation(
            CalculationStatus.ERROR,
            tuple(product_results),
            None,
            (),
            None,
            None,
            product_error,
        )

    intermediate: list[tuple[MemberInput, float, float]] = []
    total_weight = 0.0
    try:
        sale = float32(cook_sale)
        normalized_votes = tuple(float32(value) for value in vote_values)
        for member_index, member in enumerate(members):
            vote_weight = 0.0
            for vote_index in member.vote_indexes:
                if vote_index < 0 or vote_index >= len(normalized_votes):
                    raise LegacyCalculationError(
                        f"member {member_index} references invalid vote index {vote_index}"
                    )
                vote_weight = _f32_add(vote_weight, normalized_votes[vote_index])
            effective_weight = _f32_multiply(vote_weight, member.permanent_sale)
            if member.active:
                effective_weight = _f32_multiply(effective_weight, sale)
            total_weight = _f32_add(total_weight, effective_weight)
            intermediate.append((member, vote_weight, effective_weight))

        if total_weight == 0.0:
            raise LegacyCalculationError("total effective weight is zero")

        unit_price = _f32_divide(total, total_weight)
        member_results: list[MemberCalculation] = []
        total_charges = 0
        for index, (member, vote_weight, effective_weight) in enumerate(intermediate):
            charge = ceil_to_5(_f32_multiply(unit_price, effective_weight))
            total_charges += charge
            if total_charges < INT32_MIN or total_charges > INT32_MAX:
                raise LegacyCalculationError("total rounded charges are outside the Int32 range")
            member_results.append(
                MemberCalculation(index, member.user_id, vote_weight, effective_weight, charge)
            )
    except LegacyCalculationError as exc:
        partial_members = tuple(
            MemberCalculation(index, member.user_id, vote_weight, effective_weight, None)
            for index, (member, vote_weight, effective_weight) in enumerate(intermediate)
        )
        return CookCalculation(
            CalculationStatus.ERROR,
            tuple(product_results),
            total,
            partial_members,
            total_weight if math.isfinite(total_weight) else None,
            None,
            str(exc),
        )

    return CookCalculation(
        CalculationStatus.VALID,
        tuple(product_results),
        total,
        tuple(member_results),
        total_weight,
        total_charges,
    )


__all__ = [
    "CalculationStatus",
    "CookCalculation",
    "ExpressionResult",
    "LegacyCalculationError",
    "MemberCalculation",
    "MemberInput",
    "ProductCalculation",
    "ProductInput",
    "calculate_cook",
    "ceil_to_5",
    "evaluate_expression",
    "float32",
    "float32_bits",
    "truncating_integer_division",
]
