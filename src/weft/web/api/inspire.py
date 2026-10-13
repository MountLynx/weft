"""灵感管线 API（webui-react 设计 §3.2）：提案列表 / 运行 / 提案对比 / 应用。

语义与旧 HTML 路由一一对应（routes/inspire.py）。收件箱文件由"人"经表单写入
（inspirations/web-<时间戳>.md），非 AI 产物白名单问题；inspire 落盘（草稿卡/
proposals/报告/.runs 快照）全部走 engine 既有逻辑（红线 4 原样）。
"""
from __future__ import annotations

import difflib
import threading
import time

import frontmatter
import yaml
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from weft.engine import make_client
from weft.engine.inspire.apply import apply_inspiration, apply_proposal
from weft.engine.inspire.run import run_inspire
from weft.models.cards import ClaimCard, FactCard, NoteCard
from weft.store.loader import load_project
from weft.validation import validate_project
from weft.web.common import load_project_or_404, load_reviewable_or_404
from weft.web.runs import RunEvent

router = APIRouter(prefix="/api")


@router.get("/projects/{pid}/inspire")
def inspire_list(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    proposals_dir = entry.project.root / "inspirations" / "proposals"
    proposals = []
    if proposals_dir.is_dir():
        for path in sorted(proposals_dir.glob("*.md")):
            proposals.append({"id": path.stem})
    return {"proposals": proposals}


class InspireRunBody(BaseModel):
    text: str = ""
    mock: bool = False


@router.post("/projects/{pid}/inspire/run")
async def inspire_run(request: Request, pid: str, body: InspireRunBody):
    entry = load_project_or_404(request, pid)
    project, load_diags = load_project(entry.path)
    diagnostics = load_diags + validate_project(project)
    if any(d.is_error for d in diagnostics) or not body.text.strip():
        return JSONResponse(
            status_code=422,
            content={"detail": "校验存在错误或灵感文本为空，拒绝处理"})
    run = request.app.state.runs.try_start(pid)
    if run is None:
        raise HTTPException(status_code=409, detail="已有任务在运行，请等待完成")

    def worker() -> None:
        try:
            source = project.root / "inspirations" / f"web-{time.strftime('%Y%m%d-%H%M%S')}.md"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(body.text.replace("\r\n", "\n").replace("\r", "\n"),
                              encoding="utf-8", newline="\n")
            run.emit(RunEvent("run_started", message=f"inspire：{source.name}"))
            result = run_inspire(project, body.text, client=make_client(
                body.mock, project_root=project.root), source=source.name)
            if result.resumed:
                run.emit(RunEvent("node_finished", message="断点续跑：已完成节点取自上次快照"))
            outcome = apply_inspiration(project, source=source, logic=result.logic,
                                        extract=result.extract, review=result.review,
                                        match=result.match, coverage=result.coverage)
            for p in outcome.written_cards:
                run.emit(RunEvent("node_finished",
                                  message=f"写入 {p.relative_to(project.root).as_posix()}"))
            run.emit(RunEvent("draft_written",
                              message=f"{len(outcome.proposals)} 张替换提案待审"))
            run.emit(RunEvent("run_finished",
                              message=f"报告 {outcome.report.relative_to(project.root).as_posix()}"))
        except Exception as exc:
            run.error = str(exc)
            run.emit(RunEvent("run_failed", message=str(exc)))
        finally:
            request.app.state.runs.finish(pid, run)

    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True, "run_id": run.id}


@router.post("/projects/{pid}/inspire/proposals/{card_id}/apply")
def proposal_apply(request: Request, pid: str, card_id: str):
    entry = load_project_or_404(request, pid)
    try:
        apply_proposal(entry.project, card_id)
    except ValueError:
        # 与旧路由同语义：应用被拒（提案不存在/前置不成立）静默回列表，前端刷新自见
        return {"ok": False}
    return {"ok": True}


def _diff_rows(old_text: str, new_text: str, old_label: str, new_label: str):
    """统一 diff 行分类（proposal-diff 设计 §3.2）：+/-/@@/头 各自着色。"""
    rows = []
    for line in difflib.unified_diff(old_text.splitlines(), new_text.splitlines(),
                                     fromfile=old_label, tofile=new_label,
                                     lineterm="", n=3):
        if line.startswith(("--- ", "+++ ")):
            cls = "meta"
        elif line.startswith("@@"):
            cls = "hunk"
        elif line.startswith("+"):
            cls = "add"
        elif line.startswith("-"):
            cls = "del"
        else:
            cls = "ctx"
        rows.append({"cls": cls, "text": line})
    return rows


def _fmt_field(key: str, value) -> str:
    if key == "entry" and value:
        return yaml.safe_dump(value, allow_unicode=True, sort_keys=False).rstrip("\n")
    if value is None:
        return ""
    if isinstance(value, list):
        return "、".join(str(x) for x in value) if value else "（无）"
    return str(value)


@router.get("/projects/{pid}/inspire/proposals/{card_id}")
def proposal_compare(request: Request, pid: str, card_id: str):
    """替换提案对比（proposal-diff 设计 §2-§4）：字段对照 + 逐行 diff，只读。

    加载同卡详情口径（reviewable）：校验 error 项目恰恰最需要审提案；
    提案文件缺失 404；目标缺失/解析失败/id 不一致只呈现警示并 applicable=false
    隐藏应用按钮（apply 本必拒绝，UI 直陈原因，磁盘零改动）。
    """
    entry = load_reviewable_or_404(request, pid)
    project = entry.project
    proposal_path = project.root / "inspirations" / "proposals" / f"{card_id}.md"
    if not proposal_path.is_file():
        raise HTTPException(status_code=404, detail="替换提案不存在")
    new_text = proposal_path.read_text(encoding="utf-8", errors="replace")
    new_label = f"提案 inspirations/proposals/{card_id}.md"

    old_rel = project.card_paths.get(card_id)
    if old_rel is None:
        return {"card_id": card_id,
                "warn": f"目标卡 {card_id} "
                "不存在——提案为陈旧残留，应用必被拒绝；确认无用后可手动删除提案文件。",
                "rows": None, "diff_rows": None, "raw_new": new_text,
                "old_rel": None, "applicable": False}

    old_path = project.root / old_rel
    old_text = (old_path.read_text(encoding="utf-8", errors="replace")
                if old_path.is_file() else None)
    old_label = f"当前 {old_rel.as_posix()}"

    is_note = "notes" in old_rel.parts
    is_fact = "facts" in old_rel.parts
    model = NoteCard if is_note else (FactCard if is_fact else ClaimCard)
    warn = None
    new_card = None
    try:
        post = frontmatter.load(proposal_path)
        new_card = model.model_validate(post.metadata)
        if new_card.id != card_id:
            warn = f"提案卡 id {new_card.id} 与目标 {card_id} 不一致，应用必被拒绝。"
            new_card = None
    except Exception as exc:
        warn = f"提案卡解析失败：{exc}"

    rows = None
    if new_card is not None and old_text is not None:
        old_card = (project.notes if is_note
                    else project.facts if is_fact else project.claims).get(card_id)
        old_fields = old_card.model_dump()
        rows = [{"key": k, "old": _fmt_field(k, old_fields.get(k)),
                 "new": _fmt_field(k, v), "changed": old_fields.get(k) != v}
                for k, v in new_card.model_dump().items()]
    return {"card_id": card_id, "warn": warn, "rows": rows,
            "diff_rows": (_diff_rows(old_text, new_text, old_label, new_label)
                          if old_text is not None else None) or None,
            "raw_new": new_text if warn else None,
            "old_rel": old_rel.as_posix(), "applicable": warn is None}


def register(app: FastAPI) -> None:
    app.include_router(router)
