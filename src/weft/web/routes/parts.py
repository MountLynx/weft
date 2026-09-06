"""叙事工作台（webui 设计 §5）：part 页签、节点审阅、节点编辑（Task 10）、生成（Task 11）。"""
from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse

from weft.store.writer import save_part
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
    part.nodes[part.nodes.index(node)] = node.model_copy(
        update={"status": status, "comment": str(form.get("comment", ""))})
    save_part(entry.project, part)
    return RedirectResponse(f"/p/{pid}/parts/{part_id}", status_code=303)


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
    return RedirectResponse(f"/p/{pid}/parts/{part_id}", status_code=303)


def register(app: FastAPI) -> None:
    app.include_router(router)
