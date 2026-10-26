"""叙事工作台 API（webui-react 设计 §3.2）：part 清单/面板/工作流覆盖/节点/生成/SSE。

语义与旧 HTML 路由一一对应（routes/parts.py）。面板类 POST 返回刷新后的面板
payload（替代旧 htmx 片段交换，前端少一次回读）。
"""
from __future__ import annotations

import threading

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ValidationError

from weft.engine import make_client
from weft.engine.part_draft import run_part_draft
from weft.labels import KEY_FIELD, label_map
from weft.models.narrative import Node, Use
from weft.store.loader import load_project
from weft.store.writer import save_part
from weft.validation import validate_project
from weft.validation.rules import PURPOSE_VOCAB, ROLE_VOCAB
from weft.web.common import KIND_ATTRS, load_entry_or_404, load_project_or_404
from weft.web.runs import RunEvent
from weft.workflow import WORKFLOW_VOCAB, normalize_chapter

router = APIRouter(prefix="/api")

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


def _chapter_cards(project, part) -> list[dict]:
    """本章标签卡（card-chapters 设计 §5.1）：chapters 匹配本 part 章节的全部
    标签卡（六卡种、含全状态），used = 已被本 part 任一节点 uses 引用。"""
    chapter = project.part_chapters.get(part.id, "")
    if not chapter:
        return []
    target = normalize_chapter(chapter)
    used_ids = {u.id for n in part.nodes for u in n.uses}
    cards = []
    for kind, attr in KIND_ATTRS.items():
        for cid, card in getattr(project, attr).items():
            if not any(normalize_chapter(t) == target for t in card.chapters):
                continue
            cards.append({"id": cid, "kind": kind, "status": card.status,
                          "key": getattr(card, KEY_FIELD[kind], "") or "",
                          "used": cid in used_ids})
    cards.sort(key=lambda c: (c["kind"], c["id"]))
    return cards


def _panel_payload(entry, part) -> dict:
    project = entry.project
    chapter = project.part_chapters.get(part.id, "")
    return {"ok": True, "part": {"id": part.id, "workflow": part.workflow},
            "workflow_vocab": list(WORKFLOW_VOCAB),
            "chapter": chapter,
            "chapter_norm": normalize_chapter(chapter) if chapter else "",
            "chapter_cards": _chapter_cards(project, part),
            "nodes": [{"id": n.id, "purpose": n.purpose, "status": n.status,
                       "comment": n.comment,
                       "uses": [{"id": u.id, "role": u.role} for u in n.uses]}
                      for n in part.nodes],
            "use_labels": label_map(
                project, [u.id for n in part.nodes for u in n.uses]),
            "draft_text": _draft_text(project, part.id)}


@router.get("/projects/{pid}/parts")
def parts_list(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    if not entry.project.parts:
        raise HTTPException(status_code=404, detail="项目没有叙事 part")
    parts = [{"id": p.id, "workflow": p.workflow, "n_nodes": len(p.nodes)}
             for p in entry.project.parts]
    return {"ok": True, "parts": parts, "first": entry.project.parts[0].id}


@router.get("/projects/{pid}/parts/{part_id}")
def part_panel(request: Request, pid: str, part_id: str):
    entry = load_project_or_404(request, pid)
    part = _find_part(entry, part_id)
    return _panel_payload(entry, part)


class WorkflowBody(BaseModel):
    workflow: str = ""


@router.post("/projects/{pid}/parts/{part_id}/workflow")
async def part_workflow(request: Request, pid: str, part_id: str,
                        body: WorkflowBody):
    """part 级 workflow 显式路由覆盖（空值 = 清除，走 chapter 自动路由）。"""
    entry = load_project_or_404(request, pid)
    part = _find_part(entry, part_id)
    workflow = body.workflow.strip()
    if workflow and workflow not in WORKFLOW_VOCAB:
        raise HTTPException(status_code=400,
                            detail="未知 workflow（词表见 E-WORKFLOW-UNKNOWN）")
    part.workflow = workflow or None
    save_part(entry.project, part)
    return _panel_payload(entry, part)


class NodeStatusBody(BaseModel):
    status: str = ""
    comment: str | None = None   # None = 快捷 ✅/❌ 不携带 comment 时保留原值


@router.post("/projects/{pid}/parts/{part_id}/nodes/{node_id}/status")
async def node_review(request: Request, pid: str, part_id: str, node_id: str,
                      body: NodeStatusBody):
    entry = load_project_or_404(request, pid)
    part = _find_part(entry, part_id)
    node = _find_node(part, node_id)
    if body.status not in _STATUSES:
        raise HTTPException(status_code=400, detail="非法 status")
    updates: dict = {"status": body.status}
    if body.comment is not None:
        updates["comment"] = body.comment
    part.nodes[part.nodes.index(node)] = node.model_copy(update=updates)
    save_part(entry.project, part)
    return _panel_payload(entry, part)


def _known_ids(project) -> set[str]:
    known: set[str] = set()
    for attr in ("data_cards", "facts", "claims", "notes", "methods", "params"):
        known |= set(getattr(project, attr))
    return known


@router.get("/projects/{pid}/parts/{part_id}/nodes/{node_id}")
def node_edit_get(request: Request, pid: str, part_id: str, node_id: str):
    entry = load_project_or_404(request, pid)
    part = _find_part(entry, part_id)
    node = _find_node(part, node_id)
    project = entry.project
    values = node.model_dump()
    values["use_id"] = [u.id for u in node.uses]
    values["use_role"] = [u.role for u in node.uses]
    return {"node": {"id": node.id, "part_id": part.id}, "values": values,
            "purpose_vocab": sorted(PURPOSE_VOCAB), "role_vocab": sorted(ROLE_VOCAB),
            "entity_ids": sorted(_known_ids(project)),
            "entity_labels": label_map(project, sorted(_known_ids(project)))}


class UseItem(BaseModel):
    id: str = ""
    role: str = ""


class NodeBody(BaseModel):
    purpose: str = ""
    logic: str = ""
    status: str = "draft"
    comment: str = ""
    uses: list[UseItem] = []


@router.patch("/projects/{pid}/parts/{part_id}/nodes/{node_id}")
async def node_edit_patch(request: Request, pid: str, part_id: str, node_id: str,
                          body: NodeBody):
    entry = load_project_or_404(request, pid)
    part = _find_part(entry, part_id)
    node = _find_node(part, node_id)
    uses = [Use(id=u.id.strip(), role=u.role.strip())
            for u in body.uses if u.id.strip()]
    values = {"purpose": body.purpose, "logic": body.logic,
              "status": body.status, "comment": body.comment,
              "use_id": [u.id for u in body.uses],
              "use_role": [u.role for u in body.uses]}
    try:
        new_node = Node(id=node_id, purpose=body.purpose.strip(), uses=uses,
                        logic=body.logic, status=body.status,
                        comment=body.comment)
    except ValidationError as exc:
        errors = {(".".join(str(p) for p in e["loc"]) or "__all__"): e["msg"]
                  for e in exc.errors()}
        return _node_errors_422(errors, values)
    bad = [u.id for u in new_node.uses if u.id not in _known_ids(entry.project)]
    if bad:
        return _node_errors_422(
            {"uses": "实体不存在：" + "、".join(sorted(set(bad)))}, values)
    part.nodes[part.nodes.index(node)] = new_node
    save_part(entry.project, part)
    return _panel_payload(entry, part)


def _node_errors_422(errors: dict, values: dict):
    return JSONResponse(status_code=422,
                        content={"detail": "校验失败", "errors": errors,
                                 "values": values})


class GenerateBody(BaseModel):
    mock: bool = False


@router.post("/projects/{pid}/parts/{part_id}/generate")
async def generate(request: Request, pid: str, part_id: str,
                   body: GenerateBody):
    # 只校验 pid 存在，不要求扫描快照 available：闸门（红线 6）才是唯一裁决者，
    # 校验错误必须在响应里展示而非 404（设计 §6）。
    entry = load_entry_or_404(request, pid)

    # 闸门（红线 6）：新生成快照，load + validate，有 error 即拒绝
    project, load_diags = load_project(entry.path)
    diagnostics = load_diags + validate_project(project)
    if any(d.is_error for d in diagnostics):
        from weft.web.common import diags_to_json

        return JSONResponse(
            status_code=422,
            content={"detail": "校验存在错误，拒绝生成",
                     "diagnostics": diags_to_json(
                         [d for d in diagnostics if d.is_error])})
    part = _find_part_by_project(project, part_id)
    run = request.app.state.runs.try_start(pid)
    if run is None:
        raise HTTPException(status_code=409,
                            detail="已有生成任务在运行，请等待完成")

    def worker() -> None:
        try:
            client = make_client(body.mock, project_root=project.root)
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
    return {"ok": True, "run_id": run.id, "part_id": part_id}


def _find_part_by_project(project, part_id: str):
    for part in project.parts:
        if part.id == part_id:
            return part
    raise HTTPException(status_code=404, detail="叙事 part 不存在")


@router.get("/projects/{pid}/runs/{run_id}/events")
def sse_events(request: Request, pid: str, run_id: str):
    run = request.app.state.runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    return StreamingResponse(run.stream_sse(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def register(app: FastAPI) -> None:
    app.include_router(router)
