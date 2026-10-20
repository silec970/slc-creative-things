from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from supercalc_core import APP_VERSION, Engine
from supercalc_core.api import EngineConfig
from supercalc_core.ast import format_ast_tree
from supercalc_core.diagnostics import Diagnostic
from supercalc_core.exporting import write_export
from supercalc_core.latex import from_latex
from supercalc_core.models import EvaluationResult
from supercalc_core.numeric import inspect_float64
from supercalc_core.workspace import Workspace, WorkspaceError, run_workspace


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _config(args: argparse.Namespace) -> EngineConfig:
    return EngineConfig(
        mode=getattr(args, "mode", "exact"),
        precision=getattr(args, "precision", 50),
        rounding=getattr(args, "rounding", "half_even"),
        angle=getattr(args, "angle", "radians"),
    )


def _print_diagnostics(diagnostics: list[Diagnostic]) -> None:
    for diagnostic in diagnostics:
        span_text = ""
        if diagnostic.span:
            span_text = f" [第 {diagnostic.span.line} 行第 {diagnostic.span.column} 列]"
        print(
            f"{diagnostic.code} {diagnostic.severity.value}{span_text}: {diagnostic.message}",
            file=sys.stderr,
        )
        if diagnostic.snippet:
            print(f"  {diagnostic.snippet}", file=sys.stderr)
        if diagnostic.hint:
            print(f"  提示：{diagnostic.hint}", file=sys.stderr)


def _print_result(result: EvaluationResult) -> None:
    if result.value is not None:
        marker = "=" if result.value.exact else "≈"
        print(f"{marker} {result.value.display}")
        print(
            f"类型: {result.value.type}  精确性: {result.exactness}  "
            f"精度: {result.precision} 位  舍入: {result.rounding}",
            file=sys.stderr,
        )
        if result.algorithm:
            print(f"算法: {result.algorithm}", file=sys.stderr)
        if result.steps:
            for step in result.steps:
                print(f"步骤: {step.get('title', '')} — {step.get('detail', '')}", file=sys.stderr)
    _print_diagnostics(result.diagnostics)


def cmd_eval(args: argparse.Namespace) -> int:
    source = args.expression
    if source == "-":
        source = sys.stdin.read()
    if args.latex:
        source = from_latex(source)
    result = Engine(_config(args)).evaluate(source, script=args.script)
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_result(result)
    return 0 if result.ok else 1


def cmd_run(args: argparse.Namespace) -> int:
    try:
        workspace = Workspace.load(args.path)
    except WorkspaceError as exc:
        print(f"SC7001: {exc}", file=sys.stderr)
        return 1
    if args.mode:
        workspace.settings.mode = args.mode
    if args.precision:
        workspace.settings.precision = args.precision
    engine, runs = run_workspace(workspace)
    if args.json:
        print(
            json.dumps(
                {
                    "apiVersion": 1,
                    "ok": all(run.ok for run in runs),
                    "workspace": workspace.to_dict(),
                    "runs": [
                        {
                            "cellId": run.cell.id,
                            "kind": run.cell.kind,
                            "ok": run.ok,
                            "result": run.result.to_dict() if run.result else None,
                            "script": run.script_result.to_dict() if run.script_result else None,
                        }
                        for run in runs
                    ],
                    "environment": engine.snapshot().to_dict(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for run in runs:
            if run.cell.kind in {"markdown", "plot"}:
                continue
            print(f"[{run.cell.kind}] {run.cell.source.strip()}")
            if run.script_result is not None:
                print(
                    f"脚本{'通过' if run.script_result.ok else '失败'}，断言 {run.script_result.assertions} 个"
                )
                _print_diagnostics(run.script_result.diagnostics)
            elif run.result is not None:
                _print_result(run.result)
    ok = all(run.ok for run in runs)
    return 0 if ok else 1


def cmd_test(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if path.suffix.lower() == ".scscript":
        result = Engine(_config(args)).run_script(path.read_text(encoding="utf-8"))
        if args.json:
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(
                f"{'PASS' if result.ok else 'FAIL'}: {path.name} ({result.assertions} assertions)"
            )
            _print_diagnostics(result.diagnostics)
        return 0 if result.ok else 1
    try:
        workspace = Workspace.load(path)
    except WorkspaceError as exc:
        print(f"SC7001: {exc}", file=sys.stderr)
        return 1
    _, runs = run_workspace(workspace)
    assertions = sum(run.script_result.assertions for run in runs if run.script_result is not None)
    ok = all(run.ok for run in runs)
    if args.json:
        print(json.dumps({"ok": ok, "assertions": assertions}, ensure_ascii=False, indent=2))
    else:
        print(f"{'PASS' if ok else 'FAIL'}: {path.name} ({assertions} assertions)")
        for run in runs:
            _print_diagnostics(run.diagnostics())
    return 0 if ok else 1


def cmd_ieee(args: argparse.Namespace) -> int:
    result = Engine(_config(args)).evaluate(f"f64({args.value})")
    if not result.ok or result.value is None:
        _print_diagnostics(result.diagnostics)
        return 1
    data = inspect_float64(result.value)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(f"值: {data['value']!r}")
        print(f"分类: {data['classification']}")
        print(f"符号位: {data['sign']}")
        print(f"指数位: {data['exponentBits']:011b} ({data['exponentBits']})")
        print(f"尾数位: {data['mantissaBits']:052b}")
        print(f"十六进制: {data['hex']}")
    return 0


def cmd_ast(args: argparse.Namespace) -> int:
    engine = Engine(_config(args))
    try:
        program = engine.parse(args.expression)
    except Exception as exc:
        print(f"SC1000: {exc}", file=sys.stderr)
        return 1
    data = [
        format_ast_tree(statement.expr) if hasattr(statement, "expr") else repr(statement)
        for statement in program.statements
    ]
    print(json.dumps(data, ensure_ascii=False, indent=2) if args.json else "\n".join(data))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    try:
        workspace = Workspace.load(args.path)
        target = write_export(workspace, args.output, args.format)
    except (WorkspaceError, ValueError, OSError) as exc:
        print(f"SC7002: {exc}", file=sys.stderr)
        return 1
    print(str(target))
    return 0


def cmd_version(_: argparse.Namespace) -> int:
    print(f"SuperCalc {APP_VERSION} / API 1")
    return 0


def cmd_worker(_: argparse.Namespace) -> int:
    from supercalc_cli.worker import main as worker_main

    return worker_main()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="SuperCalcCLI",
        description="SuperCalc 离线计算引擎命令行",
    )
    parser.add_argument("--json", action="store_true", help="输出版本化 JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)

    evaluate = subparsers.add_parser("eval", help="计算表达式或脚本")
    evaluate.add_argument("expression", help="表达式；- 表示从标准输入读取")
    evaluate.add_argument("--mode", choices=["exact", "approx"], default="exact")
    evaluate.add_argument("--precision", type=int, default=50)
    evaluate.add_argument("--rounding", default="half_even")
    evaluate.add_argument("--angle", choices=["radians", "degrees"], default="radians")
    evaluate.add_argument("--script", action="store_true", help="按脚本 DSL 解析")
    evaluate.add_argument("--latex", action="store_true", help="先把输入作为 LaTeX 子集导入")
    evaluate.add_argument("--json", action="store_true")
    evaluate.set_defaults(func=cmd_eval)

    run = subparsers.add_parser("run", help="运行 .scws 工作区")
    run.add_argument("path")
    run.add_argument("--json", action="store_true")
    run.add_argument("--mode", choices=["exact", "approx"])
    run.add_argument("--precision", type=int)
    run.set_defaults(func=cmd_run)

    test = subparsers.add_parser("test", help="执行工作区或脚本断言")
    test.add_argument("path")
    test.add_argument("--json", action="store_true")
    test.set_defaults(func=cmd_test)

    ieee = subparsers.add_parser("ieee", help="查看 binary64 字段")
    ieee.add_argument("value", help="可计算的数值表达式")
    ieee.add_argument("--json", action="store_true")
    ieee.set_defaults(func=cmd_ieee)

    ast_parser = subparsers.add_parser("ast", help="显示解析树")
    ast_parser.add_argument("expression")
    ast_parser.add_argument("--json", action="store_true")
    ast_parser.set_defaults(func=cmd_ast)

    export = subparsers.add_parser("export", help="导出工作区")
    export.add_argument("path")
    export.add_argument("--format", choices=["latex", "markdown", "json", "csv"], required=True)
    export.add_argument("--output", required=True)
    export.set_defaults(func=cmd_export)

    version = subparsers.add_parser("version", help="显示版本")
    version.set_defaults(func=cmd_version)

    worker = subparsers.add_parser("worker", help=argparse.SUPPRESS)
    worker.set_defaults(func=cmd_worker)
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("已取消。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
