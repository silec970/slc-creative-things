from __future__ import annotations

from supercalc_core import Engine
from supercalc_core.latex import from_latex
from supercalc_core.plotting import PlotSpec, sample_plot


def test_latex_import_subset() -> None:
    assert Engine().evaluate(from_latex(r"\frac{1}{3}+\frac{1}{6}")).value.display == "1/2"
    matrix = Engine().evaluate(from_latex(r"\begin{bmatrix}1 & 2\\3 & 4\end{bmatrix}"))
    assert matrix.ok and matrix.value.type == "Matrix"
    expression = Engine().evaluate(from_latex(r"\sqrt{2}+\sin(x)"))
    assert expression.ok and expression.value.type == "Symbolic"


def test_units_and_conversion() -> None:
    result = Engine().evaluate("to(3 m + 20 cm, cm)")
    assert result.ok and result.value is not None
    assert result.value.display == "320 cm"
    assert result.value.meta["unit"] == "cm"
    error = Engine().evaluate("1 m + 1 s")
    assert not error.ok and error.diagnostics[0].code == "SC2142"


def test_plot_sampling() -> None:
    samples = sample_plot(Engine(), PlotSpec(expression="sin(x)", x_min=0, x_max=3.14, samples=50))
    assert len(samples.x) == 50
    assert abs(max(samples.y) - 1.0) < 0.01


def test_polar_plot() -> None:
    samples = sample_plot(
        Engine(),
        PlotSpec(expression="1", kind="polar", x_min=0, x_max=6.28, samples=40),
    )
    assert len(samples.x) == 40
    assert all(abs(value - 1.0) < 1e-9 for value in samples.y)


def test_implicit_circle_plot() -> None:
    samples = sample_plot(
        Engine(),
        PlotSpec(equation="y^2 + x^2 = 1", x_min=-2, x_max=2, samples=200),
    )
    assert samples.kind == "implicit"
    assert len(samples.grid_x) >= 120
    assert samples.grid_z
