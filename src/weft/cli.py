"""typer 入口：weft init / validate / graph / review / draft / assemble / render / inspire / parse / replace / missing-cites / bib / projects / serve。"""
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

bib_app = typer.Typer(add_completion=False, help="bib 生成与维护（managed 模式，bibgen 设计）")
app.add_typer(bib_app, name="bib")

projects_app = typer.Typer(add_completion=False,
                           help="全局项目注册表管理（projects registry 设计）")
app.add_typer(projects_app, name="projects")


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


def _registry_error(exc) -> None:
    """RegistryError → 诊断输出 + 退出码 1（exc.diagnostic() 自带 E-REG-* 码）。"""
    _print_diagnostics([exc.diagnostic()])
    raise typer.Exit(code=1)


def _load_registry():
    """读全局注册表；损坏 fail-closed（E-REG-MALFORMED → 退出码 1）。"""
    from weft.registry import RegistryError, load_registry

    try:
        return load_registry()
    except RegistryError as exc:
        _registry_error(exc)


def _save_registry(reg) -> None:
    """写全局注册表；环境异常（只读 home/磁盘满/位点被占等）转 ERROR 行，不裸 traceback。"""
    from weft.registry import save_registry

    try:
        save_registry(reg)
    except OSError as exc:
        typer.echo(f"ERROR 注册表写入失败：{exc}")
        raise typer.Exit(code=1) from exc


def _init_collision_diagnostic(exc) -> Diagnostic:
    """E-INIT-COLLISION 诊断（init 与 projects new 共用；exc 为 InitCollisionError）。"""
    preview = "、".join(exc.entries[:5]) + ("…" if len(exc.entries) > 5 else "")
    return Diagnostic(
        Level.ERROR, "E-INIT-COLLISION", str(exc.root), None,
        f"目标目录非空（{preview}）；为避免覆盖，未写入任何文件")


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
        _print_diagnostics([_init_collision_diagnostic(exc)])
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
    from weft.engine import DraftError, DraftRuleError, make_client
    from weft.engine.part_draft import run_part_draft

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
    client = make_client(mock, project_root=project.root)
    try:
        result = run_part_draft(project, part, client=client)
    except (DraftRuleError, DraftError) as exc:
        typer.echo(f"ERROR {exc}")
        raise typer.Exit(code=1) from exc
    for reminder in result.reminders:
        typer.echo(f"WARN {reminder}")
    typer.echo(
        f"已写入 {result.path.relative_to(project.root).as_posix()}"
        f"（{len(result.paragraphs)} 段，run={result.run_id}）")
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

    try:
        text = source.read_text(encoding="utf-8")
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


@app.command()
def parse(
    target: Path = typer.Argument(
        None, help="文章 md/txt（须在 articles/ 下）或项目根目录；缺省取当前项目收件箱最旧一个"),
    project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录"),
    key: str = typer.Option(None, "--key",
                            help="文献模式：bib key（必须已在 bib；不给 = 拆解模式）"),
    mock: bool = typer.Option(False, "--mock", help="免 key 假客户端（管线冒烟）"),
) -> None:
    """解析一篇文章 → 草稿卡 + 替换提案 + 处理报告（parse 管线，fail-closed）。"""
    from weft.engine import DraftError, make_client
    from weft.engine.parse.apply import apply_article
    from weft.engine.parse.run import ParseError, run_parse

    file: Path | None = target
    if target is not None and target.is_dir():
        # 单位置用法：weft parse <项目根>（同 validate/inspire 的习惯）
        project_dir, file = target, None

    project, load_diags = load_project(project_dir)
    diagnostics = load_diags + validate_project(project)
    if any(d.is_error for d in diagnostics):
        _print_diagnostics(diagnostics)
        typer.echo("—— 校验存在错误，拒绝处理文章")
        raise typer.Exit(code=1)
    if key is not None and key not in project.bib_keys:
        _print_diagnostics([Diagnostic(
            Level.ERROR, "E-ARTICLE-KEY", "articles", None,
            f"--key 不在 bib 中：{key}")])
        raise typer.Exit(code=1)

    inbox = project.root / "articles"
    if file is None:
        candidates = sorted(p for pattern in ("*.md", "*.txt")
                            for p in (inbox.glob(pattern) if inbox.is_dir() else []))
        if not candidates:
            typer.echo(f"ERROR 文章收件箱为空：{inbox}")
            raise typer.Exit(code=1)
        source = min(candidates, key=lambda p: p.stat().st_mtime)
    else:
        source = file if file.is_absolute() else Path.cwd() / file
        if (not source.is_file() or source.suffix.lower() not in (".md", ".txt")
                or source.resolve().parent != inbox.resolve()):
            typer.echo(f"ERROR 文章文件必须是 {inbox} 下的 .md/.txt：{file}")
            raise typer.Exit(code=1)

    try:
        text = source.read_text(encoding="utf-8")
        result = run_parse(project, text,
                           client=make_client(mock, project_root=project.root),
                           source=source.name, bib_key=key)
        outcome = apply_article(project, source=source, logic=result.logic,
                                extract=result.extract, review=result.review,
                                match=result.match, coverage=result.coverage,
                                bib_key=key)
    except (ParseError, DraftError, ValueError, OSError) as exc:
        typer.echo(f"ERROR {exc}")
        raise typer.Exit(code=1) from exc
    if result.resumed:
        typer.echo("本次为断点续跑：已完成节点取自上次快照（generated/articles/.runs/）")
    for path in outcome.written_cards:
        typer.echo(f"已写入 {path.relative_to(project.root).as_posix()}")
    for path in outcome.proposals:
        typer.echo(f"已生成替换提案 {path.relative_to(project.root).as_posix()}"
                   "（审后 weft replace 应用）")
    typer.echo(f"报告 {outcome.report.relative_to(project.root).as_posix()}")
    for warning in result.warnings:
        typer.echo(f"WARN {warning}")
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
    from weft.engine.inspire.apply import apply_proposal

    project, load_diags = load_project(project_dir)
    if any(d.is_error for d in load_diags):
        _print_diagnostics(load_diags)
        raise typer.Exit(code=1)
    try:
        new_path, archive_path = apply_proposal(project, card_id)
    except ValueError as exc:
        typer.echo(f"ERROR {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"已替换 {new_path.relative_to(project.root).as_posix()}")
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


@app.command()
def serve(
    projects_root: Path = typer.Argument(
        None, help="扫描模式：projects 根目录。省略 = 注册表模式（全局注册表，多项目共存）"),
    host: str = typer.Option("127.0.0.1", "--host", help="监听地址；部署用 0.0.0.0"),
    port: int = typer.Option(8000, "--port", help="监听端口"),
) -> None:
    """启动 WebUI 主程序（webui 设计 §10、projects registry 设计 §5）。

    weft serve —— 注册表模式：列出全局注册表的全部项目，项目可位于磁盘任意位置。
    weft serve <projects_root> —— 扫描模式：现状行为（扫描一级子目录）。
    """
    try:
        import uvicorn
    except ImportError as exc:
        typer.echo("ERROR WebUI 依赖未安装：pip install 'weft[web]'")
        raise typer.Exit(code=1) from exc
    from weft.web import create_app

    if projects_root is None:
        uvicorn.run(create_app(use_registry=True), host=host, port=port)
        return
    if not projects_root.is_dir():
        typer.echo(f"ERROR 项目根目录不存在：{projects_root}")
        raise typer.Exit(code=1)
    uvicorn.run(create_app(projects_root), host=host, port=port)


@projects_app.command("add")
def projects_add(
    path: Path = typer.Argument(..., help="要登记的 weft 项目根目录"),
    name: str = typer.Option(None, "--name", help="注册名（缺省取目录名）"),
) -> None:
    """校验是合法 weft 项目后登记进全局注册表（不动项目文件）。"""
    from weft.registry import (
        RegistryError,
        register_project,
        save_registry,
    )
    from weft.store.loader import is_weft_project

    if not path.is_dir() or not is_weft_project(path):
        _print_diagnostics([Diagnostic(
            Level.ERROR, "E-REG-NOT-PROJECT", str(path), None,
            f"{path} 不是 weft 项目根目录（缺少 metadata/ 与 _quarto.yml）")])
        raise typer.Exit(code=1)
    resolved = path.resolve()
    reg_name = name if name is not None else resolved.name
    reg = _load_registry()
    try:
        entry = register_project(reg, reg_name, resolved)
        _save_registry(reg)
    except RegistryError as exc:
        _registry_error(exc)
    typer.echo(f"已登记 {entry.name} -> {entry.path}")


@projects_app.command("new")
def projects_new(
    name: str = typer.Argument(..., help="注册名（同时是项目目录名）"),
    root: Path = typer.Option(
        None, "--root", help="父目录；缺省依次回退注册表 default_root、~/weft-projects"),
) -> None:
    """新建项目并登记：init 骨架 + 注册表条目；名称冲突/目录非空零写入。"""
    from weft.registry import (
        RegistryError,
        ensure_registrable,
        register_project,
        resolve_default_root,
        validate_project_name,
    )
    from weft.scaffold import InitCollisionError, init_project

    reg = _load_registry()
    clean, name_err = validate_project_name(name)  # 先规范名，再拼路径（对齐 web 版顺序）
    if name_err is not None:
        _registry_error(RegistryError("E-REG-NAME", name, name_err))
    parent = root if root is not None else resolve_default_root(reg)
    target = parent / clean
    try:
        ensure_registrable(reg, clean, target)  # 落盘前预检：零写入
        target.parent.mkdir(parents=True, exist_ok=True)
        init_project(target)
    except RegistryError as exc:
        _registry_error(exc)
    except InitCollisionError as exc:
        _print_diagnostics([_init_collision_diagnostic(exc)])
        raise typer.Exit(code=1) from exc
    except OSError as exc:
        typer.echo(f"ERROR 无法创建项目骨架（{target}）：{exc}")
        raise typer.Exit(code=1) from exc
    try:
        entry = register_project(reg, clean, target)
        _save_registry(reg)
    except RegistryError as exc:
        _registry_error(exc)
    typer.echo(f"已创建并登记 {entry.name} -> {entry.path}")


@projects_app.command("list")
def projects_list() -> None:
    """列出注册表全部项目（纯只读，失联条目只展示不清理）。"""
    from weft.store.loader import is_weft_project

    reg = _load_registry()
    if not reg.projects:
        typer.echo("注册表为空——用 weft projects add <路径> 登记现有项目，"
                   "或 weft projects new <名称> 新建。")
        return
    typer.echo("名称\t路径\t状态\t登记时间")
    for entry in reg.projects:
        path = Path(entry.path)
        status = "ok" if path.is_dir() and is_weft_project(path) else "missing"
        typer.echo(f"{entry.name}\t{entry.path}\t{status}\t{entry.registered_at}")


@projects_app.command("remove")
def projects_remove(
    name: str = typer.Argument(..., help="要摘除的注册名"),
) -> None:
    """只从注册表摘除项目；本地文件一律不动。"""
    from weft.registry import (
        RegistryError,
        save_registry,
        unregister_project,
    )

    reg = _load_registry()
    try:
        entry = unregister_project(reg, name)
        _save_registry(reg)
    except RegistryError as exc:
        _registry_error(exc)
    typer.echo(f"已从注册表摘除 {entry.name}")
    typer.echo(f"本地文件未删除：{entry.path}")


@projects_app.command("root")
def projects_root(
    directory: Path = typer.Argument(
        None, help="省略 = 显示当前默认根；给出 = 设置（相对路径按当前目录解析）"),
) -> None:
    """查看/设置 `projects new` 的默认父目录（存注册表 default_root）。"""
    from weft.registry import resolve_default_root

    reg = _load_registry()
    if directory is None:
        if reg.default_root:
            typer.echo(f"默认根（配置值）：{reg.default_root}")
        else:
            typer.echo(f"默认根（默认值）：{resolve_default_root(reg)}")
        return
    reg.default_root = directory.resolve().as_posix()
    _save_registry(reg)
    typer.echo(f"已设置默认根：{reg.default_root}")


@bib_app.command("sync")
def bib_sync(
    project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录"),
    check: bool = typer.Option(False, "--check", help="不写文件：不一致时 W-BIB-STALE 且退出 1"),
) -> None:
    """把已批准文献卡（approved + entry）渲染为 bibliography 目标文件。"""
    from weft import bibgen

    project, load_diags = load_project(project_dir)
    if project.bib_managed:
        load_diags = [d for d in load_diags
                      if not (d.code == "E-BIB-MISSING" and d.path in project.bib_files)]
    if any(d.is_error for d in load_diags):
        _print_diagnostics(load_diags)
        raise typer.Exit(code=1)
    if not project.bib_managed:
        typer.echo("ERROR 未启用 bib.managed（weft.yaml），本命令仅用于 managed 项目")
        raise typer.Exit(code=1)
    if project.bib_cfg_error:
        _print_diagnostics([Diagnostic(
            Level.ERROR, "E-BIB-SHAPE", "weft.yaml", "bib", project.bib_cfg_error)])
        raise typer.Exit(code=1)
    if len(project.bib_files) != 1:
        _print_diagnostics([Diagnostic(
            Level.ERROR, "E-BIB-SHAPE", "_quarto.yml", "bibliography",
            "managed 项目 bibliography 必须恰好指向一个文件（生成目标）")])
        raise typer.Exit(code=1)
    try:
        if check:
            target = bibgen.managed_target(project)
            if not target.exists():
                _print_diagnostics([Diagnostic(
                    Level.ERROR, "E-BIB-MISSING", project.bib_files[0], "bibliography",
                    "bib 文件不存在，先运行 weft bib sync 生成")])
                raise typer.Exit(code=1)
            if bibgen.bib_is_stale(project):
                _print_diagnostics([Diagnostic(
                    Level.WARNING, "W-BIB-STALE", project.bib_files[0], None,
                    "bib 文件与已批准文献卡不一致")])
                raise typer.Exit(code=1)
            n = len(bibgen.bib_keys_in(target.read_text(encoding="utf-8")))
            typer.echo(f"bib 与已批准文献卡一致（{n} 条）：{project.bib_files[0]}")
            return
        _, stats = bibgen.sync_bib(project)
    except bibgen.BibValueError as exc:
        _print_diagnostics([Diagnostic(
            Level.ERROR, "E-BIB-VALUE", project.bib_files[0], "entry", str(exc))])
        raise typer.Exit(code=1) from exc
    typer.echo(f"已写入 {project.bib_files[0]}"
               f"（{stats['total']} 条，+{stats['added']} / -{stats['removed']}）")
