"""pdftext（pdf-ingest 设计）：上传名校验 + PDF→文本确定性转换。"""
from pathlib import Path

import pytest

pytest.importorskip("pymupdf4llm")

from weft.pdftext import (
    MIN_TEXT_CHARS,
    PdfTextError,
    extract_text,
    normalize_lf,
    validate_upload_name,
)


def _make_pdf(path: Path, lines: list[str]) -> Path:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    for i, line in enumerate(lines):
        page.insert_text((72, 72 + 14 * i), line)
    doc.save(path)
    doc.close()
    return path


def test_validate_upload_name_accepts_pdf_case_insensitive():
    validate_upload_name("paper.pdf")
    validate_upload_name("Paper.PDF")


@pytest.mark.parametrize("name", ["paper.md", "paper", ""])
def test_validate_upload_name_rejects_non_pdf(name):
    with pytest.raises(PdfTextError) as ei:
        validate_upload_name(name)
    assert ei.value.code == "E-PDF-SHAPE"


def test_extract_text_reads_generated_pdf(tmp_path):
    pdf = _make_pdf(tmp_path / "a.pdf",
                    [f"Thermally activated catalysis in batch reactors {i}"
                     for i in range(5)])
    text = extract_text(pdf)
    assert "Thermally activated catalysis" in text


def test_extract_text_short_text_raises(tmp_path):
    pdf = _make_pdf(tmp_path / "empty.pdf", [])
    with pytest.raises(PdfTextError) as ei:
        extract_text(pdf)
    assert ei.value.code == "E-PDF-CONVERT"
    assert "文本层" in ei.value.message


def test_extract_text_missing_file_raises(tmp_path):
    with pytest.raises(PdfTextError) as ei:
        extract_text(tmp_path / "ghost.pdf")
    assert ei.value.code == "E-PDF-CONVERT"


def test_normalize_lf():
    assert normalize_lf("a\r\nb\rc\nd") == "a\nb\nc\nd"
