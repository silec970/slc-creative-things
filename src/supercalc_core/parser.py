from __future__ import annotations

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
)
from .diagnostics import CalcError, span_for
from .lexer import Lexer, Token

_NATURAL_FUNCTIONS = {
    "sin",
    "cos",
    "tan",
    "asin",
    "acos",
    "atan",
    "sinh",
    "cosh",
    "tanh",
    "ln",
    "log",
    "exp",
    "sqrt",
    "abs",
}

_INFIX: dict[str, tuple[int, int, str]] = {
    "=": (10, 11, "left"),
    "?": (5, 6, "right"),
    "||": (20, 21, "left"),
    "or": (20, 21, "left"),
    "&&": (30, 31, "left"),
    "and": (30, 31, "left"),
    "==": (40, 41, "left"),
    "!=": (40, 41, "left"),
    "<": (40, 41, "left"),
    "<=": (40, 41, "left"),
    ">": (40, 41, "left"),
    ">=": (40, 41, "left"),
    "..": (45, 46, "left"),
    "|": (50, 51, "left"),
    "xor": (55, 56, "left"),
    "&": (60, 61, "left"),
    "<<": (70, 71, "left"),
    ">>": (70, 71, "left"),
    "+": (80, 81, "left"),
    "-": (80, 81, "left"),
    "*": (90, 91, "left"),
    "/": (90, 91, "left"),
    "%": (90, 91, "left"),
    "^": (110, 110, "right"),
}


class Parser:
    def __init__(self, source: str, *, script: bool = False) -> None:
        self.source = source
        self.tokens = Lexer(source).tokenize()
        self.index = 0
        self.script = script
        self.stop_values: list[set[str]] = []

    @property
    def current(self) -> Token:
        return self.tokens[self.index]

    def peek(self, offset: int = 1) -> Token:
        idx = min(self.index + offset, len(self.tokens) - 1)
        return self.tokens[idx]

    def advance(self) -> Token:
        token = self.current
        if self.index < len(self.tokens) - 1:
            self.index += 1
        return token

    def match(self, value: str | None = None, kind: str | None = None) -> Token | None:
        token = self.current
        if value is not None and token.value != value:
            return None
        if kind is not None and token.kind != kind:
            return None
        self.advance()
        return token

    def expect(self, value: str | None = None, kind: str | None = None) -> Token:
        token = self.match(value, kind)
        if token is None:
            label = value if value is not None else kind or "记号"
            raise CalcError(
                "SC1003",
                f"这里需要“{label}”，实际是“{self.current.value or '文件结尾'}”",
                hint="检查括号、逗号或语句结构是否完整。",
                span=self.current.span(self.source),
                category="parse",
            )
        return token

    def skip_separators(self) -> None:
        while self.current.kind == "NEWLINE" or self.current.value == ";":
            self.advance()

    def parse(self) -> Program:
        self.skip_separators()
        statements: list[Statement] = []
        while self.current.kind != "EOF":
            statements.extend(self.parse_statement())
            self.skip_separators()
        start = 0
        end = len(self.source)
        return Program(span_for(self.source, start, end), self.source, statements, self.script)

    def parse_statement(self) -> list[Statement]:
        token = self.current
        if token.kind != "IDENT":
            if token.value == "}":
                return []
            expr = self.parse_expression()
            self._consume_line_end()
            return [ExprStatement(self._expr_span(expr), expr)]
        word = token.value
        if word == "set":
            start = self.advance()
            name = self.expect(kind="IDENT")
            value_parts: list[str] = []
            while self.current.kind not in ("NEWLINE", "EOF") and self.current.value != ";":
                value_parts.append(self.advance().value)
            if not value_parts:
                raise CalcError(
                    "SC1004",
                    "set 命令缺少值",
                    hint="例如：set precision 50。",
                    span=start.span(self.source),
                    category="parse",
                )
            self._consume_line_end()
            end = self.tokens[self.index - 1].end if self.index else name.end
            return [
                Directive(
                    span_for(self.source, start.start, end),
                    name.value,
                    "".join(value_parts),
                )
            ]
        if word == "assume" and self.peek().value == "(":
            expr = self.parse_expression()
            self._consume_line_end()
            return [ExprStatement(self._expr_span(expr), expr)]
        if word == "fn":
            return [self._parse_fn_block()]
        if self.script and word == "if":
            return [self._parse_if()]
        if self.script and word == "while":
            return [self._parse_while()]
        if self.script and word == "for":
            return [self._parse_for()]
        if self.script and word == "assert":
            return [self._parse_assert()]
        if self.script and word == "return":
            start = self.advance()
            expr = self.parse_expression()
            self._consume_line_end()
            return [ReturnStatement(span_for(self.source, start.start, expr.span.end), expr)]
        if self.script and word == "use":
            start = self.advance()
            path = self.expect(kind="STRING")
            self._consume_line_end()
            return [
                ModuleUse(
                    span_for(self.source, start.start, path.end),
                    path.value,
                )
            ]

        saved = self.index
        if word in {"if", "while", "for", "fn", "assert", "return", "use"} and not self.script:
            # These constructs are allowed in script cells only. The generic
            # parser then emits a useful expression/name diagnostic.
            pass
        function_def = self._try_function_def()
        if function_def is not None:
            return [function_def]
        self.index = saved
        name = self.current
        if name.kind == "IDENT" and self.peek().value == ":=":
            self.advance()
            self.advance()
            expr = self.parse_expression()
            self._consume_line_end()
            return [
                Assignment(
                    span_for(self.source, name.start, expr.span.end),
                    name.value,
                    expr,
                )
            ]
        expr = self.parse_expression()
        self._consume_line_end()
        return [ExprStatement(self._expr_span(expr), expr)]

    def _try_function_def(self) -> FunctionDef | None:
        saved = self.index
        if not self._looks_like_function_def():
            return None
        name = self.advance()
        self.advance()
        params: list[str] = []
        if self.current.value != ")":
            while True:
                param = self.expect(kind="IDENT")
                params.append(param.value)
                if not self.match(","):
                    break
        self.expect(")")
        if not self.match(":="):
            self.index = saved
            return None
        body = self.parse_expression()
        self._consume_line_end()
        return FunctionDef(
            span_for(self.source, name.start, body.span.end),
            name.value,
            params,
            body=body,
        )

    def _looks_like_function_def(self) -> bool:
        index = self.index
        if self.tokens[index].kind != "IDENT" or self.tokens[index + 1].value != "(":
            return False
        index += 2
        expect_param = True
        while index < len(self.tokens):
            token = self.tokens[index]
            if token.value == ")":
                index += 1
                return index < len(self.tokens) and self.tokens[index].value == ":="
            if expect_param:
                if token.kind != "IDENT":
                    return False
                expect_param = False
            elif token.value == ",":
                expect_param = True
            elif token.kind == "NEWLINE" or token.kind == "EOF":
                return False
            else:
                return False
            index += 1
        return False

    def _parse_fn_block(self) -> FunctionDef:
        start = self.expect("fn")
        name = self.expect(kind="IDENT")
        self.expect("(")
        params: list[str] = []
        if self.current.value != ")":
            while True:
                params.append(self.expect(kind="IDENT").value)
                if not self.match(","):
                    break
        self.expect(")")
        block = self._parse_block()
        return FunctionDef(
            span_for(self.source, start.start, block.span.end), name.value, params, block=block
        )

    def _parse_block(self) -> Block:
        start = self.expect("{")
        statements: list[Statement] = []
        self.skip_separators()
        while self.current.kind != "EOF" and self.current.value != "}":
            statements.extend(self.parse_statement())
            self.skip_separators()
        end = self.expect("}")
        return Block(span_for(self.source, start.start, end.end), statements)

    def _parse_condition(self) -> Expr:
        self.stop_values.append({"{"})
        try:
            return self.parse_expression()
        finally:
            self.stop_values.pop()

    def _parse_if(self) -> IfStatement:
        start = self.expect("if")
        condition = self._parse_condition()
        then_block = self._parse_block()
        self.skip_separators()
        else_block = None
        if self.current.kind == "IDENT" and self.current.value == "else":
            self.advance()
            else_block = self._parse_block()
        end = else_block.span.end if else_block else then_block.span.end
        return IfStatement(
            span_for(self.source, start.start, end), condition, then_block, else_block
        )

    def _parse_while(self) -> WhileStatement:
        start = self.expect("while")
        condition = self._parse_condition()
        block = self._parse_block()
        return WhileStatement(span_for(self.source, start.start, block.span.end), condition, block)

    def _parse_for(self) -> ForStatement:
        start = self.expect("for")
        name = self.expect(kind="IDENT")
        if not (self.current.kind == "IDENT" and self.current.value == "in"):
            raise CalcError(
                "SC1005",
                "for 循环缺少 in",
                hint="写成 for x in 1..10 { ... }。",
                span=self.current.span(self.source),
                category="parse",
            )
        self.advance()
        iterable = self._parse_condition()
        block = self._parse_block()
        return ForStatement(
            span_for(self.source, start.start, block.span.end),
            name.value,
            iterable,
            block,
        )

    def _parse_assert(self) -> AssertStatement:
        start = self.expect("assert")
        self.stop_values.append({":", "\n", "}", ";"})
        try:
            condition = self.parse_expression()
            message = ""
            if self.match(":"):
                string_token = self.expect(kind="STRING")
                message = string_token.value
        finally:
            self.stop_values.pop()
        self._consume_line_end()
        return AssertStatement(
            span_for(self.source, start.start, self.tokens[self.index - 1].end),
            condition,
            message,
        )

    def _consume_line_end(self) -> None:
        if self.current.kind == "NEWLINE" or self.current.value == ";":
            self.skip_separators()
        elif self.current.kind != "EOF" and self.current.value != "}":
            raise CalcError(
                "SC1006",
                f"语句结束后出现多余记号“{self.current.value}”",
                hint="检查是否漏写逗号、运算符或换行。",
                span=self.current.span(self.source),
                category="parse",
            )

    def parse_expression(self, rbp: int = 0) -> Expr:
        token = self.advance()
        left = self._nud(token)
        while True:
            token = self.current
            if self._is_stop(token):
                break
            value = token.value
            if value == "!":
                if 120 <= rbp:
                    break
                self.advance()
                left = CallExpr(
                    span_for(self.source, left.span.start, token.end),
                    NameExpr(token.span(self.source), "factorial"),
                    [left],
                )
                continue
            info = _INFIX.get(value)
            implicit = False
            if info is None:
                if self._starts_atom(token):
                    info = (90, 91, "left")
                    implicit = True
                else:
                    break
            lbp, next_rbp, assoc = info
            if lbp < rbp:
                break
            if not implicit:
                self.advance()
            if value == "?":
                if_true = self.parse_expression(0)
                self.expect(":")
                if_false = self.parse_expression(next_rbp)
                left = ConditionalExpr(
                    span_for(self.source, left.span.start, if_false.span.end),
                    left,
                    if_true,
                    if_false,
                )
                continue
            right = self.parse_expression(next_rbp if assoc == "right" else next_rbp)
            op = "*" if implicit else value
            if op == "=":
                left = EquationExpr(
                    span_for(self.source, left.span.start, right.span.end), left, right
                )
            else:
                left = BinaryExpr(
                    span_for(self.source, left.span.start, right.span.end),
                    op,
                    left,
                    right,
                )
        return left

    def _is_stop(self, token: Token) -> bool:
        if token.kind in ("EOF", "NEWLINE"):
            return True
        if token.value in {")", "]", "}", ",", ";", ":", "{", "else"}:
            return True
        return any(token.value in stops for stops in self.stop_values)

    def _starts_atom(self, token: Token) -> bool:
        if token.kind in ("NUMBER", "STRING", "IDENT"):
            return True
        return token.value in {"(", "["}

    def _nud(self, token: Token) -> Expr:
        if token.kind == "NUMBER":
            return NumberExpr(token.span(self.source), token.value)
        if token.kind == "STRING":
            return StringExpr(token.span(self.source), token.value)
        if token.kind == "IDENT":
            name = token.value
            if name == "not":
                operand = self.parse_expression(100)
                return UnaryExpr(
                    span_for(self.source, token.start, operand.span.end), "not", operand
                )
            if name in {"true", "false", "True", "False"}:
                return NameExpr(token.span(self.source), name.lower())
            if (
                name in _NATURAL_FUNCTIONS
                and self._starts_atom(self.current)
                and self.current.value != "("
            ):
                arg = self.parse_expression(100)
                return CallExpr(
                    span_for(self.source, token.start, arg.span.end),
                    NameExpr(token.span(self.source), name),
                    [arg],
                )
            if self.current.value == "(":
                self.advance()
                args: list[Expr] = []
                if self.current.value != ")":
                    while True:
                        args.append(self.parse_expression())
                        if not self.match(","):
                            break
                end = self.expect(")")
                return CallExpr(
                    span_for(self.source, token.start, end.end),
                    NameExpr(token.span(self.source), name),
                    args,
                )
            return NameExpr(token.span(self.source), name)
        if token.value in {"+", "-", "~"}:
            operand = self.parse_expression(100)
            return UnaryExpr(
                span_for(self.source, token.start, operand.span.end), token.value, operand
            )
        if token.value == "(":
            expr = self.parse_expression()
            end = self.expect(")")
            expr.span = span_for(self.source, token.start, end.end)
            return expr
        if token.value == "[":
            items: list[Expr] = []
            if self.current.value != "]":
                while True:
                    items.append(self.parse_expression())
                    if not self.match(","):
                        break
            end = self.expect("]")
            return ListExpr(span_for(self.source, token.start, end.end), items)
        if token.value == "{":
            set_items: list[Expr] = []
            if self.current.value != "}":
                while True:
                    set_items.append(self.parse_expression())
                    if not self.match(","):
                        break
            end = self.expect("}")
            return CallExpr(
                span_for(self.source, token.start, end.end),
                NameExpr(token.span(self.source), "set"),
                set_items,
            )
        raise CalcError(
            "SC1007",
            f"表达式不能以“{token.value or '文件结尾'}”开始",
            hint="这里需要数字、名称、函数调用或带括号的表达式。",
            span=token.span(self.source),
            category="parse",
        )

    def _expr_span(self, expr: Expr):
        return expr.span


def parse(source: str, *, script: bool = False) -> Program:
    return Parser(source, script=script).parse()
