from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from supercalc_core.plugins import PluginError, execute_plugin, load_plugin_package


def test_example_plugin() -> None:
    package = load_plugin_package(Path("examples/plugins/sequence_tools"))
    result = execute_plugin(package)
    assert result.ok
    assert result.assertions == 2


def test_plugin_traversal_rejected(tmp_path: Path) -> None:
    root = tmp_path / "bad"
    root.mkdir()
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "id": "bad",
                "name": "bad",
                "version": "1",
                "apiVersion": 1,
                "entry": "../outside.scscript",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "outside.scscript").write_text("1+1", encoding="utf-8")
    with pytest.raises(PluginError):
        load_plugin_package(root)


def test_plugin_native_file_rejected(tmp_path: Path) -> None:
    source = Path("examples/plugins/sequence_tools")
    root = tmp_path / "plugin"
    shutil.copytree(source, root)
    (root / "payload.dll").write_bytes(b"MZ")
    with pytest.raises(PluginError):
        load_plugin_package(root)
