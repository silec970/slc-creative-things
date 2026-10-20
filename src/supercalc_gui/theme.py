APP_STYLE = """
QWidget {
    color: #202a38;
    font-family: "Microsoft YaHei UI", "Segoe UI";
    font-size: 10pt;
}
QMainWindow, QDialog {
    background: #eef2f7;
}
QMenuBar {
    background: #f8fafc;
    border-bottom: 1px solid #d8e0ea;
}
QMenuBar::item:selected, QMenu::item:selected {
    background: #dceafb;
    color: #0f4f87;
}
QToolBar {
    background: #f8fafc;
    border-bottom: 1px solid #d8e0ea;
    spacing: 6px;
    padding: 5px 8px;
}
QStatusBar {
    background: #f8fafc;
    border-top: 1px solid #d8e0ea;
}
QDockWidget {
    titlebar-close-icon: none;
    font-weight: 600;
}
QDockWidget::title {
    background: #e4ebf4;
    padding: 7px 10px;
    border-bottom: 1px solid #d2dce8;
}
QTabWidget::pane {
    border: none;
    background: #eef2f7;
}
QTabBar::tab {
    background: #e2e8f0;
    padding: 8px 18px;
    border: 1px solid #d1d9e3;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #fbfcfe;
    color: #0f5b96;
    font-weight: 600;
}
QFrame#cellCard {
    background: #fbfcfe;
    border: 1px solid #d8e3ef;
    border-radius: 8px;
}
QFrame#cellCard:hover {
    border-color: #b8cee4;
}
QLabel#cellNumber {
    color: #7d8b9c;
    font-family: "Cascadia Mono";
    font-weight: 700;
}
QLabel#resultText {
    color: #123b5d;
    font-family: "Cascadia Mono", "Microsoft YaHei UI";
    font-size: 13pt;
    padding: 7px 9px;
    background: #f2f7fd;
    border-radius: 5px;
}
QLabel#mutedLabel {
    color: #6d7b8c;
    font-size: 9pt;
}
QLabel#resultBadge {
    border-radius: 8px;
    padding: 2px 8px;
    background: #edf1f5;
    color: #667385;
    font-size: 8.5pt;
}
QLabel#resultBadge[state="ok"] {
    background: #e2f5eb;
    color: #176b46;
}
QLabel#resultBadge[state="error"] {
    background: #fde7e7;
    color: #a02727;
}
QPlainTextEdit, QTextEdit, QTextBrowser, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #ffffff;
    border: 1px solid #cfd9e5;
    border-radius: 5px;
    padding: 5px 7px;
    selection-background-color: #b9d7f5;
}
QPlainTextEdit:focus, QTextEdit:focus, QLineEdit:focus {
    border-color: #4d8dca;
}
QPushButton {
    background: #f7f9fb;
    border: 1px solid #cfd9e5;
    border-radius: 5px;
    padding: 6px 12px;
}
QPushButton:hover {
    background: #edf4fb;
    border-color: #a9c3dc;
}
QPushButton#primaryButton {
    background: #1769aa;
    color: white;
    border-color: #1769aa;
    font-weight: 600;
}
QPushButton#primaryButton:hover {
    background: #0f5b96;
}
QToolButton {
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 4px 7px;
}
QToolButton:hover {
    background: #e7eff8;
    border-color: #c8d7e6;
}
QToolButton#templateButton {
    font-family: "Cambria Math", "Segoe UI Symbol";
    min-width: 26px;
    background: #f4f7fb;
    border: 1px solid #e1e7ef;
}
QScrollArea, QWidget#notebookContainer {
    background: #eef2f7;
}
QListWidget, QTreeWidget {
    background: #fbfcfe;
    border: 1px solid #dbe3ec;
    border-radius: 4px;
    alternate-background-color: #f5f8fb;
}
QHeaderView::section {
    background: #edf2f7;
    border: none;
    border-right: 1px solid #dbe3ec;
    border-bottom: 1px solid #dbe3ec;
    padding: 5px;
    font-weight: 600;
}
QLineEdit#commandInput {
    font-size: 12pt;
    padding: 9px;
}
"""
