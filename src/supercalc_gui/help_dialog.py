from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QPushButton, QTextBrowser, QVBoxLayout, QWidget


def interface_guide_path() -> Path:
    return _document_path("interface-guide.md")


def function_reference_path() -> Path:
    return _document_path("function-reference.md")


def scripting_guide_path() -> Path:
    return _document_path("scripting-guide.md")


def _document_path(filename: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / "docs" / filename


class MarkdownHelpDialog(QDialog):
    def __init__(
        self,
        title: str,
        document_path: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(980, 760)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        try:
            browser.setMarkdown(document_path.read_text(encoding="utf-8"))
        except OSError:
            browser.setPlainText(
                "帮助文档未找到。请重新解压完整的超级计算器程序包，"
                "并确保 docs 文件夹与主程序位于同一发布目录。"
            )
        close_button = QPushButton("关闭")
        close_button.setObjectName("primaryButton")
        close_button.clicked.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addWidget(browser, 1)
        layout.addWidget(close_button, 0, Qt.AlignmentFlag.AlignRight)


class InterfaceGuideDialog(MarkdownHelpDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("界面与按钮说明", interface_guide_path(), parent)
