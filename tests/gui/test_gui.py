from __future__ import annotations

import re
from pathlib import Path

from supercalc_core.api import Engine
from supercalc_core.workspace import Settings, Workspace
from supercalc_gui.client import ComputeClient
from supercalc_gui.formula_editor import FormulaEditor
from supercalc_gui.help_dialog import (
    function_reference_path,
    interface_guide_path,
    scripting_guide_path,
)
from supercalc_gui.main_window import MainWindow
from supercalc_gui.notebook import PlotView


def test_main_window_runs_exact_cell(qtbot, monkeypatch) -> None:
    monkeypatch.setenv("SUPERCALC_NO_RECOVERY", "1")
    window = MainWindow(inprocess=True)
    qtbot.addWidget(window)
    window.show()
    window.run_all()
    qtbot.waitUntil(lambda: not window._busy, timeout=5000)
    document = window.current_document()
    assert document is not None
    assert "1/2" in document.view.cells[0].result.text()
    assert "精确" in document.view.cells[0].badge.text()
    document.modified = False
    window._autosave_timer.stop()
    window.client.close()


def test_approximate_mode_shows_badge(qtbot, monkeypatch) -> None:
    monkeypatch.setenv("SUPERCALC_NO_RECOVERY", "1")
    window = MainWindow(inprocess=True)
    qtbot.addWidget(window)
    window.show()
    document = window.current_document()
    assert document is not None
    cell = document.view.cells[0]
    cell.formula.setPlainText("0.1 + 0.2")
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("approx"))
    window.run_all()
    qtbot.waitUntil(lambda: not window._busy, timeout=5000)
    assert "近似" in cell.badge.text()
    assert "SC3001" in cell.detail.text()
    assert window.diagnostics.topLevelItemCount() >= 2
    document.modified = False
    window._autosave_timer.stop()
    window.client.close()


def test_wysiwyg_preview_and_template(qtbot) -> None:
    editor = FormulaEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("1/2 + sqrt(x)")
    editor.refresh_preview()
    assert editor.preview._pixmap is not None
    editor.insert_template("fraction")
    assert "/" in editor.toPlainText()


def test_plot_widget_samples(qtbot) -> None:
    view = PlotView(Settings())
    qtbot.addWidget(view)
    view.expression.setText("sin(x)")
    view.x_min.setValue(-3.14)
    view.x_max.setValue(3.14)
    view.update_plot()
    assert "采样完成" in view.status.text()
    initial_span = view.axes.get_xlim()[1] - view.axes.get_xlim()[0]
    view.zoom_in_button.click()
    zoomed_span = view.axes.get_xlim()[1] - view.axes.get_xlim()[0]
    assert zoomed_span < initial_span
    view.zoom_out_button.click()
    restored_span = view.axes.get_xlim()[1] - view.axes.get_xlim()[0]
    assert restored_span > zoomed_span
    view.reset_view_button.click()
    assert view.axes.get_xlim() == view._home_limits[0]


def test_compute_client_keeps_cell_errors_visible(qtbot) -> None:
    client = ComputeClient()
    completed: list[dict] = []
    failed: list[str] = []
    client.completed.connect(lambda _request_id, payload: completed.append(payload))
    client.failed.connect(lambda _request_id, message: failed.append(message))
    client.pending = "request-1"
    client._deliver(
        {
            "id": "request-1",
            "ok": False,
            "runs": [{"cellId": "c1", "ok": False, "result": {"ok": False}}],
            "environment": {},
        }
    )
    assert completed
    assert not failed


def test_compute_client_falls_back_when_worker_cannot_start(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(
        "supercalc_gui.client.worker_command",
        lambda: ["C:\\definitely-missing\\supercalc-worker.exe"],
    )
    client = ComputeClient()
    client.inprocess = False
    completed: list[dict] = []
    failed: list[str] = []
    client.completed.connect(lambda _request_id, payload: completed.append(payload))
    client.failed.connect(lambda _request_id, message: failed.append(message))
    client.run_workspace(Workspace(cells=[]))
    qtbot.waitUntil(lambda: bool(completed or failed), timeout=15000)
    assert completed
    assert client.used_fallback
    assert not failed


def test_interface_guide_exists() -> None:
    guide = interface_guide_path()
    assert guide.exists()
    text = guide.read_text(encoding="utf-8")
    for label in ("运行全部", "取消计算", "放大", "缩小", "复位视图", "语法树"):
        assert label in text


def test_function_reference_covers_every_builtin() -> None:
    text = function_reference_path().read_text(encoding="utf-8")
    documented = set(re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)", text))
    actual = {name[9:] for name in dir(Engine) if name.startswith("_builtin_")}
    actual.update({"i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64"})
    assert not actual - documented


def test_scripting_guide_covers_script_language() -> None:
    text = scripting_guide_path().read_text(encoding="utf-8")
    for label in ("赋值", "函数", "条件", "循环", "断言", "模块", "安全限制"):
        assert label in text


def test_gui_save_document(qtbot, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SUPERCALC_NO_RECOVERY", "1")
    window = MainWindow(inprocess=True)
    qtbot.addWidget(window)
    window.show()
    document = window.current_document()
    assert document is not None
    assert window._save_document(document, tmp_path / "gui.scws")
    loaded = Workspace.load(tmp_path / "gui.scws")
    assert len(loaded.cells) == 3
    document.modified = False
    window._autosave_timer.stop()
    window.client.close()
