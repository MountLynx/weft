"""typer 入口：weft init / validate / graph / review / draft / assemble / render。"""
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
def init(
    project_dir: Path = typer.Argument(Path("."), help="要创建的项目目录（默认当前目录）"),
) -> None:
    """生成最小合法项目骨架（init 后即可通过 weft validate）。"""
    from weft.scaffold import InitCollisionError, init_project

    try:
        created = init_project(project_dir)
    except InitCollisionError as exc:
        preview = "、".join(exc.entries[:5]) + ("…" if len(exc.entries) > 5 else "")
        _print_diagnostics([Diagnostic(
            Level.ERROR, "E-INIT-COLLISION", str(exc.root), None,
            f"目标目录非空（{preview}）；为避免覆盖，未写入任何文件")])
        raise typer.Exit(code=1) from exc
    for path in created:
        typer.echo(f"已创建 {path.relative_to(project_dir).as_posix()}")


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
) -> None:
    """对指定叙事 part 逐节点执行六节点生成管线，产物写入 drafts/<part>.md。"""
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
    approved = [n for n in part.nodes if n.status == "approved"]
    if not approved:
        _print_diagnostics([Diagnostic(
            Level.ERROR, "E-NOTHING-TO-DRAFT",
            project.part_paths[part.id].as_posix(), None,
            f"part {part_id} 内没有 status: approved 的叙事节点")])
        raise typer.Exit(code=1)

    warnings = [d for d in diagnostics if not d.is_error]
    overview_path = project.root / "overview.md"
    overview = overview_path.read_text(encoding="utf-8") if overview_path.exists() else ""
    workflow = resolve_workflow(part, project.part_chapters[part.id])
    client = make_client(mock, project_root=project.root)

    paragraphs: dict[str, str] = {}
    all_reminders: list[str] = []
    run_id = ""
    try:
        for node in approved:
            tail = None
            for other in project.parts:
                if other.id == part_id:
                    break
                draft_file = project.root / "drafts" / f"{other.id}.md"
                if draft_file.exists():
                    blocks = [ln for ln in draft_file.read_text(encoding="utf-8").splitlines()
                              if ln.strip() and not ln.startswith("<!--")]
                    if blocks:
                        tail = blocks[-1]
            result = run_draft(project, part, node, client=client,
                               workflow=workflow, overview=overview,
                               prior_paragraphs=[paragraphs[n.id] for n in approved
                                                 if n.id in paragraphs],
                               prev_tail=tail)
            paragraphs[node.id] = result.paragraph
            all_reminders.extend(result.reminders)
            run_id = result.run_id
    except (DraftRuleError, DraftError) as exc:
        typer.echo(f"ERROR {exc}")
        raise typer.Exit(code=1) from exc

    content = render_draft_markdown(part, paragraphs, run_id)
    try:
        path = write_draft(project, part.id, content)
    except OSError as exc:
        typer.echo(f"ERROR 无法写入 drafts/：{exc}")
        raise typer.Exit(code=1) from exc
    for reminder in all_reminders:
        typer.echo(f"WARN {reminder}")
    typer.echo(
        f"已写入 {path.relative_to(project.root).as_posix()}"
        f"（{len(paragraphs)} 段，run={run_id}）")
    if warnings:
        _print_diagnostics(warnings)


@app.command()
def assemble(project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录")) -> None:
    """拼装已批准草稿 → generated/…/part-NN.qmd、chapter 级合并 qmd 与项目根 paper.qmd。

    纯脚本无 LLM（v1.1 §4.4；paper.qmd 拼接见 M3 设计 §1-§3）；
    strict/lenient 经 weft.yaml assemble_mode 配置。
    """
    from weft.assemble import assemble_project

    project, load_diags = load_project(project_dir)
    diagnostics = load_diags + validate_project(project)
    if any(d.is_error for d in diagnostics):
        _print_diagnostics(diagnostics)
        typer.echo("—— 校验存在错误，拒绝拼装")
        raise typer.Exit(code=1)
    try:
        written, asm_diags = assemble_project(project, mode=project.assemble_mode)
    except OSError as exc:
        typer.echo(f"ERROR 无法写入拼装产物：{exc}")
        raise typer.Exit(code=1) from exc
    for path in written:
        typer.echo(f"已写入 {path.relative_to(project.root).as_posix()}")
    errors = [d for d in asm_diags if d.is_error]
    if errors:
        _print_diagnostics(errors)
        typer.echo(f"—— {len(errors)} 个 part 拼装失败（strict 模式）")
        raise typer.Exit(code=1)


@app.command()
def render(
    project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录"),
    to: str = typer.Option("docx", "--to", help="目标格式（quarto --to，默认 docx）"),
) -> None:
    """渲染拼装产物（weft.yaml paper_file，默认 paper.qmd）→ 目标格式。

    需先 weft assemble；不重复校验闸门（assemble 已闸），仅要求项目可加载。
    """
    from weft import render as render_mod

    project, load_diags = load_project(project_dir)
    if any(d.is_error for d in load_diags):
        _print_diagnostics(load_diags)
        raise typer.Exit(code=1)
    try:
        out_path = render_mod.render_paper(project.root,
                                           paper_file=project.paper_file, to=to)
    except (render_mod.QuartoNotFoundError, render_mod.QuartoRenderError) as exc:
        typer.echo(f"ERROR {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"已生成 {out_path.relative_to(project.root).as_posix()}")


@app.command()
def inspire(
    target: Path = typer.Argument(
        None, help="灵感 md（须在 inspirations/ 下）或项目根目录；缺省取当前项目收件箱最旧一个"),
    project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录"),
    mock: bool = typer.Option(False, "--mock", help="免 key 假客户端（管线冒烟）"),
) -> None:
    """处理一个灵感 md → 草稿卡 + 替换提案 + 处理报告（inspire 管线，fail-closed）。"""
    from weft.engine import DraftError, make_client
    from weft.engine.inspire.apply import apply_inspiration
    from weft.engine.inspire.run import InspireError, run_inspire

    file: Path | None = target
    if target is not None and target.is_dir():
        # 单位置用法：weft inspire <项目根>（同 validate 等命令的习惯）
        project_dir, file = target, None

    project, load_diags = load_project(project_dir)
    diagnostics = load_diags + validate_project(project)
    if any(d.is_error for d in diagnostics):
        _print_diagnostics(diagnostics)
        typer.echo("—— 校验存在错误，拒绝处理灵感")
        raise typer.Exit(code=1)

    inbox = project.root / "inspirations"
    if file is None:
        candidates = sorted(inbox.glob("*.md")) if inbox.is_dir() else []
        if not candidates:
            typer.echo(f"ERROR 灵感收件箱为空：{inbox}")
            raise typer.Exit(code=1)
        source = min(candidates, key=lambda p: p.stat().st_mtime)
    else:
        source = file if file.is_absolute() else Path.cwd() / file
        if not source.is_file() or source.resolve().parent != inbox.resolve():
            typer.echo(f"ERROR 灵感文件必须存在于 {inbox} 下：{file}")
            raise typer.Exit(code=1)

    text = source.read_text(encoding="utf-8")
    try:
        result = run_inspire(project, text, client=make_client(mock, project_root=project.root),
                             source=source.name)
        outcome = apply_inspiration(project, source=source, logic=result.logic,
                                    extract=result.extract, review=result.review,
                                    match=result.match, coverage=result.coverage)
    except (InspireError, DraftError, ValueError, OSError) as exc:
        typer.echo(f"ERROR {exc}")
        raise typer.Exit(code=1) from exc
    if result.resumed:
        typer.echo("本次为断点续跑：已完成节点取自上次快照（generated/inspirations/.runs/）")
    for path in outcome.written_cards:
        typer.echo(f"已写入 {path.relative_to(project.root).as_posix()}")
    for path in outcome.proposals:
        typer.echo(f"已生成替换提案 {path.relative_to(project.root).as_posix()}"
                   "（审后 weft replace 应用）")
    typer.echo(f"报告 {outcome.report.relative_to(project.root).as_posix()}")
    for note in outcome.notes:
        typer.echo(f"WARN {note}")
    warnings = [d for d in diagnostics if not d.is_error]
    if warnings:
        _print_diagnostics(warnings)


@app.command(name="replace")
def replace_proposal(
    card_id: str = typer.Argument(..., help="目标卡 id（对应 inspirations/proposals/<id>.md）"),
    project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录"),
) -> None:
    """应用替换提案：新卡替换旧卡，旧卡归档 archive/cards/<类型>/。"""
    import frontmatter

    from weft.engine.inspire.cards import _normalize
    from weft.models.cards import ClaimCard, FactCard


    project, load_diags = load_project(project_dir)
    if any(d.is_error for d in load_diags):
        _print_diagnostics(load_diags)
        raise typer.Exit(code=1)

    proposal_path = project.root / "inspirations" / "proposals" / f"{card_id}.md"
    if card_id not in project.card_paths:
        typer.echo(f"ERROR 目标卡不存在：{card_id}")
        raise typer.Exit(code=1)
    if not proposal_path.is_file():
        typer.echo(f"ERROR 替换提案不存在：{proposal_path}")
        raise typer.Exit(code=1)
    old_rel = project.card_paths[card_id]
    old_path = project.root / old_rel
    is_fact = "facts" in old_rel.parts
    model = FactCard if is_fact else ClaimCard
    try:
        post = frontmatter.load(proposal_path)
        new_card = model.model_validate(post.metadata)
    except Exception as exc:
        typer.echo(f"ERROR 提案卡解析失败：{exc}")
        raise typer.Exit(code=1) from exc
    if new_card.id != card_id:
        typer.echo(f"ERROR 提案卡 id {new_card.id} 与目标 {card_id} 不一致")
        raise typer.Exit(code=1)

    # 闸门：内存替换后全量校验，有 error 即拒绝（磁盘零改动）
    table = project.facts if is_fact else project.claims
    table[card_id] = new_card
    gate = validate_project(project)
    gate_errors = [d for d in gate if d.is_error]
    if gate_errors:
        _print_diagnostics(gate_errors)
        typer.echo("—— 替换被校验闸门拒绝，磁盘未改动")
        raise typer.Exit(code=1)

    archive_dir = project.root / "archive" / "cards" / old_rel.parent.name
    archive_path = archive_dir / old_rel.name
    if archive_path.exists():
        typer.echo(f"ERROR 归档重名，拒绝覆盖：{archive_path}")
        raise typer.Exit(code=1)
    try:
        archive_dir.mkdir(parents=True, exist_ok=True)
        old_path.rename(archive_path)
        old_path.write_text(
            _normalize(proposal_path.read_text(encoding="utf-8")),
            encoding="utf-8", newline="\n")
        proposal_path.unlink()
    except OSError as exc:
        typer.echo(f"ERROR 替换落盘失败：{exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"已替换 {old_rel.as_posix()}")
    typer.echo(f"旧卡归档 {archive_path.relative_to(project.root).as_posix()}")


@app.command(name="missing-cites")
def missing_cites(
    project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录"),
) -> None:
    """列出 cites 为空的 cited 卡（缺文献清单）；纯数据层报告，不阻断。"""
    project, load_diags = load_project(project_dir)
    if any(d.is_error for d in load_diags):
        _print_diagnostics(load_diags)
        raise typer.Exit(code=1)
    hits = [(cid, c) for cid, c in project.claims.items()
            if c.claim_type == "cited" and not c.cites and c.status != "rejected"]
    if not hits:
        typer.echo("（无缺文献的 cited 卡）")
        return
    for cid, claim in hits:
        statement = claim.statement if len(claim.statement) <= 40 \
            else claim.statement[:39] + "…"
        typer.echo(f"{cid}  {project.card_paths[cid].as_posix()}  {statement}")
    typer.echo(f"—— {len(hits)} 张 cited 卡缺文献")
