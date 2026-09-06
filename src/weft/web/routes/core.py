"""核心页面路由：项目列表 / 项目总览仪表盘（graph、诊断、文件预览在 Task 12 扩充）。"""
from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, FastAPI, Request

from weft.web.common import KIND_ATTRS, load_entry_or_404, templates

router = APIRouter()


@router.get("/")
def index(request: Request):
    from weft.web.discovery import scan_projects

    entries = scan_projects(request.app.state.projects_root)
    return templates.TemplateResponse(
        request, "index.html",
        {"entries": entries,
         "projects_root": str(request.app.state.projects_root)})


@router.get("/p/{pid}/")
def dashboard(request: Request, pid: str):
    entry = load_entry_or_404(request, pid)
    if not entry.available:
        return templates.TemplateResponse(
            request, "unavailable.html",
            {"pid": pid, "diagnostics": entry.diagnostics})
    project = entry.project
    status_counts = Counter()
    review_queue: list[dict] = []
    for kind, attr in KIND_ATTRS.items():
        table = getattr(project, attr)
        status_counts.update(card.status for card in table.values())
        for cid, card in table.items():
            if card.status == "draft":
                review_queue.append({
                    "kind": kind, "id": cid,
                    "rel": project.card_paths[cid].as_posix(),
                    "url": f"/p/{pid}/cards/{kind}/{cid}"})
    for part in project.parts:
        for node in part.nodes:
            status_counts[node.status] += 1
            if node.status == "draft":
                review_queue.append({
                    "kind": "叙事节点", "id": node.id,
                    "rel": project.part_paths[part.id].as_posix(),
                    "url": f"/p/{pid}/parts/{part.id}/nodes/{node.id}"})
    return templates.TemplateResponse(
        request, "dashboard.html",
        {"entry": entry, "project": project, "review_queue": review_queue,
         "status_counts": status_counts})


def register(app: FastAPI) -> None:
    app.include_router(router)
