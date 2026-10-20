from __future__ import annotations

import html
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSignalBlocker, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QKeySequence, QTextCursor, QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDockWidget,
    QFileDialog,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QSpinBox,
    QStatusBar,
    QTabWidget,
    QTextBrowser,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from supercalc_core import API_VERSION, APP_VERSION
from supercalc_core.ast import format_ast_tree
from supercalc_core.exporting import workspace_to_markdown, write_export
from supercalc_core.plugins import PluginError, load_plugin_package
from supercalc_core.workspace import (
    HistoryEntry,
    RecentFiles,
    RecoveryStore,
    Settings,
    Workspace,
    WorkspaceError,
    app_data_dir,
    default_workspace,
)

from .client import ComputeClient
from .command_palette import Command, CommandPalette
from .gui_text import (
    algorithm_name,
    angle_name,
    assumption_name,
    assumptions_text,
    exactness_name,
    rounding_name,
    type_name,
)
from .help_dialog import (
    InterfaceGuideDialog,
    MarkdownHelpDialog,
    function_reference_path,
    scripting_guide_path,
)
from .notebook import NotebookView
from .plugin_dialog import PluginDialog


@dataclass
class Document:
    workspace: Workspace
    view: NotebookView
    path: Path | None = None
    modified: bool = False
    restoring: bool = False


def _resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / relative


class MainWindow(QMainWindow):
    def __init__(self, *, inprocess: bool = False) -> None:
        super().__init__()
        self.setWindowTitle("超级计算器")
        self.resize(1460, 930)
        self.setMinimumSize(QSize(980, 680))
        icon_path = _resource_path("assets/supercalc.svg")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.recent = RecentFiles()
        self.recovery = RecoveryStore()
        self._busy = False
        self._run_document: Document | None = None
        self._last_results: dict[str, dict[str, Any]] = {}
        self._last_diagnostics: list[tuple[str, dict[str, Any]]] = []
        self.client = ComputeClient(self)
        if inprocess:
            self.client.inprocess = True
        self.client.completed.connect(self._run_completed)
        self.client.failed.connect(self._run_failed)
        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_tabs()
        self._build_docks()
        self._build_status_bar()
        self._restore_window_state()
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(5000)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start()
        self.new_document()
        QTimer.singleShot(350, self._check_recovery)

    def _build_actions(self) -> None:
        self.action_new = self._action("新建", "Ctrl+N", self.new_document)
        self.action_open = self._action("打开…", "Ctrl+O", self.open_dialog)
        self.action_save = self._action("保存", "Ctrl+S", self.save_current)
        self.action_save_as = self._action("另存为…", "Ctrl+Shift+S", self.save_as)
        self.action_print = self._action("打印…", "Ctrl+P", self.print_current)
        self.action_close = self._action("关闭工作区", "Ctrl+W", self.close_current)
        self.action_exit = self._action("退出", "Ctrl+Q", self.close)
        self.action_undo = self._action("撤销", QKeySequence.StandardKey.Undo, self.undo)
        self.action_redo = self._action("重做", QKeySequence.StandardKey.Redo, self.redo)
        self.action_cut = self._action("剪切", QKeySequence.StandardKey.Cut, self.cut)
        self.action_copy = self._action("复制", QKeySequence.StandardKey.Copy, self.copy)
        self.action_paste = self._action("粘贴", QKeySequence.StandardKey.Paste, self.paste)
        self.action_copy_latex = self._action("复制公式源码", "Ctrl+Shift+C", self.copy_latex)
        self.action_run = self._action("运行全部", "F5", self.run_all)
        self.action_run_cell = self._action("运行当前单元", "Ctrl+Return", self.run_all)
        self.action_cancel = self._action("取消计算", "Shift+F5", self.cancel_run)
        self.action_palette = self._action("命令面板…", "Ctrl+Shift+P", self.show_palette)
        self.action_plugins = self._action("本地插件…", "", self.show_plugins)
        self.action_help_guide = self._action("界面与按钮说明", "F1", self.show_interface_guide)
        self.action_function_help = self._action("内置函数参考", "F2", self.show_function_reference)
        self.action_script_help = self._action("脚本编写指南", "F3", self.show_scripting_guide)
        self.action_about = self._action("关于超级计算器", "", self.show_about)
        self.action_export_latex = self._action(
            "导出公式源文件…", "", lambda: self.export_workspace("latex")
        )
        self.action_export_markdown = self._action(
            "导出说明文档…", "", lambda: self.export_workspace("markdown")
        )
        self.action_export_json = self._action(
            "导出结构化工作区…", "", lambda: self.export_workspace("json")
        )
        self.action_export_csv = self._action(
            "导出矩阵表格…", "", lambda: self.export_workspace("csv")
        )
        self.action_export_pdf = self._action("导出版式文档…", "", self.export_pdf)
        self.action_clear_recent = self._action("清除最近文件", "", self.clear_recent)

    def _action(self, text: str, shortcut: Any, callback) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(
                shortcut if isinstance(shortcut, QKeySequence) else QKeySequence(shortcut)
            )
        action.triggered.connect(callback)
        return action

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("文件")
        for action in (self.action_new, self.action_open, self.action_save, self.action_save_as):
            file_menu.addAction(action)
        self.recent_menu = file_menu.addMenu("最近文件")
        file_menu.addSeparator()
        export_menu = file_menu.addMenu("导出")
        for action in (
            self.action_export_latex,
            self.action_export_markdown,
            self.action_export_json,
            self.action_export_csv,
            self.action_export_pdf,
        ):
            export_menu.addAction(action)
        file_menu.addAction(self.action_print)
        file_menu.addSeparator()
        file_menu.addAction(self.action_close)
        file_menu.addAction(self.action_exit)

        edit_menu = self.menuBar().addMenu("编辑")
        for action in (self.action_undo, self.action_redo):
            edit_menu.addAction(action)
        edit_menu.addSeparator()
        for action in (
            self.action_cut,
            self.action_copy,
            self.action_paste,
            self.action_copy_latex,
        ):
            edit_menu.addAction(action)

        run_menu = self.menuBar().addMenu("运行")
        run_menu.addAction(self.action_run)
        run_menu.addAction(self.action_run_cell)
        run_menu.addAction(self.action_cancel)

        view_menu = self.menuBar().addMenu("视图")
        view_menu.addAction(self.action_palette)
        self.steps_action = QAction("显示计算步骤", self)
        self.steps_action.setCheckable(True)
        self.steps_action.setChecked(True)
        self.steps_action.toggled.connect(self._toggle_steps)
        view_menu.addAction(self.steps_action)

        tools_menu = self.menuBar().addMenu("工具")
        tools_menu.addAction(self.action_plugins)

        help_menu = self.menuBar().addMenu("帮助")
        help_menu.addAction(self.action_help_guide)
        help_menu.addAction(self.action_function_help)
        help_menu.addAction(self.action_script_help)
        help_menu.addAction(self.action_about)
        self._refresh_recent_menu()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("主工具栏", self)
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.addAction(self.action_run)
        toolbar.addAction(self.action_cancel)
        toolbar.addSeparator()
        toolbar.addWidget(QLabel("模式"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("精确", "exact")
        self.mode_combo.addItem("近似", "approx")
        self.mode_combo.currentIndexChanged.connect(self._settings_changed)
        toolbar.addWidget(self.mode_combo)
        toolbar.addWidget(QLabel("精度"))
        self.precision_spin = QSpinBox()
        self.precision_spin.setRange(2, 10_000)
        self.precision_spin.setValue(50)
        self.precision_spin.setSuffix(" 位")
        self.precision_spin.setToolTip("有效十进制位数；近似计算使用对应二进制精度")
        self.precision_spin.valueChanged.connect(self._settings_changed)
        toolbar.addWidget(self.precision_spin)
        toolbar.addWidget(QLabel("角度"))
        self.angle_combo = QComboBox()
        self.angle_combo.addItem("弧度", "radians")
        self.angle_combo.addItem("角度", "degrees")
        self.angle_combo.currentIndexChanged.connect(self._settings_changed)
        toolbar.addWidget(self.angle_combo)
        self.steps_check = QCheckBox("步骤")
        self.steps_check.setChecked(True)
        self.steps_check.toggled.connect(self._settings_changed)
        toolbar.addWidget(self.steps_check)
        toolbar.addSeparator()
        toolbar.addAction(self.action_palette)
        toolbar.addAction(self.action_plugins)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        offline = QLabel("本地计算 · 无网络")
        offline.setObjectName("mutedLabel")
        toolbar.addWidget(offline)
        self.addToolBar(toolbar)

    def _build_tabs(self) -> None:
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.setCentralWidget(self.tabs)

    def _build_docks(self) -> None:
        self.variable_tree = QTreeWidget()
        self.variable_tree.setHeaderLabels(["名称", "值", "类型", "精确性"])
        self.variable_tree.setAlternatingRowColors(True)
        self.variable_tree.setRootIsDecorated(False)
        self.function_list = QListWidget()
        self.assumption_list = QListWidget()
        self.history_list = QListWidget()
        left_tabs = QTabWidget()
        left_tabs.addTab(self.variable_tree, "变量")
        left_tabs.addTab(self.function_list, "函数")
        left_tabs.addTab(self.assumption_list, "假设")
        left_tabs.addTab(self.history_list, "历史")
        self.left_dock = QDockWidget("工作区状态", self)
        self.left_dock.setObjectName("leftDock")
        self.left_dock.setWidget(left_tabs)
        self.left_dock.setMinimumWidth(290)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.left_dock)

        self.inspector = QTextBrowser()
        self.inspector.setOpenExternalLinks(False)
        self.inspector.setHtml(
            "<p style='color:#6d7b8c'>运行单元后，这里显示类型、精确性、精度、假设、算法和步骤。</p>"
        )
        self.diagnostics = QTreeWidget()
        self.diagnostics.setHeaderLabels(["代码", "位置", "说明", "修复建议"])
        self.diagnostics.setAlternatingRowColors(True)
        self.diagnostics.itemDoubleClicked.connect(self._focus_diagnostic)
        right_tabs = QTabWidget()
        right_tabs.addTab(self.inspector, "结果检查")
        right_tabs.addTab(self.diagnostics, "诊断")
        self.right_dock = QDockWidget("可验证结果", self)
        self.right_dock.setObjectName("rightDock")
        self.right_dock.setWidget(right_tabs)
        self.right_dock.setMinimumWidth(330)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.right_dock)

    def _build_status_bar(self) -> None:
        status = QStatusBar()
        self.setStatusBar(status)
        self.status_mode = QLabel("精确模式 · 50 位")
        self.status_algorithm = QLabel("就绪")
        self.status_offline = QLabel(f"离线运行 · 接口 {API_VERSION} · 版本 {APP_VERSION}")
        self.status_offline.setObjectName("mutedLabel")
        status.addWidget(self.status_mode)
        status.addWidget(self.status_algorithm, 1)
        status.addPermanentWidget(self.status_offline)

    def new_document(self) -> None:
        workspace = default_workspace()
        self._add_document(workspace, None, modified=False)

    def _add_document(self, workspace: Workspace, path: Path | None, *, modified: bool) -> Document:
        view = NotebookView(workspace.settings)
        view.load_workspace(workspace.cells)
        document = Document(workspace=workspace, view=view, path=path, modified=modified)
        self._register_document_view(view, document)
        view.changed.connect(lambda doc=document: self._document_changed(doc))
        view.runCell.connect(lambda _cell_id, doc=document: self._run_document_now(doc))
        view.showAst.connect(self.show_ast)
        index = self.tabs.addTab(view, workspace.title)
        self.tabs.setCurrentIndex(index)
        self._sync_controls_from(document)
        self._update_tab_title(index)
        self._refresh_history()
        self._refresh_recent_menu()
        return document

    def current_document(self) -> Document | None:
        widget = self.tabs.currentWidget()
        for index in range(self.tabs.count()):
            candidate = self.tabs.widget(index)
            if candidate is widget:
                doc = self._document_for_view(candidate)
                return doc
        return None

    def _document_for_view(self, view: QWidget) -> Document | None:
        for index in range(self.tabs.count()):
            if self.tabs.widget(index) is view:
                # Documents are attached to views through the closure in
                # _add_document; the mapping below is populated lazily.
                pass
        return getattr(view, "_supercalc_document", None)

    def _register_document_view(self, view: NotebookView, document: Document) -> None:
        view._supercalc_document = document  # type: ignore[attr-defined]

    def _tab_changed(self, index: int) -> None:
        if index < 0:
            return
        view = self.tabs.widget(index)
        document = getattr(view, "_supercalc_document", None)
        if document is not None:
            self._sync_controls_from(document)
            self._refresh_history()

    def _sync_controls_from(self, document: Document) -> None:
        blockers = [
            QSignalBlocker(self.mode_combo),
            QSignalBlocker(self.precision_spin),
            QSignalBlocker(self.angle_combo),
            QSignalBlocker(self.steps_check),
            QSignalBlocker(self.steps_action),
        ]
        settings = document.workspace.settings
        self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findData(settings.mode)))
        self.precision_spin.setValue(settings.precision)
        self.angle_combo.setCurrentIndex(max(0, self.angle_combo.findData(settings.angle)))
        self.steps_check.setChecked(settings.show_steps)
        self.steps_action.setChecked(settings.show_steps)
        del blockers
        self._update_status_mode()

    def _settings_changed(self, *_args: Any) -> None:
        document = self.current_document()
        if document is None:
            return
        settings = Settings(
            mode=str(self.mode_combo.currentData()),
            precision=self.precision_spin.value(),
            rounding=document.workspace.settings.rounding,
            angle=str(self.angle_combo.currentData()),
            random_seed=document.workspace.settings.random_seed,
            show_steps=self.steps_check.isChecked(),
        )
        document.workspace.settings = settings
        document.view.settings = settings
        for cell in document.view.cells:
            cell.settings = settings
            if cell.plot_view is not None:
                cell.plot_view.settings = settings
        if document.restoring:
            document.restoring = False
            document.modified = False
        else:
            document.modified = True
        self._update_tab_title(self.tabs.currentIndex())
        self._update_status_mode()

    def _toggle_steps(self, checked: bool) -> None:
        blocker = QSignalBlocker(self.steps_check)
        self.steps_check.setChecked(checked)
        del blocker
        self._settings_changed()

    def _update_status_mode(self) -> None:
        document = self.current_document()
        if document is None:
            return
        settings = document.workspace.settings
        label = "精确模式" if settings.mode == "exact" else "近似模式"
        self.status_mode.setText(
            f"{label} · {settings.precision} 位 · "
            f"{rounding_name(settings.rounding)} · {angle_name(settings.angle)}"
        )

    def _document_changed(self, document: Document) -> None:
        if not document.modified:
            document.modified = True
            for index in range(self.tabs.count()):
                if getattr(self.tabs.widget(index), "_supercalc_document", None) is document:
                    self._update_tab_title(index)
                    break

    def _update_tab_title(self, index: int) -> None:
        if index < 0:
            return
        view = self.tabs.widget(index)
        document = getattr(view, "_supercalc_document", None)
        if document is None:
            return
        name = document.path.stem if document.path else document.workspace.title
        self.tabs.setTabText(index, ("● " if document.modified else "") + name)
        self.setWindowTitle(f"{name} — 超级计算器")

    def run_all(self) -> None:
        document = self.current_document()
        if document is not None:
            self._run_document_now(document)

    def _run_document_now(self, document: Document) -> None:
        if self._busy:
            return
        document.workspace.cells = document.view.to_cells()
        self._busy = True
        self._run_document = document
        self.action_run.setEnabled(False)
        self.status_algorithm.setText("计算中…")
        self.client.run_workspace(document.workspace)

    def cancel_run(self) -> None:
        if self._busy:
            self.client.cancel()
            self._busy = False
            self.action_run.setEnabled(True)
            self.status_algorithm.setText("计算已取消")

    def _run_completed(self, request_id: str, response: dict[str, Any]) -> None:
        self._busy = False
        self.action_run.setEnabled(True)
        document = self._run_document or self.current_document()
        if document is None:
            return
        runs = response.get("runs", [])
        document.view.set_results(runs)
        self._last_results = {
            str(run.get("cellId")): run for run in runs if run.get("result") is not None
        }
        history_data = response.get("history", [])
        if history_data:
            document.workspace.history.extend(HistoryEntry.from_dict(item) for item in history_data)
        environment = response.get("environment", {})
        self._update_environment(environment)
        self._refresh_history()
        self._update_diagnostics(runs)
        self._update_inspector(runs, environment)
        errors = sum(1 for run in runs if not run.get("ok"))
        suffix = "（兼容计算模式）" if self.client.used_fallback else ""
        self.status_algorithm.setText(
            f"完成：{len(runs) - errors} 个单元成功，{errors} 个失败{suffix}"
        )
        if document.workspace.extra.get("pluginErrors"):
            self.status_algorithm.setText("有插件未加载，请查看诊断")
        document.modified = True
        for index in range(self.tabs.count()):
            if getattr(self.tabs.widget(index), "_supercalc_document", None) is document:
                self._update_tab_title(index)
                break

    def _run_failed(self, request_id: str, message: str) -> None:
        self._busy = False
        self.action_run.setEnabled(True)
        self.status_algorithm.setText("本地计算未能完成")
        self.diagnostics.clear()
        log_path = app_data_dir() / "compute-worker.log"
        item = QTreeWidgetItem(
            [
                "SC7003",
                "",
                message,
                f"可重试。计算进程日志保存在：{log_path}",
            ]
        )
        self.diagnostics.addTopLevelItem(item)
        QMessageBox.warning(self, "本地计算未能完成", message)

    def _update_environment(self, environment: dict[str, Any]) -> None:
        self.variable_tree.clear()
        variables = environment.get("variables", {})
        for name, payload in sorted(variables.items()):
            value = payload.get("display", "") if isinstance(payload, dict) else str(payload)
            value_type = payload.get("type", "") if isinstance(payload, dict) else ""
            exact = payload.get("exact", True) if isinstance(payload, dict) else True
            item = QTreeWidgetItem(
                [
                    str(name),
                    str(value),
                    type_name(str(value_type)),
                    "精确" if exact else "近似",
                ]
            )
            item.setToolTip(1, str(value))
            self.variable_tree.addTopLevelItem(item)
        self.function_list.clear()
        for name, source in sorted(environment.get("functions", {}).items()):
            self.function_list.addItem(f"{name}  :  {source}")
        self.assumption_list.clear()
        assumptions = environment.get("assumptions", {})
        for name, flags in sorted(assumptions.items()):
            translated = "、".join(assumption_name(flag) for flag in flags)
            self.assumption_list.addItem(f"{name}：{translated}")
        if not assumptions:
            self.assumption_list.addItem("尚无变量假设")
        self.variable_tree.resizeColumnToContents(0)

    def _refresh_history(self) -> None:
        document = self.current_document()
        if document is None:
            return
        self.history_list.clear()
        for entry in reversed(document.workspace.history[-80:]):
            prefix = "✓" if entry.status == "ok" else "×"
            self.history_list.addItem(
                f"{prefix} {entry.timestamp[11:19]}  "
                f"{exactness_name(entry.exactness)}  {entry.display[:80]}"
            )

    def _update_diagnostics(self, runs: list[dict[str, Any]]) -> None:
        self.diagnostics.clear()
        self._last_diagnostics = []
        for run in runs:
            cell_id = str(run.get("cellId", ""))
            result = run.get("result") or {}
            script = run.get("script") or {}
            for diagnostic in (result.get("diagnostics") or []) + (script.get("diagnostics") or []):
                span = diagnostic.get("span")
                location = f"第 {span['line']} 行:{span['column']} 列" if span else ""
                item = QTreeWidgetItem(
                    [
                        str(diagnostic.get("code", "")),
                        location,
                        str(diagnostic.get("message", "")),
                        str(diagnostic.get("hint", "")),
                    ]
                )
                item.setData(0, Qt.ItemDataRole.UserRole, cell_id)
                item.setData(1, Qt.ItemDataRole.UserRole, span)
                self.diagnostics.addTopLevelItem(item)
                self._last_diagnostics.append((cell_id, diagnostic))
        for column in range(4):
            self.diagnostics.resizeColumnToContents(column)
        if self._last_diagnostics:
            self.right_dock.raise_()

    def _update_inspector(self, runs: list[dict[str, Any]], environment: dict[str, Any]) -> None:
        if not runs:
            return
        last = None
        for run in reversed(runs):
            if run.get("result") or run.get("script"):
                last = run
                break
        if last is None:
            return
        result = last.get("result")
        script = last.get("script")
        if script is not None:
            diagnostics = script.get("diagnostics", [])
            body = (
                f"<h3>脚本执行</h3><p>{'通过' if script.get('ok') else '失败'} · "
                f"{script.get('assertions', 0)} 个断言 · "
                f"{script.get('timingMs', 0):.1f} 毫秒</p>"
            )
            if diagnostics:
                body += "<h4>诊断</h4>" + "".join(
                    f"<p><b>{html.escape(d.get('code', ''))}</b> {html.escape(d.get('message', ''))}</p>"
                    for d in diagnostics
                )
            self.inspector.setHtml(body)
            return
        if not result:
            return
        value = result.get("value") or {}
        assumptions = result.get("assumptions") or {}
        steps = result.get("steps") or []
        rows = [
            ("显示", value.get("display", "")),
            ("类型", type_name(str(value.get("type", "")))),
            ("精确性", "精确" if value.get("exact") else "近似"),
            ("精度", f"{result.get('precision')} 位"),
            ("舍入", rounding_name(str(result.get("rounding", "")))),
            ("单位", result.get("unit") or "无"),
            ("算法", algorithm_name(str(result.get("algorithm") or ""))),
            ("假设", assumptions_text(assumptions)),
            ("耗时", f"{result.get('timingMs', 0):.2f} 毫秒"),
        ]
        body = "<h3>结果元数据</h3><table cellspacing='4'>"
        for label, value_text in rows:
            body += f"<tr><td><b>{html.escape(label)}</b></td><td>{html.escape(str(value_text))}</td></tr>"
        body += "</table>"
        if steps:
            body += "<h4>计算步骤</h4><ol>"
            for step in steps:
                body += (
                    f"<li><b>{html.escape(step.get('title', ''))}</b> — "
                    f"{html.escape(step.get('detail', ''))}</li>"
                )
            body += "</ol>"
        diagnostics = result.get("diagnostics", [])
        if diagnostics:
            body += "<h4>诊断</h4>"
            for diagnostic in diagnostics:
                body += (
                    f"<p><b>{html.escape(diagnostic.get('code', ''))}</b> "
                    f"{html.escape(diagnostic.get('message', ''))}<br>"
                    f"<small>{html.escape(diagnostic.get('hint', ''))}</small></p>"
                )
        self.inspector.setHtml(body)

    def _focus_diagnostic(self, item: QTreeWidgetItem, column: int) -> None:
        cell_id = item.data(0, Qt.ItemDataRole.UserRole)
        span = item.data(1, Qt.ItemDataRole.UserRole)
        document = self.current_document()
        if document is None:
            return
        for cell in document.view.cells:
            if cell.cell.id != cell_id:
                continue
            editor = cell.formula.editor if cell.formula is not None else cell.text_editor
            if editor is None:
                return
            editor.setFocus()
            if span:
                cursor = editor.textCursor()
                cursor.setPosition(min(len(editor.toPlainText()), int(span.get("start", 0))))
                if span.get("end") is not None:
                    cursor.setPosition(
                        min(len(editor.toPlainText()), int(span["end"])),
                        QTextCursor.MoveMode.KeepAnchor,
                    )
                editor.setTextCursor(cursor)
            return

    def save_current(self) -> bool:
        document = self.current_document()
        if document is None:
            return False
        if document.path is None:
            return self.save_as()
        return self._save_document(document, document.path)

    def save_as(self) -> bool:
        document = self.current_document()
        if document is None:
            return False
        initial = str(document.path or Path.home() / f"{document.workspace.title}.scws")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存工作区",
            initial,
            "超级计算器工作区 (*.scws);;结构化数据 (*.json)",
        )
        if not path:
            return False
        return self._save_document(document, Path(path))

    def _save_document(self, document: Document, path: Path) -> bool:
        try:
            document.workspace.cells = document.view.to_cells()
            actual = document.workspace.save(path)
        except (WorkspaceError, OSError) as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return False
        document.path = actual
        document.workspace.title = actual.stem
        document.modified = False
        self.recovery.clear(document.workspace)
        self.recent.add(actual)
        for index in range(self.tabs.count()):
            if getattr(self.tabs.widget(index), "_supercalc_document", None) is document:
                self._update_tab_title(index)
                break
        self.status_algorithm.setText(f"已保存：{actual}")
        self._refresh_recent_menu()
        return True

    def open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "打开工作区",
            str(Path.home()),
            "超级计算器工作区 (*.scws);;结构化数据 (*.json);;所有文件 (*.*)",
        )
        if path:
            self.open_path(Path(path))

    def open_path(self, path: Path) -> None:
        try:
            workspace = Workspace.load(path)
        except WorkspaceError as exc:
            QMessageBox.critical(self, "无法打开工作区", str(exc))
            return
        plugins = workspace.extra.get("plugins", [])
        if plugins:
            valid_plugins = []
            for plugin in plugins:
                try:
                    package = load_plugin_package(plugin["path"])
                    if package.sha256 != plugin.get("sha256"):
                        QMessageBox.warning(
                            self,
                            "插件权限需要重新确认",
                            f"插件 {package.manifest.name} 的内容已改变，已从本次加载中移除。"
                            "请通过“工具 → 本地插件”重新确认权限。",
                        )
                        continue
                    valid_plugins.append(plugin)
                except PluginError as exc:
                    QMessageBox.warning(self, "插件不可用", str(exc))
            workspace.extra["plugins"] = valid_plugins
        document = self._add_document(workspace, path, modified=False)
        document.restoring = True
        self.recent.add(path)
        self._refresh_recent_menu()
        self.status_algorithm.setText(
            "工作区为只读（来自更新格式）"
            if workspace.read_only
            else "工作区已打开，正在恢复计算状态…"
        )
        if not workspace.read_only:
            self._run_document_now(document)

    def close_current(self) -> None:
        self.close_tab(self.tabs.currentIndex())

    def close_tab(self, index: int) -> None:
        if index < 0:
            return
        view = self.tabs.widget(index)
        document = getattr(view, "_supercalc_document", None)
        if document is None:
            self.tabs.removeTab(index)
            return
        if document.modified:
            response = QMessageBox.question(
                self,
                "保存更改？",
                f"“{document.workspace.title}”有未保存的更改。",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if response == QMessageBox.StandardButton.Cancel:
                return
            if response == QMessageBox.StandardButton.Save:
                self.tabs.setCurrentIndex(index)
                if not self.save_current():
                    return
        self.recovery.clear(document.workspace)
        self.tabs.removeTab(index)
        if self.tabs.count() == 0:
            self.new_document()

    def _check_recovery(self) -> None:
        if os.environ.get("SUPERCALC_NO_RECOVERY") == "1":
            return
        recoveries = self.recovery.list()
        if not recoveries:
            return
        response = QMessageBox.question(
            self,
            "发现崩溃恢复副本",
            f"检测到 {len(recoveries)} 个自动保存的工作区。是否恢复最近一个？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if response == QMessageBox.StandardButton.Yes:
            self.open_path(recoveries[0])

    def _autosave(self) -> None:
        for index in range(self.tabs.count()):
            document = getattr(self.tabs.widget(index), "_supercalc_document", None)
            if document is not None and document.modified:
                try:
                    document.workspace.cells = document.view.to_cells()
                    self.recovery.write(document.workspace)
                except OSError:
                    pass

    def export_workspace(self, format_name: str) -> None:
        document = self.current_document()
        if document is None:
            return
        document.workspace.cells = document.view.to_cells()
        extension = {"latex": "tex", "markdown": "md", "json": "json", "csv": "csv"}[format_name]
        filters = {
            "latex": "数学公式源文件 (*.tex)",
            "markdown": "说明文档 (*.md)",
            "json": "结构化数据 (*.json)",
            "csv": "表格数据 (*.csv)",
        }
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出工作区",
            str(Path.home() / f"{document.workspace.title}.{extension}"),
            filters[format_name],
        )
        if not path:
            return
        try:
            write_export(document.workspace, path, format_name)
        except (ValueError, OSError) as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        self.status_algorithm.setText(f"已导出：{path}")

    def export_pdf(self) -> None:
        document = self.current_document()
        if document is None:
            return
        document.workspace.cells = document.view.to_cells()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出版式文档",
            str(Path.home() / f"{document.workspace.title}.pdf"),
            "便携文档 (*.pdf)",
        )
        if not path:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        text_document = QTextDocument()
        markdown = workspace_to_markdown(document.workspace)
        text_document.setPlainText(markdown)
        text_document.print_(printer)
        self.status_algorithm.setText(f"已导出版式文档：{path}")

    def print_current(self) -> None:
        document = self.current_document()
        if document is None:
            return
        document.workspace.cells = document.view.to_cells()
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        text_document = QTextDocument()
        text_document.setPlainText(workspace_to_markdown(document.workspace))
        text_document.print_(printer)

    def copy_latex(self) -> None:
        document = self.current_document()
        if document is None or not self._last_results:
            return
        for cell in reversed(document.view.cells):
            result = self._last_results.get(cell.cell.id)
            if result and result.get("result", {}).get("value"):
                value = result["result"]["value"]
                QApplication.clipboard().setText(value.get("latex") or value.get("display", ""))
                self.status_algorithm.setText("已复制公式源码")
                return

    def undo(self) -> None:
        widget = QApplication.focusWidget()
        if widget is not None and hasattr(widget, "undo"):
            widget.undo()

    def redo(self) -> None:
        widget = QApplication.focusWidget()
        if widget is not None and hasattr(widget, "redo"):
            widget.redo()

    def cut(self) -> None:
        widget = QApplication.focusWidget()
        if widget is not None and hasattr(widget, "cut"):
            widget.cut()

    def copy(self) -> None:
        widget = QApplication.focusWidget()
        if widget is not None and hasattr(widget, "copy"):
            widget.copy()

    def paste(self) -> None:
        widget = QApplication.focusWidget()
        if widget is not None and hasattr(widget, "paste"):
            widget.paste()

    def show_palette(self) -> None:
        commands = []
        for action in self.findChildren(QAction):
            if not action.text() or action.text().startswith("&"):
                continue
            shortcut = action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
            commands.append(Command(action.text().replace("&", ""), shortcut, action.trigger))
        dialog = CommandPalette(commands, self)
        dialog.exec()

    def show_ast(self, source: str) -> None:
        try:
            from supercalc_core.parser import parse

            parsed = parse(source)
            lines = [
                format_ast_tree(statement.expr) if hasattr(statement, "expr") else repr(statement)
                for statement in parsed.statements
            ]
        except Exception as exc:
            QMessageBox.warning(self, "无法生成语法树", str(exc))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("语法树")
        dialog.resize(680, 420)
        browser = QTextBrowser()
        browser.setPlainText("\n\n".join(lines))
        layout = QVBoxLayout(dialog)
        layout.addWidget(browser)
        dialog.exec()

    def show_plugins(self) -> None:
        document = self.current_document()
        if document is None:
            return
        dialog = PluginDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.package is None:
            return
        package = dialog.package
        plugins = [
            plugin
            for plugin in document.workspace.extra.get("plugins", [])
            if plugin.get("id") != package.manifest.id
        ]
        plugins.append(
            {
                "id": package.manifest.id,
                "name": package.manifest.name,
                "version": package.manifest.version,
                "path": str(package.root),
                "sha256": package.sha256,
                "permissions": package.manifest.permissions,
            }
        )
        document.workspace.extra["plugins"] = plugins
        document.modified = True
        self._update_tab_title(self.tabs.currentIndex())
        self.status_algorithm.setText(
            f"插件“{package.manifest.name}”已确认；运行工作区后其函数可用。"
        )

    def show_interface_guide(self) -> None:
        dialog = InterfaceGuideDialog(self)
        dialog.exec()

    def show_function_reference(self) -> None:
        dialog = MarkdownHelpDialog("内置函数参考", function_reference_path(), self)
        dialog.exec()

    def show_scripting_guide(self) -> None:
        dialog = MarkdownHelpDialog("脚本编写指南", scripting_guide_path(), self)
        dialog.exec()

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "关于超级计算器",
            (
                f"<h3>超级计算器 {APP_VERSION}</h3>"
                "<p>离线原生数学工作台，核心接口版本 1。</p>"
                "<p>精确有理数、符号与数值计算、矩阵、程序员工具、"
                "所见即所得公式输入、沙箱脚本和基础二维绘图。</p>"
                "<p>无遥测、无强制联网、不启动本地网络服务。</p>"
                "<p>数学后端与界面均在本机运行，不依赖浏览器。</p>"
            ),
        )

    def _refresh_recent_menu(self) -> None:
        self.recent_menu.clear()
        entries = self.recent.read()
        if not entries:
            empty = QAction("（无）", self)
            empty.setEnabled(False)
            self.recent_menu.addAction(empty)
        for entry in entries:
            action = QAction(entry, self)
            action.triggered.connect(lambda checked=False, path=entry: self.open_path(Path(path)))
            self.recent_menu.addAction(action)
        if entries:
            self.recent_menu.addSeparator()
            self.recent_menu.addAction(self.action_clear_recent)

    def clear_recent(self) -> None:
        self.recent.clear()
        self._refresh_recent_menu()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith((".scws", ".json")):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() in {".scws", ".json"}:
                self.open_path(path)
                break

    def _restore_window_state(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        settings = app.property("settings")
        if settings is None:
            return
        geometry = settings.value("window/geometry")
        state = settings.value("window/state")
        if geometry is not None:
            self.restoreGeometry(geometry)
        if state is not None:
            self.restoreState(state)

    def closeEvent(self, event: QCloseEvent) -> None:
        for index in range(self.tabs.count()):
            document = getattr(self.tabs.widget(index), "_supercalc_document", None)
            if document is None or not document.modified:
                continue
            self.tabs.setCurrentIndex(index)
            response = QMessageBox.question(
                self,
                "保存更改？",
                f"“{document.workspace.title}”有未保存的更改。",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if response == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if response == QMessageBox.StandardButton.Save and not self.save_current():
                event.ignore()
                return
        while self.tabs.count():
            widget = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if widget is not None:
                widget.deleteLater()
        app = QApplication.instance()
        settings = app.property("settings") if app is not None else None
        if settings is not None:
            settings.setValue("window/geometry", self.saveGeometry())
            settings.setValue("window/state", self.saveState())
        self.client.close()
        event.accept()
