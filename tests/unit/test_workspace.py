from __future__ import annotations

from pathlib import Path

from supercalc_core.workspace import Cell, Settings, Workspace


def test_workspace_roundtrip(tmp_path: Path) -> None:
    workspace = Workspace(
        title="验收",
        settings=Settings(mode="exact", precision=60),
        cells=[
            Cell(id="c1", kind="math", source="x := 1/3"),
            Cell(id="c2", kind="math", source="x + 1/6"),
        ],
    )
    path = tmp_path / "sample.scws"
    workspace.save(path)
    loaded = Workspace.load(path)
    assert loaded.title == "验收"
    assert loaded.settings.precision == 60
    assert [cell.source for cell in loaded.cells] == ["x := 1/3", "x + 1/6"]


def test_future_schema_is_read_only(tmp_path: Path) -> None:
    path = tmp_path / "future.scws"
    path.write_text(
        '{"schemaVersion": 99, "appVersion": "9", "title": "future", '
        '"settings": {}, "cells": [], "history": [], "snapshot": {}}',
        encoding="utf-8",
    )
    loaded = Workspace.load(path)
    assert loaded.read_only is True
