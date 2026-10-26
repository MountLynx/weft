"""卡片 API（webui-react 设计 §3.2）：列表/表单规格/新建/详情/审阅/改名/编辑/文献提案。

语义与旧 HTML 路由一一对应（routes/cards.py），仅响应形态 HTML→JSON：
- 校验失败 422 {"errors": {字段: 消息}}，不落盘（失败回显语义由前端持有表单态承担）。
- note 卡批准后 managed bib 同步结果在响应 "bib" 字段（旧 ?bib= 横幅）。
- id 是用户可控落盘路径组件：新建时守卫 _CARD_ID_RE（模型层 schema 冻结）。
"""
from __future__ import annotations

import re
import shutil
from dataclasses import asdict
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.datastructures import UploadFile  # 表单解析产生的是 starlette 基类实例

from weft import bibgen
from weft.bibgen import sync_managed_bib
from weft.engine.bib_propose import BibProposeError, propose_note
from weft.engine.clients import make_client
from weft.engine.draft_rules import DraftError
from weft.graphgen.index import build_index
from weft.labels import KEY_FIELD
from weft.pdftext import (
    CLUES_CHARS,
    PdfTextError,
    extract_text,
    normalize_lf,
    validate_upload_name,
)
from weft.rename import RenameError, apply_rename, plan_rename
from weft.scaffold import NewCollisionError, NewNameError
from weft.store.writer import create_card, next_card_id, save_card
from weft.web.card_forms import (
    FIELD_SPECS,
    KIND_ID_WIDGET,
    KIND_MODELS,
    KIND_PREFIX,
    build_choices,
    build_labels,
    parse_tags,
    validation_errors,
    values_for_template,
)
from weft.web.common import (
    KIND_ATTRS,
    KIND_LABELS,
    load_project_or_404,
    load_reviewable_or_404,
)

router = APIRouter(prefix="/api")

_STATUSES = ("draft", "approved", "rejected")
# 新建卡的 id 是用户可控的落盘路径组件（模型层 id 无约束且 schema 冻结，只能在此守卫）
_CARD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


def _table(request: Request, pid: str, kind: str):
    if kind not in KIND_ATTRS:
        raise HTTPException(status_code=404, detail="未知卡种")
    entry = load_reviewable_or_404(request, pid)
    return entry, getattr(entry.project, KIND_ATTRS[kind])


def _kind_counts(entry) -> dict[str, int]:
    return {kind: len(getattr(entry.project, attr))
            for kind, attr in KIND_ATTRS.items()}


@router.get("/projects/{pid}/cards")
def cards_overview(request: Request, pid: str):
    entry = load_reviewable_or_404(request, pid)
    return {"counts": _kind_counts(entry), "labels": KIND_LABELS}


# 正向链接字段 → 目标卡种（值是真实落盘内容：悬空引用保留；反向边由 build_index 过滤）
_LINK_FIELDS: dict[str, dict[str, str]] = {
    "fact": {"data": "data", "supports": "claim"},
    "claim": {"cites": "note"},
    "method": {"derived_from": "note"},
    "param": {"method": "method", "derived_from": "note"},
}


@router.get("/projects/{pid}/cards/links")
def cards_links(request: Request, pid: str):
    """全量卡链路（webui-card-links 设计 §2）：实时反向索引 + 正向链接合并。

    只读、无落盘；rejected 卡包含（决策 L8）。路由先于 /cards/{kind}（决策 L2）。
    """
    entry = load_reviewable_or_404(request, pid)
    entities = build_index(entry.project)["entities"]
    for kind, fields in _LINK_FIELDS.items():
        for cid, card in getattr(entry.project, KIND_ATTRS[kind]).items():
            links: dict[str, list[str]] = {}
            for field, target in fields.items():
                value = getattr(card, field)
                # param.method 是标量 str，其余链接字段均为 list（模型层 schema 冻结）
                links[target] = list(value) if isinstance(value, list) else [value]
            entities[cid]["links"] = links
    for ent in entities.values():
        ent.setdefault("links", {})
    return {"entities": entities}


@router.get("/projects/{pid}/cards/{kind}")
def card_list(request: Request, pid: str, kind: str):
    entry, table = _table(request, pid, kind)
    rows = []
    for cid, card in sorted(table.items()):
        rows.append({
            "id": cid, "status": card.status,
            "key": getattr(card, KEY_FIELD[kind], "") or "",
            "chapters": list(card.chapters),
            "rel": entry.project.card_paths[cid].as_posix()})
    return {"kind": kind, "label": KIND_LABELS[kind], "rows": rows,
            "counts": _kind_counts(entry)}


def _blank_values(kind: str) -> dict:
    blank = {"status": "draft", "comment": "", "chapters": ""}
    if kind == "param":
        blank["values"] = ""
    return blank


def _form_spec(entry, kind: str, card=None) -> dict:
    """表单规格（旧 card_form.html 渲染上下文的 JSON 化，动态表单的唯一数据源）。"""
    project = entry.project
    widget = KIND_ID_WIDGET[kind]
    prefilled = ""
    id_choices: list[str] = []
    if card is None:
        if widget == "auto":
            prefilled = next_card_id(project, KIND_PREFIX[kind])
        elif widget == "bibkey":
            id_choices = sorted(project.bib_keys)
    return {"kind": kind, "label": KIND_LABELS[kind], "is_new": card is None,
            "id_widget": widget, "prefilled_id": prefilled,
            "id_choices": id_choices,
            "specs": [asdict(s) for s in FIELD_SPECS[kind]],
            "choices": build_choices(kind, project),
            "labels": build_labels(project),
            "values": (values_for_template(kind, card) if card is not None
                       else _blank_values(kind))}


@router.get("/projects/{pid}/card-forms/{kind}")
def card_form_new(request: Request, pid: str, kind: str):
    if kind not in KIND_ATTRS:
        raise HTTPException(status_code=404, detail="未知卡种")
    entry = load_project_or_404(request, pid)
    return _form_spec(entry, kind, None)


def payload_to_meta(kind: str, payload: dict, *, is_new: bool,
                    card_id: str | None) -> tuple[dict, dict[str, str]]:
    """JSON payload → 模型 meta 字典；(meta, 字段级错误)。id 一律服务端裁定。

    与旧 form_to_meta 同构：multiselect 收列表；yaml_map 收字符串（服务端解析，
    错误文案不变）或已解析的映射对象。
    """
    meta: dict = {}
    errors: dict[str, str] = {}
    for spec in FIELD_SPECS[kind]:
        raw = payload.get(spec.name)
        if spec.widget == "multiselect":
            if raw is None or raw == "":
                meta[spec.name] = []
            elif isinstance(raw, list):
                meta[spec.name] = [str(v) for v in raw]
            else:
                meta[spec.name] = [str(raw)]
        elif spec.widget == "tags":
            # tags 控件收字符串（前端直接提交表单态）；列表也容忍（API 直调）
            meta[spec.name] = parse_tags(raw) if not isinstance(raw, list) \
                else [str(v).strip() for v in raw if str(v).strip()]
        elif spec.widget == "yaml_map":
            if isinstance(raw, dict):
                meta[spec.name] = raw
            else:
                text = str(raw or "").strip()
                parsed: dict = {}
                if text:
                    try:
                        loaded = yaml.safe_load(text)
                    except yaml.YAMLError as exc:
                        errors.setdefault(spec.name, f"YAML 解析失败：{exc}")
                        loaded = {}
                    if not isinstance(loaded, dict):
                        errors.setdefault(spec.name, "必须是 YAML 映射（键: 值）")
                        loaded = {}
                    parsed = loaded
                meta[spec.name] = parsed
        else:
            meta[spec.name] = str(raw or "").strip()
    meta["status"] = str(payload.get("status", "draft")) or "draft"
    meta["comment"] = str(payload.get("comment", ""))
    if kind == "note" and not meta.get("entry"):
        meta["entry"] = None   # 空映射 = 无书目字段（避免 BibEntryFields 必填校验误伤，P-D2）
    meta["id"] = (str(payload.get("id") or "").strip() if is_new
                  else (card_id or ""))
    return meta, errors


def _entry_value_error(project, card) -> str | None:
    """预检：假设卡写盘后渲染 bib 是否合法（E-BIB-VALUE 前置，避免毒化项目）。"""
    from dataclasses import replace

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


@router.post("/projects/{pid}/cards/{kind}")
async def card_new_post(request: Request, pid: str, kind: str,
                        payload: dict):
    if kind not in KIND_ATTRS:
        raise HTTPException(status_code=404, detail="未知卡种")
    entry = load_project_or_404(request, pid)
    meta, errors = payload_to_meta(kind, payload, is_new=True, card_id=None)
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
            return errors_422({"id": str(exc)})
    if errors:
        return errors_422(errors)
    bib = None
    if kind == "note" and card.status == "approved":
        bib = sync_managed_bib(entry.project.root)
    return {"ok": True, "id": card.id, "bib": bib}


def errors_422(errors: dict[str, str]):
    """字段级校验失败统一形态：{"detail": 文案, "errors": {字段: 消息}}（不落盘）。"""
    return JSONResponse(status_code=422,
                        content={"detail": "校验失败", "errors": errors})


def _detail_payload(entry, kind: str, card) -> dict:
    fields = {k: (yaml.safe_dump(v, allow_unicode=True, sort_keys=False)
                  if k == "entry" and v else ("" if v is None else v))
              for k, v in card.model_dump().items()
              if k not in ("id", "status", "comment")}
    fixable = (card.id in bibgen.fixable_notes(entry.project)
               if kind == "note" else False)
    return {"kind": kind, "label": KIND_LABELS[kind], "id": card.id,
            "status": card.status, "comment": card.comment,
            "rel": entry.project.card_paths[card.id].as_posix(),
            "fields": fields, "fixable": fixable,
            "bib_managed": entry.project.bib_managed}


@router.get("/projects/{pid}/cards/{kind}/{card_id}")
def card_detail(request: Request, pid: str, kind: str, card_id: str):
    # 容错加载同 _table：校验错误项目恰恰最需要看卡——
    # 提案落位的 unmanaged draft note 必触发 E-NOTE-NOT-IN-BIB，
    # 严格闸门会让落位失败提示永不可见（pdf-ingest 设计 U10 / 计划 P-D2）。
    entry, table = _table(request, pid, kind)
    card = table.get(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="卡片不存在")
    return _detail_payload(entry, kind, card)


@router.get("/projects/{pid}/cards/{kind}/{card_id}/edit")
def card_edit_get(request: Request, pid: str, kind: str, card_id: str):
    entry, table = _table(request, pid, kind)
    card = table.get(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="卡片不存在")
    spec = _form_spec(entry, kind, card)
    return spec


@router.patch("/projects/{pid}/cards/{kind}/{card_id}")
async def card_edit_patch(request: Request, pid: str, kind: str, card_id: str,
                          payload: dict):
    entry, table = _table(request, pid, kind)
    old_card = table.get(card_id)
    if old_card is None:
        raise HTTPException(status_code=404, detail="卡片不存在")
    meta, errors = payload_to_meta(kind, payload, is_new=False, card_id=card_id)
    card = None
    if not errors:
        try:
            card = KIND_MODELS[kind].model_validate(meta)
        except ValidationError as exc:
            errors = validation_errors(exc)
    if card is not None and kind == "note":
        err = _entry_value_error(entry.project, card)
        if err:
            errors = {"entry": f"[E-BIB-VALUE] {err}"}
            card = None
    if errors:
        return errors_422(errors)
    save_card(entry.project.root, card,
              old_rel=entry.project.card_paths[card_id].as_posix())
    bib = None
    if kind == "note":
        bib = sync_managed_bib(entry.project.root)
    return {"ok": True, "id": card_id, "bib": bib}


class RenameBody(BaseModel):
    new_id: str = ""


@router.post("/projects/{pid}/cards/{kind}/{card_id}/rename")
async def card_rename(request: Request, pid: str, kind: str, card_id: str,
                      body: RenameBody):
    """卡片改名（rename 设计 R9）：与 CLI 共用 plan/apply 引擎，错误 422 回传。"""
    entry, table = _table(request, pid, kind)
    card = table.get(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="卡片不存在")
    new_id = body.new_id.strip()
    try:
        plan = plan_rename(entry.project, card_id, new_id)
    except RenameError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except NewNameError as exc:
        raise HTTPException(status_code=422, detail=f"[E-NEW-NAME] {exc}") from exc
    except NewCollisionError as exc:
        raise HTTPException(status_code=422,
                            detail=f"[E-NEW-COLLISION] {exc}") from exc
    apply_rename(entry.project, plan)
    return {"ok": True, "id": new_id}


class StatusBody(BaseModel):
    status: str = ""
    comment: str = ""


@router.post("/projects/{pid}/cards/{kind}/{card_id}/status")
async def card_review(request: Request, pid: str, kind: str, card_id: str,
                      body: StatusBody):
    entry, table = _table(request, pid, kind)
    card = table.get(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="卡片不存在")
    status = body.status
    if status not in _STATUSES:
        raise HTTPException(status_code=400, detail="非法 status")
    new_card = card.model_copy(update={"status": status, "comment": body.comment})
    if kind == "note":
        err = _entry_value_error(entry.project, new_card)
        if err:
            raise HTTPException(status_code=422,
                                detail=f"[E-BIB-VALUE] {err}")
    save_card(entry.project.root, new_card,
              old_rel=entry.project.card_paths[card_id].as_posix())
    bib = None
    if kind == "note":
        bib = sync_managed_bib(entry.project.root)
    return {"ok": True, "status": status, "bib": bib}


@router.post("/projects/{pid}/notes/propose")
async def bib_propose_post(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    form = await request.form()
    clues = str(form.get("clues") or "")
    upload = form.get("pdf_file")
    has_file = isinstance(upload, UploadFile) and bool(upload.filename)
    project = entry.project

    def reject(error: str):
        raise HTTPException(status_code=422, detail=error)

    if not clues.strip() and not has_file:
        return reject("请上传 PDF 或填写线索（至少其一）。")

    staging: Path | None = None
    full_text = ""
    if has_file:
        try:
            validate_upload_name(upload.filename)
        except PdfTextError as exc:
            return reject(str(exc))
        staging = project.root / "articles" / Path(upload.filename).name
        data = await upload.read()
        if not data:
            return reject("[E-PDF-SHAPE] 上传文件内容为空。")
        try:
            staging.parent.mkdir(parents=True, exist_ok=True)   # 内容合法才动文件系统（零写入）
            staging.write_bytes(data)
        except OSError as exc:
            return reject(
                f"[E-PDF-STAGING] 上传文件落盘失败（文件名含非法字符或磁盘不可写）：{exc}")
        try:
            full_text = extract_text(staging)   # PdfTextError → PDF 留 staging（U3）
        except PdfTextError as exc:
            return reject(str(exc))

    merged_clues = full_text[:CLUES_CHARS]
    if clues.strip():
        merged_clues = (f"{merged_clues}\n\n补充线索：{clues.strip()}"
                        if merged_clues else clues.strip())

    try:
        client = make_client(mock=False, project_root=project.root)
        key, fields = await propose_note(
            project, merged_clues, client,
            source_pdf=upload.filename if has_file else None)
    except (BibProposeError, DraftError) as exc:
        return reject(str(exc))

    if has_file:
        fields["pdf"] = f"pdfs/{key}.pdf"   # key 定了才回填（设计 §引擎规格）
    from weft.engine.card_writer import write_proposed_cards
    write_proposed_cards(project, [("note", fields)])

    pdfwarn = False
    if has_file:
        try:
            dest = project.root / "pdfs" / f"{key}.pdf"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.unlink(missing_ok=True)    # U2：同名孤儿归档覆盖语义
            shutil.move(str(staging), str(dest))
            (project.root / "articles" / f"{key}.md").write_text(
                normalize_lf(full_text), encoding="utf-8", newline="\n")
        except OSError:
            pdfwarn = True
    return {"ok": True, "id": key, "pdfwarn": pdfwarn}


def register(app: FastAPI) -> None:
    app.include_router(router)
