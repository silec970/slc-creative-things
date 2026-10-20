from __future__ import annotations

from supercalc_core import Engine


def test_parse_error_has_source_span() -> None:
    result = Engine().evaluate("1 + * 2")
    assert not result.ok
    diagnostic = result.diagnostics[0]
    assert diagnostic.code.startswith("SC")
    assert diagnostic.span is not None
    assert diagnostic.span.start == 4


def test_unknown_function() -> None:
    result = Engine().evaluate("does_not_exist(1)")
    assert not result.ok
    assert result.diagnostics[0].code == "SC2202"
    assert "does_not_exist" in result.diagnostics[0].message


def test_unbalanced_parenthesis() -> None:
    result = Engine().evaluate("(1 + 2")
    assert not result.ok
    assert result.diagnostics[0].span is not None
