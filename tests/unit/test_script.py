from __future__ import annotations

from supercalc_core import Engine
from supercalc_core.api import EngineConfig


def test_recursive_function_and_assert() -> None:
    source = """
    f(n) := n <= 1 ? 1 : n * f(n - 1)
    assert f(20) == 2432902008176640000 : "factorial mismatch"
    f(10)
    """
    result = Engine().run_script(source)
    assert result.ok, result.to_dict()
    assert result.assertions == 1
    assert result.results[-1].value is not None
    assert int(result.results[-1].value.data) == 3628800


def test_for_loop_and_block_function() -> None:
    source = """
    fn total(n) {
        acc := 0
        for k in 1..n {
            acc := acc + k
        }
        return acc
    }
    assert total(10) == 55
    """
    result = Engine().run_script(source)
    assert result.ok, result.to_dict()


def test_script_step_quota() -> None:
    engine = Engine(EngineConfig(max_script_steps=20))
    result = engine.run_script(
        """
        x := 0
        while true {
            x := x + 1
        }
        """
    )
    assert not result.ok
    assert any(d.code in {"SC6004", "SC6009"} for d in result.diagnostics)


def test_python_escape_is_not_available() -> None:
    result = Engine().run_script('__import__("os").system("whoami")')
    assert not result.ok
