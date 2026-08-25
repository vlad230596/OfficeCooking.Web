from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domain.legacy_calculation import (
    CalculationStatus,
    MemberInput,
    ProductInput,
    calculate_cook,
    ceil_to_5,
    evaluate_expression,
    float32_bits,
    truncating_integer_division,
)

EXPRESSION_CORPUS_PATH = Path(__file__).parent / "fixtures/legacy-expression-corpus.json"


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("8*90+2*95", 910.0),
        ("10,5*2", 21.0),
        ("(100-15)*2", 170.0),
        ("1+2*3", 7.0),
        ("-(2+3)*4", -20.0),
        ("1/4", 0.25),
        ("", 0.0),
    ],
)
def test_expression_grammar_and_precedence(expression: str, expected: float) -> None:
    result = evaluate_expression(expression)
    assert result.error is None
    assert result.value == expected


@pytest.mark.parametrize("expression", ["abs(1)", "1;2", "2 2", "("])
def test_expression_errors_are_protective(expression: str) -> None:
    result = evaluate_expression(expression)
    assert result.status is CalculationStatus.ERROR
    assert result.value is None
    assert result.error


def test_expression_resource_limits_are_protective() -> None:
    assert evaluate_expression("1" * 4097).status is CalculationStatus.ERROR
    assert evaluate_expression("(" * 65 + "1" + ")" * 65).status is CalculationStatus.ERROR


def test_expression_corpus_matches_datatable_or_uses_documented_protection() -> None:
    corpus = json.loads(EXPRESSION_CORPUS_PATH.read_text(encoding="utf-8"))
    assert corpus["schemaVersion"] == "office-cook-legacy-expression-corpus/v1"

    for case in corpus["cases"]:
        result = evaluate_expression(case["expression"])
        if not case["isValid"]:
            # Legacy substitutes float.MinValue. Web v1 intentionally preserves
            # the expression but exposes a controlled error instead.
            assert result.status is CalculationStatus.ERROR, case["id"]
            assert result.value is None, case["id"]
        elif case["legacyFloat32Bits"] in {"7f800000", "ff800000", "7fc00000"}:
            # API/DB fields never serialize NaN or infinity.
            assert result.status is CalculationStatus.ERROR, case["id"]
            assert result.value is None, case["id"]
        else:
            assert result.status is not CalculationStatus.ERROR, case["id"]
            assert float32_bits(result.value or 0.0) == case["legacyFloat32Bits"], case["id"]


def test_empty_expression_is_a_distinct_zero_state() -> None:
    result = evaluate_expression(None)
    assert result.status is CalculationStatus.EMPTY
    assert float32_bits(result.value or 0.0) == "00000000"


@pytest.mark.parametrize(
    ("value", "expected"), [(0.0, 0), (1.0, 5), (5.99, 5), (6.0, 10), (-1.0, 0)]
)
def test_ceil_to_5_matches_csharp(value: float, expected: int) -> None:
    assert ceil_to_5(value) == expected


def test_integer_division_truncates_toward_zero() -> None:
    assert truncating_integer_division(-7, 5) == -1
    assert truncating_integer_division(7, -5) == -1


def test_zero_weight_returns_controlled_distribution_error() -> None:
    result = calculate_cook(
        [ProductInput("x", "100")],
        [1.0],
        [MemberInput(0, True, [0], 0.0)],
        0.6,
    )
    assert result.status is CalculationStatus.ERROR
    assert result.total_price == 100.0
    assert result.total_rounded_charges is None
    assert result.error == "total effective weight is zero"


def test_invalid_expression_makes_total_and_charges_unavailable() -> None:
    result = calculate_cook(
        [ProductInput("x", "not arithmetic")],
        [1.0],
        [MemberInput(0, True, [0], 1.0)],
        0.6,
    )
    assert result.status is CalculationStatus.ERROR
    assert result.total_price is None
    assert result.members == ()
    assert result.total_rounded_charges is None
