"""按 part 的草稿生成编排：CLI（cli.draft）与 WebUI 共用的唯一路径（webui 设计 §1.1）。

事件生命周期归本函数所有；on_event 收到 DraftEvent(kind, node_id, message)。
编排语义与原 cli.draft 逐行等价（前文传递 prev_tail 取更早 part 草稿末段，M2 决策）。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from weft.engine.draft_rules import DraftError, DraftRuleError
from weft.engine.drafts import render_draft_markdown, write_draft
from weft.engine.run import run_draft
from weft.models.narrative import NarrativePart
from weft.store.project import Project
from weft.workflow import resolve_workflow


@dataclass(frozen=True)
class DraftEvent:
    kind: str                # run_started|node_started|node_finished|node_failed|draft_written|run_finished|run_failed
    node_id: str | None = None
    message: str = ""


@dataclass
class PartDraftResult:
    paragraphs: dict[str, str]
    reminders: list[str]
    run_id: str
    path: Path


def run_part_draft(project: Project, part: NarrativePart, *, client,
                   on_event=None) -> PartDraftResult:
    """闸门（validate 无 error）由调用方负责；本函数编排单 part 全部 approved 节点。"""
    def emit(kind: str, node_id: str | None = None, message: str = "") -> None:
        if on_event is not None:
            on_event(DraftEvent(kind, node_id, message))

    approved = [n for n in part.nodes if n.status == "approved"]
    if not approved:
        message = "[E-NOTHING-TO-DRAFT] part 内没有 status: approved 的叙事节点"
        emit("run_started", message=part.id)
        emit("run_failed", message=message)
        raise DraftError(message)

    overview_path = project.root / "overview.md"
    overview = overview_path.read_text(encoding="utf-8") if overview_path.exists() else ""
    workflow = resolve_workflow(part, project.part_chapters[part.id])
    emit("run_started", message=f"{part.id}（workflow={workflow}，{len(approved)} 节点）")

    paragraphs: dict[str, str] = {}
    all_reminders: list[str] = []
    run_id = ""
    try:
        for node in approved:
            tail = None
            for other in project.parts:
                if other.id == part.id:
                    break
                draft_file = project.root / "drafts" / f"{other.id}.md"
                if draft_file.exists():
                    blocks = [ln for ln in draft_file.read_text(encoding="utf-8").splitlines()
                              if ln.strip() and not ln.startswith("<!--")]
                    if blocks:
                        tail = blocks[-1]
            emit("node_started", node.id)
            try:
                result = run_draft(project, part, node, client=client,
                                   workflow=workflow, overview=overview,
                                   prior_paragraphs=[paragraphs[n.id] for n in approved
                                                     if n.id in paragraphs],
                                   prev_tail=tail)
            except (DraftRuleError, DraftError) as exc:
                emit("node_failed", node.id, str(exc))
                raise
            paragraphs[node.id] = result.paragraph
            all_reminders.extend(result.reminders)
            run_id = result.run_id
            emit("node_finished", node.id,
                 f"{len(result.reminders)} 条提醒" if result.reminders else "完成")
    except Exception as exc:
        emit("run_failed", message=str(exc))
        raise

    content = render_draft_markdown(part, paragraphs, run_id)
    try:
        path = write_draft(project, part.id, content)
    except OSError as exc:
        emit("run_failed", message=str(exc))
        raise DraftError(f"无法写入 drafts/：{exc}") from exc
    emit("draft_written", message=path.relative_to(project.root).as_posix())
    emit("run_finished", message=f"{len(paragraphs)} 段，run={run_id}")
    return PartDraftResult(paragraphs=paragraphs, reminders=all_reminders,
                           run_id=run_id, path=path)
