"""卡片路由（webui 设计 §3/§4）：总览、列表、详情、审阅、编辑、新建。

路由注册顺序：/cards/{kind}/new 必须先于 /cards/{kind}/{card_id} 注册（设计文档注）。
"""
from __future__ import annotations

import re

import yaml
from pydantic import ValidationError

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse

from weft.engine.bib_propose import BibProposeError, propose_note
from weft.engine.clients import make_client
from weft.store.writer import create_card, next_card_id, save_card
from weft.web.card_forms import (
    FIELD_SPECS,
    KIND_ID_WIDGET,
    KIND_MODELS,
    KIND_PREFIX,
    build_choices,
    form_to_meta,
    form_to_values,
    validation_errors,
    values_for_template,
)
from weft.web.common import KIND_ATTRS, KIND_LABELS, load_project_or_404, templates

router = APIRouter()

_STATUSES = ("draft", "approved", "rejected")
# 新建卡的 id 是用户可控的落盘路径组件（模型层 id 无约束且 schema 冻结，只能在此守卫）
_CARD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
# 列表页展示的"关键字段"（有则显示），按卡种
_KEY_FIELD = {"data": "description", "fact": "statement", "claim": "statement",
              "note": "summary", "method": "statement", "param": "method"}


def _sync_managed_bib(project_root) -> str | None:
    """note 卡写盘后重渲 managed bib；返回重定向标记（None = unmanaged/形状不齐，P-D1）。"""
    from weft import bibgen
    from weft.store.loader import load_project

    project, _ = load_project(project_root)
    if not project.bib_managed or len(project.bib_files) != 1:
        return None
    try:
        bibgen.sync_bib(project)
    except (bibgen.BibValueError, OSError, UnicodeDecodeError):
        return "bib_error"
    return "bib_updated"


def _entry_value_error(project, card) -> str | None:
    """预检：假设卡写盘后渲染 bib 是否合法（E-BIB-VALUE 前置，避免毒化项目）。"""
    from dataclasses import replace

    from weft import bibgen

    if not project.bib_managed:
        return None
    if card.entry is None:
        return None
    notes = dict(project.notes)
    notes[card.id] = card
    try:
        bibgen.render_bib(replace(project, notes=notes))
    except bibgen.BibValueError as exc:
        return str(exc)
    return None


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


@router.get("/p/{pid}/cards/{kind}/new")
def card_new_get(request: Request, pid: str, kind: str):
    if kind not in KIND_ATTRS:
        raise HTTPException(status_code=404, detail="未知卡种")
    entry = load_project_or_404(request, pid)
    widget = KIND_ID_WIDGET[kind]
    prefilled = ""
    id_choices: list[str] = []
    if widget == "auto":
        prefilled = next_card_id(entry.project, KIND_PREFIX[kind])
    elif widget == "bibkey":
        id_choices = sorted(entry.project.bib_keys)
    blank = {"status": "draft", "comment": ""}
    if kind == "param":
        blank["values"] = ""
    return templates.TemplateResponse(
        request, "card_form.html",
        {"pid": pid, "kind": kind,
         "form_title": f"新建 {KIND_LABELS[kind]}",
         "action": f"/p/{pid}/cards/{kind}/new",
         "cancel_url": f"/p/{pid}/cards/{kind}",
         "is_new": True, "id_widget": widget, "prefilled_id": prefilled,
         "id_choices": id_choices, "specs": FIELD_SPECS[kind],
         "values": blank, "choices": build_choices(kind, entry.project),
         "errors": {}})


@router.post("/p/{pid}/cards/{kind}/new")
async def card_new_post(request: Request, pid: str, kind: str):
    if kind not in KIND_ATTRS:
        raise HTTPException(status_code=404, detail="未知卡种")
    entry = load_project_or_404(request, pid)
    form = await request.form()

    def rerender(errors: dict[str, str]):
        widget = KIND_ID_WIDGET[kind]
        prefilled = (next_card_id(entry.project, KIND_PREFIX[kind])
                     if widget == "auto" else "")
        id_choices = sorted(entry.project.bib_keys) if widget == "bibkey" else []
        return templates.TemplateResponse(
            request, "card_form.html",
            {"pid": pid, "kind": kind, "form_title": f"新建 {KIND_LABELS[kind]}",
             "action": f"/p/{pid}/cards/{kind}/new",
             "cancel_url": f"/p/{pid}/cards/{kind}",
             "is_new": True, "id_widget": widget, "prefilled_id": prefilled,
             "id_choices": id_choices, "specs": FIELD_SPECS[kind],
             "values": form_to_values(kind, form),
             "choices": build_choices(kind, entry.project), "errors": errors})

    meta, errors = form_to_meta(kind, form, is_new=True, card_id=None)
    card = None
    if not errors:
        try:
            card = KIND_MODELS[kind].model_validate(meta)
        except ValidationError as exc:
            errors = validation_errors(exc)
    if card is not None and (".." in card.id or not _CARD_ID_RE.match(card.id)):
        # id 是用户可控的落盘路径组件：拒绝空串/路径片段（模型层 id 无约束且 schema 冻结）
        errors = {"id": "id 非法：须以字母或数字开头，仅含 A-Z a-z 0-9 . _ : -，且不含 '..'"}
        card = None
    if card is not None and kind == "note":
        err = _entry_value_error(entry.project, card)
        if err:
            errors = {"entry": f"[E-BIB-VALUE] {err}"}
            card = None
    if card is not None:
        try:
            create_card(entry.project.root, card)
        except FileExistsError as exc:
            errors = {"id": str(exc)}
            card = None
    if card is None:
        return rerender(errors)
    url = f"/p/{pid}/cards/{kind}/{card.id}"
    if kind == "note" and card.status == "approved":
        flag = _sync_managed_bib(entry.project.root)
        if flag:
            url += f"?bib={flag}"
    return RedirectResponse(url, status_code=303)


@router.get("/p/{pid}/notes/propose")
def bib_propose_get(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    return templates.TemplateResponse(
        request, "bib_propose.html",
        {"pid": pid, "action": f"/p/{pid}/notes/propose",
         "cancel_url": f"/p/{pid}/cards/note", "clues": "", "error": ""})


@router.post("/p/{pid}/notes/propose")
async def bib_propose_post(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    form = await request.form()
    clues = str(form.get("clues") or "")
    client = make_client(mock=False, project_root=entry.project.root)

    def rerender(error: str):
        return templates.TemplateResponse(
            request, "bib_propose.html",
            {"pid": pid, "action": f"/p/{pid}/notes/propose",
             "cancel_url": f"/p/{pid}/cards/note", "clues": clues, "error": error})

    try:
        key, fields = await propose_note(entry.project, clues, client)
    except BibProposeError as exc:
        return rerender(str(exc))
    from weft.engine.card_writer import write_proposed_cards
    write_proposed_cards(entry.project, [("note", fields)])
    return RedirectResponse(f"/p/{pid}/cards/note/{key}", status_code=303)


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
         "fields": {k: (yaml.safe_dump(v, allow_unicode=True, sort_keys=False)
                        if k == "entry" and v else ("" if v is None else v))
                    for k, v in card.model_dump().items()
                    if k not in ("id", "status", "comment")},
         "bib_flag": request.query_params.get("bib"),})


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
    if kind == "note":
        err = _entry_value_error(entry.project, new_card)
        if err:
            raise HTTPException(status_code=400, detail=f"[E-BIB-VALUE] {err}")
    save_card(entry.project.root, new_card,
              old_rel=entry.project.card_paths[card_id].as_posix())
    url = f"/p/{pid}/cards/{kind}/{card_id}"
    if kind == "note":
        flag = _sync_managed_bib(entry.project.root)
        if flag:
            url += f"?bib={flag}"
    return RedirectResponse(url, status_code=303)


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
    if card is not None and kind == "note":
        err = _entry_value_error(entry.project, card)
        if err:
            errors = {"entry": f"[E-BIB-VALUE] {err}"}
            card = None
    if card is None:
        return rerender(errors)
    save_card(entry.project.root, card,
              old_rel=entry.project.card_paths[card_id].as_posix())
    url = f"/p/{pid}/cards/{kind}/{card_id}"
    if kind == "note":
        flag = _sync_managed_bib(entry.project.root)
        if flag:
            url += f"?bib={flag}"
    return RedirectResponse(url, status_code=303)


def register(app: FastAPI) -> None:
    app.include_router(router)
