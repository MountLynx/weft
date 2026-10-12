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
    load_for_edit,
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
            load_error = f"{exc.code} {exc.message}"
        if load_error is None:
            load_error = "项目加载失败（与 figures.yaml 无关），先看诊断页"
    return templates.TemplateResponse(
        request, "figures.html",
        {"entry": entry, "rows": rows, "load_error": load_error})


def register(app: FastAPI) -> None:
    app.include_router(router)
