from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

from supercalc_core import Engine
from supercalc_core.api import EngineConfig
from supercalc_core.workspace import Cell, Settings, Workspace, run_workspace


def test_acceptance_exact_fraction() -> None:
    result = Engine().evaluate("1/3 + 1/6")
    assert result.ok
    assert result.value is not None
    assert result.value.display == "1/2"
    assert result.exactness == "exact"


def test_acceptance_float_mode_is_visibly_approximate() -> None:
    result = Engine(EngineConfig(mode="approx")).evaluate("0.1 + 0.2")
    assert result.ok
    assert result.value is not None and not result.value.exact
    assert any(diagnostic.code == "SC3001" for diagnostic in result.diagnostics)
    assert result.exactness == "approximate"


def test_acceptance_fixed_width_overflow() -> None:
    result = Engine().evaluate("i64(9223372036854775807) + 1")
    assert result.ok
    assert result.value is not None
    assert result.value.meta["overflow"]["wrapped"] == -9223372036854775808
    assert any(diagnostic.code == "SC3002" for diagnostic in result.diagnostics)


def test_acceptance_ieee_viewer() -> None:
    result = Engine().evaluate("bits(f64(0.1))")
    assert result.ok
    assert result.value is not None
    assert result.value.meta["ieee754"]["sign"] == 0
    assert result.value.meta["ieee754"]["exponentBits"] == 1019
    assert result.value.meta["ieee754"]["mantissaBits"] == 2702159776422298


def test_acceptance_cas_and_matrix() -> None:
    assert Engine().evaluate("solve(x^2 = 9, x, real)").ok
    assert Engine().evaluate("diff(sin(x)*x^2, x)").ok
    eigen = Engine().evaluate("eigenvalues([[2, 0], [0, 3]])")
    assert eigen.ok and eigen.value is not None
    assert {value.display for value in eigen.value.data} == {"2", "3"}


def test_acceptance_assert_script() -> None:
    result = Engine().run_script(
        """
        f(n) := n <= 1 ? 1 : n * f(n - 1)
        assert f(20) == 2432902008176640000 : "factorial"
        """
    )
    assert result.ok and result.assertions == 1


def test_acceptance_workspace_roundtrip(tmp_path: Path) -> None:
    workspace = Workspace(
        title="acceptance",
        settings=Settings(mode="exact", precision=70),
        cells=[
            Cell(kind="math", source="x := 1/3"),
            Cell(kind="math", source="x + 1/6"),
        ],
    )
    path = workspace.save(tmp_path / "acceptance.scws")
    loaded = Workspace.load(path)
    engine, runs = run_workspace(loaded)
    assert loaded.settings.precision == 70
    assert runs[-1].result is not None and runs[-1].result.value is not None
    assert runs[-1].result.value.display == "1/2"
    assert engine.snapshot().variables["x"]["display"] == "1/3"


def test_acceptance_error_span() -> None:
    result = Engine().evaluate("1 + unknown_func(2)")
    assert not result.ok
    diagnostic = result.diagnostics[0]
    assert diagnostic.code == "SC2202"
    assert diagnostic.span is not None
    assert diagnostic.span.start == 4


def test_acceptance_no_socket_use(monkeypatch, tmp_path: Path) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("application attempted network access")

    monkeypatch.setattr(socket, "socket", forbidden)
    result = Engine().evaluate("1/3 + 1/6")
    assert result.ok
    path = Workspace(cells=[Cell(source="2 + 2")]).save(tmp_path / "offline.scws")
    assert path.exists()


def test_acceptance_cli_json() -> None:
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "supercalc_cli.main",
            "eval",
            "1/3 + 1/6",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert process.returncode == 0, process.stderr
    payload = json.loads(process.stdout)
    assert payload["value"]["display"] == "1/2"
    assert payload["value"]["exact"] is True
