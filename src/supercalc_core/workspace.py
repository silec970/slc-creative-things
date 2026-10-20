from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .api import Engine, EngineConfig
from .models import EvaluationResult, RunResult

SCHEMA_VERSION = 1
WORKSPACE_EXTENSION = ".scws"


class WorkspaceError(ValueError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class Settings:
    mode: str = "exact"
    precision: int = 50
    rounding: str = "half_even"
    angle: str = "radians"
    random_seed: int = 0
    show_steps: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "precision": self.precision,
            "rounding": self.rounding,
            "angle": self.angle,
            "randomSeed": self.random_seed,
            "showSteps": self.show_steps,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Settings:
        data = data or {}
        precision = int(data.get("precision", 50))
        if not 2 <= precision <= 10_000:
            raise WorkspaceError("精度必须在 2 到 10000 位之间")
        mode = str(data.get("mode", "exact"))
        if mode not in {"exact", "approx"}:
            raise WorkspaceError("未知计算模式")
        return cls(
            mode=mode,
            precision=precision,
            rounding=str(data.get("rounding", "half_even")),
            angle=str(data.get("angle", "radians")),
            random_seed=int(data.get("randomSeed", 0)),
            show_steps=bool(data.get("showSteps", True)),
        )

    def engine_config(self) -> EngineConfig:
        return EngineConfig(
            mode=self.mode,
            precision=self.precision,
            rounding=self.rounding,
            angle=self.angle,
            random_seed=self.random_seed,
        )


@dataclass
class Cell:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    kind: str = "math"
    source: str = ""
    tags: list[str] = field(default_factory=list)
    plot: dict[str, Any] = field(default_factory=dict)
    collapsed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "source": self.source,
            "tags": self.tags,
            "plot": self.plot,
            "collapsed": self.collapsed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Cell:
        kind = str(data.get("kind", "math"))
        if kind not in {"math", "script", "markdown", "plot"}:
            raise WorkspaceError(f"未知单元类型：{kind}")
        return cls(
            id=str(data.get("id") or uuid.uuid4()),
            kind=kind,
            source=str(data.get("source", "")),
            tags=[str(tag) for tag in data.get("tags", [])],
            plot=dict(data.get("plot") or {}),
            collapsed=bool(data.get("collapsed", False)),
        )


@dataclass
class HistoryEntry:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    cell_id: str = ""
    timestamp: str = field(default_factory=_now)
    source_hash: str = ""
    status: str = "ok"
    exactness: str = ""
    display: str = ""
    code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "cellId": self.cell_id,
            "timestamp": self.timestamp,
            "sourceHash": self.source_hash,
            "status": self.status,
            "exactness": self.exactness,
            "display": self.display,
            "code": self.code,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HistoryEntry:
        return cls(
            id=str(data.get("id") or uuid.uuid4()),
            cell_id=str(data.get("cellId", "")),
            timestamp=str(data.get("timestamp", _now())),
            source_hash=str(data.get("sourceHash", "")),
            status=str(data.get("status", "ok")),
            exactness=str(data.get("exactness", "")),
            display=str(data.get("display", "")),
            code=str(data.get("code", "")),
        )


@dataclass
class Workspace:
    title: str = "未命名工作区"
    settings: Settings = field(default_factory=Settings)
    cells: list[Cell] = field(default_factory=list)
    history: list[HistoryEntry] = field(default_factory=list)
    snapshot: dict[str, Any] = field(default_factory=dict)
    workspace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    app_version: str = "0.1.0"
    read_only: bool = False
    source_path: Path | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schemaVersion": SCHEMA_VERSION,
            "appVersion": self.app_version,
            "workspaceId": self.workspace_id,
            "title": self.title,
            "createdAt": self.created_at,
            "updatedAt": _now(),
            "settings": self.settings.to_dict(),
            "cells": [cell.to_dict() for cell in self.cells],
            "history": [entry.to_dict() for entry in self.history],
            "snapshot": self.snapshot,
        }
        data.update(self.extra)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, path: Path | None = None) -> Workspace:
        if not isinstance(data, dict):
            raise WorkspaceError("工作区根节点必须是 JSON 对象")
        schema_version = int(data.get("schemaVersion", 1))
        cells_data = data.get("cells", [])
        if not isinstance(cells_data, list):
            raise WorkspaceError("cells 必须是数组")
        workspace = cls(
            title=str(data.get("title", "未命名工作区")),
            settings=Settings.from_dict(data.get("settings")),
            cells=[Cell.from_dict(cell) for cell in cells_data],
            history=[HistoryEntry.from_dict(item) for item in data.get("history", [])],
            snapshot=dict(data.get("snapshot") or {}),
            workspace_id=str(data.get("workspaceId") or uuid.uuid4()),
            created_at=str(data.get("createdAt") or _now()),
            updated_at=str(data.get("updatedAt") or _now()),
            app_version=str(data.get("appVersion", "0.0.0")),
            source_path=path,
        )
        if schema_version > SCHEMA_VERSION:
            workspace.read_only = True
        workspace.extra = {
            key: value
            for key, value in data.items()
            if key
            not in {
                "schemaVersion",
                "appVersion",
                "workspaceId",
                "title",
                "createdAt",
                "updatedAt",
                "settings",
                "cells",
                "history",
                "snapshot",
            }
        }
        return workspace

    def save(self, path: str | Path) -> Path:
        if self.read_only:
            raise WorkspaceError("该工作区来自更新版本，当前只能只读打开")
        target = Path(path)
        if target.suffix.lower() != WORKSPACE_EXTENSION:
            target = target.with_suffix(WORKSPACE_EXTENSION)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.copy2(target, target.with_suffix(target.suffix + ".bak"))
        payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.stem}.",
            suffix=".tmp",
            dir=target.parent,
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, target)
        except Exception:
            Path(temporary_name).unlink(missing_ok=True)
            raise
        self.source_path = target
        self.updated_at = _now()
        return target

    @classmethod
    def load(cls, path: str | Path) -> Workspace:
        source = Path(path)
        try:
            text = source.read_text(encoding="utf-8")
        except OSError as exc:
            raise WorkspaceError(f"无法读取工作区：{exc}") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise WorkspaceError(
                f"工作区 JSON 损坏：第 {exc.lineno} 行第 {exc.colno} 列，{exc.msg}"
            ) from exc
        return cls.from_dict(data, path=source)


@dataclass
class CellRun:
    cell: Cell
    result: EvaluationResult | None = None
    script_result: RunResult | None = None

    @property
    def ok(self) -> bool:
        if self.cell.kind in {"markdown", "plot"}:
            return True
        if self.script_result is not None:
            return self.script_result.ok
        return self.result is not None and self.result.ok

    def diagnostics(self):
        if self.script_result is not None:
            return self.script_result.diagnostics
        return self.result.diagnostics if self.result else []


def run_workspace(workspace: Workspace) -> tuple[Engine, list[CellRun]]:
    engine = Engine(workspace.settings.engine_config())
    plugin_errors: list[str] = []
    for plugin_info in workspace.extra.get("plugins", []):
        try:
            from .plugins import execute_plugin, load_plugin_package

            package = load_plugin_package(plugin_info["path"])
            expected_hash = str(plugin_info.get("sha256", ""))
            if expected_hash and package.sha256 != expected_hash:
                plugin_errors.append(f"插件 {package.manifest.name} 的内容已改变，需重新确认权限")
                continue
            plugin_result = execute_plugin(package, engine)
            if not plugin_result.ok:
                message = (
                    plugin_result.diagnostics[0].message
                    if plugin_result.diagnostics
                    else "未知错误"
                )
                plugin_errors.append(f"插件 {package.manifest.name} 加载失败：{message}")
        except Exception as exc:
            plugin_errors.append(f"插件加载失败：{exc}")
    runs: list[CellRun] = []
    for cell in workspace.cells:
        if cell.kind == "markdown" or cell.kind == "plot":
            runs.append(CellRun(cell))
            continue
        if cell.kind == "script":
            script_run = engine.run_script(cell.source)
            runs.append(CellRun(cell, script_result=script_run))
            status = "ok" if script_run.ok else "error"
            exactness = "script"
            display = f"{script_run.assertions} assertions"
            code = (
                ""
                if script_run.ok
                else (script_run.diagnostics[0].code if script_run.diagnostics else "")
            )
        else:
            math_run = engine.evaluate(cell.source)
            runs.append(CellRun(cell, result=math_run))
            status = "ok" if math_run.ok else "error"
            exactness = math_run.exactness
            display = math_run.value.display if math_run.value else ""
            code = (
                ""
                if math_run.ok
                else (math_run.diagnostics[0].code if math_run.diagnostics else "")
            )
        workspace.history.append(
            HistoryEntry(
                cell_id=cell.id,
                source_hash=hashlib.sha256(cell.source.encode()).hexdigest(),
                status=status,
                exactness=exactness,
                display=display,
                code=code,
            )
        )
        if not runs[-1].ok:
            break
    workspace.snapshot = engine.snapshot().to_dict()
    if plugin_errors:
        workspace.extra["pluginErrors"] = plugin_errors
    else:
        workspace.extra.pop("pluginErrors", None)
    return engine, runs


def default_workspace() -> Workspace:
    return Workspace(
        title="未命名工作区",
        cells=[
            Cell(kind="math", source="1/3 + 1/6"),
            Cell(kind="math", source="solve(x^2 = 9, x, real)"),
            Cell(
                kind="markdown", source="# 新工作区\n\n在公式单元中直接输入，按 Ctrl+Enter 运行。"
            ),
        ],
    )


def app_data_dir() -> Path:
    override = os.environ.get("SUPERCALC_DATA_DIR")
    if override:
        return Path(override)
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif os.sys.platform == "darwin":  # type: ignore[attr-defined]
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / "SuperCalc"


class RecoveryStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (app_data_dir() / "recovery")

    def recovery_path(self, workspace: Workspace) -> Path:
        return self.root / f"{workspace.workspace_id}.autosave.scws"

    def write(self, workspace: Workspace) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.recovery_path(workspace)
        payload = json.dumps(workspace.to_dict(), ensure_ascii=False, indent=2)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, path)
        return path

    def list(self) -> list[Path]:
        if not self.root.exists():
            return []
        return sorted(
            self.root.glob("*.autosave.scws"), key=lambda p: p.stat().st_mtime, reverse=True
        )

    def clear(self, workspace: Workspace) -> None:
        path = self.recovery_path(workspace)
        if path.exists():
            path.unlink()


class RecentFiles:
    def __init__(self, path: Path | None = None, limit: int = 12) -> None:
        self.path = path or (app_data_dir() / "recent.json")
        self.limit = limit

    def read(self) -> list[str]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return [str(item) for item in data if Path(item).exists()]
        except (OSError, json.JSONDecodeError, TypeError):
            return []

    def add(self, path: str | Path) -> list[str]:
        resolved = str(Path(path).resolve())
        entries = [entry for entry in self.read() if entry != resolved]
        entries.insert(0, resolved)
        entries = entries[: self.limit]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)
        return entries

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
