from __future__ import annotations

import re

from .ast import (
    BinaryExpr,
    CallExpr,
    ConditionalExpr,
    EquationExpr,
    Expr,
    ListExpr,
    NameExpr,
    NumberExpr,
    StringExpr,
    UnaryExpr,
)
from .diagnostics import CalcError


def _read_group(text: str, start: int) -> tuple[str, int]:
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text) or text[start] != "{":
        if start < len(text):
            return text[start], start + 1
        raise CalcError("SC5001", "LaTeX 命令缺少参数", category="latex")
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : index], index + 1
    raise CalcError("SC5002", "LaTeX 花括号不匹配", category="latex")


def from_latex(text: str) -> str:
    """Translate a documented, safe LaTeX subset into SuperCalc syntax."""

    value = text.strip()
    value = re.sub(r"^\s*(\$\$?|\\\[|\\\()", "", value)
    value = re.sub(r"(\$\$?|\\\]|\\\))\s*$", "", value)
    value = value.replace("\\left", "").replace("\\right", "")
    value = value.replace("\\,", " ").replace("\\;", " ").replace("\\!", "")
    value = value.replace("\\cdot", "*").replace("\\times", "*").replace("\\div", "/")
    value = value.replace("\\pi", "pi").replace("\\infty", "oo")
    value = value.replace("\\le", "<=").replace("\\leq", "<=")
    value = value.replace("\\ge", ">=").replace("\\geq", ">=")
    value = value.replace("\\ne", "!=").replace("\\neq", "!=")
    value = value.replace("\\alpha", "alpha").replace("\\beta", "beta")
    value = value.replace("\\gamma", "gamma").replace("\\theta", "theta")

    matrix_pattern = re.compile(r"\\begin\{([pbvBV]?matrix)\}(.*?)\\end\{\1\}", re.S)

    def matrix_replace(match: re.Match[str]) -> str:
        body = match.group(2).strip()
        rows = re.split(r"\\\\", body)
        parsed_rows = []
        for row in rows:
            cells = [cell.strip() for cell in row.split("&")]
            parsed_rows.append("[" + ", ".join(cells) + "]")
        return "[" + ", ".join(parsed_rows) + "]"

    value = matrix_pattern.sub(matrix_replace, value)

    # Expand simple commands from the inside out. The loop also handles nested
    # fractions and roots because each replacement preserves balanced groups.
    for _ in range(128):
        changed = False
        for command in ("frac", "dfrac", "tfrac"):
            marker = f"\\{command}"
            index = value.find(marker)
            if index >= 0:
                numerator, after_numerator = _read_group(value, index + len(marker))
                denominator, after_denominator = _read_group(value, after_numerator)
                value = (
                    value[:index] + f"(({numerator})/({denominator}))" + value[after_denominator:]
                )
                changed = True
                break
        if changed:
            continue
        index = value.find("\\sqrt")
        if index >= 0:
            cursor = index + len("\\sqrt")
            root_index = None
            if cursor < len(value) and value[cursor] == "[":
                close = value.find("]", cursor)
                if close < 0:
                    raise CalcError("SC5003", "LaTeX 根指数缺少右括号", category="latex")
                root_index = value[cursor + 1 : close]
                cursor = close + 1
            radicand, after = _read_group(value, cursor)
            replacement = (
                f"sqrt({radicand})" if root_index is None else f"(({radicand})^(1/({root_index})))"
            )
            value = value[:index] + replacement + value[after:]
            continue
        text_match = re.search(r"\\text\{([^{}]*)\}", value)
        if text_match:
            value = (
                value[: text_match.start()]
                + '"'
                + text_match.group(1).replace('"', '\\"')
                + '"'
                + value[text_match.end() :]
            )
            continue
        break

    function_map = {
        r"\sin": "sin",
        r"\cos": "cos",
        r"\tan": "tan",
        r"\ln": "ln",
        r"\log": "log",
        r"\exp": "exp",
        r"\max": "max",
        r"\min": "min",
    }
    for latex_name, plain_name in function_map.items():
        value = value.replace(latex_name, plain_name)
    value = re.sub(r"\\(operatorname|mathrm)\{([^{}]+)\}", r"\2", value)
    value = re.sub(r"\\([A-Za-z]+)", r"\1", value)
    value = value.replace("\\{", '"{"').replace("\\}", '"}"')
    value = value.replace("\\%", "%").replace("\\_", "_")

    # Convert remaining grouping braces to parentheses, while preserving the
    # braces that belong to a matrix literal.
    def brace_convert(match: re.Match[str]) -> str:
        content = match.group(1)
        return content if content in {"true", "false"} else f"({content})"

    for _ in range(16):
        new_value = re.sub(r"\{([^{}]*)\}", brace_convert, value)
        if new_value == value:
            break
        value = new_value

    value = re.sub(r"\^\{([^{}]*)\}", r"^(\1)", value)
    value = re.sub(r"_\{([^{}]*)\}", r"_\1", value)
    value = value.replace("−", "-").replace("×", "*").replace("÷", "/")
    return value.strip()


def expr_to_latex(expr: Expr) -> str:
    if isinstance(expr, NumberExpr):
        return expr.raw.replace("_", "")
    if isinstance(expr, StringExpr):
        safe = expr.value.replace("\\", r"\backslash ").replace("_", r"\_")
        return rf"\text{{{safe}}}"
    if isinstance(expr, NameExpr):
        return {
            "pi": r"\pi",
            "e": "e",
            "i": "i",
            "oo": r"\infty",
        }.get(expr.name, expr.name.replace("_", r"\_"))
    if isinstance(expr, UnaryExpr):
        return f"{expr.op}{expr_to_latex(expr.operand)}"
    if isinstance(expr, BinaryExpr):
        left = expr_to_latex(expr.left)
        right = expr_to_latex(expr.right)
        if expr.op == "/":
            return rf"\frac{{{left}}}{{{right}}}"
        if expr.op == "^":
            return f"{{{left}}}^{{{right}}}"
        operator = {
            "*": r"\cdot ",
            "<=": r"\le ",
            ">=": r"\ge ",
            "!=": r"\ne ",
            "..": r"\ldots ",
            "&": r"\mathbin{\&} ",
            "|": r"\mid ",
        }.get(expr.op, expr.op)
        return f"{left} {operator} {right}"
    if isinstance(expr, CallExpr):
        name = expr_to_latex(expr.callee)
        args = ", ".join(expr_to_latex(arg) for arg in expr.args)
        return rf"\operatorname{{{name}}}\left({args}\right)"
    if isinstance(expr, ListExpr):
        return (
            r"\begin{bmatrix}"
            + r" \\ ".join(expr_to_latex(item) for item in expr.items)
            + r"\end{bmatrix}"
        )
    if isinstance(expr, EquationExpr):
        return f"{expr_to_latex(expr.left)} = {expr_to_latex(expr.right)}"
    if isinstance(expr, ConditionalExpr):
        return (
            rf"\begin{{cases}}{expr_to_latex(expr.if_true)}, & "
            rf"{expr_to_latex(expr.condition)}\\"
            rf"{expr_to_latex(expr.if_false)}, & \text{{otherwise}}\end{{cases}}"
        )
    return r"\mathrm{?}"
