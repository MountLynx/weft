"""typer 入口：weft validate / graph / review（spec §8，M1 交付前三个）。"""
from __future__ import annotations

import sys
from pathlib import Path

import typer

from weft.diagnostics import Diagnostic, Level
from weft.graphgen.writer import write_outputs
from weft.store.loader import load_project
from weft.store.project import Project
from weft.validation import validate_project

app = typer.Typer(add_completion=False,
                  help="weft —— 元数据为经线、叙事流为纬线的 AI 学术写作引擎")


def _ensure_utf8_stdout() -> None:
    """Windows 重定向输出默认 GBK，中文诊断会 UnicodeEncodeError；统一切 UTF-8。

    在模块导入时执行一次：除命令输出外，--help 与 typer 的用法错误提示也一并覆盖。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.encoding and stream.encoding.lower() not in ("utf-8", "utf8"):
                stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass


_ensure_utf8_stdout()


def _print_diagnostics(diagnostics: list[Diagnostic]) -> None:
    for d in diagnostics:
        prefix = "ERROR" if d.is_error else "WARN "
        field = f" 字段 {d.field}:" if d.field else ""
        typer.echo(f"{prefix} {d.path} [{d.code}]{field} {d.message}")


def _print_review(project: Project) -> None:
    typer.echo("待审阅实体（status: draft）：")
    groups = (("data", project.data_cards), ("fact", project.facts),
              ("claim", project.claims), ("note", project.notes))
    entity_found = False
    for label, cards in groups:
        for cid, card in cards.items():
            if card.status == "draft":
                entity_found = True
                rel = project.card_paths[cid].as_posix()
                typer.echo(f"  {label}  {cid}  {rel}")
    if not entity_found:
        typer.echo("  （无）")
    typer.echo("待审阅叙事节点：")
    node_found = False
    for part in project.parts:
        for node in part.nodes:
            if node.status == "draft":
                node_found = True
                rel = project.part_paths[part.id].as_posix()
                typer.echo(f"  {part.id}/{node.id}  {rel}")
    if not node_found:
        typer.echo("  （无）")


@app.command()
def validate(project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录")) -> None:
    """运行 §4 全部校验，报告错误与提醒；有错误时退出码 1。"""
    project, load_diags = load_project(project_dir)
    diagnostics = load_diags + validate_project(project)
    _print_diagnostics(diagnostics)
    n_errors = sum(1 for d in diagnostics if d.is_error)
    typer.echo(f"—— {n_errors} 个错误，{len(diagnostics) - n_errors} 个提醒")
    if n_errors:
        raise typer.Exit(code=1)


@app.command()
def graph(project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录")) -> None:
    """生成 generated/graph.json、used-metadata.json、orphans.md；校验有错误时拒绝。"""
    project, load_diags = load_project(project_dir)
    diagnostics = load_diags + validate_project(project)
    if any(d.is_error for d in diagnostics):
        _print_diagnostics(diagnostics)
        typer.echo("—— 校验存在错误，拒绝生成反向索引")
        raise typer.Exit(code=1)
    try:
        written = write_outputs(project, project.root / "generated")
    except OSError as exc:
        typer.echo(f"ERROR 无法写入 generated/：{exc}")
        raise typer.Exit(code=1) from exc
    for path in written:
        typer.echo(f"已写入 {path.relative_to(project.root).as_posix()}")
    warnings = [d for d in diagnostics if not d.is_error]
    if warnings:
        _print_diagnostics(warnings)


@app.command()
def review(project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录")) -> None:
    """按类型列出未审阅（status: draft）的实体与叙事节点。"""
    project, load_diags = load_project(project_dir)
    if any(d.is_error for d in load_diags):
        _print_diagnostics(load_diags)
        raise typer.Exit(code=1)
    _print_review(project)


@app.command()
def draft(
    part_id: str = typer.Argument(..., help="part id，如 part-startup-01"),
    project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录"),
    mock: bool = typer.Option(False, "--mock", help="免 key 假客户端（管线冒烟）"),
    no_align: bool = typer.Option(False, "--no-align", help="跳过对齐检查节点"),
) -> None:
    """对指定叙事 part 执行生成（SpecModule run），产物写入 drafts/<part>.md。"""
    from weft.engine import DraftError, DraftRuleError, make_client, run_draft
    from weft.engine.drafts import render_draft_markdown, write_draft
    from weft.workflow import resolve_workflow

    project, load_diags = load_project(project_dir)
    diagnostics = load_diags + validate_project(project)
    if any(d.is_error for d in diagnostics):
        _print_diagnostics(diagnostics)
        typer.echo("—— 校验存在错误，拒绝生成")
        raise typer.Exit(code=1)

    part = next((p for p in project.parts if p.id == part_id), None)
    if part is None:
        _print_diagnostics([Diagnostic(
            Level.ERROR, "E-PART-NOT-FOUND", ".", None,
            f"叙事 part {part_id} 不存在")])
        raise typer.Exit(code=1)
    if not any(n.status == "approved" for n in part.nodes):
        _print_diagnostics([Diagnostic(
            Level.ERROR, "E-NOTHING-TO-DRAFT",
            project.part_paths[part.id].as_posix(), None,
            f"part {part_id} 内没有 status: approved 的叙事节点")])
        raise typer.Exit(code=1)

    warnings = [d for d in diagnostics if not d.is_error]

    try:
        client = make_client(mock, project_root=project.root)
        result = run_draft(project, part, client=client, align=not no_align,
                           workflow=resolve_workflow(part,
                                                     project.part_chapters[part.id]))
    except (DraftRuleError, DraftError) as exc:
        typer.echo(f"ERROR {exc}")
        raise typer.Exit(code=1) from exc

    paragraphs = {nid: d["paragraph"] for nid, d in result.drafts_by_node.items()}
    content = render_draft_markdown(part, paragraphs, result.run_id)
    try:
        path = write_draft(project, part.id, content)
    except OSError as exc:
        typer.echo(f"ERROR 无法写入 drafts/：{exc}")
        raise typer.Exit(code=1) from exc
    for reminder in result.reminders:
        typer.echo(f"WARN {reminder}")
    typer.echo(
        f"已写入 {path.relative_to(project.root).as_posix()}"
        f"（{len(paragraphs)} 段，run={result.run_id}）")
    if warnings:
        _print_diagnostics(warnings)
