"""WebUI 共享 helpers：卡种映射、项目解析、诊断序列化（webui-react 设计 §3）。"""
from __future__ import annotations

from fastapi import HTTPException, Request

from weft.diagnostics import Diagnostic
from weft.labels import KIND_ATTRS
from weft.web.discovery import ProjectEntry

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


def load_reviewable_or_404(request: Request, pid: str) -> ProjectEntry:
    """审阅面（仪表盘/卡列表/详情/审阅/编辑/改名）：校验错误项目恰恰最需要审卡。

    校验 error（如 unmanaged 提案 note 触发 E-NOTE-NOT-IN-BIB）不阻断——UI 造出的
    状态必须能经 UI 修复（pdf-ingest 计划 P-D2 延伸至写路径，P-D9）；加载级损坏
    （project=None，E-PARSE 等）无卡表可查，仍 404。
    """
    entry = load_entry_or_404(request, pid)
    if entry.project is None:
        raise HTTPException(status_code=404, detail="项目不可用")
    return entry


def diag_to_json(d: Diagnostic) -> dict:
    """诊断 → JSON（E-*/W-* 码原样透传，稳定标识红线）。"""
    return {"level": d.level.value, "code": d.code, "path": d.path,
            "field": d.field, "message": d.message, "is_error": d.is_error}


def diags_to_json(diags) -> list[dict]:
    return [diag_to_json(d) for d in diags]


def entry_to_json(entry: ProjectEntry) -> dict:
    return {"pid": entry.pid, "path": str(entry.path),
            "available": entry.available, "missing": entry.missing,
            "n_cards": entry.n_cards, "n_errors": entry.n_errors,
            "n_warnings": entry.n_warnings}
