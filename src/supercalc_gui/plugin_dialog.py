from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from supercalc_core.plugins import PluginError, PluginPackage, load_plugin_package


class PluginDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("本地插件")
        self.resize(620, 430)
        self.package: PluginPackage | None = None
        explanation = QLabel(
            "插件从本地目录加载，只能包含清单、文档和 .scscript 数学脚本。"
            "不加载原生二进制、不访问网络，也不会自动执行。"
        )
        explanation.setWordWrap(True)
        self.output = QTextBrowser()
        self.output.setOpenExternalLinks(False)
        choose = QPushButton("选择插件目录…")
        choose.setObjectName("primaryButton")
        choose.clicked.connect(self.choose)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(choose)
        buttons.addWidget(cancel)
        layout = QVBoxLayout(self)
        layout.addWidget(explanation)
        layout.addWidget(self.output, 1)
        layout.addLayout(buttons)

    def choose(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择 .scplugin 目录")
        if not directory:
            return
        try:
            package = load_plugin_package(directory)
        except PluginError as exc:
            QMessageBox.critical(self, "插件无效", str(exc))
            return
        permission_names = {
            "workspace.variables.read": "读取工作区变量",
            "clipboard.write": "写入系统剪贴板",
        }
        permissions = [
            permission_names.get(permission, permission)
            for permission in package.manifest.permissions
        ] or ["无额外权限"]
        response = QMessageBox.question(
            self,
            "确认加载插件",
            (
                f"名称：{package.manifest.name}\n"
                f"版本：{package.manifest.version}\n"
                f"标识：{package.manifest.id}\n"
                f"内容校验值：{package.sha256[:24]}…\n\n"
                f"请求权限：\n- " + "\n- ".join(permissions) + "\n\n"
                "仅在你信任该本地目录时继续。"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        self.package = package
        self.output.setHtml(
            f"<h3>{package.manifest.name}</h3>"
            f"<p>{package.manifest.description}</p>"
            f"<p><b>版本：</b>{package.manifest.version}<br>"
            f"<b>路径：</b>{package.root}<br>"
            f"<b>权限：</b>{'、'.join(permissions)}</p>"
            "<p>脚本将在受限数学沙箱中运行；无法访问文件系统、网络、进程或宿主程序运行时。</p>"
        )
        self.accept()
