from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import sympy as sp

from .api import Engine
from .diagnostics import CalcError, Diagnostic, Severity
from .numeric import value_to_sympy


@dataclass
class PlotSpec:
    expression: str = "sin(x)"
    variable: str = "x"
    x_min: float = -10.0
    x_max: float = 10.0
    samples: int = 600
    kind: str = "cartesian"

    def to_dict(self) -> dict[str, Any]:
        return {
            "expression": self.expression,
            "variable": self.variable,
            "xMin": self.x_min,
            "xMax": self.x_max,
            "samples": self.samples,
            "kind": self.kind,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlotSpec:
        return cls(
            expression=str(data.get("expression", "sin(x)")),
            variable=str(data.get("variable", "x")),
            x_min=float(data.get("xMin", -10.0)),
            x_max=float(data.get("xMax", 10.0)),
            samples=int(data.get("samples", 600)),
            kind=str(data.get("kind", "cartesian")),
        )


@dataclass
class PlotSamples:
    x: list[float]
    y: list[float]
    kind: str
    expression: str
    diagnostics: list[Diagnostic]

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "kind": self.kind,
            "expression": self.expression,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }


def sample_plot(engine: Engine, spec: PlotSpec) -> PlotSamples:
    if spec.kind not in {"cartesian", "polar"}:
        raise CalcError(
            "SC5101",
            f"不支持的绘图类型：{spec.kind}",
            hint="MVP 支持 cartesian 和 polar。",
            category="plot",
        )
    if not 2 <= spec.samples <= 20_000:
        raise CalcError("SC5102", "采样点数量必须在 2 到 20000 之间", category="plot")
    if not math.isfinite(spec.x_min) or not math.isfinite(spec.x_max):
        raise CalcError("SC5103", "绘图范围必须是有限数", category="plot")
    if spec.x_min >= spec.x_max:
        raise CalcError("SC5104", "绘图范围起点必须小于终点", category="plot")
    result = engine.evaluate(spec.expression)
    if not result.ok or result.value is None:
        return PlotSamples([], [], spec.kind, spec.expression, result.diagnostics)
    try:
        expr = value_to_sympy(result.value)
    except CalcError:
        return PlotSamples(
            [],
            [],
            spec.kind,
            spec.expression,
            result.diagnostics
            + [
                Diagnostic(
                    code="SC5105",
                    severity=Severity.ERROR,
                    message="绘图表达式必须是数值函数",
                    category="plot",
                )
            ],
        )
    variable = sp.Symbol(spec.variable)
    if expr.free_symbols - {variable}:
        names = ", ".join(sorted(str(symbol) for symbol in expr.free_symbols - {variable}))
        return PlotSamples(
            [],
            [],
            spec.kind,
            spec.expression,
            [
                Diagnostic(
                    code="SC5106",
                    severity=Severity.ERROR,
                    message=f"绘图表达式含未绑定变量：{names}",
                    hint="在绘图前给其他变量赋值，或只保留一个自变量。",
                    category="plot",
                )
            ],
        )
    x_values = np.linspace(spec.x_min, spec.x_max, spec.samples)
    try:
        function = sp.lambdify(variable, expr, modules=["numpy"])
        with np.errstate(all="ignore"):
            y_values = np.asarray(function(x_values), dtype=float)
        if y_values.ndim == 0:
            y_values = np.full_like(x_values, float(y_values))
    except Exception as exc:
        return PlotSamples(
            [],
            [],
            spec.kind,
            spec.expression,
            [
                Diagnostic(
                    code="SC5107",
                    severity=Severity.ERROR,
                    message=f"无法采样该表达式：{exc}",
                    hint="检查函数定义域与实数结果。",
                    category="plot",
                )
            ],
        )
    return PlotSamples(
        x=[float(value) for value in x_values],
        y=[float(value) for value in y_values],
        kind=spec.kind,
        expression=spec.expression,
        diagnostics=result.diagnostics,
    )
