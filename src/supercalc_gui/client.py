from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QProcess, QRunnable, QThreadPool, QTimer, Signal

from supercalc_core.workspace import Workspace, app_data_dir


def worker_command() -> list[str]:
    if getattr(sys, "frozen", False):
        sibling = Path(sys.executable).with_name("SuperCalcCLI.exe")
        if sibling.exists():
            return [str(sibling), "worker"]
    return [sys.executable, "-m", "supercalc_cli.worker"]


class _FallbackSignals(QObject):
    done = Signal(dict)


class _FallbackTask(QRunnable):
    def __init__(self, request: dict[str, Any]) -> None:
        super().__init__()
        self.request = request
        self.signals = _FallbackSignals()

    def run(self) -> None:
        try:
            from supercalc_cli.worker import process_request

            response = process_request(self.request)
        except Exception as exc:
            response = {
                "apiVersion": 1,
                "id": self.request.get("id"),
                "ok": False,
                "error": f"兼容计算失败：{exc}",
            }
        self.signals.done.emit(response)


class ComputeClient(QObject):
    completed = Signal(str, dict)
    failed = Signal(str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.process: QProcess | None = None
        self.buffer = b""
        self.pending: str | None = None
        self.pending_request: dict[str, Any] | None = None
        self.inprocess = os.environ.get("SUPERCALC_GUI_INPROCESS") == "1"
        self.used_fallback = False
        self.last_stderr = ""
        self._fallback_tasks: set[_FallbackTask] = set()
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self._on_timeout)

    def _ensure_process(self) -> bool:
        if self.inprocess:
            return True
        if self.process is not None and self.process.state() == QProcess.ProcessState.Running:
            return True
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        environment = process.processEnvironment()
        for key in list(environment.keys()):
            if key.upper().startswith("_PYI") or key.upper() in {"_MEIPASS", "_MEIPASS2"}:
                environment.remove(key)
        temp_directory = os.environ.get("TEMP") or os.environ.get("TMP") or tempfile.gettempdir()
        environment.insert("TEMP", temp_directory)
        environment.insert("TMP", temp_directory)
        environment.insert("PYTHONIOENCODING", "utf-8")
        environment.insert("PYTHONUTF8", "1")
        process.setProcessEnvironment(environment)
        if getattr(sys, "frozen", False):
            process.setWorkingDirectory(str(Path(sys.executable).resolve().parent))
        process.readyReadStandardOutput.connect(self._read_stdout)
        process.readyReadStandardError.connect(self._read_stderr)
        process.errorOccurred.connect(self._process_error)
        process.finished.connect(self._process_finished)
        command = worker_command()
        process.start(command[0], command[1:])
        if not process.waitForStarted(10000):
            return False
        self.process = process
        return True

    def run_workspace(self, workspace: Workspace, timeout_ms: int = 60_000) -> str:
        request_id = str(uuid.uuid4())
        request = {
            "id": request_id,
            "op": "workspace",
            "title": workspace.title,
            "settings": workspace.settings.to_dict(),
            "cells": [cell.to_dict() for cell in workspace.cells],
        }
        self.pending = request_id
        self.pending_request = request
        self.used_fallback = False
        self.timeout.start(timeout_ms)
        if self.inprocess:
            self._start_fallback(request)
            return request_id
        if not self._ensure_process():
            self._start_fallback(request)
            return request_id
        assert self.process is not None
        payload = json.dumps(request, ensure_ascii=False).encode("utf-8") + b"\n"
        self.process.write(payload)
        return request_id

    def cancel(self) -> None:
        self.timeout.stop()
        if self.process is not None and self.process.state() == QProcess.ProcessState.Running:
            self.process.kill()
            self.process.waitForFinished(2000)
        self.pending = None

    def _read_stdout(self) -> None:
        if self.process is None:
            return
        self.buffer += self.process.readAllStandardOutput().data()
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                response = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                if self.pending_request is not None:
                    request = self.pending_request
                    self._restart_after_failure()
                    self._start_fallback(request)
                continue
            self._deliver(response)

    def _read_stderr(self) -> None:
        if self.process is None:
            return
        data = (
            memoryview(self.process.readAllStandardError().data())
            .tobytes()
            .decode("utf-8", errors="replace")
        )
        if data.strip():
            self.last_stderr = data[-8000:]
            try:
                log_path = app_data_dir() / "compute-worker.log"
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write(data)
            except OSError:
                pass

    def _deliver(self, response: dict[str, Any]) -> None:
        request_id = str(response.get("id") or self.pending or "")
        if self.pending is None:
            return
        if self.pending and request_id != self.pending:
            return
        self.pending = None
        self.pending_request = None
        self.timeout.stop()
        if "runs" in response or "result" in response or response.get("ok"):
            self.completed.emit(request_id, response)
        else:
            detail = str(response.get("error") or "本地计算没有返回结果。")
            if self.last_stderr:
                detail += f"\n\n计算进程信息：{self.last_stderr[-1200:]}"
            self.failed.emit(request_id, detail)

    def _start_fallback(self, request: dict[str, Any]) -> None:
        if self.used_fallback:
            return
        self.used_fallback = True
        task = _FallbackTask(request)
        self._fallback_tasks.add(task)
        task.signals.done.connect(
            lambda response, current=task: self._fallback_done(response, current)
        )
        QThreadPool.globalInstance().start(task)

    def _fallback_done(self, response: dict[str, Any], task: _FallbackTask) -> None:
        self._fallback_tasks.discard(task)
        self._deliver(response)

    def _restart_after_failure(self) -> None:
        if self.process is not None:
            self.process.kill()
            self.process.waitForFinished(1500)
            self.process = None
        self.buffer = b""

    def _on_timeout(self) -> None:
        if self.pending:
            request_id = self.pending
            self.pending = None
            self.pending_request = None
            if self.process is not None:
                self.process.kill()
                self.process.waitForFinished(2000)
            self.failed.emit(request_id, "计算超时，已终止本地计算进程。")

    def _process_error(self, error: QProcess.ProcessError) -> None:
        if self.pending and self.pending_request is not None:
            request = self.pending_request
            self._restart_after_failure()
            self._start_fallback(request)

    def _process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        if self.pending and self.pending_request is not None:
            request = self.pending_request
            self._restart_after_failure()
            self._start_fallback(request)

    def close(self) -> None:
        self.timeout.stop()
        if self.process is not None:
            self.process.terminate()
            if not self.process.waitForFinished(1500):
                self.process.kill()
            self.process = None
