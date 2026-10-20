from __future__ import annotations

import io

from matplotlib import mathtext
from matplotlib.font_manager import FontProperties
from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPixmap,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from supercalc_core.ast import ExprStatement, FunctionDef
from supercalc_core.latex import expr_to_latex
from supercalc_core.parser import parse


class _MathHighlighter(QSyntaxHighlighter):
    KEYWORDS = {
        "solve",
        "diff",
        "integrate",
        "limit",
        "series",
        "summation",
        "product",
        "assume",
        "simplify",
        "expand",
        "factor",
        "matrix",
        "det",
        "inv",
    }

    def __init__(self, document) -> None:
        super().__init__(document)
        self.function_format = QTextCharFormat()
        self.function_format.setForeground(QColor("#1769aa"))
        self.function_format.setFontWeight(QFont.Weight.DemiBold)
        self.number_format = QTextCharFormat()
        self.number_format.setForeground(QColor("#9a5b00"))
        self.comment_format = QTextCharFormat()
        self.comment_format.setForeground(QColor("#708090"))
        self.comment_format.setFontItalic(True)

    def highlightBlock(self, text: str) -> None:
        import re

        for match in re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]*\b", text):
            word = match.group(0)
            if word in self.KEYWORDS or (
                match.end() < len(text) and text[match.end() :].lstrip().startswith("(")
            ):
                self.setFormat(match.start(), len(word), self.function_format)
        for match in re.finditer(r"\b(?:0[xob][0-9A-Fa-f_]+|\d[\d_]*(?:\.\d+)?)\b", text):
            self.setFormat(match.start(), match.end() - match.start(), self.number_format)
        if "#" in text:
            index = text.find("#")
            self.setFormat(index, len(text) - index, self.comment_format)


class FormulaTextEdit(QPlainTextEdit):
    runRequested = Signal()


class FormulaPreview(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._fallback = ""
        self.last_error = ""
        self.setMinimumHeight(54)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_formula(self, latex: str, fallback: str = "") -> None:
        self._fallback = fallback
        if not latex:
            self._pixmap = None
            self.update()
            return
        try:
            output = io.BytesIO()
            mathtext.math_to_image(
                f"${latex}$",
                output,
                prop=FontProperties(size=18),
                dpi=150,
                format="png",
            )
            pixmap = QPixmap()
            loaded = pixmap.loadFromData(output.getvalue())
            self._pixmap = pixmap if not pixmap.isNull() else None
            if not loaded:
                self.last_error = "无法解码公式排版图像"
        except Exception as exc:
            self.last_error = str(exc)
            self._pixmap = None
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#fbfcfe"))
        if self._pixmap is not None:
            target = self._pixmap.scaledToHeight(
                min(46, self.height() - 8),
                Qt.TransformationMode.SmoothTransformation,
            )
            if target.width() > self.width() - 16:
                target = target.scaledToWidth(
                    self.width() - 16,
                    Qt.TransformationMode.SmoothTransformation,
                )
            painter.drawPixmap(
                QPoint(
                    (self.width() - target.width()) // 2, (self.height() - target.height()) // 2
                ),
                target,
            )
        else:
            painter.setPen(QColor("#758196"))
            font = QFont("Cascadia Mono", 11)
            font.setStyleHint(QFont.StyleHint.Monospace)
            painter.setFont(font)
            painter.drawText(
                self.rect().adjusted(10, 0, -10, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                self._fallback or "输入公式以显示排版预览",
            )
        painter.end()


class FormulaEditor(QWidget):
    textChanged = Signal()
    runRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.preview = FormulaPreview(self)
        self.editor = FormulaTextEdit(self)
        self.editor.setPlaceholderText("输入表达式，例如 1/3 + 1/6、diff(sin(x), x)")
        self.editor.setFont(QFont("Cascadia Mono", 11))
        self.editor.setMinimumHeight(78)
        self.editor.setTabChangesFocus(True)
        self.highlighter = _MathHighlighter(self.editor.document())
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(280)
        self._timer.timeout.connect(self.refresh_preview)
        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.runRequested.connect(self.runRequested)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(3)
        templates = [
            ("分式", "fraction", "a/b"),
            ("幂", "power", "x^2"),
            ("根式", "sqrt", "√"),
            ("函数", "function", "f(x)"),
            ("矩阵", "matrix", "▦"),
            ("求和", "sum", "Σ"),
            ("积分", "integral", "∫"),
            ("导数", "derivative", "d/dx"),
        ]
        template_label = QLabel("结构")
        template_label.setObjectName("mutedLabel")
        toolbar.addWidget(template_label)
        for label, action, glyph in templates:
            button = QToolButton()
            button.setText(glyph)
            button.setToolTip(f"{label}模板")
            button.setObjectName("templateButton")
            button.clicked.connect(lambda checked=False, name=action: self.insert_template(name))
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        source_button = QToolButton()
        source_button.setText("源码")
        source_button.setCheckable(True)
        source_button.setToolTip("显示/隐藏线性源码")
        source_button.toggled.connect(self.editor.setVisible)
        toolbar.addWidget(source_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(toolbar)
        layout.addWidget(self.preview)
        layout.addWidget(self.editor)

    def _on_text_changed(self) -> None:
        self._timer.start()
        self.textChanged.emit()

    def refresh_preview(self) -> None:
        source = self.editor.toPlainText().strip()
        if not source:
            self.preview.set_formula("", "")
            return
        try:
            program = parse(source)
            if len(program.statements) == 1:
                statement = program.statements[0]
                if isinstance(statement, ExprStatement):
                    latex = expr_to_latex(statement.expr)
                elif isinstance(statement, FunctionDef) and statement.body is not None:
                    latex = (
                        rf"{statement.name}\left({', '.join(statement.params)}\right)"
                        rf" := {expr_to_latex(statement.body)}"
                    )
                else:
                    latex = ""
            else:
                latex = ""
        except Exception:
            latex = ""
        self.preview.set_formula(latex, source.replace("\n", "  "))

    def setPlainText(self, text: str) -> None:
        self.editor.setPlainText(text)

    def toPlainText(self) -> str:
        return self.editor.toPlainText()

    def insert_template(self, name: str) -> None:
        cursor = self.editor.textCursor()
        selection = cursor.selectedText().replace("\u2029", "\n")
        templates: dict[str, tuple[str, int]] = {
            "fraction": (f"({selection or ''})/(", len(selection) + 4 if selection else 3),
            "power": (f"({selection or ''})^(", len(selection) + 4 if selection else 3),
            "sqrt": (f"sqrt({selection})", len(selection) + 5),
            "function": (f"f({selection})", 2),
            "matrix": ("[[1, 0], [0, 1]]", 2),
            "sum": (f"summation({selection or 'k'}, k, 1, n)", 11),
            "integral": (
                f"integrate({selection or 'f(x)'}, x)",
                len(selection) + 11 if selection else 11,
            ),
            "derivative": (
                f"diff({selection or 'f(x)'}, x)",
                len(selection) + 6 if selection else 6,
            ),
        }
        text, relative = templates[name]
        cursor.insertText(text)
        position = cursor.position() - (len(text) - relative)
        cursor.setPosition(position)
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    def focus_editor(self) -> None:
        self.editor.setFocus()
