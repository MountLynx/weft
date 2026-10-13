"""figures.yaml API（webui-react 设计 §3.2）：列表 / 新增 / 编辑 / 删除。

语义与旧 HTML 路由一一对应（routes/figures.py）：
- 列表读 store 加载视图（figures.yaml 坏条目时页面仍可看，F3 → load_error 只读）；
- 一切写操作经 figures_edit 引擎自读自写磁盘（F12），FiguresEditError → 422 带 code。
"""
from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from weft.figures_edit import (
    FiguresEditError,
    add_entry,
    load_for_edit,
    parse_subfigs,
    remove_entry,
    update_entry,
    write_figures_yaml,
)
from weft.web.common import load_entry_or_404

router = APIRouter(prefix="/api")


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


def _load_error(entry) -> str | None:
    """project=None 时探查 figures.yaml 是否为坏因（E-FIG-LOAD 文案，F3）。"""
    try:
        load_for_edit(entry.path)
    except FiguresEditError as exc:
        # 尾巴只属于 E-FIG-LOAD（注册表带病需手修 yaml）；兜底文案不带
        # （与 figures.yaml 无关时不该催用户改 yaml）。
        return f"{exc.code} {exc.message}（请手工修复后刷新）"
    return "项目加载失败（与 figures.yaml 无关），先看诊断页"


@router.get("/projects/{pid}/figures")
def figures_list(request: Request, pid: str):
    # 故意不用 load_project_or_404：figures.yaml 坏掉的项目恰恰最需要这个页面
    # 指路修复（同诊断页先例；F3 页面转只读）。
    entry = load_entry_or_404(request, pid)
    rows: list[dict] = []
    load_error: str | None = None
    if entry.project is not None:
        rows = _rows(entry)
    else:
        load_error = _load_error(entry)
    return {"rows": rows, "load_error": load_error}


_PREFIXES = {"fig": "fig-", "tbl": "tbl-"}


class FigurePayload(BaseModel):
    key: str = ""
    caption: str = ""
    subfigs: str = ""
    prefix: str = "fig"


def _fig_error(exc: FiguresEditError):
    message = f"{exc.code} {exc.message}"
    if exc.code == "E-FIG-LOAD":
        message += "（请手工修复后刷新）"
    return JSONResponse(status_code=422,
                        content={"detail": message, "code": exc.code})


@router.get("/projects/{pid}/figures/{key}")
def figure_get(request: Request, pid: str, key: str):
    entry = load_entry_or_404(request, pid)
    try:
        entries = load_for_edit(entry.path)
    except FiguresEditError as exc:
        return _fig_error(exc)
    fig = entries.get(key)
    if fig is None:
        raise HTTPException(status_code=404, detail="图注条目不存在")
    subfigs_text = "\n".join(f"{s}: {c}" for s, c in fig.subfigs.items())
    return {"key": key,
            "values": {"caption": fig.caption, "subfigs": subfigs_text}}


@router.post("/projects/{pid}/figures")
async def figure_new_post(request: Request, pid: str, body: FigurePayload):
    entry = load_entry_or_404(request, pid)
    return _submit(entry, None, body)


@router.patch("/projects/{pid}/figures/{key}")
async def figure_edit_patch(request: Request, pid: str, key: str,
                            body: FigurePayload):
    entry = load_entry_or_404(request, pid)
    return _submit(entry, key, body)


@router.post("/projects/{pid}/figures/{key}/delete")
def figure_delete(request: Request, pid: str, key: str):
    entry = load_entry_or_404(request, pid)
    try:
        entries = load_for_edit(entry.path)
    except FiguresEditError as exc:
        return _fig_error(exc)
    if entry.project is None:
        # 引用检查需要 project 的 data 卡视图；项目带病时宁可拒绝（F6 从严），
        # 指向诊断页让用户先修项目——figures.yaml 本身没坏（否则上面已只读）。
        return JSONResponse(
            status_code=422,
            content={"detail": "项目加载失败，删除需要完整引用检查，先看诊断页",
                     "code": ""})
    references = {cid: set(card.refs)
                  for cid, card in entry.project.data_cards.items()}
    try:
        entries = remove_entry(entries, key, references)
        write_figures_yaml(entry.path, entries)
    except FiguresEditError as exc:
        return _fig_error(exc)
    return {"ok": True}


def _submit(entry, key: str | None, body: FigurePayload):
    caption = body.caption.strip()
    values = {"caption": caption, "subfigs": body.subfigs,
              "prefix": body.prefix}
    if key is None:
        # 回显保真：键是身份（F8），冲突/键名错误重显时不能丢用户键名，
        # 否则没注意就重交 → 静默落自动编号。
        values["key"] = body.key.strip()
    try:
        subfigs = parse_subfigs(body.subfigs)
        entries = load_for_edit(entry.path)
        if key is None:
            entries = add_entry(entries, body.key.strip(), caption, subfigs,
                                _PREFIXES.get(body.prefix, "fig-"))
        else:
            entries = update_entry(entries, key, caption, subfigs)
        write_figures_yaml(entry.path, entries)
    except FiguresEditError as exc:
        message = f"{exc.code} {exc.message}"
        if exc.code == "E-FIG-LOAD":
            message += "（请手工修复后刷新）"
        return JSONResponse(status_code=422, content={
            "detail": message, "code": exc.code,
            "values": {**values, "key": body.key.strip()}})
    return {"ok": True}


def register(app: FastAPI) -> None:
    app.include_router(router)
