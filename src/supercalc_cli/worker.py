from __future__ import annotations

import json
import sys
import traceback
from typing import Any

from supercalc_core import Engine
from supercalc_core.workspace import Cell, Settings, Workspace, run_workspace


def _response(request_id: Any, ok: bool, **payload: Any) -> dict[str, Any]:
    return {"apiVersion": 1, "id": request_id, "ok": ok, **payload}


def process_request(request: dict[str, Any]) -> dict[str, Any]:
    request_id = request.get("id")
    operation = request.get("op")
    settings_data = request.get("settings", {})
    settings = Settings.from_dict(settings_data)
    if operation == "eval":
        engine = Engine(settings.engine_config())
        result = engine.evaluate(str(request.get("source", "")), script=bool(request.get("script")))
        return _response(request_id, result.ok, result=result.to_dict())
    if operation == "script":
        engine = Engine(settings.engine_config())
        script_result = engine.run_script(str(request.get("source", "")))
        return _response(request_id, script_result.ok, result=script_result.to_dict())
    if operation == "workspace":
        cells = [Cell.from_dict(item) for item in request.get("cells", [])]
        workspace = Workspace(
            title=str(request.get("title", "worker")),
            settings=settings,
            cells=cells,
            extra={"plugins": list(request.get("plugins", []))},
        )
        engine, runs = run_workspace(workspace)
        payload_runs = []
        for run in runs:
            payload_runs.append(
                {
                    "cellId": run.cell.id,
                    "kind": run.cell.kind,
                    "ok": run.ok,
                    "result": run.result.to_dict() if run.result else None,
                    "script": run.script_result.to_dict() if run.script_result else None,
                }
            )
        ok = all(run.ok for run in runs)
        return _response(
            request_id,
            ok,
            runs=payload_runs,
            environment=engine.snapshot().to_dict(),
            history=[entry.to_dict() for entry in workspace.history],
        )
    if operation == "cell":
        cells = [Cell.from_dict(item) for item in request.get("cells", [])]
        target_id = str(request.get("cellId", ""))
        target_index = next(
            (index for index, cell in enumerate(cells) if cell.id == target_id),
            -1,
        )
        if target_index < 0:
            return _response(request_id, False, error="找不到要运行的单元。")
        workspace = Workspace(
            title=str(request.get("title", "worker")),
            settings=settings,
            cells=cells[: target_index + 1],
            extra={"plugins": list(request.get("plugins", []))},
        )
        engine, runs = run_workspace(workspace)
        if not runs or runs[-1].cell.id != target_id:
            last = runs[-1] if runs else None
            reason = (
                last.diagnostics()[0].message
                if last is not None and last.diagnostics()
                else "目标单元之前的单元执行失败。"
            )
            return _response(request_id, False, error=reason)
        target_run = runs[-1]
        payload = {
            "cellId": target_run.cell.id,
            "kind": target_run.cell.kind,
            "ok": target_run.ok,
            "result": target_run.result.to_dict() if target_run.result else None,
            "script": target_run.script_result.to_dict() if target_run.script_result else None,
        }
        target_history = [
            entry.to_dict() for entry in workspace.history if entry.cell_id == target_id
        ]
        return _response(
            request_id,
            True,
            runs=[payload],
            environment=engine.snapshot().to_dict(),
            history=target_history,
        )
    if operation == "ping":
        return _response(request_id, True, version="0.1.0")
    return _response(request_id, False, error=f"未知 worker 操作：{operation}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        stdout_stream: Any = sys.stdout
        stdin_stream: Any = sys.stdin
        stdout_stream.reconfigure(encoding="utf-8")
        stdin_stream.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = process_request(request)
        except Exception as exc:
            response = _response(
                None,
                False,
                error=str(exc),
                traceback=traceback.format_exc(limit=8),
            )
        print(json.dumps(response, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
