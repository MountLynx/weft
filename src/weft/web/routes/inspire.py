"""灵感页（webui 设计 §6）：输入文本段 → 后台 run_inspire+apply_inspiration → SSE → 提案应用。

收件箱文件由"人"经表单写入（inspirations/web-<时间戳>.md），非 AI 产物白名单问题；
inspire 落盘（草稿卡/proposals/报告/.runs 快照）全部走 engine 既有逻辑（红线 4 原样）。
"""
from __future__ import annotations

import threading
import time

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from weft.engine import make_client
from weft.engine.inspire.apply import apply_inspiration, apply_proposal
from weft.engine.inspire.run import run_inspire
from weft.store.loader import load_project
from weft.validation import validate_project
from weft.web.common import load_project_or_404, templates
from weft.web.runs import RunEvent

router = APIRouter()


@router.get("/p/{pid}/inspire")
def inspire_page(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    proposals_dir = entry.project.root / "inspirations" / "proposals"
    proposals = []
    if proposals_dir.is_dir():
        import frontmatter

        for path in sorted(proposals_dir.glob("*.md")):
            proposals.append({"id": path.stem})
    return templates.TemplateResponse(
        request, "inspire.html",
        {"entry": entry, "proposals": proposals})


@router.post("/p/{pid}/inspire/run")
async def inspire_run(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    form = await request.form()
    text = str(form.get("text", ""))
    mock = str(form.get("mock", "")) == "1"
    project, load_diags = load_project(entry.path)
    diagnostics = load_diags + validate_project(project)
    if any(d.is_error for d in diagnostics) or not text.strip():
        return HTMLResponse(
            '<div class="banner error">校验存在错误或灵感文本为空，拒绝处理</div>'
            '<div id="run-log" class="run-log"></div>')
    run = request.app.state.runs.try_start(pid)
    if run is None:
        return HTMLResponse(
            '<div class="banner error">已有任务在运行，请等待完成</div>'
            '<div id="run-log" class="run-log"></div>', status_code=409)

    def worker() -> None:
        try:
            source = project.root / "inspirations" / f"web-{time.strftime('%Y%m%d-%H%M%S')}.md"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(text.replace("\r\n", "\n").replace("\r", "\n"),
                              encoding="utf-8", newline="\n")
            run.emit(RunEvent("run_started", message=f"inspire：{source.name}"))
            result = run_inspire(project, text, client=make_client(
                mock, project_root=project.root), source=source.name)
            if result.resumed:
                run.emit(RunEvent("node_finished", message="断点续跑：已完成节点取自上次快照"))
            outcome = apply_inspiration(project, source=source, logic=result.logic,
                                        extract=result.extract, review=result.review,
                                        match=result.match, coverage=result.coverage)
            for p in outcome.written_cards:
                run.emit(RunEvent("node_finished",
                                  message=f"写入 {p.relative_to(project.root).as_posix()}"))
            run.emit(RunEvent("draft_written",
                              message=f"{len(outcome.proposals)} 张替换提案待审"))
            run.emit(RunEvent("run_finished",
                              message=f"报告 {outcome.report.relative_to(project.root).as_posix()}"))
        except Exception as exc:
            run.error = str(exc)
            run.emit(RunEvent("run_failed", message=str(exc)))
        finally:
            request.app.state.runs.finish(pid, run)

    threading.Thread(target=worker, daemon=True).start()
    return templates.TemplateResponse(
        request, "run_console.html",
        {"pid": pid, "part_id": "inspire", "run_id": run.id})


@router.post("/p/{pid}/inspire/proposals/{card_id}/apply")
def proposal_apply(request: Request, pid: str, card_id: str):
    entry = load_project_or_404(request, pid)
    try:
        apply_proposal(entry.project, card_id)
    except ValueError:
        return RedirectResponse(f"/p/{pid}/inspire", status_code=303)
    return RedirectResponse(f"/p/{pid}/inspire", status_code=303)


def register(app: FastAPI) -> None:
    app.include_router(router)
