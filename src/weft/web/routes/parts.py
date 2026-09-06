"""叙事工作台（webui 设计 §5）：part 页签、节点审阅、节点编辑（Task 10）、生成（Task 11）。"""
from __future__ import annotations

import html as _html
import threading

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from pydantic import ValidationError

from weft.engine import make_client
from weft.engine.part_draft import run_part_draft
from weft.models.narrative import Node, Use
from weft.store.loader import load_project
from weft.store.writer import save_part
from weft.validation import validate_project
from weft.validation.rules import PURPOSE_VOCAB, ROLE_VOCAB
from weft.web.common import load_entry_or_404, load_project_or_404, templates
from weft.web.runs import RunEvent
from weft.workflow import WORKFLOW_VOCAB

router = APIRouter()

_STATUSES = ("draft", "approved", "rejected")


def _find_part(entry, part_id: str):
    for part in entry.project.parts:
        if part.id == part_id:
            return part
    raise HTTPException(status_code=404, detail="叙事 part 不存在")


def _find_node(part, node_id: str):
    for node in part.nodes:
        if node.id == node_id:
            return node
    raise HTTPException(status_code=404, detail="叙事节点不存在")


def _draft_text(project, part_id: str) -> str | None:
    path = project.root / "drafts" / f"{part_id}.md"
    return path.read_text(encoding="utf-8") if path.exists() else None


def _panel_ctx(entry, part) -> dict:
    project = entry.project
    return {"entry": entry, "pid": entry.pid, "part": part,
            "nodes": part.nodes, "draft_text": _draft_text(project, part.id),
            "workflow_vocab": list(WORKFLOW_VOCAB)}


@router.get("/p/{pid}/parts")
def parts_page(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    if not entry.project.parts:
        raise HTTPException(status_code=404, detail="项目没有叙事 part")
    first = entry.project.parts[0]
    return templates.TemplateResponse(
        request, "parts.html",
        {"entry": entry, "pid": pid, "parts": entry.project.parts,
         "current": first.id, **_panel_ctx(entry, first)})


@router.get("/p/{pid}/parts/{part_id}")
def part_panel(request: Request, pid: str, part_id: str):
    entry = load_project_or_404(request, pid)
    part = _find_part(entry, part_id)
    return templates.TemplateResponse(request, "part_panel.html",
                                      _panel_ctx(entry, part))


@router.post("/p/{pid}/parts/{part_id}/nodes/{node_id}/status")
async def node_review(request: Request, pid: str, part_id: str, node_id: str):
    entry = load_project_or_404(request, pid)
    part = _find_part(entry, part_id)
    node = _find_node(part, node_id)
    form = await request.form()
    status = str(form.get("status", ""))
    if status not in _STATUSES:
        raise HTTPException(status_code=400, detail="非法 status")
    updates: dict = {"status": status}
    if "comment" in form:          # 快捷 ✅/❌ 不携带 comment 时保留原值
        updates["comment"] = str(form.get("comment", ""))
    part.nodes[part.nodes.index(node)] = node.model_copy(update=updates)
    save_part(entry.project, part)
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "part_panel.html",
                                          _panel_ctx(entry, part))
    return RedirectResponse(f"/p/{pid}/parts", status_code=303)


@router.post("/p/{pid}/parts/{part_id}/workflow")
async def part_workflow(request: Request, pid: str, part_id: str):
    """part 级 workflow 显式路由覆盖（空值 = 清除，走 chapter 自动路由）。"""
    entry = load_project_or_404(request, pid)
    part = _find_part(entry, part_id)
    form = await request.form()
    workflow = str(form.get("workflow", "")).strip()
    if workflow and workflow not in WORKFLOW_VOCAB:
        raise HTTPException(status_code=400, detail="未知 workflow（词表见 E-WORKFLOW-UNKNOWN）")
    part.workflow = workflow or None
    save_part(entry.project, part)
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "part_panel.html",
                                          _panel_ctx(entry, part))
    return RedirectResponse(f"/p/{pid}/parts", status_code=303)


def _known_ids(project) -> set[str]:
    known: set[str] = set()
    for attr in ("data_cards", "facts", "claims", "notes", "methods", "params"):
        known |= set(getattr(project, attr))
    return known


def _node_form_ctx(entry, part, node, values, errors):
    project = entry.project
    return {"pid": entry.pid, "part": part, "node": node,
            "purpose_vocab": sorted(PURPOSE_VOCAB), "role_vocab": sorted(ROLE_VOCAB),
            "entity_ids": sorted(_known_ids(project)), "values": values,
            "errors": errors}


@router.get("/p/{pid}/parts/{part_id}/nodes/{node_id}")
def node_edit_get(request: Request, pid: str, part_id: str, node_id: str):
    entry = load_project_or_404(request, pid)
    part = _find_part(entry, part_id)
    node = _find_node(part, node_id)
    values = node.model_dump()
    values["use_id"] = [u.id for u in node.uses]
    values["use_role"] = [u.role for u in node.uses]
    return templates.TemplateResponse(
        request, "node_form.html",
        _node_form_ctx(entry, part, node, values, {}))


@router.post("/p/{pid}/parts/{part_id}/nodes/{node_id}")
async def node_edit_post(request: Request, pid: str, part_id: str, node_id: str):
    entry = load_project_or_404(request, pid)
    part = _find_part(entry, part_id)
    node = _find_node(part, node_id)
    form = await request.form()
    # 回显值手工构造：uses 两列保持列表（模板按 use_id 长度循环），其余为标量
    values = {"purpose": str(form.get("purpose", "")),
              "logic": str(form.get("logic", "")),
              "status": str(form.get("status", "draft")),
              "comment": str(form.get("comment", "")),
              "use_id": [str(v) for v in form.getlist("use_id")],
              "use_role": [str(v) for v in form.getlist("use_role")]}
    uses = [Use(id=str(i).strip(), role=str(r).strip())
            for i, r in zip(form.getlist("use_id"), form.getlist("use_role"))
            if str(i).strip()]
    try:
        new_node = Node(id=node_id, purpose=str(form.get("purpose", "")).strip(),
                        uses=uses, logic=str(form.get("logic", "")),
                        status=str(form.get("status", "draft")),
                        comment=str(form.get("comment", "")))
    except ValidationError as exc:
        errors = {(".".join(str(p) for p in e["loc"]) or "__all__"): e["msg"]
                  for e in exc.errors()}
        return templates.TemplateResponse(
            request, "node_form.html",
            _node_form_ctx(entry, part, node, values, errors))
    bad = [u.id for u in new_node.uses if u.id not in _known_ids(entry.project)]
    if bad:
        return templates.TemplateResponse(
            request, "node_form.html",
            _node_form_ctx(entry, part, node, values,
                           {"uses": "实体不存在：" + "、".join(sorted(set(bad)))}))
    part.nodes[part.nodes.index(node)] = new_node
    save_part(entry.project, part)
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "part_panel.html",
                                          _panel_ctx(entry, part))
    return RedirectResponse(f"/p/{pid}/parts/{part_id}", status_code=303)


def _find_part_by_project(project, part_id: str):
    for part in project.parts:
        if part.id == part_id:
            return part
    raise HTTPException(status_code=404, detail="叙事 part 不存在")


@router.post("/p/{pid}/parts/{part_id}/generate")
async def generate(request: Request, pid: str, part_id: str):
    # 只校验 pid 存在，不要求扫描快照 available：闸门（红线 6）才是唯一裁决者，
    # 校验错误必须在 banner 里展示而非 404（设计 §6）。
    entry = load_entry_or_404(request, pid)
    form = await request.form()
    mock = str(form.get("mock", "")) == "1"

    # 闸门（红线 6）：新生成快照，load + validate，有 error 即拒绝
    project, load_diags = load_project(entry.path)
    diagnostics = load_diags + validate_project(project)
    if any(d.is_error for d in diagnostics):
        # HTMLResponse 不经模板 autoescape，诊断字段（源自卡内容）必须手工转义
        banner = "".join(
            f'<div class="field-error">{_html.escape(d.path)} '
            f'[{_html.escape(d.code)}] {_html.escape(d.message)}</div>'
            for d in diagnostics if d.is_error)
        html = (f'<div class="banner error"><div>校验存在错误，拒绝生成</div>{banner}</div>'
                f'<div id="run-log" class="run-log"></div>')
        return HTMLResponse(html)
    part = _find_part_by_project(project, part_id)
    run = request.app.state.runs.try_start(pid)
    if run is None:
        return HTMLResponse(
            '<div class="banner error">已有生成任务在运行，请等待完成</div>'
            '<div id="run-log" class="run-log"></div>', status_code=409)

    def worker() -> None:
        try:
            client = make_client(mock, project_root=project.root)
            run_part_draft(project, part, client=client, on_event=lambda e: run.emit(
                RunEvent(e.kind, e.node_id, e.message)))
        except Exception as exc:
            # runner 自身失败时已发过 run_failed（D1）；pre-try 异常（如 make_client 无 key）
            # 需在此补发终态事件，否则 SSE 静默挂死到超时
            run.error = str(exc)
            run.emit(RunEvent("run_failed", message=str(exc)))
        finally:
            request.app.state.runs.finish(pid, run)

    threading.Thread(target=worker, daemon=True).start()
    return templates.TemplateResponse(
        request, "run_console.html",
        {"pid": pid, "part_id": part_id, "run_id": run.id})


@router.get("/p/{pid}/runs/{run_id}/events")
def sse_events(request: Request, pid: str, run_id: str):
    run = request.app.state.runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    return StreamingResponse(run.stream_sse(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def register(app: FastAPI) -> None:
    app.include_router(router)
