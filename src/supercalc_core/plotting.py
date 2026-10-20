from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import sympy as sp

from .api import Engine
from .diagnostics import CalcError, Diagnostic, Severity
from .numeric import value_to_sympy


@dataclass(init=False)
class PlotSpec:
    equation: str
    x_min: float
    x_max: float
    samples: int
    kind: str

    def __init__(
        self,
        equation: str | None = None,
        x_min: float = -10.0,
        x_max: float = 10.0,
        samples: int = 600,
        kind: str = "cartesian",
        *,
        expression: str | None = None,
        variable: str = "x",
    ) -> None:
        if equation is None:
            source = expression or "sin(x)"
            if kind == "polar":
                equation = f"r = {source}"
            else:
                equation = f"y = {source}"
            del variable
        self.equation = equation.strip()
        self.x_min = x_min
        self.x_max = x_max
        self.samples = samples
        self.kind = kind

    @property
    def expression(self) -> str:
        return self.equation

    def to_dict(self) -> dict[str, Any]:
        return {
            "equation": self.equation,
            "xMin": self.x_min,
            "xMax": self.x_max,
            "samples": self.samples,
            "kind": self.kind,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlotSpec:
        if "equation" in data:
            return cls(
                equation=str(data.get("equation", "y = sin(x)")),
                x_min=float(data.get("xMin", -10.0)),
                x_max=float(data.get("xMax", 10.0)),
                samples=int(data.get("samples", 600)),
                kind=str(data.get("kind", "cartesian")),
            )
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
    equation: str
    diagnostics: list[Diagnostic]
    grid_x: list[float] = field(default_factory=list)
    grid_y: list[float] = field(default_factory=list)
    grid_z: list[list[float]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "kind": self.kind,
            "equation": self.equation,
            "gridX": self.grid_x,
            "gridY": self.grid_y,
            "gridZ": self.grid_z,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }


def _error(
    code: str,
    message: str,
    *,
    hint: str = "",
    equation: str = "",
    kind: str = "explicit",
) -> PlotSamples:
    return PlotSamples(
        [],
        [],
        kind,
        equation,
        [
            Diagnostic(
                code=code,
                severity=Severity.ERROR,
                message=message,
                hint=hint,
                category="plot",
            )
        ],
    )


def sample_plot(engine: Engine, spec: PlotSpec) -> PlotSamples:
    if spec.kind not in {"cartesian", "polar"}:
        raise CalcError(
            "SC5101",
            f"不支持的绘图类型：{spec.kind}",
            hint="支持直角/隐式曲线和极坐标曲线。",
            category="plot",
        )
    if not 2 <= spec.samples <= 20_000:
        raise CalcError("SC5102", "采样点数量必须在 2 到 20000 之间", category="plot")
    if not math.isfinite(spec.x_min) or not math.isfinite(spec.x_max):
        raise CalcError("SC5103", "绘图范围必须是有限数", category="plot")
    if spec.x_min >= spec.x_max:
        raise CalcError("SC5104", "绘图范围起点必须小于终点", category="plot")
    if "=" not in spec.equation:
        return _error(
            "SC5108",
            "绘图方程必须包含等号，例如 y = sin(x) 或 y^2 + x^2 = 1。",
            equation=spec.equation,
        )
    result = engine.evaluate(spec.equation)
    if not result.ok or result.value is None or result.value.type != "Equation":
        return _error(
            "SC5109",
            "无法解析绘图方程。",
            hint="绘图单元需要单个方程，例如 y = x^2。",
            equation=spec.equation,
        )
    left_value, right_value = result.value.data
    try:
        left = value_to_sympy(left_value)
        right = value_to_sympy(right_value)
    except CalcError:
        return _error(
            "SC5110",
            "方程两侧必须是数学表达式。",
            equation=spec.equation,
        )

    if spec.kind == "polar":
        return _sample_polar(engine, spec, left, right, result.diagnostics)

    y_symbol = sp.Symbol("y")
    if sp.simplify(left - y_symbol) == 0:
        expression = right
    elif sp.simplify(right - y_symbol) == 0:
        expression = left
    else:
        return _sample_implicit(engine, spec, left - right, result.diagnostics)
    return _sample_explicit(engine, spec, expression, result.diagnostics)


def _sample_explicit(
    engine: Engine,
    spec: PlotSpec,
    expression: sp.Expr,
    diagnostics: list[Diagnostic],
) -> PlotSamples:
    del engine
    x_symbol = sp.Symbol("x")
    unexpected = expression.free_symbols - {x_symbol}
    if unexpected:
        return _error(
            "SC5106",
            f"方程含未绑定变量：{', '.join(sorted(str(item) for item in unexpected))}",
            hint="直角坐标方程只能使用 x 和 y，例如 y = sin(x)。",
            equation=spec.equation,
        )
    x_values = np.linspace(spec.x_min, spec.x_max, spec.samples)
    try:
        function = sp.lambdify(x_symbol, expression, modules=["numpy"])
        with np.errstate(all="ignore"):
            y_values = np.asarray(function(x_values), dtype=float)
        if y_values.ndim == 0:
            y_values = np.full_like(x_values, float(y_values))
    except Exception as exc:
        return _error(
            "SC5107",
            f"无法采样该表达式：{exc}",
            hint="检查函数定义域与实数结果。",
            equation=spec.equation,
        )
    return PlotSamples(
        x=[float(value) for value in x_values],
        y=[float(value) for value in y_values],
        kind="explicit",
        equation=spec.equation,
        diagnostics=diagnostics,
    )


def _sample_polar(
    engine: Engine,
    spec: PlotSpec,
    left: sp.Expr,
    right: sp.Expr,
    diagnostics: list[Diagnostic],
) -> PlotSamples:
    del engine
    r_symbols = {sp.Symbol("r")}
    theta_symbol = sp.Symbol("theta")
    if not (left.free_symbols & r_symbols):
        return _error(
            "SC5111",
            "极坐标方程应为 r = f(theta)。",
            equation=spec.equation,
            kind="polar",
        )
    expression = right
    unexpected = expression.free_symbols - {theta_symbol, sp.Symbol("θ")}
    if unexpected:
        return _error(
            "SC5112",
            f"极坐标方程含未绑定变量：{', '.join(sorted(str(item) for item in unexpected))}",
            hint="使用 theta 作为极角变量。",
            equation=spec.equation,
            kind="polar",
        )
    if sp.Symbol("θ") in expression.free_symbols:
        expression = expression.subs(sp.Symbol("θ"), theta_symbol)
    theta_values = np.linspace(spec.x_min, spec.x_max, spec.samples)
    try:
        function = sp.lambdify(theta_symbol, expression, modules=["numpy"])
        with np.errstate(all="ignore"):
            radius = np.asarray(function(theta_values), dtype=float)
        if radius.ndim == 0:
            radius = np.full_like(theta_values, float(radius))
    except Exception as exc:
        return _error(
            "SC5113",
            f"无法采样极坐标方程：{exc}",
            equation=spec.equation,
            kind="polar",
        )
    return PlotSamples(
        x=[float(value) for value in theta_values],
        y=[float(value) for value in radius],
        kind="polar",
        equation=spec.equation,
        diagnostics=diagnostics,
    )


def _sample_implicit(
    engine: Engine,
    spec: PlotSpec,
    expression: sp.Expr,
    diagnostics: list[Diagnostic],
) -> PlotSamples:
    del engine
    x_symbol = sp.Symbol("x")
    y_symbol = sp.Symbol("y")
    unexpected = expression.free_symbols - {x_symbol, y_symbol}
    if unexpected:
        return _error(
            "SC5114",
            f"隐式方程含未绑定变量：{', '.join(sorted(str(item) for item in unexpected))}",
            equation=spec.equation,
        )
    grid_points = max(120, min(800, int(math.sqrt(spec.samples * 400))))
    x_values = np.linspace(spec.x_min, spec.x_max, grid_points)
    y_values = np.linspace(spec.x_min, spec.x_max, grid_points)
    try:
        function = sp.lambdify((x_symbol, y_symbol), expression, modules=["numpy"])
        grid_x, grid_y = np.meshgrid(x_values, y_values)
        with np.errstate(all="ignore"):
            grid_z = np.asarray(function(grid_x, grid_y), dtype=float)
    except Exception as exc:
        return _error(
            "SC5115",
            f"无法采样隐式方程：{exc}",
            equation=spec.equation,
        )
    return PlotSamples(
        [],
        [],
        kind="implicit",
        equation=spec.equation,
        diagnostics=diagnostics,
        grid_x=[float(value) for value in x_values],
        grid_y=[float(value) for value in y_values],
        grid_z=grid_z.tolist(),
    )
