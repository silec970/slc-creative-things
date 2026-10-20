from __future__ import annotations

from typing import Any

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from supercalc_core.api import Engine
from supercalc_core.plotting import PlotSpec, sample_plot
from supercalc_core.workspace import Cell, Settings

from .formula_editor import FormulaEditor
from .gui_text import algorithm_name, assumptions_text, rounding_name, type_name


class PlotView(QWidget):
    changed = Signal()

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.equation = QLineEdit("y = sin(x)")
        self.equation.setPlaceholderText("方程，例如 y = sin(x) 或 y^2 + x^2 = 1")
        self.equation.editingFinished.connect(self.changed)
        self.x_min = QDoubleSpinBox()
        self.x_min.setRange(-1e9, 1e9)
        self.x_min.setValue(-10)
        self.x_min.setDecimals(4)
        self.x_min.valueChanged.connect(self.changed)
        self.x_max = QDoubleSpinBox()
        self.x_max.setRange(-1e9, 1e9)
        self.x_max.setValue(10)
        self.x_max.setDecimals(4)
        self.x_max.valueChanged.connect(self.changed)
        self.kind = QComboBox()
        self.kind.addItem("直角坐标或隐式曲线", "cartesian")
        self.kind.addItem("极坐标曲线", "polar")
        self.kind.currentIndexChanged.connect(self.changed)
        self.plot_button = QPushButton("绘图")
        self.plot_button.setObjectName("primaryButton")
        self.plot_button.clicked.connect(self.update_plot)
        self.export_button = QToolButton()
        self.export_button.setText("导出")
        self.export_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        export_menu = QMenu(self.export_button)
        export_menu.addAction("导出位图…", lambda: self.export_image("png"))
        export_menu.addAction("导出矢量图…", lambda: self.export_image("svg"))
        self.export_button.setMenu(export_menu)
        self.status = QLabel("")
        self.status.setObjectName("mutedLabel")
        self.status.setWordWrap(True)

        controls = QHBoxLayout()
        controls.setSpacing(6)
        controls.addWidget(QLabel("方程"))
        controls.addWidget(self.equation, 1)
        controls.addWidget(QLabel("范围"))
        controls.addWidget(self.x_min)
        controls.addWidget(QLabel("—"))
        controls.addWidget(self.x_max)
        controls.addWidget(self.kind)
        controls.addWidget(self.plot_button)
        controls.addWidget(self.export_button)

        self.figure = Figure(figsize=(5, 2.7), dpi=100, facecolor="#fbfcfe")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumHeight(260)
        self.axes = self.figure.add_subplot(111)
        self.axes.grid(True, alpha=0.25)
        self._home_limits: tuple[tuple[float, float], tuple[float, float]] | None = None
        self._drag_start: tuple[float, float] | None = None
        self._drag_limits: tuple[tuple[float, float], tuple[float, float]] | None = None

        self.zoom_in_button = QPushButton("放大")
        self.zoom_in_button.setToolTip("以图中心为中心放大坐标范围")
        self.zoom_in_button.clicked.connect(lambda: self.zoom_plot(0.75))
        self.zoom_out_button = QPushButton("缩小")
        self.zoom_out_button.setToolTip("以图中心为中心缩小坐标范围")
        self.zoom_out_button.clicked.connect(lambda: self.zoom_plot(1.333333))
        self.reset_view_button = QPushButton("复位视图")
        self.reset_view_button.setToolTip("恢复绘制时的初始坐标范围")
        self.reset_view_button.clicked.connect(self.reset_view)
        view_controls = QHBoxLayout()
        view_controls.setSpacing(6)
        view_controls.addWidget(QLabel("视图"))
        view_controls.addWidget(self.zoom_in_button)
        view_controls.addWidget(self.zoom_out_button)
        view_controls.addWidget(self.reset_view_button)
        view_hint = QLabel("鼠标滚轮缩放；按住左键拖动平移")
        view_hint.setObjectName("mutedLabel")
        view_controls.addWidget(view_hint)
        view_controls.addStretch(1)

        self.canvas.mpl_connect("scroll_event", self._on_scroll)
        self.canvas.mpl_connect("button_press_event", self._on_press)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self.canvas.mpl_connect("button_release_event", self._on_release)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(controls)
        layout.addLayout(view_controls)
        layout.addWidget(self.canvas)
        layout.addWidget(self.status)
        self.update_plot()

    def to_config(self) -> dict[str, Any]:
        return PlotSpec(
            equation=self.equation.text(),
            x_min=self.x_min.value(),
            x_max=self.x_max.value(),
            kind=str(self.kind.currentData()),
        ).to_dict()

    def load_config(self, data: dict[str, Any]) -> None:
        spec = PlotSpec.from_dict(data)
        self.equation.setText(spec.equation)
        self.x_min.setValue(spec.x_min)
        self.x_max.setValue(spec.x_max)
        index = self.kind.findData(spec.kind)
        self.kind.setCurrentIndex(max(0, index))
        self.update_plot()

    def update_plot(self) -> None:
        spec = PlotSpec.from_dict(self.to_config())
        try:
            samples = sample_plot(Engine(self.settings.engine_config()), spec)
        except Exception as exc:
            self.status.setText(f"绘图失败：{exc}")
            return
        self.axes.clear()
        self.axes.grid(True, alpha=0.25)
        if samples.kind in {"explicit", "polar"} and samples.x:
            x_values = np.asarray(samples.x, dtype=float)
            y_values = np.asarray(samples.y, dtype=float)
            if samples.kind == "polar":
                theta = x_values
                radius = y_values
                x_plot = radius * np.cos(theta)
                y_plot = radius * np.sin(theta)
                finite = np.isfinite(x_plot) & np.isfinite(y_plot)
                x_plot = np.ma.masked_where(~finite, x_plot)
                y_plot = np.ma.masked_where(~finite, y_plot)
                self.axes.plot(x_plot, y_plot, color="#1769aa", linewidth=1.8)
                x_limits = self._robust_limits(np.ma.compressed(x_plot))
                y_limits = self._robust_limits(np.ma.compressed(y_plot))
                self.axes.set_xlim(*x_limits)
                self.axes.set_ylim(*y_limits)
                self.axes.set_aspect("equal", adjustable="datalim")
            else:
                self.axes.plot(
                    x_values,
                    self._masked_tan_style_discontinuities(y_values),
                    color="#1769aa",
                    linewidth=1.8,
                )
                self.axes.set_xlim(spec.x_min, spec.x_max)
                y_limits = self._robust_limits(y_values)
                self.axes.set_ylim(*y_limits)
                self.axes.axhline(0, color="#7f8a9a", linewidth=0.7)
                self.axes.axvline(0, color="#7f8a9a", linewidth=0.7)
            self.axes.set_title(samples.equation, fontsize=10)
            self.axes.tick_params(labelsize=8)
            self.figure.tight_layout()
            self.canvas.draw_idle()
            self._home_limits = (self.axes.get_xlim(), self.axes.get_ylim())
            messages = [d.message for d in samples.diagnostics if d.severity == "warning"]
            self.status.setText(" · ".join(messages) if messages else "采样完成，可缩放和平移。")
        elif samples.kind == "implicit" and samples.grid_x:
            grid_x = np.asarray(samples.grid_x, dtype=float)
            grid_y = np.asarray(samples.grid_y, dtype=float)
            grid_z = np.asarray(samples.grid_z, dtype=float)
            grid_z = np.ma.masked_where(np.abs(grid_z) > 1e12, grid_z)
            self.axes.contour(
                grid_x,
                grid_y,
                grid_z,
                levels=[0],
                colors=["#1769aa"],
                linewidths=1.8,
            )
            self.axes.set_xlim(spec.x_min, spec.x_max)
            self.axes.set_ylim(spec.x_min, spec.x_max)
            self.axes.set_aspect("equal", adjustable="box")
            self.axes.set_title(samples.equation, fontsize=10)
            self.axes.tick_params(labelsize=8)
            self.figure.tight_layout()
            self.canvas.draw_idle()
            self._home_limits = (self.axes.get_xlim(), self.axes.get_ylim())
            messages = [d.message for d in samples.diagnostics if d.severity == "warning"]
            self.status.setText(
                " · ".join(messages) if messages else "隐式曲线采样完成，可缩放和平移。"
            )
        else:
            reason = samples.diagnostics[0].message if samples.diagnostics else "没有可绘制的数据"
            self.status.setText(reason)
            self.canvas.draw_idle()

    def _robust_limits(self, values: np.ndarray) -> tuple[float, float]:
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            return (-1.0, 1.0)
        low, high = np.percentile(finite, [5, 95])
        if not np.isfinite(low) or not np.isfinite(high) or high <= low:
            center = float(np.nanmedian(finite))
            span = max(1.0, abs(center) * 0.2)
            return center - span, center + span
        padding = (high - low) * 0.15
        return float(low - padding), float(high + padding)

    def _masked_tan_style_discontinuities(self, values: np.ndarray) -> np.ma.MaskedArray:
        mask = ~np.isfinite(values)
        if values.size > 1:
            finite = values[np.isfinite(values)]
            if finite.size:
                low, high = np.percentile(finite, [5, 95])
                threshold = max(float((high - low) * 4), 1e-9)
                mask |= values > high + threshold
                mask |= values < low - threshold
                jumps = np.abs(np.diff(values))
                jump_indices = np.where(np.isfinite(jumps) & (jumps > threshold))[0]
                for index in jump_indices:
                    mask[index] = True
                    mask[index + 1] = True
        return np.ma.masked_where(mask, values)

    def export_image(self, format_name: str) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出图像",
            f"plot.{format_name}",
            ("位图 (*.png)" if format_name == "png" else "矢量图 (*.svg)"),
        )
        if path:
            self.figure.savefig(path, format=format_name, dpi=180, bbox_inches="tight")

    def zoom_plot(self, factor: float, center: tuple[float, float] | None = None) -> None:
        x_limits = self.axes.get_xlim()
        y_limits = self.axes.get_ylim()
        center_x = center[0] if center else (x_limits[0] + x_limits[1]) / 2
        center_y = center[1] if center else (y_limits[0] + y_limits[1]) / 2
        x_width = max(1e-12, (x_limits[1] - x_limits[0]) * factor)
        y_height = max(1e-12, (y_limits[1] - y_limits[0]) * factor)
        self.axes.set_xlim(center_x - x_width / 2, center_x + x_width / 2)
        self.axes.set_ylim(center_y - y_height / 2, center_y + y_height / 2)
        self.canvas.draw_idle()

    def reset_view(self) -> None:
        if self._home_limits is None:
            return
        self.axes.set_xlim(*self._home_limits[0])
        self.axes.set_ylim(*self._home_limits[1])
        self.canvas.draw_idle()

    def _on_scroll(self, event) -> None:
        if event.inaxes is not self.axes or event.xdata is None or event.ydata is None:
            return
        factor = 0.8 if event.button == "up" else 1.25
        self.zoom_plot(factor, (float(event.xdata), float(event.ydata)))

    def _on_press(self, event) -> None:
        if event.inaxes is not self.axes or event.button != 1:
            return
        self._drag_start = (float(event.x), float(event.y))
        self._drag_limits = (self.axes.get_xlim(), self.axes.get_ylim())
        self.canvas.setCursor(Qt.CursorShape.ClosedHandCursor)

    def _on_motion(self, event) -> None:
        if self._drag_start is None or self._drag_limits is None:
            return
        bbox = self.axes.bbox
        delta_x = float(event.x) - self._drag_start[0]
        delta_y = float(event.y) - self._drag_start[1]
        x_limits, y_limits = self._drag_limits
        x_span = x_limits[1] - x_limits[0]
        y_span = y_limits[1] - y_limits[0]
        shift_x = -delta_x / max(1.0, bbox.width) * x_span
        shift_y = -delta_y / max(1.0, bbox.height) * y_span
        self.axes.set_xlim(x_limits[0] + shift_x, x_limits[1] + shift_x)
        self.axes.set_ylim(y_limits[0] + shift_y, y_limits[1] + shift_y)
        self.canvas.draw_idle()

    def _on_release(self, event) -> None:
        self._drag_start = None
        self._drag_limits = None
        self.canvas.setCursor(Qt.CursorShape.ArrowCursor)


class CellWidget(QFrame):
    changed = Signal()
    runCell = Signal(str)
    deleteCell = Signal(str)
    showAst = Signal(str)

    def __init__(
        self,
        cell: Cell,
        settings: Settings,
        index: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.cell = cell
        self.settings = settings
        self.index = index
        self.formula: FormulaEditor | None = None
        self.text_editor: QPlainTextEdit | None = None
        self.plot_view: PlotView | None = None
        self.setObjectName("cellCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        self.kind_box = QComboBox()
        self.kind_box.addItem("公式", "math")
        self.kind_box.addItem("脚本", "script")
        self.kind_box.addItem("说明文本", "markdown")
        self.kind_box.addItem("二维绘图", "plot")
        index_kind = self.kind_box.findData(cell.kind)
        self.kind_box.setCurrentIndex(max(0, index_kind))
        self.kind_box.currentIndexChanged.connect(self._change_kind)
        header = QHBoxLayout()
        number = QLabel(f"{index + 1:02d}")
        number.setObjectName("cellNumber")
        header.addWidget(number)
        header.addWidget(self.kind_box)
        self.badge = QLabel("")
        self.badge.setObjectName("resultBadge")
        header.addWidget(self.badge)
        header.addStretch(1)
        self.run_button = QToolButton()
        self.run_button.setText("▶ 运行")
        self.run_button.setToolTip("运行此单元（控制键加回车）")
        self.run_button.clicked.connect(lambda: self.runCell.emit(self.cell.id))
        header.addWidget(self.run_button)
        delete_button = QToolButton()
        delete_button.setText("删除")
        delete_button.setToolTip("删除此单元")
        delete_button.clicked.connect(lambda: self.deleteCell.emit(self.cell.id))
        header.addWidget(delete_button)
        ast_button = QToolButton()
        ast_button.setText("语法树")
        ast_button.setToolTip("查看此单元的语法树")
        ast_button.clicked.connect(lambda: self.showAst.emit(self.source()))
        header.addWidget(ast_button)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 4, 0, 0)
        self.body.setSpacing(6)
        self.result = QLabel("尚未运行")
        self.result.setObjectName("resultText")
        self.result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.result.setWordWrap(True)
        self.detail = QLabel("")
        self.detail.setObjectName("mutedLabel")
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 10)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addLayout(self.body)
        layout.addWidget(self.result)
        layout.addWidget(self.detail)
        self._build_editor()
        self.set_result(None)

    def _clear_body(self) -> None:
        while self.body.count():
            item = self.body.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        self.formula = None
        self.text_editor = None
        self.plot_view = None

    def _build_editor(self) -> None:
        self._clear_body()
        kind = self.cell.kind
        if kind == "math":
            self.formula = FormulaEditor()
            self.formula.setPlainText(self.cell.source)
            self.formula.textChanged.connect(self._editor_changed)
            self.formula.runRequested.connect(lambda: self.runCell.emit(self.cell.id))
            self.body.addWidget(self.formula)
        elif kind == "plot":
            self.plot_view = PlotView(self.settings)
            if self.cell.plot:
                self.plot_view.load_config(self.cell.plot)
            self.plot_view.changed.connect(self._editor_changed)
            self.body.addWidget(self.plot_view)
        else:
            self.text_editor = QPlainTextEdit()
            self.text_editor.setPlainText(self.cell.source)
            self.text_editor.setFont(QFont("Cascadia Mono", 11))
            self.text_editor.setMinimumHeight(100 if kind == "script" else 72)
            self.text_editor.setPlaceholderText(
                "输入脚本，例如 f(n) := n <= 1 ? 1 : n * f(n-1)"
                if kind == "script"
                else "说明文本，可直接输入段落与简单标记"
            )
            self.text_editor.textChanged.connect(self._editor_changed)
            self.body.addWidget(self.text_editor)

    def _change_kind(self) -> None:
        new_kind = str(self.kind_box.currentData())
        self.cell.kind = new_kind
        self.cell.source = self.source()
        self._build_editor()
        self.changed.emit()

    def _editor_changed(self) -> None:
        self.changed.emit()

    def source(self) -> str:
        if self.formula is not None:
            return self.formula.toPlainText()
        if self.text_editor is not None:
            return self.text_editor.toPlainText()
        return self.cell.source

    def to_cell(self) -> Cell:
        self.cell.source = self.source()
        if self.plot_view is not None:
            self.cell.plot = self.plot_view.to_config()
        return self.cell

    def set_result(self, payload: dict[str, Any] | None) -> None:
        if payload is None:
            self.result.setText("尚未运行")
            self.detail.setText("")
            self.badge.setText("")
            self.badge.setProperty("state", "")
            self._repolish()
            return
        result = payload.get("result")
        script = payload.get("script")
        if script is not None:
            ok = bool(script.get("ok"))
            assertions = int(script.get("assertions", 0))
            self.result.setText(("✓ 脚本通过" if ok else "× 脚本失败") + f" · {assertions} 个断言")
            diagnostics = script.get("diagnostics", [])
            timing = float(script.get("timingMs", 0))
            self.detail.setText(f"耗时 {timing:.1f} 毫秒" + self._diagnostic_suffix(diagnostics))
            self._set_badge("脚本", ok)
            return
        if result is None:
            self.set_result(None)
            return
        value = result.get("value")
        diagnostics = result.get("diagnostics", [])
        ok = bool(result.get("ok"))
        if value is None:
            self.result.setText("计算失败")
            self.detail.setText(self._diagnostic_suffix(diagnostics).lstrip(" ·"))
            self._set_badge("错误", False)
            return
        marker = "=" if value.get("exact") else "≈"
        self.result.setText(f"{marker} {value.get('display', '')}")
        exactness = "精确" if value.get("exact") else "近似"
        metadata = [
            type_name(str(value.get("type", ""))),
            exactness,
            f"{result.get('precision', self.settings.precision)} 位",
            rounding_name(str(result.get("rounding", self.settings.rounding))),
        ]
        if result.get("algorithm"):
            metadata.append(algorithm_name(str(result["algorithm"])))
        if result.get("assumptions"):
            metadata.append(f"假设 {assumptions_text(result['assumptions'])}")
        if result.get("steps") and self.settings.show_steps:
            metadata.append(
                "步骤："
                + "；".join(
                    step.get("detail", "") for step in result["steps"] if step.get("detail")
                )
            )
        self.detail.setText(" · ".join(metadata) + self._diagnostic_suffix(diagnostics))
        self._set_badge("精确" if value.get("exact") else "近似", ok)

    def _diagnostic_suffix(self, diagnostics: list[dict[str, Any]]) -> str:
        if not diagnostics:
            return ""
        rendered = []
        for diagnostic in diagnostics[:4]:
            span = diagnostic.get("span")
            location = f" 第{span['line']}行:{span['column']}列" if span else ""
            rendered.append(f"{diagnostic.get('code')}: {diagnostic.get('message')}{location}")
        return " · " + "；".join(rendered)

    def _set_badge(self, text: str, ok: bool) -> None:
        self.badge.setText(text)
        self.badge.setProperty("state", "ok" if ok else "error")
        self._repolish()

    def _repolish(self) -> None:
        self.badge.style().unpolish(self.badge)
        self.badge.style().polish(self.badge)


class NotebookView(QWidget):
    changed = Signal()
    runCell = Signal(str)
    showAst = Signal(str)

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.cells: list[CellWidget] = []
        self.container = QWidget()
        self.container.setObjectName("notebookContainer")
        self.cell_layout = QVBoxLayout(self.container)
        self.cell_layout.setContentsMargins(12, 10, 12, 24)
        self.cell_layout.setSpacing(10)
        self.cell_layout.addStretch(1)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.container)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        add_math = QPushButton("+ 公式")
        add_math.setObjectName("primaryButton")
        add_math.clicked.connect(lambda: self.add_cell("math"))
        add_script = QPushButton("+ 脚本")
        add_script.clicked.connect(lambda: self.add_cell("script"))
        add_markdown = QPushButton("+ 说明")
        add_markdown.clicked.connect(lambda: self.add_cell("markdown"))
        add_plot = QPushButton("+ 绘图")
        add_plot.clicked.connect(lambda: self.add_cell("plot"))
        add_bar = QHBoxLayout()
        add_bar.addWidget(add_math)
        add_bar.addWidget(add_script)
        add_bar.addWidget(add_markdown)
        add_bar.addWidget(add_plot)
        add_bar.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(add_bar)
        layout.addWidget(self.scroll_area, 1)

    def add_cell(
        self, kind: str, source: str = "", plot: dict[str, Any] | None = None
    ) -> CellWidget:
        cell = Cell(kind=kind, source=source, plot=plot or {})
        widget = CellWidget(cell, self.settings, len(self.cells))
        widget.changed.connect(self.changed)
        widget.runCell.connect(self.runCell)
        widget.deleteCell.connect(self.delete_cell)
        widget.showAst.connect(self.showAst)
        self.cells.append(widget)
        self.cell_layout.insertWidget(self.cell_layout.count() - 1, widget)
        widget.formula.editor.setFocus() if widget.formula is not None else None
        self.changed.emit()
        return widget

    def delete_cell(self, cell_id: str) -> None:
        for index, widget in enumerate(self.cells):
            if widget.cell.id == cell_id:
                self.cells.pop(index)
                widget.setParent(None)
                widget.deleteLater()
                self._renumber()
                self.changed.emit()
                return

    def clear(self) -> None:
        for widget in self.cells:
            widget.setParent(None)
            widget.deleteLater()
        self.cells = []
        while self.cell_layout.count():
            item = self.cell_layout.takeAt(0)
            child = item.widget() if item is not None else None
            if child is not None:
                child.deleteLater()
        self.cell_layout.addStretch(1)

    def load_workspace(self, cells: list[Cell]) -> None:
        self.clear()
        for cell in cells:
            widget = CellWidget(cell, self.settings, len(self.cells))
            widget.changed.connect(self.changed)
            widget.runCell.connect(self.runCell)
            widget.deleteCell.connect(self.delete_cell)
            widget.showAst.connect(self.showAst)
            self.cells.append(widget)
            self.cell_layout.insertWidget(self.cell_layout.count() - 1, widget)
        self.changed.emit()

    def to_cells(self) -> list[Cell]:
        return [widget.to_cell() for widget in self.cells]

    def set_results(
        self,
        runs: list[dict[str, Any]],
        *,
        clear_missing: bool = True,
    ) -> None:
        by_id = {str(run.get("cellId")): run for run in runs}
        for widget in self.cells:
            if widget.cell.id in by_id:
                widget.set_result(by_id[widget.cell.id])
            elif clear_missing:
                widget.set_result(None)

    def _renumber(self) -> None:
        for index, widget in enumerate(self.cells):
            widget.index = index
            label = widget.findChild(QLabel, "cellNumber")
            if label is not None:
                label.setText(f"{index + 1:02d}")
