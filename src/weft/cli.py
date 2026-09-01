"""typer 入口：weft validate / graph / review（spec §8，M1 交付前三个）。"""
from __future__ import annotations

import sys
from pathlib import Path

import typer

from weft.diagnostics import Diagnostic
from weft.store.loader import load_project
from weft.validation import validate_project

app = typer.Typer(add_completion=False,
                  help="weft —— 元数据为经线、叙事流为纬线的 AI 学术写作引擎")


def _ensure_utf8_stdout() -> None:
    """Windows 重定向输出默认 GBK，中文诊断会 UnicodeEncodeError；统一切 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.encoding and stream.encoding.lower() not in ("utf-8", "utf8"):
                stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass


def _print_diagnostics(diagnostics: list[Diagnostic]) -> None:
    for d in diagnostics:
        prefix = "ERROR" if d.is_error else "WARN "
        field = f" 字段 {d.field}:" if d.field else ""
        typer.echo(f"{prefix} {d.path} [{d.code}]{field} {d.message}")


@app.command()
def validate(project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录")) -> None:
    """运行 §4 全部校验，报告错误与提醒；有错误时退出码 1。"""
    _ensure_utf8_stdout()
    project, load_diags = load_project(project_dir)
    diagnostics = load_diags + validate_project(project)
    _print_diagnostics(diagnostics)
    n_errors = sum(1 for d in diagnostics if d.is_error)
    typer.echo(f"—— {n_errors} 个错误，{len(diagnostics) - n_errors} 个提醒")
    if n_errors:
        raise typer.Exit(code=1)


@app.command()
def graph(project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录")) -> None:
    """生成 generated/graph.json、used-metadata.json、orphans.md。"""
    _ensure_utf8_stdout()
    typer.echo("尚未实现（M1 Task 13）")
    raise typer.Exit(code=2)


@app.command()
def review(project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录")) -> None:
    """按类型列出未审阅（status: draft）的实体与叙事节点。"""
    _ensure_utf8_stdout()
    typer.echo("尚未实现（M1 Task 14）")
    raise typer.Exit(code=2)
