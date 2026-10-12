"""文献 PDF 文本提取（pdf-ingest 设计）：上传 → 确定性转换 → 提案线索。

纯本地确定性预处理（非 AI 落盘）；pymupdf4llm 懒加载（web extra 依赖），
CLI-only 安装不受影响；不碰 llm/module_harness（红线 1 不涉）。
"""
from __future__ import annotations

from pathlib import Path

CLUES_CHARS = 6000    # 进提案线索的截取上限（propose 单次轻量调用，U9）
MIN_TEXT_CHARS = 200  # 低于此视为无有效文本层（扫描版/纯图页，U5）


class PdfTextError(Exception):
    """PDF 收录失败：携带 E-PDF-* 诊断码（WebUI banner 呈现）。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code} {message}")
        self.code = code
        self.message = message


def validate_upload_name(filename: str | None) -> None:
    """非 .pdf（大小写不敏感）/ 空文件名 / 裸 .pdf（无 stem）→ E-PDF-SHAPE（staging 之前拒绝，U11）。"""
    name = (filename or "").strip()
    if len(name) <= 4 or not name.lower().endswith(".pdf"):
        raise PdfTextError("E-PDF-SHAPE", f"上传文件必须是 .pdf：{name or '（空）'}")


def extract_text(pdf_path: Path) -> str:
    """PDF → Markdown 全文；转换失败 / 无文本层 → E-PDF-CONVERT。"""
    try:
        import pymupdf4llm

        text = pymupdf4llm.to_markdown(str(pdf_path))
    except Exception as exc:
        raise PdfTextError("E-PDF-CONVERT", f"PDF 转换失败：{exc}") from exc
    if len(text.strip()) < MIN_TEXT_CHARS:
        raise PdfTextError(
            "E-PDF-CONVERT",
            f"PDF 无有效文本层（扫描版？）：有效文本不足 {MIN_TEXT_CHARS} 字符")
    return text


def normalize_lf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")
