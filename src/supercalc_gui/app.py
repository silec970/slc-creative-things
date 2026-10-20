from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow, _resource_path
from .theme import APP_STYLE


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("SuperCalc")
    app.setApplicationDisplayName("超级计算器")
    app.setOrganizationName("SuperCalc")
    app.setOrganizationDomain("supercalc.local")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    icon_path = _resource_path("assets/supercalc.svg")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    settings = QSettings("SuperCalc", "SuperCalc")
    app.setProperty("settings", settings)
    window = MainWindow(inprocess=os.environ.get("SUPERCALC_GUI_INPROCESS") == "1")
    window.show()
    if "--smoke-test" in sys.argv:
        window.run_all()

        def finish_smoke() -> None:
            screenshot = os.environ.get("SUPERCALC_SMOKE_SCREENSHOT")
            if screenshot:
                window.grab().save(screenshot)
            status_path = os.environ.get("SUPERCALC_SMOKE_STATUS")
            if status_path:
                document = window.current_document()
                first_result = (
                    document.view.cells[0].result.text()
                    if document is not None and document.view.cells
                    else ""
                )
                Path(status_path).write_text(
                    f"{window.status_algorithm.text()}\n{first_result}\n",
                    encoding="utf-8",
                )
            document = window.current_document()
            if document is not None:
                document.modified = False
            window.close()
            window.client.close()
            app.quit()

        deadline = time.monotonic() + 25

        def poll_smoke() -> None:
            document = window.current_document()
            first_result = (
                document.view.cells[0].result.text()
                if document is not None and document.view.cells
                else ""
            )
            finished = bool(first_result) and first_result not in {
                "尚未运行",
                "计算中…",
            }
            if (not window._busy and finished) or time.monotonic() >= deadline:
                finish_smoke()
                return
            QTimer.singleShot(150, poll_smoke)

        QTimer.singleShot(150, poll_smoke)
    if len(sys.argv) > 1:
        candidate = Path(sys.argv[1])
        if candidate.is_file() and not candidate.name.startswith("--"):
            window.open_path(candidate)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
