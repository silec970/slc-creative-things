from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import math
import random
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

import mpmath as mp
import sympy as sp

from .ast import (
    AssertStatement,
    Assignment,
    BinaryExpr,
    Block,
    CallExpr,
    ConditionalExpr,
    Directive,
    EquationExpr,
    Expr,
    ExprStatement,
    ForStatement,
    FunctionDef,
    IfStatement,
    ListExpr,
    ModuleUse,
    NameExpr,
    NumberExpr,
    Program,
    ReturnStatement,
    Statement,
    StringExpr,
    UnaryExpr,
    WhileStatement,
    expr_to_source,
)
from .diagnostics import CalcError, Diagnostic, Severity, Span, warning
from .models import EnvironmentSnapshot, EvaluationResult, RunResult, Value
from .numeric import (
    NUMERIC_TYPES,
    approx_value,
    binary_arithmetic,
    bits_from_float,
    bool_value,
    complex_exact_value,
    float64_value,
    int_value,
    make_fixed,
    matrix_value,
    null_value,
    parse_number_literal,
    rational_value,
    set_value,
    string_value,
    symbolic_value,
    unary_arithmetic,
    value_from_python,
    value_to_mpf,
    value_to_python,
    value_to_sympy,
    vector_value,
)
from .parser import parse
from .units import UNITS, unit_value


@dataclass
class EngineConfig:
    mode: str = "exact"
    precision: int = 50
    rounding: str = "half_even"
    angle: str = "radians"
    random_seed: int = 0
    max_recursion: int = 128
    max_script_steps: int = 1_000_000
    max_collection_size: int = 100_000
    max_output_chars: int = 1_000_000


@dataclass
class _Environment:
    variables: dict[str, Value] = field(default_factory=dict)
    functions: dict[str, FunctionDef] = field(default_factory=dict)
    assumptions: dict[str, set[str]] = field(default_factory=dict)
    module_cache: dict[str, str] = field(default_factory=dict)


@dataclass
class _RunState:
    diagnostics: list[Diagnostic] = field(default_factory=list)
    steps: list[dict[str, str]] = field(default_factory=list)
    algorithm: str = ""
    recursion_depth: int = 0
    steps_used: int = 0
    assertions: int = 0
    start_time: float = field(default_factory=time.monotonic)


_ASSUMPTION_FLAGS = {
    "real",
    "complex",
    "positive",
    "negative",
    "integer",
    "rational",
    "irrational",
    "nonzero",
    "zero",
    "even",
    "odd",
    "finite",
    "infinite",
}

_RESERVED_FUNCTIONS = {
    "solve",
    "simplify",
    "expand",
    "factor",
    "diff",
    "integrate",
    "limit",
    "series",
    "summation",
    "product",
    "det",
    "inv",
    "eigenvalues",
    "approx",
    "n",
    "f64",
}


class Engine:
    """Headless SuperCalc evaluation engine."""

    api_version = 1
    app_version = "0.1.0"

    def __init__(
        self, config: EngineConfig | None = None, environment: _Environment | None = None
    ) -> None:
        self.config = config or EngineConfig()
        self.environment = environment or _Environment()
        self.module_root: Path | None = None
        self._cache: dict[str, EvaluationResult] = {}
        self._state = _RunState()
        self._rng = random.Random(self.config.random_seed)

    def parse(self, source: str, *, script: bool = False) -> Program:
        return parse(source, script=script)

    def load_workspace(self, path: str | Path):
        from .workspace import Workspace

        return Workspace.load(path)

    def save_workspace(self, workspace: Any, path: str | Path) -> Path:
        return workspace.save(path)

    def snapshot(self) -> EnvironmentSnapshot:
        return EnvironmentSnapshot(
            variables={name: value.to_dict() for name, value in self.environment.variables.items()},
            functions={
                name: expr_to_source(definition.body)
                if definition.body is not None
                else f"fn {name}({', '.join(definition.params)})"
                for name, definition in self.environment.functions.items()
            },
            assumptions={
                name: sorted(values) for name, values in self.environment.assumptions.items()
            },
            mode=self.config.mode,
            precision=self.config.precision,
            rounding=self.config.rounding,
            angle=self.config.angle,
            random_seed=self.config.random_seed,
        )

    def evaluate(self, source: str, *, script: bool = False) -> EvaluationResult:
        start = time.monotonic()
        self._state = _RunState(start_time=start)
        value: Value | None = null_value()
        statement_count = 0
        try:
            program = self.parse(source, script=script)
            statement_count = len(program.statements)
            for statement in program.statements:
                value = self._execute_statement(statement, {}, self._state, collect=False)
        except CalcError as exc:
            self._state.diagnostics.append(exc.diagnostic(source))
            value = None
        except RecursionError:
            self._state.diagnostics.append(
                Diagnostic(
                    code="SC6003",
                    severity=Severity.ERROR,
                    message="递归深度超过限制",
                    hint=f"当前上限为 {self.config.max_recursion}，请检查递归终止条件。",
                    category="script",
                )
            )
            value = None
        except Exception as exc:  # pragma: no cover - defensive boundary
            self._state.diagnostics.append(
                Diagnostic(
                    code="SC9000",
                    severity=Severity.ERROR,
                    message=f"内部计算错误：{exc}",
                    hint="请保存工作区并报告此问题。表达式未被修改。",
                    category="internal",
                )
            )
            value = None
        elapsed = (time.monotonic() - start) * 1000
        exactness = "exact" if value is not None and value.exact else "approximate"
        if value is not None and value.type == "Symbolic":
            exactness = "symbolic"
        if value is None:
            exactness = "unknown"
        return EvaluationResult(
            value=value,
            diagnostics=self._state.diagnostics,
            environment=self.snapshot(),
            steps=self._state.steps,
            algorithm=self._state.algorithm,
            precision=self.config.precision,
            rounding=self.config.rounding,
            exactness=exactness,
            assumptions={
                name: sorted(values) for name, values in self.environment.assumptions.items()
            },
            unit=value.meta.get("unit") if value else None,
            timing_ms=elapsed,
            statement_count=statement_count,
        )

    def execute(self, program: Program) -> RunResult:
        start = time.monotonic()
        results: list[EvaluationResult] = []
        aggregate = _RunState(start_time=start)
        for statement in program.statements:
            self._state = aggregate
            try:
                value = self._execute_statement(statement, {}, aggregate, collect=False)
                result = EvaluationResult(
                    value=value,
                    diagnostics=list(aggregate.diagnostics),
                    environment=self.snapshot(),
                    steps=list(aggregate.steps),
                    algorithm=aggregate.algorithm,
                    precision=self.config.precision,
                    rounding=self.config.rounding,
                    exactness="exact" if value and value.exact else "approximate",
                    assumptions={
                        name: sorted(values)
                        for name, values in self.environment.assumptions.items()
                    },
                )
            except CalcError as exc:
                diagnostic = exc.diagnostic(program.source)
                aggregate.diagnostics.append(diagnostic)
                result = EvaluationResult(
                    value=None,
                    diagnostics=[diagnostic],
                    environment=self.snapshot(),
                    precision=self.config.precision,
                    rounding=self.config.rounding,
                    exactness="unknown",
                )
            results.append(result)
        elapsed = (time.monotonic() - start) * 1000
        return RunResult(
            results=results,
            diagnostics=list(aggregate.diagnostics),
            environment=self.snapshot(),
            timing_ms=elapsed,
            assertions=aggregate.assertions,
        )

    def run_script(self, source: str) -> RunResult:
        start = time.monotonic()
        self._state = _RunState(start_time=start)
        results: list[EvaluationResult] = []
        try:
            program = self.parse(source, script=True)
            for statement in program.statements:
                value = self._execute_statement(statement, {}, self._state, collect=True)
                if value is not None:
                    results.append(
                        EvaluationResult(
                            value=value,
                            diagnostics=list(self._state.diagnostics),
                            environment=self.snapshot(),
                            steps=list(self._state.steps),
                            precision=self.config.precision,
                            rounding=self.config.rounding,
                            exactness="exact" if value.exact else "approximate",
                        )
                    )
        except CalcError as exc:
            self._state.diagnostics.append(exc.diagnostic(source))
        except Exception as exc:  # pragma: no cover
            self._state.diagnostics.append(
                Diagnostic(
                    code="SC9000",
                    severity=Severity.ERROR,
                    message=f"内部脚本错误：{exc}",
                    category="internal",
                )
            )
        elapsed = (time.monotonic() - start) * 1000
        return RunResult(
            results=results,
            diagnostics=list(self._state.diagnostics),
            environment=self.snapshot(),
            timing_ms=elapsed,
            assertions=self._state.assertions,
        )

    def _execute_statement(
        self,
        statement: Statement,
        local: dict[str, Value],
        state: _RunState,
        *,
        collect: bool,
    ) -> Value | None:
        self._check_step(state)
        if isinstance(statement, Directive):
            self._apply_directive(statement, state)
            return Value(
                "String",
                f"{statement.name}={statement.value}",
                True,
                f"{statement.name} = {statement.value}",
                "",
                {"directive": statement.name},
            )
        if isinstance(statement, Assignment):
            value = self._eval_expr(statement.expr, local, state)
            self.environment.variables[statement.name] = value
            state.steps.append({"title": "赋值", "detail": f"{statement.name} := {value.display}"})
            return value
        if isinstance(statement, FunctionDef):
            if statement.name.startswith("__"):
                raise CalcError(
                    "SC6005", "函数名不能以双下划线开始", category="security", span=statement.span
                )
            self.environment.functions[statement.name] = statement
            return Value(
                "Function",
                statement.name,
                True,
                f"{statement.name}({', '.join(statement.params)})",
                "",
                {"params": statement.params},
            )
        if isinstance(statement, ExprStatement):
            return self._eval_expr(statement.expr, local, state)
        if isinstance(statement, IfStatement):
            condition = self._eval_expr(statement.condition, local, state)
            block: Block | None
            if self._truthy(condition):
                block = statement.then_block
            else:
                block = statement.else_block
            if block is not None:
                return self._execute_block(block, local, state, collect=collect)
            return null_value()
        if isinstance(statement, WhileStatement):
            result: Value = null_value()
            iterations = 0
            while self._truthy(self._eval_expr(statement.condition, local, state)):
                self._check_step(state)
                result = self._execute_block(statement.block, local, state, collect=collect)
                iterations += 1
                if iterations > self.config.max_script_steps:
                    raise CalcError(
                        "SC6004",
                        "循环超过最大迭代次数",
                        hint="检查循环终止条件或提高脚本额度。",
                        category="script",
                        span=statement.span,
                    )
            return result
        if isinstance(statement, ForStatement):
            iterable = self._eval_expr(statement.iterable, local, state)
            items = self._iter_values(iterable)
            result = null_value()
            for item in items:
                local[statement.name] = item
                result = self._execute_block(statement.block, local, state, collect=collect)
            return result
        if isinstance(statement, AssertStatement):
            condition = self._eval_expr(statement.condition, local, state)
            state.assertions += 1
            if not self._truthy(condition):
                message = statement.message or "断言失败"
                raise CalcError(
                    "SC6001",
                    message,
                    hint="检查该断言涉及的计算与精度设置。",
                    category="assertion",
                    span=statement.span,
                )
            return bool_value(True)
        if isinstance(statement, ReturnStatement):
            raise _ReturnSignal(self._eval_expr(statement.expr, local, state))
        if isinstance(statement, ModuleUse):
            return self._load_module(statement.path, statement.span, local, state, collect=collect)
        raise CalcError("SC9001", f"未知语句类型 {type(statement).__name__}", category="internal")

    def _execute_block(
        self,
        block: Block,
        local: dict[str, Value],
        state: _RunState,
        *,
        collect: bool,
    ) -> Value:
        result: Value = null_value()
        for statement in block.statements:
            try:
                value = self._execute_statement(statement, local, state, collect=collect)
            except _ReturnSignal as signal:
                return signal.value
            if value is not None:
                result = value
        return result

    def _load_module(
        self,
        path: str,
        span: Span | None,
        local: dict[str, Value],
        state: _RunState,
        *,
        collect: bool,
    ) -> Value:
        if path.startswith("__") or ".." in Path(path).parts:
            raise CalcError(
                "SC6006",
                "模块路径不允许跳出插件目录",
                hint="模块路径必须是插件目录内的相对 .scscript 文件。",
                category="security",
                span=span,
            )
        base = getattr(self, "module_root", None)
        if base is None:
            raise CalcError(
                "SC6007",
                "当前上下文不允许加载外部模块",
                hint="模块只能由已加载的本地插件声明。",
                category="security",
                span=span,
            )
        root = Path(base).resolve()
        candidate = (root / path).resolve()
        if root not in candidate.parents or candidate.suffix.lower() != ".scscript":
            raise CalcError(
                "SC6008",
                "模块路径越界",
                hint="只能加载插件目录内的 .scscript 文件。",
                category="security",
                span=span,
            )
        if str(candidate) in self.environment.module_cache:
            return null_value()
        source = candidate.read_text(encoding="utf-8")
        self.environment.module_cache[str(candidate)] = source
        program = self.parse(source, script=True)
        return self._execute_block(
            Block(span or program.span, program.statements), local, state, collect=collect
        )

    def _apply_directive(self, directive: Directive, state: _RunState) -> None:
        name = directive.name.lower()
        value = directive.value.strip().lower()
        try:
            if name == "precision":
                precision = int(value)
                if not 2 <= precision <= 10_000:
                    raise ValueError
                self.config.precision = precision
            elif name == "mode":
                if value not in {"exact", "approx"}:
                    raise ValueError
                self.config.mode = value
            elif name == "rounding":
                if value not in {"half_even", "half_up", "floor", "ceiling", "down", "up"}:
                    raise ValueError
                self.config.rounding = value
            elif name == "angle":
                if value not in {"radians", "degrees"}:
                    raise ValueError
                self.config.angle = value
            elif name == "seed":
                self.config.random_seed = int(value)
                self._rng.seed(self.config.random_seed)
            else:
                raise CalcError(
                    "SC1101",
                    f"未知设置项“{directive.name}”",
                    hint="可用设置：precision、mode、rounding、angle、seed。",
                    category="configuration",
                    span=directive.span,
                )
        except ValueError as exc:
            raise CalcError(
                "SC1102",
                f"设置值“{directive.value}”无效",
                hint="检查数值范围或允许的枚举值。",
                category="configuration",
                span=directive.span,
            ) from exc
        state.steps.append({"title": "设置", "detail": f"{name} = {value}"})

    def _eval_expr(self, expr: Expr, local: dict[str, Value], state: _RunState) -> Value:
        self._check_step(state)
        if isinstance(expr, NumberExpr):
            value, diagnostics = parse_number_literal(
                expr.raw,
                mode=self.config.mode,
                precision=self.config.precision,
                span=expr.span,
            )
            state.diagnostics.extend(diagnostics)
            return value
        if isinstance(expr, StringExpr):
            return string_value(expr.value)
        if isinstance(expr, NameExpr):
            return self._lookup_name(expr.name, local)
        if isinstance(expr, UnaryExpr):
            return unary_arithmetic(
                expr.op,
                self._eval_expr(expr.operand, local, state),
                precision=self.config.precision,
            )
        if isinstance(expr, BinaryExpr):
            left = self._eval_expr(expr.left, local, state)
            if expr.op in {"&&", "and"} and not self._truthy(left):
                return bool_value(False)
            if expr.op in {"||", "or"} and self._truthy(left):
                return bool_value(True)
            right = self._eval_expr(expr.right, local, state)
            if expr.op == "..":
                start = self._as_int(left, "范围起点")
                end = self._as_int(right, "范围终点")
                return Value("Range", (start, end), True, f"{start}..{end}", "")
            try:
                result = binary_arithmetic(expr.op, left, right, precision=self.config.precision)
            except CalcError as exc:
                if exc.span is None:
                    exc.span = expr.span
                raise
            self._collect_value_diagnostics(result, expr.span, state)
            return result
        if isinstance(expr, ConditionalExpr):
            condition = self._eval_expr(expr.condition, local, state)
            branch = expr.if_true if self._truthy(condition) else expr.if_false
            return self._eval_expr(branch, local, state)
        if isinstance(expr, EquationExpr):
            left = self._eval_expr(expr.left, local, state)
            right = self._eval_expr(expr.right, local, state)
            display = f"{left.display} = {right.display}"
            return Value(
                "Equation",
                (left, right),
                left.exact and right.exact,
                display,
                rf"{left.latex} = {right.latex}",
            )
        if isinstance(expr, ListExpr):
            items = [self._eval_expr(item, local, state) for item in expr.items]
            if items and all(item.type == "Vector" for item in items):
                return matrix_value([item.data for item in items])
            return vector_value(items)
        if isinstance(expr, CallExpr):
            return self._eval_call(expr, local, state)
        raise CalcError("SC9002", f"未知表达式类型 {type(expr).__name__}", category="internal")

    def _lookup_name(self, name: str, local: dict[str, Value]) -> Value:
        if name in local:
            return local[name]
        if name in self.environment.variables:
            return self.environment.variables[name]
        if name in UNITS:
            return unit_value(name)
        lowered = name.lower()
        if lowered in {"true", "false"}:
            return bool_value(lowered == "true")
        if lowered in {"pi", "π"}:
            return symbolic_value(sp.pi)
        if lowered in {"e", "euler"}:
            return symbolic_value(sp.E)
        if lowered in {"i", "j"}:
            return complex_exact_value(0, 1)
        if lowered in {"oo", "inf", "infinity"}:
            return symbolic_value(sp.oo)
        if lowered in {"nan"}:
            return approx_value(mp.nan, self.config.precision)
        assumptions = self.environment.assumptions.get(name, set())
        symbols_kwargs = {
            flag: True for flag in assumptions if flag in _ASSUMPTION_FLAGS and flag != "complex"
        }
        if "complex" in assumptions and "real" not in assumptions:
            symbols_kwargs["complex"] = True
        return (
            symbolic_value(sp.Symbol(name, **symbols_kwargs))
            if symbols_kwargs
            else symbolic_value(sp.Symbol(name))
        )

    def _eval_call(self, expr: CallExpr, local: dict[str, Value], state: _RunState) -> Value:
        if not isinstance(expr.callee, NameExpr):
            raise CalcError("SC2201", "只能调用具名函数", category="type", span=expr.callee.span)
        name = expr.callee.name
        if name in self.environment.functions:
            return self._call_user_function(name, expr.args, local, state, expr.span)
        handler = getattr(self, f"_builtin_{name}", None)
        if handler is None:
            raise CalcError(
                "SC2202",
                f"未知函数“{name}”",
                hint="检查拼写，或在变量/函数面板查看可用函数。",
                category="name",
                span=expr.callee.span,
            )
        return handler(expr.args, local, state, expr.span)

    def _arg_values(
        self, args: list[Expr], local: dict[str, Value], state: _RunState
    ) -> list[Value]:
        return [self._eval_expr(arg, local, state) for arg in args]

    def _call_user_function(
        self,
        name: str,
        args: list[Expr],
        local: dict[str, Value],
        state: _RunState,
        span: Span,
    ) -> Value:
        definition = self.environment.functions[name]
        if len(args) != len(definition.params):
            raise CalcError(
                "SC2203",
                f"{name} 需要 {len(definition.params)} 个参数，实际给了 {len(args)} 个",
                category="type",
                span=span,
            )
        values = self._arg_values(args, local, state)
        if state.recursion_depth >= self.config.max_recursion:
            raise CalcError(
                "SC6003",
                "递归深度超过限制",
                hint=f"当前上限为 {self.config.max_recursion}。",
                category="script",
                span=span,
            )
        child = dict(local)
        child.update(zip(definition.params, values, strict=True))
        state.recursion_depth += 1
        try:
            if definition.body is not None:
                return self._eval_expr(definition.body, child, state)
            if definition.block is not None:
                return self._execute_block(definition.block, child, state, collect=True)
        finally:
            state.recursion_depth -= 1
        return null_value()

    def _one(
        self, args: list[Expr], local: dict[str, Value], state: _RunState, span: Span, name: str
    ) -> Value:
        if len(args) != 1:
            raise CalcError("SC2204", f"{name} 需要 1 个参数", category="type", span=span)
        return self._eval_expr(args[0], local, state)

    def _two(
        self,
        args: list[Expr],
        local: dict[str, Value],
        state: _RunState,
        span: Span,
        name: str,
    ) -> tuple[Value, Value]:
        if len(args) != 2:
            raise CalcError("SC2205", f"{name} 需要 2 个参数", category="type", span=span)
        return self._eval_expr(args[0], local, state), self._eval_expr(args[1], local, state)

    def _collect_value_diagnostics(self, value: Value, span: Span, state: _RunState) -> None:
        overflow = value.meta.get("overflow")
        if overflow:
            state.diagnostics.append(
                warning(
                    "SC3002",
                    f"定宽整数溢出，结果已回绕为 {overflow['wrapped']}",
                    hint=f"原始值 {overflow['original']} 超出位宽 {overflow['width']} 的表示范围。",
                    span=span,
                    category="overflow",
                )
            )

    def _truthy(self, value: Value) -> bool:
        if value.type == "Bool":
            return bool(value.data)
        if value.type in NUMERIC_TYPES:
            if value.type == "Int":
                return int(value.data) != 0
            if value.type == "Rational":
                return Fraction(value.data) != 0
            if value.type == "ApproxReal":
                return mp.mpf(value.data) != 0
        raise CalcError(
            "SC2206",
            f"{value.type} 不能作为条件",
            hint="条件必须求值为布尔值。",
            category="type",
        )

    def _iter_values(self, value: Value) -> list[Value]:
        if value.type in {"Vector", "Set"}:
            return list(value.data)
        if value.type == "Range":
            start, end = value.data
            step = 1 if end >= start else -1
            return [int_value(i) for i in range(start, end + step, step)]
        raise CalcError(
            "SC2207",
            f"{value.type} 不能用于 for 循环",
            hint="循环对象应为范围、向量或集合。",
            category="type",
        )

    def _check_step(self, state: _RunState) -> None:
        state.steps_used += 1
        if state.steps_used > self.config.max_script_steps:
            raise CalcError(
                "SC6004",
                "脚本执行步数超过限制",
                hint=f"当前上限为 {self.config.max_script_steps}。",
                category="script",
            )
        if state.steps_used % 1024 == 0 and time.monotonic() - state.start_time > 30:
            raise CalcError(
                "SC6009",
                "脚本执行时间超过限制",
                hint="减少循环规模或提高脚本额度。",
                category="timeout",
            )

    # Constants and core numeric builtins
    def _builtin_approx(self, args, local, state, span):
        value = self._one(args, local, state, span, "approx")
        return self._numeric_approx(value, self.config.precision)

    def _builtin_n(self, args, local, state, span):
        if len(args) not in {1, 2}:
            raise CalcError("SC2204", "n 需要 1 或 2 个参数", category="type", span=span)
        value = self._eval_expr(args[0], local, state)
        digits = self.config.precision
        if len(args) == 2:
            digits_value = self._eval_expr(args[1], local, state)
            digits = int(self._as_int(digits_value, "n 的精度参数"))
            if not 2 <= digits <= 10_000:
                raise CalcError(
                    "SC2208", "精度必须在 2 到 10000 位之间", category="domain", span=span
                )
        return self._numeric_approx(value, digits)

    def _numeric_approx(self, value: Value, precision: int) -> Value:
        if value.type in {"Int", "Rational"}:
            with mp.workdps(precision):
                return approx_value(value_to_mpf(value, precision), precision)
        if value.type == "ApproxReal":
            return approx_value(mp.mpf(value.data), precision)
        if value.type == "Symbolic":
            evaluated = sp.N(value.data, precision)
            if evaluated.is_number:
                try:
                    complex_value = complex(evaluated)
                except (TypeError, ValueError):
                    return symbolic_value(evaluated)
                return approx_value(complex_value, precision)
            return symbolic_value(evaluated)
        if value.type in {"ComplexExact", "ApproxComplex"}:
            python_value = value_to_python(value)
            return approx_value(python_value, precision)
        raise CalcError("SC2209", f"{value.type} 不能转换为近似值", category="type")

    def _builtin_f64(self, args, local, state, span):
        value = self._one(args, local, state, span, "f64")
        try:
            return float64_value(float(value_to_python(value)))
        except (TypeError, ValueError, OverflowError) as exc:
            raise CalcError(
                "SC2210", "数值无法转换为 IEEE 754 binary64", category="type", span=span
            ) from exc

    def _builtin_ieee64(self, args, local, state, span):
        value = self._one(args, local, state, span, "ieee64")
        if value.type != "Float64":
            value = float64_value(float(value_to_python(value)))
        return Value(
            "Float64",
            value.data,
            False,
            bits_from_float(value).display,
            "",
            value.meta,
        )

    def _builtin_to(self, args, local, state, span):
        if len(args) != 2:
            raise CalcError("SC2205", "to 需要带单位的量和目标单位", category="type", span=span)
        value = self._eval_expr(args[0], local, state)
        target = self._eval_expr(args[1], local, state)
        from .numeric import convert_quantity

        return convert_quantity(value, target, precision=self.config.precision)

    _builtin_convert = _builtin_to

    def _builtin_bits(self, args, local, state, span):
        value = self._one(args, local, state, span, "bits")
        if value.type != "Float64":
            value = float64_value(float(value_to_python(value)))
        return bits_from_float(value)

    def _builtin_abs(self, args, local, state, span):
        value = self._one(args, local, state, span, "abs")
        if value.type in {"Int", "Rational", "ComplexExact", "FixedInt"}:
            if value.type == "ComplexExact":
                return symbolic_value(sp.Abs(value_to_sympy(value)))
            return make_positive_abs(value)
        if value.type == "ApproxReal":
            return approx_value(abs(mp.mpf(value.data)), self.config.precision)
        return symbolic_value(sp.Abs(value_to_sympy(value)))

    def _builtin_sign(self, args, local, state, span):
        value = self._one(args, local, state, span, "sign")
        if value.type == "Int":
            return int_value((int(value.data) > 0) - (int(value.data) < 0))
        if value.type == "Rational":
            fraction = Fraction(value.data)
            return int_value((fraction > 0) - (fraction < 0))
        return symbolic_value(sp.sign(value_to_sympy(value)))

    def _builtin_floor(self, args, local, state, span):
        value = self._one(args, local, state, span, "floor")
        if value.type == "Int":
            return value
        if value.type == "Rational":
            return int_value(math.floor(Fraction(value.data)))
        return symbolic_value(sp.floor(value_to_sympy(value)))

    def _builtin_ceil(self, args, local, state, span):
        value = self._one(args, local, state, span, "ceil")
        if value.type == "Int":
            return value
        if value.type == "Rational":
            return int_value(math.ceil(Fraction(value.data)))
        return symbolic_value(sp.ceiling(value_to_sympy(value)))

    def _builtin_round(self, args, local, state, span):
        if len(args) not in {1, 2}:
            raise CalcError("SC2204", "round 需要 1 或 2 个参数", category="type", span=span)
        value = self._eval_expr(args[0], local, state)
        digits = 0
        if len(args) == 2:
            digits = int(self._as_int(self._eval_expr(args[1], local, state), "round 位数"))
        if value.type == "Int" and digits >= 0:
            return value
        python_value = float(value_to_python(value))
        rounded = round(python_value, digits)
        return approx_value(mp.mpf(rounded), self.config.precision)

    def _builtin_factorial(self, args, local, state, span):
        value = self._one(args, local, state, span, "factorial")
        integer = self._as_int(value, "factorial 参数")
        if integer < 0:
            raise CalcError("SC2211", "阶乘参数不能为负", category="domain", span=span)
        if integer > 100_000:
            raise CalcError(
                "SC2212", "阶乘参数过大", hint="上限为 100000。", category="domain", span=span
            )
        return int_value(math.factorial(integer))

    def _builtin_gamma(self, args, local, state, span):
        value = self._one(args, local, state, span, "gamma")
        return symbolic_value(sp.gamma(value_to_sympy(value)))

    def _builtin_sqrt(self, args, local, state, span):
        return self._function_from_sympy(sp.sqrt, args, local, state, span, "sqrt")

    def _builtin_cbrt(self, args, local, state, span):
        value = self._one(args, local, state, span, "cbrt")
        return symbolic_value(sp.real_root(value_to_sympy(value), 3))

    def _window_angle(self, value: Value) -> Value:
        if self.config.angle != "degrees":
            return value
        return binary_arithmetic(
            "*",
            value,
            symbolic_value(sp.pi / 180),
            precision=self.config.precision,
        )

    def _trig(self, name: str, args, local, state, span):
        value = self._one(args, local, state, span, name)
        if value.type.startswith("Approx"):
            with mp.workdps(self.config.precision):
                numeric = value_to_mpf(value, self.config.precision)
                if self.config.angle == "degrees":
                    numeric = numeric * mp.pi / 180
                function = getattr(
                    mp,
                    {"ln": "log", "asin": "asin", "acos": "acos", "atan": "atan"}.get(name, name),
                )
                return approx_value(function(numeric), self.config.precision)
        value = self._window_angle(value)
        function = getattr(
            sp, {"ln": "log", "asin": "asin", "acos": "acos", "atan": "atan"}.get(name, name)
        )
        return symbolic_value(function(value_to_sympy(value)))

    def _builtin_sin(self, args, local, state, span):
        return self._trig("sin", args, local, state, span)

    def _builtin_cos(self, args, local, state, span):
        return self._trig("cos", args, local, state, span)

    def _builtin_tan(self, args, local, state, span):
        return self._trig("tan", args, local, state, span)

    def _builtin_ln(self, args, local, state, span):
        return self._trig("ln", args, local, state, span)

    def _builtin_exp(self, args, local, state, span):
        return self._trig("exp", args, local, state, span)

    def _builtin_asin(self, args, local, state, span):
        return self._trig("asin", args, local, state, span)

    def _builtin_acos(self, args, local, state, span):
        return self._trig("acos", args, local, state, span)

    def _builtin_atan(self, args, local, state, span):
        return self._trig("atan", args, local, state, span)

    def _builtin_log(self, args, local, state, span):
        if len(args) == 1:
            return self._trig("ln", args, local, state, span)
        if len(args) != 2:
            raise CalcError("SC2205", "log 需要 1 或 2 个参数", category="type", span=span)
        value, base = self._arg_values(args, local, state)
        expr = sp.log(value_to_sympy(value), value_to_sympy(base))
        return symbolic_value(expr)

    # CAS and numerical calculus
    def _builtin_simplify(self, args, local, state, span):
        return self._cas_unary(sp.simplify, args, local, state, span, "simplify")

    def _builtin_expand(self, args, local, state, span):
        return self._cas_unary(sp.expand, args, local, state, span, "expand")

    def _builtin_factor(self, args, local, state, span):
        return self._cas_unary(sp.factor, args, local, state, span, "factor")

    def _builtin_together(self, args, local, state, span):
        return self._cas_unary(sp.together, args, local, state, span, "together")

    def _builtin_apart(self, args, local, state, span):
        if len(args) < 2:
            raise CalcError("SC2205", "apart 需要表达式和变量", category="type", span=span)
        expr = value_to_sympy(self._eval_expr(args[0], local, state))
        variable = value_to_sympy(self._eval_expr(args[1], local, state))
        return symbolic_value(sp.apart(expr, variable))

    def _builtin_diff(self, args, local, state, span):
        if len(args) not in {2, 3}:
            raise CalcError("SC2205", "diff 需要表达式、变量，可选阶数", category="type", span=span)
        expr = value_to_sympy(self._eval_expr(args[0], local, state))
        variable = value_to_sympy(self._eval_expr(args[1], local, state))
        order = 1
        if len(args) == 3:
            order = int(self._as_int(self._eval_expr(args[2], local, state), "diff 阶数"))
        state.algorithm = "SymPy 符号微分"
        state.steps.append({"title": "求导", "detail": f"对 {variable} 求 {order} 阶导"})
        return symbolic_value(sp.diff(expr, variable, order))

    def _builtin_integrate(self, args, local, state, span):
        if len(args) == 2:
            expr = value_to_sympy(self._eval_expr(args[0], local, state))
            variable = value_to_sympy(self._eval_expr(args[1], local, state))
            state.algorithm = "SymPy 符号积分"
            return symbolic_value(sp.integrate(expr, variable))
        if len(args) == 4:
            expr = value_to_sympy(self._eval_expr(args[0], local, state))
            variable = value_to_sympy(self._eval_expr(args[1], local, state))
            lower = value_to_sympy(self._eval_expr(args[2], local, state))
            upper = value_to_sympy(self._eval_expr(args[3], local, state))
            result = sp.integrate(expr, (variable, lower, upper))
            if isinstance(result, sp.Integral):
                raise CalcError(
                    "SC4001",
                    "未能计算该定积分",
                    hint="尝试分段、替换变量，或使用数值积分 nintegrate。",
                    category="cas",
                    span=span,
                )
            return symbolic_value(result)
        raise CalcError(
            "SC2205", "integrate 需要表达式、变量和可选上下限", category="type", span=span
        )

    def _builtin_nintegrate(self, args, local, state, span):
        if len(args) != 4:
            raise CalcError(
                "SC2205", "nintegrate 需要表达式、变量、下限和上限", category="type", span=span
            )
        expr = self._eval_expr(args[0], local, state)
        variable_value = self._eval_expr(args[1], local, state)
        if variable_value.type != "Symbolic" or not isinstance(variable_value.data, sp.Symbol):
            raise CalcError(
                "SC2213", "nintegrate 的第二个参数必须是符号变量", category="type", span=span
            )
        lower = value_to_mpf(self._eval_expr(args[2], local, state), self.config.precision)
        upper = value_to_mpf(self._eval_expr(args[3], local, state), self.config.precision)
        free_symbols = expr.data.free_symbols if expr.type == "Symbolic" else {variable_value.data}
        if free_symbols - {variable_value.data}:
            raise CalcError("SC2214", "被积表达式含其他未绑定符号", category="type", span=span)

        def function(x_value):
            if expr.type == "Symbolic":
                return float(
                    sp.N(expr.data.subs(variable_value.data, x_value), self.config.precision)
                )
            return float(value_to_python(expr))

        with mp.workdps(self.config.precision):
            result = mp.quad(function, [lower, upper])
        state.algorithm = "mpmath 自适应数值积分"
        return approx_value(result, self.config.precision)

    def _builtin_findroot(self, args, local, state, span):
        if len(args) not in {2, 3}:
            raise CalcError(
                "SC2205", "findroot 需要表达式、变量和可选初值", category="type", span=span
            )
        expr = self._eval_expr(args[0], local, state)
        variable_value = self._eval_expr(args[1], local, state)
        if variable_value.type != "Symbolic" or not isinstance(variable_value.data, sp.Symbol):
            raise CalcError(
                "SC2213", "findroot 的第二个参数必须是符号变量", category="type", span=span
            )
        guess = 0.0
        if len(args) == 3:
            guess = float(value_to_python(self._eval_expr(args[2], local, state)))
        if expr.type != "Symbolic":
            raise CalcError("SC2215", "findroot 需要符号表达式", category="type", span=span)

        def function(x_value):
            return float(sp.N(expr.data.subs(variable_value.data, x_value), self.config.precision))

        try:
            root = mp.findroot(function, guess)
        except Exception as exc:
            raise CalcError(
                "SC4002",
                f"数值求根失败：{exc}",
                hint="更换初值，或先检查函数在该区间是否有根。",
                category="numeric",
                span=span,
            ) from exc
        state.algorithm = "mpmath findroot"
        return approx_value(root, self.config.precision)

    def _builtin_limit(self, args, local, state, span):
        if len(args) not in {3, 4}:
            raise CalcError(
                "SC2205", "limit 需要表达式、变量、趋近点和可选方向", category="type", span=span
            )
        expr = value_to_sympy(self._eval_expr(args[0], local, state))
        variable = value_to_sympy(self._eval_expr(args[1], local, state))
        point = value_to_sympy(self._eval_expr(args[2], local, state))
        direction = (
            "+"
            if len(args) == 3
            else {"+": "+", "-": "-", "both": "+-"}.get(
                str(self._eval_expr(args[3], local, state).data), "+-"
            )
        )
        result = sp.limit(expr, variable, point, dir=direction)
        return symbolic_value(result)

    def _builtin_series(self, args, local, state, span):
        if len(args) < 3 or len(args) > 4:
            raise CalcError(
                "SC2205", "series 需要表达式、变量、展开点和可选阶数", category="type", span=span
            )
        expr = value_to_sympy(self._eval_expr(args[0], local, state))
        variable = value_to_sympy(self._eval_expr(args[1], local, state))
        point = value_to_sympy(self._eval_expr(args[2], local, state))
        order = 6
        if len(args) == 4:
            order = int(self._as_int(self._eval_expr(args[3], local, state), "series 阶数"))
        return symbolic_value(sp.series(expr, variable, point, order).removeO())

    def _builtin_summation(self, args, local, state, span):
        if len(args) != 4:
            raise CalcError(
                "SC2205", "summation 需要表达式、变量、下限和上限", category="type", span=span
            )
        expr = value_to_sympy(self._eval_expr(args[0], local, state))
        variable = value_to_sympy(self._eval_expr(args[1], local, state))
        lower = value_to_sympy(self._eval_expr(args[2], local, state))
        upper = value_to_sympy(self._eval_expr(args[3], local, state))
        return symbolic_value(sp.summation(expr, (variable, lower, upper)))

    def _builtin_product(self, args, local, state, span):
        if len(args) != 4:
            raise CalcError(
                "SC2205", "product 需要表达式、变量、下限和上限", category="type", span=span
            )
        expr = value_to_sympy(self._eval_expr(args[0], local, state))
        variable = value_to_sympy(self._eval_expr(args[1], local, state))
        lower = value_to_sympy(self._eval_expr(args[2], local, state))
        upper = value_to_sympy(self._eval_expr(args[3], local, state))
        return symbolic_value(sp.product(expr, (variable, lower, upper)))

    def _builtin_solve(self, args, local, state, span):
        if len(args) not in {2, 3}:
            raise CalcError(
                "SC2205", "solve 需要方程、变量，可选定义域", category="type", span=span
            )
        equation = self._eval_expr(args[0], local, state)
        variable_value = self._eval_expr(args[1], local, state)
        if variable_value.type != "Symbolic" or not isinstance(variable_value.data, sp.Symbol):
            raise CalcError(
                "SC2216", "solve 的第二个参数必须是符号变量", category="type", span=span
            )
        if equation.type == "Equation":
            left, right = equation.data
            expr = value_to_sympy(left) - value_to_sympy(right)
        else:
            expr = value_to_sympy(equation)
        domain = sp.S.Complexes
        if len(args) == 3:
            domain_text = str(self._eval_expr(args[2], local, state).data)
            domains = {
                "real": sp.S.Reals,
                "complex": sp.S.Complexes,
                "integer": sp.S.Integers,
                "positive": sp.S.Reals & sp.Interval(0, sp.oo),
            }
            domain = domains.get(domain_text)
            if domain is None:
                raise CalcError(
                    "SC2217",
                    "未知求解域",
                    hint="可用 real、complex、integer、positive。",
                    category="type",
                    span=span,
                )
        try:
            solutions = sp.solve(expr, variable_value.data, dict=False)
            if isinstance(solutions, dict):
                solutions = [solutions.get(variable_value.data)]
            if not solutions:
                return set_value([])
            if domain is not sp.S.Complexes:
                filtered = []
                for solution in solutions:
                    try:
                        if domain.contains(solution):
                            filtered.append(solution)
                    except TypeError:
                        filtered.append(solution)
                solutions = filtered
            if not solutions:
                return set_value([])
            state.algorithm = "SymPy solve + 定义域过滤"
            state.steps.append(
                {
                    "title": "求解",
                    "detail": f"在 {domain_text if len(args) == 3 else '复数域'} 中求得 {len(solutions)} 个解",
                }
            )
            return set_value([symbolic_value(solution) for solution in solutions])
        except Exception as exc:
            raise CalcError(
                "SC4003",
                f"方程求解未完成：{exc}",
                hint="尝试 simplify 或对变量增加假设；不要假定未返回的解不存在。",
                category="cas",
                span=span,
            ) from exc

    def _builtin_assume(self, args, local, state, span):
        if len(args) < 2:
            raise CalcError("SC2205", "assume 需要变量和至少一个性质", category="type", span=span)
        name_value = self._eval_expr(args[0], local, state)
        if name_value.type != "Symbolic" or not isinstance(name_value.data, sp.Symbol):
            raise CalcError("SC2218", "assume 的第一个参数必须是变量名", category="type", span=span)
        flags: set[str] = set()
        for arg in args[1:]:
            value = self._eval_expr(arg, local, state)
            text = str(value.data).strip().lower()
            if text not in _ASSUMPTION_FLAGS:
                raise CalcError(
                    "SC2219",
                    f"未知假设“{text}”",
                    hint=f"可用：{', '.join(sorted(_ASSUMPTION_FLAGS))}。",
                    category="assumption",
                    span=arg.span,
                )
            flags.add(text)
        if "positive" in flags and "negative" in flags:
            raise CalcError(
                "SC2220", "假设互斥：positive 与 negative", category="assumption", span=span
            )
        if "real" in flags and "complex" in flags:
            flags.discard("complex")
        self.environment.assumptions[name_value.data.name] = flags
        self.environment.variables.pop(name_value.data.name, None)
        return bool_value(True)

    # Matrices
    def _builtin_matrix(self, args, local, state, span):
        if len(args) == 1:
            value = self._eval_expr(args[0], local, state)
            if value.type == "Matrix":
                return value
            if value.type == "Vector" and all(item.type == "Vector" for item in value.data):
                return matrix_value([item.data for item in value.data])
        values = self._arg_values(args, local, state)
        if all(value.type == "Vector" for value in values):
            return matrix_value([value.data for value in values])
        raise CalcError(
            "SC2221",
            "matrix 需要二维数组",
            hint="例如 matrix([1,2],[3,4])。",
            category="type",
            span=span,
        )

    def _builtin_identity(self, args, local, state, span):
        size = int(self._as_int(self._one(args, local, state, span, "identity"), "矩阵阶数"))
        if size < 1 or size > 500:
            raise CalcError("SC2222", "矩阵阶数必须在 1 到 500", category="domain", span=span)
        return matrix_value(
            [[int_value(1 if i == j else 0) for j in range(size)] for i in range(size)]
        )

    _builtin_eye = _builtin_identity

    def _matrix_sympy(self, value: Value) -> sp.Matrix:
        if value.type != "Matrix":
            raise CalcError("SC2223", "此处需要矩阵", category="type")
        return sp.Matrix([[value_to_sympy(cell) for cell in row] for row in value.data])

    def _builtin_det(self, args, local, state, span):
        matrix = self._matrix_sympy(self._one(args, local, state, span, "det"))
        if matrix.rows != matrix.cols:
            raise CalcError("SC2224", "行列式只对方阵定义", category="domain", span=span)
        return symbolic_value(matrix.det())

    def _builtin_inv(self, args, local, state, span):
        matrix = self._matrix_sympy(self._one(args, local, state, span, "inv"))
        if matrix.rows != matrix.cols:
            raise CalcError("SC2224", "逆矩阵只对方阵定义", category="domain", span=span)
        if sp.simplify(matrix.det()) == 0:
            raise CalcError(
                "SC2006",
                "矩阵奇异，逆矩阵不存在",
                hint=f"det = {matrix.det()}。",
                category="singular",
                span=span,
            )
        return self._matrix_from_sympy(matrix.inv())

    def _builtin_rank(self, args, local, state, span):
        return int_value(self._matrix_sympy(self._one(args, local, state, span, "rank")).rank())

    def _builtin_transpose(self, args, local, state, span):
        return self._matrix_from_sympy(
            self._matrix_sympy(self._one(args, local, state, span, "transpose")).T
        )

    def _builtin_eigenvalues(self, args, local, state, span):
        matrix = self._matrix_sympy(self._one(args, local, state, span, "eigenvalues"))
        if matrix.rows != matrix.cols:
            raise CalcError("SC2224", "特征值只对方阵定义", category="domain", span=span)
        values = matrix.eigenvals()
        result: list[Value] = []
        for eigenvalue, multiplicity in values.items():
            result.extend([symbolic_value(eigenvalue)] * int(multiplicity))
        state.algorithm = "SymPy 特征多项式与根"
        return vector_value(result)

    def _builtin_eigenvectors(self, args, local, state, span):
        matrix = self._matrix_sympy(self._one(args, local, state, span, "eigenvectors"))
        if matrix.rows != matrix.cols:
            raise CalcError("SC2224", "特征向量只对方阵定义", category="domain", span=span)
        entries = []
        for eigenvalue, _multiplicity, vectors in matrix.eigenvects():
            for vector in vectors:
                entries.append(
                    vector_value(
                        [
                            string_value(f"λ={eigenvalue}"),
                            vector_value([symbolic_value(component) for component in vector]),
                        ]
                    )
                )
        return vector_value(entries)

    def _builtin_lu(self, args, local, state, span):
        lower, upper, permutation = self._matrix_sympy(
            self._one(args, local, state, span, "lu")
        ).LUdecomposition()
        return vector_value(
            [
                self._matrix_from_sympy(lower),
                self._matrix_from_sympy(upper),
                self._matrix_from_sympy(permutation),
            ]
        )

    def _builtin_qr(self, args, local, state, span):
        q, r = self._matrix_sympy(self._one(args, local, state, span, "qr")).QRdecomposition()
        return vector_value([self._matrix_from_sympy(q), self._matrix_from_sympy(r)])

    def _matrix_from_sympy(self, matrix: sp.MatrixBase) -> Value:
        return matrix_value(
            [
                [symbolic_value(matrix[row, col]) for col in range(matrix.cols)]
                for row in range(matrix.rows)
            ]
        )

    # Programmer tools
    def _builtin_fixed(self, args, local, state, span):
        if len(args) != 3:
            raise CalcError("SC2205", "fixed 需要值、位宽和符号标志", category="type", span=span)
        value = self._as_int(self._eval_expr(args[0], local, state), "fixed 值")
        width = int(self._as_int(self._eval_expr(args[1], local, state), "位宽"))
        signed_value = self._eval_expr(args[2], local, state)
        signed = bool(signed_value.data)
        if width not in {8, 16, 32, 64}:
            raise CalcError(
                "SC2225", "定宽整数位宽必须是 8、16、32 或 64", category="domain", span=span
            )
        return make_fixed(value, width, signed, original=value)

    def _make_fixed_builtin(self, width: int, signed: bool):
        def function(args, local, state, span):
            value = self._as_int(
                self._one(args, local, state, span, f"{'i' if signed else 'u'}{width}"), "定宽整数"
            )
            return make_fixed(value, width, signed, original=value)

        return function

    def __getattr__(self, name: str):
        match = re.fullmatch(r"_builtin_([iu])(8|16|32|64)", name)
        if match:
            return self._make_fixed_builtin(int(match.group(2)), match.group(1) == "i")
        raise AttributeError(name)

    def _builtin_bitand(self, args, local, state, span):
        left, right = self._two(args, local, state, span, "bitand")
        return binary_arithmetic("&", left, right, precision=self.config.precision)

    def _builtin_bitor(self, args, local, state, span):
        left, right = self._two(args, local, state, span, "bitor")
        return binary_arithmetic("|", left, right, precision=self.config.precision)

    def _builtin_bitxor(self, args, local, state, span):
        left, right = self._two(args, local, state, span, "bitxor")
        return binary_arithmetic("xor", left, right, precision=self.config.precision)

    def _builtin_bitnot(self, args, local, state, span):
        return unary_arithmetic(
            "~", self._one(args, local, state, span, "bitnot"), precision=self.config.precision
        )

    def _builtin_shl(self, args, local, state, span):
        left, right = self._two(args, local, state, span, "shl")
        return binary_arithmetic("<<", left, right, precision=self.config.precision)

    def _builtin_shr(self, args, local, state, span):
        left, right = self._two(args, local, state, span, "shr")
        return binary_arithmetic(">>", left, right, precision=self.config.precision)

    def _bitop(self, op: str, args, local, state, span, name: str):
        left, right = self._two(args, local, state, span, name)
        if left.type == "FixedInt":
            width = int(left.meta["width"])
            signed = bool(left.meta["signed"])
            raw = int(left.data) % (1 << width)
            shift = self._as_int(right, name) % width
            if op == "rotl":
                value = ((raw << shift) | (raw >> (width - shift))) & ((1 << width) - 1)
            elif op == "rotr":
                value = ((raw >> shift) | (raw << (width - shift))) & ((1 << width) - 1)
            else:
                raise CalcError("SC2226", f"未知位运算 {op}", category="internal")
            return make_fixed(value, width, signed)
        if right.type == "FixedInt":
            raise CalcError(
                "SC2226", "循环移位要求第一个参数是定宽整数", category="type", span=span
            )
        a = self._as_int(left, name)
        b = self._as_int(right, name)
        if op == "rotl":
            width = max(1, a.bit_length())
            shift = b % width
            mask = (1 << width) - 1
            value = ((a << shift) | (a >> (width - shift))) & mask
            return int_value(value, format(value, f"0{width}b"))
        if op == "rotr":
            width = max(1, a.bit_length())
            shift = b % width
            mask = (1 << width) - 1
            value = ((a >> shift) | (a << (width - shift))) & mask
            return int_value(value, format(value, f"0{width}b"))
        if op == "popcount":
            return int_value((a & mask_for(b)).bit_count())
        raise CalcError("SC2226", f"未知位运算 {op}", category="internal")

    def _builtin_rotl(self, args, local, state, span):
        return self._bitop("rotl", args, local, state, span, "rotl")

    def _builtin_rotr(self, args, local, state, span):
        return self._bitop("rotr", args, local, state, span, "rotr")

    def _builtin_popcount(self, args, local, state, span):
        value = self._one(args, local, state, span, "popcount")
        if value.type == "FixedInt":
            width = int(value.meta["width"])
            return int_value((int(value.data) % (1 << width)).bit_count())
        return int_value(abs(self._as_int(value, "popcount")).bit_count())

    def _builtin_base(self, args, local, state, span):
        if len(args) != 2:
            raise CalcError("SC2205", "base 需要整数和进制", category="type", span=span)
        value = self._as_int(self._eval_expr(args[0], local, state), "base 值")
        radix = int(self._as_int(self._eval_expr(args[1], local, state), "进制"))
        if not 2 <= radix <= 36:
            raise CalcError("SC2227", "进制必须在 2 到 36 之间", category="domain", span=span)
        digits = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        sign = "-" if value < 0 else ""
        number = abs(value)
        if number == 0:
            text = "0"
        else:
            parts = []
            while number:
                number, remainder = divmod(number, radix)
                parts.append(digits[remainder])
            text = "".join(reversed(parts))
        return string_value(sign + text)

    def _builtin_gcd(self, args, local, state, span):
        values = [self._as_int(v, "gcd") for v in self._arg_values(args, local, state)]
        if not values:
            raise CalcError("SC2205", "gcd 至少需要 1 个参数", category="type", span=span)
        result = 0
        for value in values:
            result = math.gcd(result, value)
        return int_value(result)

    def _builtin_lcm(self, args, local, state, span):
        values = [self._as_int(v, "lcm") for v in self._arg_values(args, local, state)]
        if not values:
            raise CalcError("SC2205", "lcm 至少需要 1 个参数", category="type", span=span)
        result = 1
        for value in values:
            result = math.lcm(result, value)
        return int_value(result)

    def _builtin_isprime(self, args, local, state, span):
        value = self._as_int(self._one(args, local, state, span, "isprime"), "isprime")
        return bool_value(sp.isprime(value))

    def _builtin_nextprime(self, args, local, state, span):
        value = self._as_int(self._one(args, local, state, span, "nextprime"), "nextprime")
        return int_value(int(sp.nextprime(value)))

    def _builtin_modpow(self, args, local, state, span):
        if len(args) != 3:
            raise CalcError("SC2205", "modpow 需要底数、指数和模数", category="type", span=span)
        base, exponent, modulus = [
            self._as_int(v, "modpow") for v in self._arg_values(args, local, state)
        ]
        if modulus == 0:
            raise CalcError("SC2228", "模数不能为零", category="domain", span=span)
        return int_value(pow(base, exponent, modulus))

    def _builtin_comb(self, args, local, state, span):
        n, k = [self._as_int(v, "comb") for v in self._arg_values(args, local, state)]
        if n < 0 or k < 0 or k > n:
            raise CalcError(
                "SC2229", "组合数参数必须满足 0 <= k <= n", category="domain", span=span
            )
        return int_value(math.comb(n, k))

    _builtin_binom = _builtin_comb

    def _builtin_hex(self, args, local, state, span):
        return self._base_from_value(args, local, state, span, 16)

    def _builtin_bin(self, args, local, state, span):
        return self._base_from_value(args, local, state, span, 2)

    def _builtin_oct(self, args, local, state, span):
        return self._base_from_value(args, local, state, span, 8)

    def _base_from_value(self, args, local, state, span, radix):
        value = self._as_int(self._one(args, local, state, span, "base"), "base")
        if radix == 16:
            return string_value(("-" if value < 0 else "") + "0x" + format(abs(value), "X"))
        if radix == 2:
            return string_value(("-" if value < 0 else "") + "0b" + format(abs(value), "b"))
        return string_value(("-" if value < 0 else "") + "0o" + format(abs(value), "o"))

    # Encodings, hashes, structured data
    def _builtin_b64encode(self, args, local, state, span):
        text = self._as_string(self._one(args, local, state, span, "b64encode"))
        return string_value(base64.b64encode(text.encode()).decode())

    def _builtin_b64decode(self, args, local, state, span):
        text = self._as_string(self._one(args, local, state, span, "b64decode"))
        try:
            return string_value(base64.b64decode(text, validate=True).decode("utf-8"))
        except Exception as exc:
            raise CalcError("SC2230", "Base64 解码失败", category="encoding", span=span) from exc

    def _builtin_urlencode(self, args, local, state, span):
        return string_value(
            urllib.parse.quote(self._as_string(self._one(args, local, state, span, "urlencode")))
        )

    def _builtin_urldecode(self, args, local, state, span):
        return string_value(
            urllib.parse.unquote(self._as_string(self._one(args, local, state, span, "urldecode")))
        )

    def _builtin_hexencode(self, args, local, state, span):
        text = self._as_string(self._one(args, local, state, span, "hexencode"))
        return string_value(text.encode().hex())

    def _builtin_hexdecode(self, args, local, state, span):
        text = self._as_string(self._one(args, local, state, span, "hexdecode"))
        try:
            return string_value(bytes.fromhex(text).decode("utf-8"))
        except Exception as exc:
            raise CalcError("SC2231", "Hex 解码失败", category="encoding", span=span) from exc

    def _hash_builtin(self, algorithm: str):
        def function(args, local, state, span):
            text = self._as_string(self._one(args, local, state, span, algorithm))
            return string_value(hashlib.new(algorithm, text.encode()).hexdigest())

        return function

    def _builtin_md5(self, args, local, state, span):
        return self._hash_builtin("md5")(args, local, state, span)

    def _builtin_sha1(self, args, local, state, span):
        return self._hash_builtin("sha1")(args, local, state, span)

    def _builtin_sha256(self, args, local, state, span):
        return self._hash_builtin("sha256")(args, local, state, span)

    def _builtin_sha512(self, args, local, state, span):
        return self._hash_builtin("sha512")(args, local, state, span)

    def _builtin_json_parse(self, args, local, state, span):
        text = self._as_string(self._one(args, local, state, span, "json_parse"))
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CalcError(
                "SC2232",
                f"JSON 解析失败：{exc.msg}",
                hint=f"第 {exc.lineno} 行第 {exc.colno} 列。",
                category="data",
                span=span,
            ) from exc
        return value_from_python(value, self.config.precision)

    def _builtin_json_stringify(self, args, local, state, span):
        value = self._one(args, local, state, span, "json_stringify")
        return string_value(json.dumps(value_to_python(value), ensure_ascii=False, default=str))

    def _builtin_csv_parse(self, args, local, state, span):
        text = self._as_string(self._one(args, local, state, span, "csv_parse"))
        rows = list(csv.reader(io.StringIO(text)))
        return Value(
            "Table",
            rows,
            True,
            f"{len(rows)} 行 CSV",
            "",
            {"rows": rows, "columns": len(rows[0]) if rows else 0},
        )

    def _builtin_regex_test(self, args, local, state, span):
        if len(args) != 2:
            raise CalcError("SC2205", "regex_test 需要模式和文本", category="type", span=span)
        pattern = self._as_string(self._eval_expr(args[0], local, state))
        text = self._as_string(self._eval_expr(args[1], local, state))
        try:
            return bool_value(re.search(pattern, text) is not None)
        except re.error as exc:
            raise CalcError("SC2233", f"正则表达式无效：{exc}", category="data", span=span) from exc

    def _builtin_timestamp(self, args, local, state, span):
        if not args:
            return Value("String", str(int(time.time())), True, str(int(time.time())), "")
        text = self._as_string(self._eval_expr(args[0], local, state))
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return int_value(int(parsed.timestamp()))
        except ValueError as exc:
            raise CalcError(
                "SC2234",
                "日期时间格式无效",
                hint="使用 ISO 8601，例如 2026-10-20T12:00:00Z。",
                category="data",
                span=span,
            ) from exc

    def _builtin_datetime(self, args, local, state, span):
        value = self._as_int(self._one(args, local, state, span, "datetime"), "时间戳")
        return string_value(datetime.fromtimestamp(value, tz=UTC).isoformat())

    def _builtin_truth_table(self, args, local, state, span):
        if not args:
            raise CalcError(
                "SC2205", "truth_table 需要布尔表达式字符串", category="type", span=span
            )
        if len(args) == 1:
            expression_source = self._as_string(self._eval_expr(args[0], local, state))
            from .ast import walk_expr

            program = self.parse(expression_source)
            if len(program.statements) != 1 or not isinstance(program.statements[0], ExprStatement):
                raise CalcError(
                    "SC2239", "truth_table 需要单个布尔表达式", category="type", span=span
                )
            expression = program.statements[0].expr
            reserved = {"true", "false", "and", "or", "not", "xor"}
            callees = {
                node.callee.name
                for node in walk_expr(expression)
                if isinstance(node, CallExpr) and isinstance(node.callee, NameExpr)
            }
            names = sorted(
                {
                    node.name
                    for node in walk_expr(expression)
                    if isinstance(node, NameExpr)
                    and node.name not in reserved | callees
                    and not node.name.startswith("_")
                }
            )
            rows: list[list[str]] = []
            for mask in range(1 << len(names)):
                assignment = {
                    name: bool_value(bool((mask >> (len(names) - 1 - index)) & 1))
                    for index, name in enumerate(names)
                }
                value = self._eval_expr(expression, assignment, state)
                rows.append(
                    [str(int(bool(assignment[name].data))) for name in names]
                    + [str(int(self._truthy(value)))]
                )
            return Value(
                "Table",
                rows,
                True,
                f"{len(rows)} 行真值表",
                "",
                {"columns": [*names, "result"], "rows": rows, "expression": expression_source},
            )
        names = [self._as_string(self._eval_expr(arg, local, state)) for arg in args]
        rows = []
        for mask in range(1 << len(names)):
            bits = [(mask >> i) & 1 for i in range(len(names))]
            rows.append([str(bit) for bit in bits])
        return Value(
            "Table", rows, True, f"{len(rows)} 行真值表", "", {"columns": names, "rows": rows}
        )

    def _builtin_ast(self, args, local, state, span):
        if not args:
            raise CalcError("SC2205", "ast 需要表达式", category="type", span=span)
        text = expr_to_source(args[0])
        return string_value(text)

    def _builtin_len(self, args, local, state, span):
        value = self._one(args, local, state, span, "len")
        if value.type in {"Vector", "Set"}:
            return int_value(len(value.data))
        if value.type == "Matrix":
            return int_value(len(value.data) * len(value.data[0]))
        if value.type == "String":
            return int_value(len(value.data))
        raise CalcError("SC2235", f"{value.type} 没有长度", category="type", span=span)

    def _builtin_set(self, args, local, state, span):
        values = self._arg_values(args, local, state)
        if len(values) == 1 and values[0].type == "Vector":
            return set_value(list(values[0].data))
        return set_value(values)

    def _builtin_range(self, args, local, state, span):
        values = [self._as_int(v, "range") for v in self._arg_values(args, local, state)]
        if len(values) == 1:
            start, end, step = 0, values[0], 1
        elif len(values) == 2:
            start, end = values
            step = 1
        elif len(values) == 3:
            start, end, step = values
        else:
            raise CalcError("SC2205", "range 需要 1 到 3 个参数", category="type", span=span)
        if step == 0:
            raise CalcError("SC2228", "range 步长不能为零", category="domain", span=span)
        return Value("Range", (start, end), True, f"{start}..{end}", "")

    def _builtin_random(self, args, local, state, span):
        return approx_value(mp.mpf(self._rng.random()), self.config.precision)

    def _builtin_ast_dump(self, args, local, state, span):
        if not args:
            raise CalcError("SC2205", "ast_dump 需要表达式", category="type", span=span)
        return string_value(repr(args[0]))

    def _builtin_version(self, args, local, state, span):
        return string_value("SuperCalc 0.1.0 / API 1")

    def _cas_unary(self, function, args, local, state, span, name: str) -> Value:
        value = self._one(args, local, state, span, name)
        state.algorithm = f"SymPy {name}"
        try:
            return symbolic_value(function(value_to_sympy(value)))
        except Exception as exc:
            raise CalcError(
                "SC4004",
                f"{name} 未完成：{exc}",
                hint="检查表达式类型和变量假设。",
                category="cas",
                span=span,
            ) from exc

    def _function_from_sympy(self, function, args, local, state, span, name: str) -> Value:
        value = self._one(args, local, state, span, name)
        if value.type.startswith("Approx"):
            with mp.workdps(self.config.precision):
                functions = {
                    "sqrt": mp.sqrt,
                    "exp": mp.exp,
                    "sin": mp.sin,
                    "cos": mp.cos,
                    "tan": mp.tan,
                }
                return approx_value(
                    functions[name](value_to_mpf(value, self.config.precision)),
                    self.config.precision,
                )
        return symbolic_value(function(value_to_sympy(value)))

    def _as_int(self, value: Value, context: str) -> int:
        if value.type == "Int":
            return int(value.data)
        if value.type == "Rational" and Fraction(value.data).denominator == 1:
            return Fraction(value.data).numerator
        if value.type == "FixedInt":
            return int(value.data)
        if value.type == "Bool":
            return int(bool(value.data))
        raise CalcError(
            "SC2236",
            f"{context} 需要整数，实际是 {value.type}",
            hint="使用 i64(...) 或整数表达式。",
            category="type",
        )

    def _as_string(self, value: Value) -> str:
        if value.type == "String":
            return str(value.data)
        raise CalcError("SC2237", "此处需要字符串", category="type")


@dataclass
class _ReturnSignal(Exception):
    value: Value


def make_positive_abs(value: Value) -> Value:
    if value.type == "Int":
        return int_value(abs(int(value.data)))
    if value.type == "Rational":
        return rational_value(abs(Fraction(value.data)))
    if value.type == "FixedInt":
        return make_fixed(
            abs(int(value.data)), int(value.meta["width"]), bool(value.meta["signed"])
        )
    raise CalcError("SC2238", "无法取绝对值", category="type")


def mask_for(bits: int) -> int:
    return (1 << bits) - 1
