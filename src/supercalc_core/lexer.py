from __future__ import annotations

from dataclasses import dataclass

from .diagnostics import CalcError, Span, span_for


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    start: int
    end: int
    line: int
    column: int

    def span(self, source: str | None = None) -> Span:
        if source is None:
            return Span(self.start, self.end, self.line, self.column)
        return span_for(source, self.start, self.end)


_UNICODE_REPLACEMENTS = {
    "×": "*",
    "·": "*",
    "÷": "/",
    "−": "-",
    "–": "-",
    "≤": "<=",
    "≥": ">=",
    "≠": "!=",
    "∧": "&&",
    "∨": "||",
    "¬": "~",
    "π": "pi",
    "∞": "oo",
}


class Lexer:
    def __init__(self, source: str) -> None:
        self.source = source
        self.length = len(source)
        self.pos = 0
        self.line = 1
        self.column = 1

    def _advance(self, count: int = 1) -> str:
        text = self.source[self.pos : self.pos + count]
        for ch in text:
            if ch == "\n":
                self.line += 1
                self.column = 1
            else:
                self.column += 1
        self.pos += count
        return text

    def _token(self, kind: str, value: str, start: int, line: int, column: int) -> Token:
        return Token(kind, value, start, self.pos, line, column)

    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []
        two_char = (":=", "==", "!=", "<=", ">=", "&&", "||", "<<", ">>", "..")
        one_char = set("+-*/^%&|~!<>()[]{},:;=?")
        while self.pos < self.length:
            ch = self.source[self.pos]
            if ch in " \t\r":
                self._advance()
                continue
            if ch == "\n":
                start, line, column = self.pos, self.line, self.column
                self._advance()
                tokens.append(self._token("NEWLINE", "\n", start, line, column))
                continue
            if ch == "#":
                while self.pos < self.length and self.source[self.pos] != "\n":
                    self._advance()
                continue
            if self.source.startswith("//", self.pos):
                while self.pos < self.length and self.source[self.pos] != "\n":
                    self._advance()
                continue
            replacement = _UNICODE_REPLACEMENTS.get(ch)
            if replacement is not None:
                start, line, column = self.pos, self.line, self.column
                self._advance()
                # Multi-character replacements are represented as a single logical
                # operator token while retaining the source span.
                tokens.append(self._token("OP", replacement, start, line, column))
                continue
            if ch.isdigit() or (
                ch == "." and self.pos + 1 < self.length and self.source[self.pos + 1].isdigit()
            ):
                tokens.append(self._lex_number())
                continue
            if ch.isalpha() or ch == "_":
                tokens.append(self._lex_identifier())
                continue
            if ch in "\"'":
                tokens.append(self._lex_string(ch))
                continue
            pair = self.source[self.pos : self.pos + 2]
            if pair in two_char:
                start, line, column = self.pos, self.line, self.column
                self._advance(2)
                tokens.append(self._token("OP", pair, start, line, column))
                continue
            if ch in one_char:
                start, line, column = self.pos, self.line, self.column
                self._advance()
                tokens.append(self._token("OP", ch, start, line, column))
                continue
            raise CalcError(
                "SC1001",
                f"无法识别字符“{ch}”",
                hint="请删除该字符或改用标准运算符。",
                span=span_for(self.source, self.pos, self.pos + 1),
                category="parse",
            )
        tokens.append(Token("EOF", "", self.length, self.length, self.line, self.column))
        return tokens

    def _lex_number(self) -> Token:
        start, line, column = self.pos, self.line, self.column
        if self.source.startswith(("0x", "0X", "0b", "0B", "0o", "0O"), self.pos):
            self._advance(2)
            while self.pos < self.length and (
                self.source[self.pos].isalnum() or self.source[self.pos] == "_"
            ):
                self._advance()
            return self._token("NUMBER", self.source[start : self.pos], start, line, column)
        seen_dot = False
        seen_exp = False
        while self.pos < self.length:
            ch = self.source[self.pos]
            if ch.isdigit() or ch == "_":
                self._advance()
            elif (
                ch == "."
                and not seen_dot
                and not seen_exp
                and not self.source.startswith("..", self.pos)
            ):
                seen_dot = True
                self._advance()
            elif ch in "eE" and not seen_exp:
                seen_exp = True
                self._advance()
                if self.pos < self.length and self.source[self.pos] in "+-":
                    self._advance()
            else:
                break
        return self._token("NUMBER", self.source[start : self.pos], start, line, column)

    def _lex_identifier(self) -> Token:
        start, line, column = self.pos, self.line, self.column
        while self.pos < self.length:
            ch = self.source[self.pos]
            if ch.isalnum() or ch == "_":
                self._advance()
            else:
                break
        return self._token("IDENT", self.source[start : self.pos], start, line, column)

    def _lex_string(self, quote: str) -> Token:
        start, line, column = self.pos, self.line, self.column
        self._advance()
        chars: list[str] = []
        while self.pos < self.length:
            ch = self.source[self.pos]
            if ch == quote:
                self._advance()
                return self._token("STRING", "".join(chars), start, line, column)
            if ch == "\\":
                self._advance()
                if self.pos >= self.length:
                    break
                escaped = self._advance()
                chars.append({"n": "\n", "t": "\t", "r": "\r"}.get(escaped, escaped))
            else:
                chars.append(self._advance())
        raise CalcError(
            "SC1002",
            "字符串没有结束引号",
            hint="在字符串末尾补上匹配的引号。",
            span=span_for(self.source, start, self.pos),
            category="parse",
        )
