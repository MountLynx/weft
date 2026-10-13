"""bib 模式切换与一键修复路由（bib-mode-fix 设计 §4）。"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse

from weft import bibgen
from weft.web.common import load_reviewable_or_404, templates

router = APIRouter()

_TO = {"managed": True, "unmanaged": False}


def _confirm_page(request: Request, entry, to: str, error: str | None):
    plan = None
    try:
        plan = bibgen.plan_switch(entry.project, _TO[to])
    except bibgen.BibModeError as exc:
        error = error or str(exc)
    return templates.TemplateResponse(
        request, "bib_switch_confirm.html",
        {"entry": entry, "to": to, "plan": plan, "error": error})


@router.get("/p/{pid}/bib/switch")
def switch_confirm(request: Request, pid: str, to: str = "managed"):
    if to not in _TO:
        raise HTTPException(status_code=404, detail="未知目标模式")
    return _confirm_page(request, load_reviewable_or_404(request, pid), to, None)


@router.post("/p/{pid}/bib/switch")
async def switch_apply(request: Request, pid: str):
    form = await request.form()
    to = str(form.get("to", ""))
    if to not in _TO:
        raise HTTPException(status_code=404, detail="未知目标模式")
    entry = load_reviewable_or_404(request, pid)
    try:
        plan = bibgen.plan_switch(entry.project, _TO[to])
        bibgen.apply_switch(entry.project.root, plan)
    except bibgen.BibModeError as exc:
        return _confirm_page(request, entry, to, str(exc))
    return RedirectResponse(f"/p/{pid}/?bibmode=switched", status_code=303)


@router.post("/p/{pid}/bib/fix/{key}")
async def fix_note(request: Request, pid: str, key: str):
    entry = load_reviewable_or_404(request, pid)
    form = await request.form()
    back = str(form.get("back", "diagnostics"))
    if back not in ("diagnostics", "card"):
        back = "diagnostics"
    try:
        result = bibgen.fix_note_in_bib(entry.project, key)
    except bibgen.BibModeError:
        result = "error"   # M8：按钮可见⇒前置曾成立，失败只剩竞态，通用横幅
    base = (f"/p/{pid}/diagnostics" if back == "diagnostics"
            else f"/p/{pid}/cards/note/{quote(key)}")
    return RedirectResponse(f"{base}?fix={result}", status_code=303)


def register(app: FastAPI) -> None:
    app.include_router(router)
