from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    line: int = 1
    column: int = 1

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass
class Diagnostic:
    code: str
    severity: Severity
    message: str
    hint: str = ""
    span: Span | None = None
    snippet: str = ""
    category: str = "general"
    related_spans: list[Span] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "code": self.code,
            "severity": str(self.severity),
            "message": self.message,
            "hint": self.hint,
            "category": self.category,
        }
        if self.span is not None:
            data["span"] = self.span.to_dict()
        if self.snippet:
            data["snippet"] = self.snippet
        if self.related_spans:
            data["relatedSpans"] = [s.to_dict() for s in self.related_spans]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Diagnostic:
        span = data.get("span")
        return cls(
            code=str(data.get("code", "SC9000")),
            severity=Severity(data.get("severity", "error")),
            message=str(data.get("message", "")),
            hint=str(data.get("hint", "")),
            span=Span(**span) if span else None,
            snippet=str(data.get("snippet", "")),
            category=str(data.get("category", "general")),
        )


class CalcError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        hint: str = "",
        span: Span | None = None,
        category: str = "general",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.span = span
        self.category = category

    def diagnostic(self, source: str = "") -> Diagnostic:
        snippet = ""
        if self.span is not None and source:
            line_start = source.rfind("\n", 0, self.span.start) + 1
            line_end = source.find("\n", self.span.end)
            if line_end < 0:
                line_end = len(source)
            snippet = source[line_start:line_end]
        return Diagnostic(
            code=self.code,
            severity=Severity.ERROR,
            message=self.message,
            hint=self.hint,
            span=self.span,
            snippet=snippet,
            category=self.category,
        )


def span_for(source: str, start: int, end: int) -> Span:
    start = max(0, min(start, len(source)))
    end = max(start, min(end, len(source)))
    line = source.count("\n", 0, start) + 1
    last_newline = source.rfind("\n", 0, start)
    column = start - last_newline
    return Span(start=start, end=end, line=line, column=column)


def warning(
    code: str,
    message: str,
    *,
    hint: str = "",
    span: Span | None = None,
    category: str = "numeric",
    snippet: str = "",
) -> Diagnostic:
    return Diagnostic(
        code=code,
        severity=Severity.WARNING,
        message=message,
        hint=hint,
        span=span,
        category=category,
        snippet=snippet,
    )
