"""quarto 子进程封装（M3 设计 §5）：渲染拼装产物（paper_file），docx 默认目标。

CLI 层模块，不 import specmodule/llm（分层红线只约束到"全项目仅 engine/ 可碰"，
本模块与 graphgen/assemble 同级为纯脚本层）。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class QuartoNotFoundError(RuntimeError):
    """quarto 可执行文件不在 PATH。"""


class QuartoRenderError(RuntimeError):
    """paper.qmd 缺失，或 quarto render 非零退出。"""


def render_paper(project_root: Path, *, paper_file: str = "paper.qmd",
                 to: str = "docx") -> Path:
    """渲染 <project_root>/<paper_file>；成功返回输出文件路径（如 paper.docx）。

    stdout/stderr 被捕获，失败时随异常携带，便于 CLI 透传。
    """
    quarto = shutil.which("quarto")
    if quarto is None:
        raise QuartoNotFoundError(
            "未找到 quarto 可执行文件；请安装 Quarto（https://quarto.org）并加入 PATH")
    paper = project_root / paper_file
    if not paper.exists():
        raise QuartoRenderError(f"未找到 {paper_file}，请先运行 weft assemble")
    completed = subprocess.run(
        [quarto, "render", paper_file, "--to", to],
        cwd=project_root, capture_output=True, text=True,
        encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise QuartoRenderError(
            f"quarto render 失败（退出码 {completed.returncode}）：{detail}")
    return paper.with_suffix(f".{to}")
