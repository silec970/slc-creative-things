from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)


@dataclass
class Command:
    title: str
    shortcut: str
    callback: Callable[[], None]
    keywords: str = ""


class CommandPalette(QDialog):
    def __init__(self, commands: list[Command], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("命令面板")
        self.resize(560, 390)
        self.commands = commands
        self.input = QLineEdit()
        self.input.setPlaceholderText("输入命令名称或关键字…")
        self.input.textChanged.connect(self._filter)
        self.list = QListWidget()
        self.list.itemActivated.connect(self._activate)
        layout = QVBoxLayout(self)
        layout.addWidget(self.input)
        layout.addWidget(self.list)
        for command in commands:
            item = QListWidgetItem(f"{command.title}    {command.shortcut}")
            item.setData(Qt.ItemDataRole.UserRole, command)
            self.list.addItem(item)
        self.input.setFocus()

    def _filter(self, text: str) -> None:
        needle = text.strip().lower()
        for index in range(self.list.count()):
            item = self.list.item(index)
            command: Command = item.data(Qt.ItemDataRole.UserRole)
            haystack = f"{command.title} {command.shortcut} {command.keywords}".lower()
            item.setHidden(bool(needle) and needle not in haystack)

    def _activate(self, item: QListWidgetItem) -> None:
        command: Command = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
        command.callback()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self.list.currentItem()
            if item is None:
                for index in range(self.list.count()):
                    candidate = self.list.item(index)
                    if not candidate.isHidden():
                        item = candidate
                        break
            if item is not None:
                self._activate(item)
                return
        if event.key() == Qt.Key.Key_Down:
            self.list.setFocus()
            self.list.setCurrentRow(max(0, self.list.currentRow()))
            return
        super().keyPressEvent(event)
