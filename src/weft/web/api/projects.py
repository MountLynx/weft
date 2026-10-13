"""项目层 API（webui-react 设计 §3.2）：列表/新建/仪表盘/诊断/bib 切换/图谱/文件。

语义与旧 HTML 路由一一对应（core.py + bibmode.py），仅响应形态 HTML→JSON：
- 项目加载级损坏（project=None）不 404，available=false + 诊断列表（红线 3 展示语义）。
- 校验 error 项目照常出 dashboard/诊断（不可用徽章 + 指路修复）。
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel

from weft.graphgen.writer import write_outputs
from weft.registry import validate_project_name
from weft.scaffold import InitCollisionError, init_project
from weft.web.common import (
    KIND_ATTRS,
    KIND_LABELS,
    diags_to_json,
    entry_to_json,
    load_entry_or_404,
    load_project_or_404,
)

router = APIRouter(prefix="/api")


def _collision_message(exc: InitCollisionError) -> str:
    """E-INIT-COLLISION 的表单文案（与 CLI 同语义：fail-closed，零写入）。"""
    preview = "、".join(exc.entries[:5]) + ("…" if len(exc.entries) > 5 else "")
    return f"目标目录非空（{preview}）；为避免覆盖，未写入任何文件"


def _index_payload(request: Request, *, entries, reg_error) -> dict:
    from weft.registry import registry_path

    registry = request.app.state.projects_source == "registry"
    base = {"entries": [entry_to_json(e) for e in entries],
            "reg_error": str(reg_error) if reg_error else None,
            "kind_labels": KIND_LABELS}
    if registry:
        base["registry_mode"] = True
        base["projects_root"] = None
        base["registry_path"] = str(registry_path())
    else:
        base["registry_mode"] = False
        base["projects_root"] = str(request.app.state.projects_root)
        base["registry_path"] = ""
    return base


@router.get("/projects")
def projects_index(request: Request):
    if request.app.state.projects_source == "registry":
        from weft.registry import RegistryError
        from weft.web.discovery import registry_projects

        try:
            entries = registry_projects()
            reg_error = None
        except RegistryError as exc:
            entries, reg_error = [], f"{exc.code} {exc.message}"
        return _index_payload(request, entries=entries, reg_error=reg_error)

    from weft.web.discovery import scan_projects

    entries = scan_projects(request.app.state.projects_root)
    return _index_payload(request, entries=entries, reg_error=None)


class NewProjectBody(BaseModel):
    name: str = ""
    location: str = ""


@router.post("/projects")
async def project_new(request: Request, body: NewProjectBody):
    name, error = validate_project_name(body.name)
    if request.app.state.projects_source == "registry":
        return _project_new_registry(body, name, error)

    from weft.web.discovery import scan_projects

    if error is None:
        try:
            init_project(request.app.state.projects_root / name)
        except InitCollisionError as exc:
            error = _collision_message(exc)
    if error is not None:
        raise HTTPException(status_code=422, detail=error)
    return {"ok": True, "pid": name}


def _project_new_registry(body: NewProjectBody, name: str, error: str | None):
    """注册表模式新建：可选位置输入（projects registry 设计 §5），创建 + 登记闭环。"""
    from weft.registry import (
        RegistryError,
        ensure_registrable,
        load_registry,
        register_project,
        save_registry,
    )

    location = body.location.strip()
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
        raise HTTPException(status_code=422, detail=error)
    return {"ok": True, "pid": name}


def _dashboard_payload(entry, pid: str) -> dict:
    if entry.project is None:
        # 只有加载级损坏（E-PARSE 等，无项目对象）才是"无法加载"；
        # 校验错误项目照常返回（不可用徽章 + 错误计数 + 待审队列指路修复）。
        return {"available": False, "pid": pid,
                "diagnostics": diags_to_json(entry.diagnostics)}
    project = entry.project
    status_counts: Counter = Counter()
    review_queue: list[dict] = []
    for kind, attr in KIND_ATTRS.items():
        table = getattr(project, attr)
        status_counts.update(card.status for card in table.values())
        for cid, card in table.items():
            if card.status == "draft":
                review_queue.append({
                    "type": "card", "card_kind": kind, "label": KIND_LABELS[kind],
                    "id": cid, "rel": project.card_paths[cid].as_posix()})
    for part in project.parts:
        for node in part.nodes:
            status_counts[node.status] += 1
            if node.status == "draft":
                review_queue.append({
                    "type": "node", "part_id": part.id, "label": "叙事节点",
                    "id": node.id, "rel": project.part_paths[part.id].as_posix()})
    return {"available": entry.available, "pid": pid, "path": str(entry.path),
            "bib_managed": project.bib_managed,
            "bib_files": list(project.bib_files),
            "status_counts": dict(status_counts),
            "kind_counts": {kind: len(getattr(project, attr))
                            for kind, attr in KIND_ATTRS.items()},
            "n_parts": len(project.parts),
            "n_errors": entry.n_errors, "n_warnings": entry.n_warnings,
            "diagnostics": diags_to_json(entry.diagnostics),
            "review_queue": review_queue}


@router.get("/projects/{pid}")
def project_dashboard(request: Request, pid: str):
    return _dashboard_payload(load_entry_or_404(request, pid), pid)


@router.get("/projects/{pid}/diagnostics")
def diagnostics_payload(request: Request, pid: str):
    # 故意用 load_entry_or_404：损坏项目也要能看诊断——诊断页正是看错误的地方（设计 §2/§7）。
    entry = load_entry_or_404(request, pid)
    fix_map: dict[str, str] = {}
    if entry.project is not None:
        from weft import bibgen
        fix_map = {entry.project.card_paths[k].as_posix(): k
                   for k in bibgen.fixable_notes(entry.project)}
    return {"pid": pid,
            "available": entry.project is not None,
            "n_errors": entry.n_errors, "n_warnings": entry.n_warnings,
            "diagnostics": diags_to_json(entry.diagnostics),
            "fixable": fix_map,
            "kind_labels": KIND_LABELS}


class BibSwitchBody(BaseModel):
    to: str = "managed"


_TO = {"managed": True, "unmanaged": False}


@router.get("/projects/{pid}/bib/switch")
def switch_confirm(request: Request, pid: str, to: str = "managed"):
    if to not in _TO:
        raise HTTPException(status_code=404, detail="未知目标模式")
    entry = load_entry_or_404(request, pid)
    return _switch_payload(entry, to, None)


def _switch_payload(entry, to: str, error: str | None) -> dict:
    from weft import bibgen

    plan = None
    try:
        plan = asdict(bibgen.plan_switch(entry.project, _TO[to]))
    except bibgen.BibModeError as exc:
        error = error or str(exc)
    return {"to": to, "plan": plan, "error": error}


@router.post("/projects/{pid}/bib/switch")
async def switch_apply(request: Request, pid: str, body: BibSwitchBody):
    from weft import bibgen

    if body.to not in _TO:
        raise HTTPException(status_code=404, detail="未知目标模式")
    entry = load_entry_or_404(request, pid)
    try:
        plan = bibgen.plan_switch(entry.project, _TO[body.to])
        bibgen.apply_switch(entry.project.root, plan)
    except bibgen.BibModeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "to": body.to}


@router.post("/projects/{pid}/bib/fix/{key}")
async def fix_note(request: Request, pid: str, key: str):
    from weft import bibgen

    entry = load_entry_or_404(request, pid)
    try:
        result = bibgen.fix_note_in_bib(entry.project, key)
    except bibgen.BibModeError:
        result = "error"   # M8：按钮可见⇒前置曾成立，失败只剩竞态，通用横幅
    return {"ok": True, "result": result}


@router.get("/projects/{pid}/graph")
def graph_payload(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    graph_path = entry.project.root / "generated" / "graph.json"
    graph = None
    if graph_path.exists():
        try:
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            graph = None   # 手工损坏的 graph.json → 前端"生成图谱"按钮自愈
    return {"graph": graph}


@router.post("/projects/{pid}/graph/regenerate")
def graph_regenerate(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    project = entry.project
    if any(d.is_error for d in entry.diagnostics):
        # 与 CLI graph 同闸门：校验有 error 拒绝生成，引导去看诊断。
        raise HTTPException(status_code=422, detail="校验存在错误，拒绝生成")
    write_outputs(project, project.root / "generated")
    return {"ok": True}


_SAFE_ROOTS = ("drafts", "generated")


@router.get("/projects/{pid}/file")
def file_view(request: Request, pid: str, path: str):
    entry = load_project_or_404(request, pid)
    root = entry.project.root.resolve()
    target = (root / path).resolve()
    parts = Path(path).parts
    allowed = (bool(parts) and parts[0] in _SAFE_ROOTS
               and (target == root or root in target.parents)
               and target.is_file())
    if not allowed:
        raise HTTPException(status_code=404, detail="文件不存在或不在白名单目录")
    return {"path": path,
            "text": target.read_text(encoding="utf-8", errors="replace")}


def register(app: FastAPI) -> None:
    app.include_router(router)
