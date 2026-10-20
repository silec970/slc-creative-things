from __future__ import annotations

from dataclasses import dataclass, field

from .diagnostics import Span


@dataclass
class Node:
    span: Span


@dataclass
class Expr(Node):
    pass


@dataclass
class NumberExpr(Expr):
    raw: str


@dataclass
class StringExpr(Expr):
    value: str


@dataclass
class NameExpr(Expr):
    name: str


@dataclass
class UnaryExpr(Expr):
    op: str
    operand: Expr


@dataclass
class BinaryExpr(Expr):
    op: str
    left: Expr
    right: Expr


@dataclass
class CallExpr(Expr):
    callee: Expr
    args: list[Expr]


@dataclass
class ListExpr(Expr):
    items: list[Expr]


@dataclass
class EquationExpr(Expr):
    left: Expr
    right: Expr


@dataclass
class ConditionalExpr(Expr):
    condition: Expr
    if_true: Expr
    if_false: Expr


@dataclass
class Statement(Node):
    pass


@dataclass
class ExprStatement(Statement):
    expr: Expr


@dataclass
class Assignment(Statement):
    name: str
    expr: Expr


@dataclass
class FunctionDef(Statement):
    name: str
    params: list[str]
    body: Expr | None = None
    block: Block | None = None


@dataclass
class Directive(Statement):
    name: str
    value: str


@dataclass
class IfStatement(Statement):
    condition: Expr
    then_block: Block
    else_block: Block | None = None


@dataclass
class WhileStatement(Statement):
    condition: Expr
    block: Block


@dataclass
class ForStatement(Statement):
    name: str
    iterable: Expr
    block: Block


@dataclass
class AssertStatement(Statement):
    condition: Expr
    message: str = ""


@dataclass
class ReturnStatement(Statement):
    expr: Expr


@dataclass
class ModuleUse(Statement):
    path: str


@dataclass
class Block(Node):
    statements: list[Statement] = field(default_factory=list)


@dataclass
class Program(Node):
    source: str
    statements: list[Statement] = field(default_factory=list)
    script: bool = False


def walk_expr(expr: Expr) -> list[Expr]:
    found: list[Expr] = [expr]
    if isinstance(expr, UnaryExpr):
        found.extend(walk_expr(expr.operand))
    elif isinstance(expr, BinaryExpr):
        found.extend(walk_expr(expr.left))
        found.extend(walk_expr(expr.right))
    elif isinstance(expr, CallExpr):
        found.extend(walk_expr(expr.callee))
        for arg in expr.args:
            found.extend(walk_expr(arg))
    elif isinstance(expr, ListExpr):
        for item in expr.items:
            found.extend(walk_expr(item))
    elif isinstance(expr, EquationExpr):
        found.extend(walk_expr(expr.left))
        found.extend(walk_expr(expr.right))
    elif isinstance(expr, ConditionalExpr):
        found.extend(walk_expr(expr.condition))
        found.extend(walk_expr(expr.if_true))
        found.extend(walk_expr(expr.if_false))
    return found


def expr_to_source(expr: Expr) -> str:
    if isinstance(expr, NumberExpr):
        return expr.raw
    if isinstance(expr, StringExpr):
        escaped = expr.value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(expr, NameExpr):
        return expr.name
    if isinstance(expr, UnaryExpr):
        space = " " if expr.op.isalpha() else ""
        return f"{expr.op}{space}{expr_to_source(expr.operand)}"
    if isinstance(expr, BinaryExpr):
        return f"{expr_to_source(expr.left)} {expr.op} {expr_to_source(expr.right)}"
    if isinstance(expr, CallExpr):
        args = ", ".join(expr_to_source(a) for a in expr.args)
        return f"{expr_to_source(expr.callee)}({args})"
    if isinstance(expr, ListExpr):
        return "[" + ", ".join(expr_to_source(x) for x in expr.items) + "]"
    if isinstance(expr, EquationExpr):
        return f"{expr_to_source(expr.left)} = {expr_to_source(expr.right)}"
    if isinstance(expr, ConditionalExpr):
        return (
            f"{expr_to_source(expr.condition)} ? {expr_to_source(expr.if_true)}"
            f" : {expr_to_source(expr.if_false)}"
        )
    return "?"


def format_ast_tree(expr: Expr, depth: int = 0) -> str:
    prefix = "  " * depth
    if isinstance(expr, NumberExpr):
        line = f"{prefix}Number({expr.raw})"
    elif isinstance(expr, StringExpr):
        line = f"{prefix}String({expr.value!r})"
    elif isinstance(expr, NameExpr):
        line = f"{prefix}Name({expr.name})"
    elif isinstance(expr, UnaryExpr):
        line = f"{prefix}Unary({expr.op})"
    elif isinstance(expr, BinaryExpr):
        line = f"{prefix}Binary({expr.op})"
    elif isinstance(expr, CallExpr):
        line = f"{prefix}Call({expr_to_source(expr.callee)})"
    elif isinstance(expr, ListExpr):
        line = f"{prefix}List({len(expr.items)} items)"
    elif isinstance(expr, EquationExpr):
        line = f"{prefix}Equation"
    elif isinstance(expr, ConditionalExpr):
        line = f"{prefix}Conditional"
    else:
        line = f"{prefix}{type(expr).__name__}"
    children: list[Expr] = []
    if isinstance(expr, UnaryExpr):
        children = [expr.operand]
    elif isinstance(expr, BinaryExpr):
        children = [expr.left, expr.right]
    elif isinstance(expr, CallExpr):
        children = [expr.callee, *expr.args]
    elif isinstance(expr, ListExpr):
        children = expr.items
    elif isinstance(expr, EquationExpr):
        children = [expr.left, expr.right]
    elif isinstance(expr, ConditionalExpr):
        children = [expr.condition, expr.if_true, expr.if_false]
    lines = [f"{line}  [{expr.span.start}:{expr.span.end}]"]
    for child in children:
        lines.append(format_ast_tree(child, depth + 1))
    return "\n".join(lines)
