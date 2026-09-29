"""核心页面路由：项目列表 / 新建项目 / 项目总览仪表盘 / 诊断表 / 元数据图谱 / 文件预览。"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse

from weft.graphgen.writer import write_outputs
from weft.registry import validate_project_name
from weft.scaffold import InitCollisionError, init_project
from weft.web.common import (
    KIND_ATTRS,
    load_entry_or_404,
    load_project_or_404,
    templates,
)

router = APIRouter()


def _collision_message(exc: InitCollisionError) -> str:
    """E-INIT-COLLISION 的表单文案（与 CLI 同语义：fail-closed，零写入）。"""
    preview = "、".join(exc.entries[:5]) + ("…" if len(exc.entries) > 5 else "")
    return f"目标目录非空（{preview}）；为避免覆盖，未写入任何文件"


def _registry_index_context(request: Request, *, entries, reg_error,
                            new_error=None, new_name="", new_location="") -> dict:
    from weft.registry import registry_path

    return {"entries": entries, "projects_root": None,
            "registry_mode": True, "registry_path": str(registry_path()),
            "reg_error": reg_error, "new_error": new_error,
            "new_name": new_name, "new_location": new_location}


@router.get("/")
def index(request: Request):
    from weft.web.discovery import scan_projects

    if request.app.state.projects_source == "registry":
        from weft.registry import RegistryError
        from weft.web.discovery import registry_projects

        try:
            entries = registry_projects()
            reg_error = None
        except RegistryError as exc:
            entries, reg_error = [], exc
        return templates.TemplateResponse(
            request, "index.html",
            _registry_index_context(request, entries=entries, reg_error=reg_error))

    entries = scan_projects(request.app.state.projects_root)
    return templates.TemplateResponse(
        request, "index.html",
        {"entries": entries,
         "projects_root": str(request.app.state.projects_root),
         "registry_mode": False, "registry_path": "", "reg_error": None,
         "new_error": None, "new_name": "", "new_location": ""})


@router.post("/projects/new")
async def project_new(request: Request):
    form = await request.form()
    name, error = validate_project_name(str(form.get("name", "")))
    if request.app.state.projects_source == "registry":
        return _project_new_registry(request, form, name, error)

    from weft.web.discovery import scan_projects

    if error is None:
        try:
            init_project(request.app.state.projects_root / name)
        except InitCollisionError as exc:
            error = _collision_message(exc)
    if error is not None:
        entries = scan_projects(request.app.state.projects_root)
        return templates.TemplateResponse(
            request, "index.html",
            {"entries": entries,
             "projects_root": str(request.app.state.projects_root),
             "registry_mode": False, "registry_path": "", "reg_error": None,
             "new_error": error, "new_name": name, "new_location": ""})
    return RedirectResponse(f"/p/{quote(name, safe='')}/", status_code=303)


def _project_new_registry(request: Request, form, name: str,
                          error: str | None):
    """注册表模式新建：可选位置输入（projects registry 设计 §5），创建 + 登记闭环。"""
    from weft.registry import (
        RegistryError,
        ensure_registrable,
        load_registry,
        register_project,
        save_registry,
    )
    from weft.web.discovery import registry_projects

    location = str(form.get("location", "")).strip()
    target: Path | None = None
    if error is None:
        try:
            reg = load_registry()
            if location:
                parent: Path = Path(location).expanduser()
            elif reg.default_root:
                parent = Path(reg.default_root)
            else:
                raise ValueError("默认根未配置——先执行 weft projects root <目录> 设置，"
                                 "或在表单中填写位置")
            target = parent / name
            clean = ensure_registrable(reg, name, target)  # 落盘前预检：零写入
            target.parent.mkdir(parents=True, exist_ok=True)
            init_project(target)
            register_project(reg, clean, target)
            save_registry(reg)
        except InitCollisionError as exc:
            error = _collision_message(exc)
        except RegistryError as exc:
            error = f"{exc.code} {exc.message}"
        except (ValueError, OSError) as exc:
            where = f"（骨架可能已部分创建于 {target}）" if target is not None else ""
            error = f"写入失败{where}：{exc}"
    if error is not None:
        try:
            entries = registry_projects()
            reg_error = None
        except RegistryError as exc:
            entries, reg_error = [], exc
        return templates.TemplateResponse(
            request, "index.html",
            _registry_index_context(request, entries=entries, reg_error=reg_error,
                                    new_error=error, new_name=name,
                                    new_location=location))
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
