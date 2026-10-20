from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from .diagnostics import Diagnostic


def _json_safe(value: Any) -> Any:
    if isinstance(value, Fraction):
        return {"numerator": value.numerator, "denominator": value.denominator}
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, Value):
        return value.to_dict()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return str(value)
    return value


@dataclass
class Value:
    type: str
    data: Any
    exact: bool = True
    display: str = ""
    latex: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "data": _json_safe(self.data),
            "exact": self.exact,
            "display": self.display,
            "latex": self.latex,
            "meta": _json_safe(self.meta),
        }


@dataclass
class EnvironmentSnapshot:
    variables: dict[str, dict[str, Any]] = field(default_factory=dict)
    functions: dict[str, str] = field(default_factory=dict)
    assumptions: dict[str, list[str]] = field(default_factory=dict)
    mode: str = "exact"
    precision: int = 50
    rounding: str = "half_even"
    angle: str = "radians"
    random_seed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "variables": self.variables,
            "functions": self.functions,
            "assumptions": self.assumptions,
            "mode": self.mode,
            "precision": self.precision,
            "rounding": self.rounding,
            "angle": self.angle,
            "randomSeed": self.random_seed,
        }


@dataclass
class EvaluationResult:
    value: Value | None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    environment: EnvironmentSnapshot = field(default_factory=EnvironmentSnapshot)
    steps: list[dict[str, str]] = field(default_factory=list)
    algorithm: str = ""
    precision: int = 50
    rounding: str = "half_even"
    exactness: str = "exact"
    assumptions: dict[str, list[str]] = field(default_factory=dict)
    unit: str | None = None
    timing_ms: float = 0.0
    cached: bool = False
    program_id: str = ""
    statement_count: int = 0

    @property
    def ok(self) -> bool:
        return not any(d.severity == "error" for d in self.diagnostics)

    def to_dict(self) -> dict[str, Any]:
        return {
            "apiVersion": 1,
            "ok": self.ok,
            "value": self.value.to_dict() if self.value else None,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "environment": self.environment.to_dict(),
            "steps": self.steps,
            "algorithm": self.algorithm,
            "precision": self.precision,
            "rounding": self.rounding,
            "exactness": self.exactness,
            "assumptions": self.assumptions,
            "unit": self.unit,
            "timingMs": round(self.timing_ms, 3),
            "cached": self.cached,
            "programId": self.program_id,
            "statementCount": self.statement_count,
        }


@dataclass
class RunResult:
    results: list[EvaluationResult]
    diagnostics: list[Diagnostic] = field(default_factory=list)
    environment: EnvironmentSnapshot = field(default_factory=EnvironmentSnapshot)
    timing_ms: float = 0.0
    assertions: int = 0

    @property
    def ok(self) -> bool:
        return not any(d.severity == "error" for d in self.diagnostics) and all(
            r.ok for r in self.results
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "apiVersion": 1,
            "ok": self.ok,
            "results": [r.to_dict() for r in self.results],
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "environment": self.environment.to_dict(),
            "timingMs": round(self.timing_ms, 3),
            "assertions": self.assertions,
        }
