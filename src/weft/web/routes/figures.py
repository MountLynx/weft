"""figures.yaml 路由（webui figures 设计定案）：列表 / 新增 / 编辑 / 删除。

注册顺序：/figures/new 必须先于 /figures/{key}（同 cards 先例）。
列表展示读 store 加载视图（figures.yaml 坏条目时页面仍可看，F3）；
一切写操作经 figures_edit 引擎自读自写磁盘（F12），错误回显 banner。
"""
from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse

from weft.figures_edit import (
    FiguresEditError,
    add_entry,
    load_for_edit,
    parse_subfigs,
    remove_entry,
    update_entry,
    write_figures_yaml,
)
from weft.web.common import load_entry_or_404, templates

router = APIRouter()


def _rows(entry) -> list[dict]:
    """列表行（F10）：类型判定 tbl- 前缀对齐 assemble；文件缺失标记对齐校验。

    文件缺失 = 键文件族（{key} ∪ {key}{sub}，同 W-FIGURE-FILE-MISSING 按 ref
    查文件的语义）在 figures_dir 下 png/pdf 全部不存在。
    """
    project = entry.project
    refs_by_card = {cid: set(card.refs)
                    for cid, card in project.data_cards.items()}
    fig_dir = project.root / project.figures_dir
    rows = []
    for key, fig in project.figures.items():
        names = [key, *(f"{key}{sub}" for sub in fig.subfigs)]
        used_by = sorted(cid for cid, refs in refs_by_card.items()
                         if refs & set(names))
        rows.append({
            "key": key, "caption": fig.caption, "subfigs": fig.subfigs,
            "kind": "table" if key.startswith("tbl-") else "figure",
            "used_by": used_by,
            "file_missing": (key.startswith("fig-")
                             and not any((fig_dir / f"{n}.png").exists()
                                         or (fig_dir / f"{n}.pdf").exists()
                                         for n in names)),
            "unused": not used_by})
    return rows


@router.get("/p/{pid}/figures")
def figures_page(request: Request, pid: str):
    # 故意不用 load_project_or_404：figures.yaml 坏掉的项目恰恰最需要这个页面
    # 指路修复（同诊断页先例；F3 页面转只读）。project 为 None 时行数据不可得，
    # banner 指认坏因（figures.yaml 的解析错误经引擎探针转 E-FIG-LOAD 文案）。
    entry = load_entry_or_404(request, pid)
    rows: list[dict] = []
    load_error: str | None = None
    if entry.project is not None:
        rows = _rows(entry)
    else:
        try:
            load_for_edit(entry.path)
        except FiguresEditError as exc:
            # 尾巴随消息走（模板不再固定拼接）：凡 FiguresEditError 消息都带，
            # 兜底文案不带（与 figures.yaml 无关时不该催用户改 yaml）。
            load_error = f"{exc.code} {exc.message}（请手工修复后刷新）"
        if load_error is None:
            load_error = "项目加载失败（与 figures.yaml 无关），先看诊断页"
    return templates.TemplateResponse(
        request, "figures.html",
        {"entry": entry, "rows": rows, "load_error": load_error})


_PREFIXES = {"fig": "fig-", "tbl": "tbl-"}


def _form(request: Request, entry, key: str | None, values: dict,
          errors: dict):
    if key is None:
        action = f"/p/{entry.pid}/figures/new"
    else:
        action = f"/p/{entry.pid}/figures/{key}"
    return templates.TemplateResponse(
        request, "figure_form.html",
        {"entry": entry, "key": key, "values": values, "action": action,
         "cancel_url": f"/p/{entry.pid}/figures", "errors": errors})


def _values(caption: str, subfigs_text: str, prefix: str) -> dict:
    return {"caption": caption, "subfigs_text": subfigs_text, "prefix": prefix}


def _list_with_error(request: Request, entry, error: str):
    return templates.TemplateResponse(
        request, "figures.html",
        {"entry": entry, "rows": _rows(entry) if entry.project is not None
         else [], "load_error": error})


@router.get("/p/{pid}/figures/new")
def figure_new_get(request: Request, pid: str):
    entry = load_entry_or_404(request, pid)
    return _form(request, entry, None, _values("", "", "fig"), {})


@router.post("/p/{pid}/figures/new")
async def figure_new_post(request: Request, pid: str):
    entry = load_entry_or_404(request, pid)
    form = await request.form()
    return _submit(request, entry, None, form)


@router.get("/p/{pid}/figures/{key}")
def figure_edit_get(request: Request, pid: str, key: str):
    entry = load_entry_or_404(request, pid)
    try:
        entries = load_for_edit(entry.path)
    except FiguresEditError as exc:
        # 与删除同款容错：注册表带病时无表可填，回列表页 banner（F3）
        return _list_with_error(
            request, entry, f"{exc.code} {exc.message}（请手工修复后刷新）")
    fig = entries.get(key)
    if fig is None:
        raise HTTPException(status_code=404, detail="图注条目不存在")
    subfigs_text = "\n".join(f"{s}: {c}" for s, c in fig.subfigs.items())
    return _form(request, entry, key, _values(fig.caption, subfigs_text, "fig"),
                 {})


@router.post("/p/{pid}/figures/{key}")
async def figure_edit_post(request: Request, pid: str, key: str):
    entry = load_entry_or_404(request, pid)
    form = await request.form()
    return _submit(request, entry, key, form)


@router.post("/p/{pid}/figures/{key}/delete")
def figure_delete(request: Request, pid: str, key: str):
    entry = load_entry_or_404(request, pid)
    references = ({cid: set(card.refs)
                   for cid, card in entry.project.data_cards.items()}
                  if entry.project is not None else {})
    try:
        entries = remove_entry(load_for_edit(entry.path), key, references)
        write_figures_yaml(entry.path, entries)
    except FiguresEditError as exc:
        return _list_with_error(
            request, entry, f"{exc.code} {exc.message}（请手工修复后刷新）")
    return RedirectResponse(f"/p/{pid}/figures", status_code=303)


def _submit(request: Request, entry, key: str | None, form):
    caption = str(form.get("caption", "")).strip()
    subfigs_text = str(form.get("subfigs", ""))
    prefix = str(form.get("prefix", "fig"))
    values = _values(caption, subfigs_text, prefix)
    try:
        subfigs = parse_subfigs(subfigs_text)
        entries = load_for_edit(entry.path)
        if key is None:
            entries = add_entry(entries, str(form.get("key", "")).strip(),
                                caption, subfigs, _PREFIXES.get(prefix, "fig-"))
        else:
            entries = update_entry(entries, key, caption, subfigs)
        write_figures_yaml(entry.path, entries)
    except FiguresEditError as exc:
        return _form(request, entry, key, values,
                     {"figures": f"{exc.code} {exc.message}"})
    return RedirectResponse(f"/p/{entry.pid}/figures", status_code=303)


def register(app: FastAPI) -> None:
    app.include_router(router)
