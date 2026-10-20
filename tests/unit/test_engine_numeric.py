from __future__ import annotations

from fractions import Fraction

import pytest

from supercalc_core import Engine
from supercalc_core.api import EngineConfig


def test_exact_rational_addition() -> None:
    result = Engine().evaluate("1/3 + 1/6")
    assert result.ok
    assert result.value is not None
    assert result.value.type == "Rational"
    assert result.value.exact is True
    assert result.value.data == Fraction(1, 2)
    assert result.value.display == "1/2"


def test_exact_decimal_is_not_float() -> None:
    result = Engine().evaluate("0.1 + 0.2")
    assert result.ok
    assert result.value is not None
    assert result.value.type == "Rational"
    assert result.value.data == Fraction(3, 10)


def test_approx_mode_warns_and_marks_result() -> None:
    result = Engine(EngineConfig(mode="approx", precision=50)).evaluate("0.1 + 0.2")
    assert result.ok
    assert result.value is not None
    assert result.value.exact is False
    assert result.value.type == "ApproxReal"
    assert any(d.code == "SC3001" for d in result.diagnostics)
    assert result.exactness == "approximate"


def test_fixed_width_overflow_is_visible() -> None:
    result = Engine().evaluate("i64(9223372036854775807) + 1")
    assert result.ok
    assert result.value is not None
    assert result.value.type == "FixedInt"
    assert int(result.value.data) == -9223372036854775808
    assert any(d.code == "SC3002" for d in result.diagnostics)


def test_ieee_fields() -> None:
    result = Engine().evaluate("bits(f64(0.1))")
    assert result.ok
    assert result.value is not None
    data = result.value.meta["ieee754"]
    assert data["sign"] == 0
    assert data["exponentBits"] == 1019
    assert data["mantissaBits"] == 2702159776422298
    assert data["classification"] == "finite"


def test_fixed_width_rotate_and_popcount() -> None:
    rotated = Engine().evaluate("rotl(u8(0b10000001), 1)")
    assert rotated.ok and rotated.value is not None
    assert int(rotated.value.data) == 3
    counted = Engine().evaluate("popcount(i8(-1))")
    assert counted.ok and counted.value is not None
    assert int(counted.value.data) == 8


def test_boolean_truth_table() -> None:
    result = Engine().evaluate('truth_table("x and y")')
    assert result.ok and result.value is not None
    assert result.value.data == [
        ["0", "0", "0"],
        ["0", "1", "0"],
        ["1", "0", "0"],
        ["1", "1", "1"],
    ]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("0xFF", 255),
        ("0b1010", 10),
        ("gcd(48, 18)", 6),
        ("lcm(12, 18)", 36),
        ("modpow(2, 10, 1000)", 24),
        ("comb(10, 3)", 120),
        ("popcount(0b101101)", 4),
    ],
)
def test_programmer_integers(source: str, expected: int) -> None:
    result = Engine().evaluate(source)
    assert result.ok, result.to_dict()
    assert result.value is not None
    assert int(result.value.data) == expected
