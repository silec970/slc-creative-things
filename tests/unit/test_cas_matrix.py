from __future__ import annotations

from supercalc_core import Engine


def test_solve_equation() -> None:
    result = Engine().evaluate("solve(x^2 = 9, x, real)")
    assert result.ok, result.to_dict()
    assert result.value is not None
    assert result.value.type == "Set"
    assert {item.display for item in result.value.data} == {"-3", "3"}


def test_derivative() -> None:
    result = Engine().evaluate("diff(sin(x)*x^2, x)")
    assert result.ok, result.to_dict()
    assert result.value is not None
    assert result.value.type == "Symbolic"
    assert "2*x*sin(x)" in str(result.value.data)


def test_matrix_eigenvalues() -> None:
    result = Engine().evaluate("eigenvalues([[2, 0], [0, 3]])")
    assert result.ok, result.to_dict()
    assert result.value is not None
    assert result.value.type == "Vector"
    assert {item.display for item in result.value.data} == {"2", "3"}


def test_singular_inverse_error() -> None:
    result = Engine().evaluate("inv([[1, 2], [2, 4]])")
    assert not result.ok
    assert result.diagnostics[0].code == "SC2006"
