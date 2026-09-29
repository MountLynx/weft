"""WebUI 共享 helpers：模板、卡种映射、项目解析（webui 设计 §3/§4.1）。"""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.templating import Jinja2Templates

from weft.web.discovery import ProjectEntry

_TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))

# kind → Project 属性名（models/cards.py 六类卡）
KIND_ATTRS = {"data": "data_cards", "fact": "facts", "claim": "claims",
              "note": "notes", "method": "methods", "param": "params"}
KIND_LABELS = {"data": "data 卡", "fact": "fact 卡", "claim": "claim 卡",
               "note": "note 卡", "method": "method 卡", "param": "param 卡"}


def _entries_for(request: Request) -> list[ProjectEntry]:
    """两模式统一的条目来源：注册表模式实时读表（R7），扫描模式目录扫描。"""
    from weft.web.discovery import registry_projects, scan_projects

    if getattr(request.app.state, "projects_source", "scan") == "registry":
        return registry_projects()
    return scan_projects(request.app.state.projects_root)


def load_entry_or_404(request: Request, pid: str) -> ProjectEntry:
    for entry in _entries_for(request):
        if entry.pid == pid:
            if entry.missing:
                raise HTTPException(status_code=404, detail="项目位置失联")
            return entry
    raise HTTPException(status_code=404, detail="项目不存在")


def load_project_or_404(request: Request, pid: str) -> ProjectEntry:
    entry = load_entry_or_404(request, pid)
    if not entry.available or entry.project is None:
        raise HTTPException(status_code=404, detail="项目不可用")
    return entry
