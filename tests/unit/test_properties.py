from __future__ import annotations

from fractions import Fraction

from hypothesis import given, settings
from hypothesis import strategies as st

from supercalc_core import Engine
from supercalc_core.numeric import float64_value, inspect_float64


@settings(max_examples=60, deadline=None)
@given(
    st.integers(min_value=-(10**9), max_value=10**9),
    st.integers(min_value=-(10**9), max_value=10**9).filter(lambda value: value != 0),
    st.integers(min_value=1, max_value=10**9),
    st.integers(min_value=1, max_value=10**9),
)
def test_rational_addition_property(a: int, b: int, c: int, d: int) -> None:
    result = Engine().evaluate(f"{a}/{b} + {c}/{d}")
    assert result.ok
    assert result.value.data == Fraction(a, b) + Fraction(c, d)


@settings(max_examples=60, deadline=None)
@given(st.integers(min_value=-(10**6), max_value=10**6), st.integers(min_value=2, max_value=36))
def test_base_roundtrip(value: int, radix: int) -> None:
    result = Engine().evaluate(f"base({value}, {radix})")
    assert result.ok
    assert int(result.value.data, radix) == value


@settings(max_examples=40, deadline=None)
@given(st.floats(allow_nan=True, allow_infinity=True, width=64))
def test_float64_bits_roundtrip(value: float) -> None:
    inspected = inspect_float64(float64_value(value))
    assert len(inspected["binary"]) == 64
    assert 0 <= inspected["sign"] <= 1
