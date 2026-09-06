"""叙事工作台（webui 设计 §5）：part 页签、节点审阅、节点编辑（Task 10）、生成（Task 11）。"""
from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from weft.models.narrative import Node, Use
from weft.store.writer import save_part
from weft.validation.rules import PURPOSE_VOCAB, ROLE_VOCAB
from weft.web.common import load_project_or_404, templates
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


def register(app: FastAPI) -> None:
    app.include_router(router)
