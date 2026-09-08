"""核心页面路由：项目列表 / 新建项目 / 项目总览仪表盘 / 诊断表 / 元数据图谱 / 文件预览。"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse

from weft.graphgen.writer import write_outputs
from weft.scaffold import InitCollisionError, init_project
from weft.web.common import (
    KIND_ATTRS,
    load_entry_or_404,
    load_project_or_404,
    templates,
)

router = APIRouter()


# 项目目录名 = 用户可控的落盘路径组件（同 cards.py 的 _CARD_ID_RE 先例，只能在此守卫）
_NAME_ILLEGAL_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_WINDOWS_RESERVED = ({"CON", "PRN", "AUX", "NUL"}
                     | {f"COM{i}" for i in range(1, 10)}
                     | {f"LPT{i}" for i in range(1, 10)})


def _validate_project_name(raw: str) -> tuple[str, str | None]:
    """返回（规范名 = 去首尾空白, 错误信息）；黑名单制允许中文等任意安全字符。"""
    name = raw.strip()
    if not name:
        return "", "项目名不能为空"
    if name in (".", "..") or name.startswith("."):
        return name, "项目名不能以 . 开头（避免与工具目录约定冲突）"
    if name.endswith("."):
        return name, "项目名不能以 . 结尾（Windows 会静默剥离，导致访问不到）"
    if _NAME_ILLEGAL_RE.search(name):
        return name, "项目名含非法字符（不允许 \\ / : * ? \" < > | 及控制字符）"
    if name.upper() in _WINDOWS_RESERVED:
        return name, "项目名是 Windows 保留设备名"
    if len(name) > 100:
        return name, "项目名过长（不超过 100 字符）"
    return name, None


@router.get("/")
def index(request: Request):
    from weft.web.discovery import scan_projects

    entries = scan_projects(request.app.state.projects_root)
    return templates.TemplateResponse(
        request, "index.html",
        {"entries": entries,
         "projects_root": str(request.app.state.projects_root),
         "new_error": None, "new_name": ""})


@router.post("/projects/new")
async def project_new(request: Request):
    from weft.web.discovery import scan_projects

    form = await request.form()
    name, error = _validate_project_name(str(form.get("name", "")))
    if error is None:
        try:
            init_project(request.app.state.projects_root / name)
        except InitCollisionError as exc:
            # 与 CLI 的 E-INIT-COLLISION 同语义：fail-closed，零写入
            preview = "、".join(exc.entries[:5]) + ("…" if len(exc.entries) > 5 else "")
            error = f"目标目录非空（{preview}）；为避免覆盖，未写入任何文件"
    if error is not None:
        entries = scan_projects(request.app.state.projects_root)
        return templates.TemplateResponse(
            request, "index.html",
            {"entries": entries,
             "projects_root": str(request.app.state.projects_root),
             "new_error": error, "new_name": name})
    return RedirectResponse(f"/p/{quote(name, safe='')}/", status_code=303)


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


@router.get("/p/{pid}/diagnostics")
def diagnostics_page(request: Request, pid: str):
    # 故意用 load_entry_or_404：损坏项目也要能看诊断——诊断页正是看错误的地方（设计 §2/§7）。
    entry = load_entry_or_404(request, pid)
    return templates.TemplateResponse(
        request, "diagnostics.html", {"entry": entry})


@router.get("/p/{pid}/graph")
def graph_page(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    graph_path = entry.project.root / "generated" / "graph.json"
    graph = None
    if graph_path.exists():
        try:
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            graph = None   # 手工损坏的 graph.json → 回退到"生成图谱"按钮自愈
    return templates.TemplateResponse(
        request, "graph.html", {"entry": entry, "graph": graph})


@router.post("/p/{pid}/graph/regenerate")
def graph_regenerate(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    project = entry.project
    if any(d.is_error for d in entry.diagnostics):
        # 与 CLI graph 同闸门：校验有 error 拒绝生成，引导去看诊断。
        return RedirectResponse(f"/p/{pid}/diagnostics", status_code=303)
    write_outputs(project, project.root / "generated")
    return RedirectResponse(f"/p/{pid}/graph", status_code=303)


_SAFE_ROOTS = ("drafts", "generated")


@router.get("/p/{pid}/files/{relpath:path}")
def file_view(request: Request, pid: str, relpath: str):
    entry = load_project_or_404(request, pid)
    root = entry.project.root.resolve()
    target = (root / relpath).resolve()
    parts = Path(relpath).parts
    allowed = (bool(parts) and parts[0] in _SAFE_ROOTS
               and (target == root or root in target.parents)
               and target.is_file())
    if not allowed:
        raise HTTPException(status_code=404, detail="文件不存在或不在白名单目录")
    return templates.TemplateResponse(
        request, "file_view.html",
        {"entry": entry, "rel": relpath,
         "text": target.read_text(encoding="utf-8", errors="replace")})


def register(app: FastAPI) -> None:
    app.include_router(router)
