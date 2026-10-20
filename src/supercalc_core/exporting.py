from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from .workspace import Workspace, run_workspace


def workspace_to_markdown(workspace: Workspace) -> str:
    _, runs = run_workspace(workspace)
    lines = [f"# {workspace.title}", ""]
    lines.append(
        f"计算模式：`{workspace.settings.mode}`；精度：`{workspace.settings.precision}` 位；"
        f"舍入：`{workspace.settings.rounding}`；角度：`{workspace.settings.angle}`"
    )
    lines.append("")
    for cell, run in zip(workspace.cells, runs, strict=False):
        if cell.kind == "markdown":
            lines.extend([cell.source, ""])
            continue
        if cell.kind == "plot":
            lines.extend(
                ["## 绘图", "", f"```text\n{json.dumps(cell.plot, ensure_ascii=False)}\n```", ""]
            )
            continue
        lines.extend([f"## {cell.kind.title()} 单元", "", "```supercalc", cell.source, "```", ""])
        if run.script_result is not None:
            lines.append(
                f"脚本：{'通过' if run.script_result.ok else '失败'}；"
                f"断言 {run.script_result.assertions} 个。"
            )
        elif run.result is not None and run.result.value is not None:
            marker = "=" if run.result.value.exact else r"\approx"
            lines.append(f"{marker} `{run.result.value.display}`")
            lines.append("")
            lines.append(
                f"精确性：`{run.result.exactness}`；算法：{run.result.algorithm or '未记录'}"
            )
        for diagnostic in run.diagnostics():
            location = ""
            if diagnostic.span:
                location = f"（第 {diagnostic.span.line} 行第 {diagnostic.span.column} 列）"
            lines.append(f"- **{diagnostic.code}**{location}：{diagnostic.message}")
        lines.append("")
    return "\n".join(lines)


def workspace_to_latex(workspace: Workspace) -> str:
    _, runs = run_workspace(workspace)
    blocks: list[str] = []
    for cell, run in zip(workspace.cells, runs, strict=False):
        if cell.kind == "markdown":
            blocks.append(cell.source)
            continue
        if run.result is not None and run.result.value is not None:
            relation = "=" if run.result.value.exact else r"\approx"
            blocks.append(f"{relation} {run.result.value.latex or run.result.value.display}")
        elif run.script_result is not None:
            blocks.append(rf"\text{{Script assertions: {run.script_result.assertions}}}")
    return "\n\n".join(blocks)


def workspace_to_csv(workspace: Workspace) -> str:
    _, runs = run_workspace(workspace)
    for run in reversed(runs):
        if run.result is None or run.result.value is None:
            continue
        value = run.result.value
        if value.type == "Matrix":
            output = io.StringIO()
            writer = csv.writer(output)
            for row in value.data:
                writer.writerow([cell.display for cell in row])
            return output.getvalue()
    raise ValueError("工作区最后一个矩阵结果为空，无法导出 CSV")


def write_export(workspace: Workspace, path: str | Path, format_name: str) -> Path:
    target = Path(path)
    name = format_name.lower()
    if name == "markdown":
        content = workspace_to_markdown(workspace)
    elif name == "latex":
        content = workspace_to_latex(workspace)
    elif name == "json":
        content = json.dumps(workspace.to_dict(), ensure_ascii=False, indent=2)
    elif name == "csv":
        content = workspace_to_csv(workspace)
    else:
        raise ValueError(f"不支持的导出格式：{format_name}")
    target.write_text(content, encoding="utf-8", newline="\n")
    return target
