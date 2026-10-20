from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from .models import Value


@dataclass(frozen=True)
class UnitSpec:
    symbol: str
    name: str
    dimension: tuple[int, int, int, int, int, int, int]
    factor: Fraction = Fraction(1)


_BASE = (0, 0, 0, 0, 0, 0, 0)


def _dims(m: int = 0, s: int = 0, kg: int = 0, a: int = 0, k: int = 0, mol: int = 0, cd: int = 0):
    return (m, s, kg, a, k, mol, cd)


UNITS: dict[str, UnitSpec] = {
    "m": UnitSpec("m", "米", _dims(m=1)),
    "km": UnitSpec("km", "千米", _dims(m=1), Fraction(1000)),
    "cm": UnitSpec("cm", "厘米", _dims(m=1), Fraction(1, 100)),
    "mm": UnitSpec("mm", "毫米", _dims(m=1), Fraction(1, 1000)),
    "s": UnitSpec("s", "秒", _dims(s=1)),
    "ms": UnitSpec("ms", "毫秒", _dims(s=1), Fraction(1, 1000)),
    "min": UnitSpec("min", "分钟", _dims(s=1), Fraction(60)),
    "h": UnitSpec("h", "小时", _dims(s=1), Fraction(3600)),
    "kg": UnitSpec("kg", "千克", _dims(kg=1)),
    "g": UnitSpec("g", "克", _dims(kg=1), Fraction(1, 1000)),
    "A": UnitSpec("A", "安培", _dims(a=1)),
    "K": UnitSpec("K", "开尔文", _dims(k=1)),
    "mol": UnitSpec("mol", "摩尔", _dims(mol=1)),
    "cd": UnitSpec("cd", "坎德拉", _dims(cd=1)),
    "N": UnitSpec("N", "牛顿", _dims(m=1, s=-2, kg=1)),
    "J": UnitSpec("J", "焦耳", _dims(m=2, s=-2, kg=1)),
    "W": UnitSpec("W", "瓦特", _dims(m=2, s=-3, kg=1)),
    "Pa": UnitSpec("Pa", "帕斯卡", _dims(m=-1, s=-2, kg=1)),
    "Hz": UnitSpec("Hz", "赫兹", _dims(s=-1)),
}


def unit_value(symbol: str) -> Value:
    spec = UNITS[symbol]
    return Value(
        "Unit",
        spec,
        True,
        spec.symbol,
        rf"\mathrm{{{spec.symbol}}}",
        {"dimension": list(spec.dimension), "name": spec.name},
    )


def quantity_value(magnitude: Value, spec: UnitSpec) -> Value:
    return Value(
        "Quantity",
        (magnitude, spec),
        magnitude.exact,
        f"{magnitude.display} {spec.symbol}",
        rf"{magnitude.latex}\ \mathrm{{{spec.symbol}}}",
        {"dimension": list(spec.dimension), "unit": spec.symbol},
    )


def dimension_symbol(dimension: tuple[int, int, int, int, int, int, int]) -> str:
    labels = ("m", "s", "kg", "A", "K", "mol", "cd")
    parts = []
    for label, exponent in zip(labels, dimension, strict=True):
        if exponent == 0:
            continue
        parts.append(label if exponent == 1 else f"{label}^{exponent}")
    return "*".join(parts) or "1"
