"""卡片路由（webui 设计 §3/§4）：总览、列表、详情、审阅、编辑、新建。

路由注册顺序：/cards/{kind}/new 必须先于 /cards/{kind}/{card_id} 注册（设计文档注）。
"""
from __future__ import annotations

from pydantic import ValidationError

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse

from weft.store.writer import save_card
from weft.web.card_forms import (
    FIELD_SPECS,
    KIND_MODELS,
    build_choices,
    form_to_meta,
    form_to_values,
    validation_errors,
    values_for_template,
)
from weft.web.common import KIND_ATTRS, KIND_LABELS, load_project_or_404, templates

router = APIRouter()

_STATUSES = ("draft", "approved", "rejected")
# 列表页展示的"关键字段"（有则显示），按卡种
_KEY_FIELD = {"data": "description", "fact": "statement", "claim": "statement",
              "note": "summary", "method": "statement", "param": "method"}


def _table(request: Request, pid: str, kind: str):
    if kind not in KIND_ATTRS:
        raise HTTPException(status_code=404, detail="未知卡种")
    entry = load_project_or_404(request, pid)
    return entry, getattr(entry.project, KIND_ATTRS[kind])


@router.get("/p/{pid}/cards")
def cards_overview(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    counts = {kind: len(getattr(entry.project, attr))
              for kind, attr in KIND_ATTRS.items()}
    return templates.TemplateResponse(
        request, "cards.html",
        {"entry": entry, "counts": counts, "labels": KIND_LABELS})


@router.get("/p/{pid}/cards/{kind}")
def card_list(request: Request, pid: str, kind: str):
    entry, table = _table(request, pid, kind)
    rows = []
    for cid, card in sorted(table.items()):
        rows.append({
            "id": cid, "status": card.status,
            "key": getattr(card, _KEY_FIELD[kind], "") or "",
            "rel": entry.project.card_paths[cid].as_posix()})
    return templates.TemplateResponse(
        request, "cards.html",
        {"entry": entry, "kind": kind, "rows": rows, "labels": KIND_LABELS,
         "counts": {k: len(getattr(entry.project, a))
                    for k, a in KIND_ATTRS.items()}})


@router.get("/p/{pid}/cards/{kind}/{card_id}")
def card_detail(request: Request, pid: str, kind: str, card_id: str):
    entry, table = _table(request, pid, kind)
    card = table.get(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="卡片不存在")
    return templates.TemplateResponse(
        request, "card_detail.html",
        {"entry": entry, "kind": kind, "card": card,
         "rel": entry.project.card_paths[card_id].as_posix(),
         "fields": {k: v for k, v in card.model_dump().items()
                    if k not in ("id", "status", "comment")}})


@router.post("/p/{pid}/cards/{kind}/{card_id}/status")
async def card_review(request: Request, pid: str, kind: str, card_id: str):
    entry, table = _table(request, pid, kind)
    card = table.get(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="卡片不存在")
    form = await request.form()
    status = str(form.get("status", ""))
    if status not in _STATUSES:
        raise HTTPException(status_code=400, detail="非法 status")
    new_card = card.model_copy(update={"status": status,
                                       "comment": str(form.get("comment", ""))})
    save_card(entry.project.root, new_card,
              old_rel=entry.project.card_paths[card_id].as_posix())
    return RedirectResponse(f"/p/{pid}/cards/{kind}/{card_id}", status_code=303)


@router.get("/p/{pid}/cards/{kind}/{card_id}/edit")
def card_edit_get(request: Request, pid: str, kind: str, card_id: str):
    entry, table = _table(request, pid, kind)
    card = table.get(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="卡片不存在")
    return templates.TemplateResponse(
        request, "card_form.html",
        {"pid": pid, "kind": kind, "form_title": f"编辑 {KIND_LABELS[kind]} {card_id}",
         "action": f"/p/{pid}/cards/{kind}/{card_id}/edit",
         "cancel_url": f"/p/{pid}/cards/{kind}/{card_id}",
         "is_new": False, "id_widget": None, "prefilled_id": "", "id_choices": [],
         "specs": FIELD_SPECS[kind],
         "values": values_for_template(kind, card),
         "choices": build_choices(kind, entry.project), "errors": {}})


@router.post("/p/{pid}/cards/{kind}/{card_id}/edit")
async def card_edit_post(request: Request, pid: str, kind: str, card_id: str):
    entry, table = _table(request, pid, kind)
    old_card = table.get(card_id)
    if old_card is None:
        raise HTTPException(status_code=404, detail="卡片不存在")
    form = await request.form()

    def rerender(errors: dict[str, str]):
        return templates.TemplateResponse(
            request, "card_form.html",
            {"pid": pid, "kind": kind,
             "form_title": f"编辑 {KIND_LABELS[kind]} {card_id}",
             "action": f"/p/{pid}/cards/{kind}/{card_id}/edit",
             "cancel_url": f"/p/{pid}/cards/{kind}/{card_id}",
             "is_new": False, "id_widget": None, "prefilled_id": "", "id_choices": [],
             "specs": FIELD_SPECS[kind], "values": form_to_values(kind, form),
             "choices": build_choices(kind, entry.project), "errors": errors})

    meta, errors = form_to_meta(kind, form, is_new=False, card_id=card_id)
    card = None
    if not errors:
        try:
            card = KIND_MODELS[kind].model_validate(meta)
        except ValidationError as exc:
            errors = validation_errors(exc)
            card = None
    if card is None:
        return rerender(errors)
    save_card(entry.project.root, card,
              old_rel=entry.project.card_paths[card_id].as_posix())
    return RedirectResponse(f"/p/{pid}/cards/{kind}/{card_id}", status_code=303)


def register(app: FastAPI) -> None:
    app.include_router(router)
