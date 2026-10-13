# 文献 PDF 上传收录（pdf-ingest）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 文献提案表单支持上传 PDF——确定性转文本作线索拟 entry 草案卡，原件归档 `pdfs/<key>.pdf` 自动填卡 `pdf` 字段，转换全文落 `articles/<key>.md` 供 `weft parse --key` 富化 summary。

**Architecture:** 转换器为 `src/weft/pdftext.py` 纯引擎模块（pymupdf4llm 懒加载，WebUI banner 呈现错误，同 figures_edit 先例）；propose 路由按 staging → 转换 → 提案 → 落卡 → 落位顺序编排；校验器新增 note 卡 pdf 缺失提醒。设计定案：`docs/superpowers/specs/2026-10-12-weft-pdf-ingest-design.md`（决策 U1–U12）。

**Tech Stack:** pymupdf4llm（web extra 新增）、FastAPI multipart（python-multipart 已有）、pydantic、pytest。

**测试基线：** 744 passed（afae618 口径）。本计划新增 25 个测试，实测 **769 passed**（2 deselected 为 smoke，下同）。后续 P-D9 死锁修复新增 4 个测试，全量 **773 passed**。

---

## 任务总览

| 任务 | 交付物 | 新增测试 |
|---|---|---|
| 0 | worktree + pymupdf4llm 依赖 | 0 |
| 1 | `src/weft/pdftext.py` 转换器引擎 | 8 |
| 2 | `propose_note` 增 `source_pdf` | 2 |
| 3 | `W-NOTE-PDF-MISSING` 校验提醒 | 4 |
| 4 | propose 路由 + 表单 + `?pdfwarn` banner | 6（另改 1 个既有测试） |
| 5 | demo 项目修正（U12）+ 锁定测试 | 1 |
| 6 | AGENTS 码表 + roadmap + 计数回填 + 合并 | 0 |

## 测试计数明细

| 文件 | 新增 | 名称 |
|---|---|---|
| tests/test_pdftext.py | 8 | upload_name 接受×1、拒绝参数化×3、extract 正常×1、短文本×1、缺文件×1、normalize_lf×1 |
| tests/test_bib_propose.py | 2 | source_pdf 进 comment×1、无 PDF 行为不变×1 |
| tests/test_validation_warnings.py | 4 | 缺失提醒×1、存在不提醒（../ 形态）×1、空字段跳过×1、rejected 跳过×1 |
| tests/test_web_bib_propose.py | 6 | 全链路×1、线索合并×1、皆空拒绝×1、非 PDF×1、转换失败留 staging×1、落位失败 pdfwarn×1 |
| tests/test_validation_warnings.py（Task 5） | 1 | demo 项目无 W-NOTE-PDF-MISSING |

---

### Task 0: worktree 与依赖

**Files:**
- Modify: `pyproject.toml:20`（web extra 行）

- [ ] **Step 0.1: 建 worktree**

```bash
cd "C:/Users/xingy/Desktop/开发/weft"
git worktree add .worktrees/pdf-ingest -b pdf-ingest
cd .worktrees/pdf-ingest
```

以下命令均在 `.worktrees/pdf-ingest` 内执行。

- [ ] **Step 0.2: pyproject.toml web extra 增 pymupdf4llm**

```toml
web = ["fastapi>=0.110", "uvicorn>=0.29", "jinja2>=3.1", "python-multipart>=0.0.9", "pymupdf4llm>=0.0.17"]
```

- [ ] **Step 0.3: 安装**

```bash
C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe -m pip install -e ".[dev,web]"
```

（venv 在主仓（绝对路径调用），`-e .` 以当前目录（worktree）为安装源 → editable 路径切到 worktree。合并回 main 后 Task 6 会重装回来。）

- [ ] **Step 0.4: 验证导入**

```bash
C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe -c "import pymupdf4llm; print(pymupdf4llm.__name__)"
```

Expected: `pymupdf4llm`

---

### Task 1: pdftext 转换器引擎

**Files:**
- Create: `src/weft/pdftext.py`
- Test: `tests/test_pdftext.py`（新建）

- [ ] **Step 1.1: 写失败测试**

创建 `tests/test_pdftext.py`：

```python
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
```

（`MIN_TEXT_CHARS` 导入用于确认常量可从包面取用；不单独设测试。）

- [ ] **Step 1.2: 跑测试确认失败**

```bash
C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe -m pytest tests/test_pdftext.py -v
```

Expected: 收集即失败（`ModuleNotFoundError: No module named 'weft.pdftext'`）或 8 个 ERROR/FAIL。

- [ ] **Step 1.3: 实现模块**

创建 `src/weft/pdftext.py`：

```python
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
    """非 .pdf（大小写不敏感）/ 空文件名 → E-PDF-SHAPE（staging 之前拒绝，U11）。"""
    name = (filename or "").strip()
    if not name or not name.lower().endswith(".pdf"):
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
```

- [ ] **Step 1.4: 跑测试确认通过**

```bash
C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe -m pytest tests/test_pdftext.py -v
```

Expected: 8 passed

- [ ] **Step 1.5: 提交**

```bash
git add src/weft/pdftext.py tests/test_pdftext.py pyproject.toml
git commit -m "feat: pdftext 转换器引擎——上传名校验 + PDF→文本确定性提取（E-PDF-SHAPE/E-PDF-CONVERT）"
```

---

### Task 2: propose_note 增 source_pdf

**Files:**
- Modify: `src/weft/engine/bib_propose.py:51-73`（propose_note）
- Test: `tests/test_bib_propose.py`（追加）

- [ ] **Step 2.1: 写失败测试**

在 `tests/test_bib_propose.py` 末尾追加：

```python
def test_propose_note_source_pdf_comment():
    project = _project_with("key2020")
    _, fields = asyncio.run(
        propose_note(project, "Smith 2020", ScriptedLLMClient(),
                     source_pdf="smith_paper.pdf"))
    assert "来源 PDF：smith_paper.pdf" in fields["comment"]


def test_propose_note_without_pdf_unchanged():
    """U6 回归保障：无 PDF 调用时行为与现状一致（comment 无 PDF 痕迹、无 pdf 键）。"""
    project = _project_with("key2020")
    _, fields = asyncio.run(
        propose_note(project, "Smith 2020", ScriptedLLMClient()))
    assert "来源 PDF" not in fields["comment"]
    assert "pdf" not in fields
```

- [ ] **Step 2.2: 跑测试确认失败**

```bash
C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe -m pytest tests/test_bib_propose.py -v
```

Expected: 新增 2 个 FAIL（`propose_note() got an unexpected keyword argument 'source_pdf'` / `"来源 PDF" not in ...` 断言失败——第二个测试此时应 PASS，属预期：回归测试先行锁定）。

- [ ] **Step 2.3: 实现**

`src/weft/engine/bib_propose.py` 中 `propose_note` 改为（签名增可选参 + comment 改变量拼装）：

```python
async def propose_note(project, clues: str, client,
                       source_pdf: str | None = None) -> tuple[str, dict]:
    """返回（拟分配 key, note 卡 frontmatter 字段 dict）；不落盘。"""
    prompt = _PROMPT_TEMPLATE.format(clues=clues.strip() or "（无）")
    try:
        response = await client.complete(prompt=prompt,
                                         output_format={"type": "json_object"})
    except BibProposeError:
        raise
    except Exception as exc:   # 边界处异常翻译：llm 层 LLMError 等不裸穿（fail-closed 先例）
        raise BibProposeError(f"LLM 调用失败：{exc}") from exc
    try:
        entry = BibEntryFields.model_validate(_sink_extras(json.loads(response.content)))
    except (json.JSONDecodeError, ValueError) as exc:   # ValueError 涵盖 ValidationError
        raise BibProposeError(f"条目提案输出非法（须为 entry JSON）：{exc}") from exc
    key = bibgen.draft_key(bibgen.key_base_from_entry(entry), all_card_ids(project))
    comment = "来源：AI 条目提案（线索：" + (clues.strip()[:40] or "无") + "…）"
    if source_pdf:
        comment += f"；来源 PDF：{source_pdf}"
    fields = {
        "id": key,
        "status": "draft",
        "summary": "",
        "entry": entry.model_dump(),
        "comment": comment,
    }
    return key, fields
```

注意：`pdf` 字段值不在此处填（key 尚未定），由路由侧拿到 key 后回填（设计 §引擎规格）。

- [ ] **Step 2.4: 跑测试确认通过**

```bash
C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe -m pytest tests/test_bib_propose.py tests/test_web_bib_propose.py -v
```

Expected: 全部 PASS（含既有 web 提案测试——回归不破）。

- [ ] **Step 2.5: 提交**

```bash
git add src/weft/engine/bib_propose.py tests/test_bib_propose.py
git commit -m "feat: propose_note 增 source_pdf——comment 记来源 PDF 文件名（U6，向后兼容）"
```

---

### Task 3: W-NOTE-PDF-MISSING 校验提醒

**Files:**
- Modify: `src/weft/validation/rules.py:209-216`（`_check_notes_summary` 后增函数 + `validate_project` 接线，约 :295）
- Test: `tests/test_validation_warnings.py`（追加）

- [ ] **Step 3.1: 写失败测试**

在 `tests/test_validation_warnings.py` 末尾追加：

```python
def test_note_pdf_missing_warns(tmp_path):
    notes = [NoteCard(id="k2020", summary="s", status="approved",
                      pdf="pdfs/k2020.pdf")]
    project = build_project(root=tmp_path, notes=notes)
    diagnostics = validate_project(project)
    assert "W-NOTE-PDF-MISSING" in _codes(diagnostics)
    d = next(d for d in diagnostics if d.code == "W-NOTE-PDF-MISSING")
    assert d.field == "pdf"


def test_note_pdf_parent_form_resolved_from_root(tmp_path):
    """U7：路径按项目根解析，../ 形态照常 Path 语义判存在。"""
    notes = [NoteCard(id="k2020", summary="s", status="approved",
                      pdf="pdfs/../pdfs/k2020.pdf")]
    (tmp_path / "pdfs").mkdir()
    (tmp_path / "pdfs" / "k2020.pdf").write_bytes(b"%PDF-1.4\n")
    project = build_project(root=tmp_path, notes=notes)
    assert "W-NOTE-PDF-MISSING" not in _codes(validate_project(project))


def test_note_pdf_empty_skipped(tmp_path):
    notes = [NoteCard(id="k2020", summary="s", status="approved")]
    project = build_project(root=tmp_path, notes=notes)
    assert "W-NOTE-PDF-MISSING" not in _codes(validate_project(project))


def test_note_pdf_rejected_skipped(tmp_path):
    """设计决策 2：rejected 卡零 W 痕迹。"""
    notes = [NoteCard(id="k2020", status="rejected", pdf="pdfs/ghost.pdf")]
    project = build_project(root=tmp_path, notes=notes)
    assert "W-NOTE-PDF-MISSING" not in _codes(validate_project(project))
```

- [ ] **Step 3.2: 跑测试确认失败**

```bash
C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe -m pytest tests/test_validation_warnings.py -v -k pdf
```

Expected: `test_note_pdf_missing_warns` FAIL（码不存在），其余 3 个 PASS（空集断言天然过）。

- [ ] **Step 3.3: 实现规则**

`src/weft/validation/rules.py` 在 `_check_notes_summary` 函数之后新增：

```python
def _check_notes_pdf(project: Project) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for nid, note in project.notes.items():
        if note.status == "rejected" or not note.pdf:
            continue
        if not (project.root / note.pdf).exists():
            out.append(Diagnostic(Level.WARNING, "W-NOTE-PDF-MISSING",
                                  _card_rel(project, nid), "pdf",
                                  f"note 卡 pdf 字段指向的文件不存在：{note.pdf}"))
    return out
```

`validate_project` 中 `_check_notes_summary(project)` 之后接线：

```python
    diagnostics += _check_notes_summary(project)
    diagnostics += _check_notes_pdf(project)
```

- [ ] **Step 3.4: 跑全量确认通过且无回归**

```bash
C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe -m pytest tests -q
```

Expected: 744 + 14 = **758 passed**（Task 1 的 8 + Task 2 的 2 + 本任务 4）。若 demo 或夹具项目有 note 卡 pdf 指向缺失文件导致新失败，按报错修数据（当前基线不应有）。

- [ ] **Step 3.5: 提交**

```bash
git add src/weft/validation/rules.py tests/test_validation_warnings.py
git commit -m "feat: 校验器增 W-NOTE-PDF-MISSING——note 卡 pdf 指向缺失文件提醒（U7，rejected 豁免）"
```

---

### Task 4: propose 路由 + 表单 + pdfwarn banner

**Files:**
- Modify: `src/weft/web/routes/cards.py`（imports、`bib_propose_post` 重写、`_render_detail` 上下文）
- Modify: `src/weft/web/templates/bib_propose.html`（表单）
- Modify: `src/weft/web/templates/card_detail.html:7-8` 附近（banner）
- Test: `tests/test_web_bib_propose.py`（追加 6 个 + 修改 1 个）

- [ ] **Step 4.1: 写失败测试**

`tests/test_web_bib_propose.py` 追加 imports（文件头部既有 import 区之后）：

```python
from weft.pdftext import PdfTextError
```

修改既有 `test_propose_page_renders`，断言增加文件输入：

```python
def test_propose_page_renders(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/notes/propose")
    assert resp.status_code == 200
    assert 'name="clues"' in resp.text and "draft" in resp.text
    assert 'type="file"' in resp.text
    assert 'enctype="multipart/form-data"' in resp.text
```

文件末尾追加：

```python
_PDF_FILES = {"pdf_file": ("smith_paper.pdf", b"%PDF-fake", "application/pdf")}


def test_propose_with_pdf_full_chain(tmp_path, monkeypatch):
    """全链路：staging → 转换（mock）→ 提案 → 落卡（pdf 字段）→ 归档 + md 落位。"""
    scripted = ScriptedLLMClient()
    client, root = make_client(tmp_path)
    _patch(monkeypatch, scripted)
    monkeypatch.setattr("weft.web.routes.cards.extract_text",
                        lambda p: "Converted full text. " * 20)
    resp = client.post("/p/demo/notes/propose", data={"clues": ""},
                       files=_PDF_FILES, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/cards/note/smith2020")
    demo = root / "demo"
    card_text = (demo / "metadata" / "notes" / "smith2020.md").read_text(encoding="utf-8")
    assert "pdf: pdfs/smith2020.pdf" in card_text
    assert "来源 PDF：smith_paper.pdf" in card_text
    assert (demo / "pdfs" / "smith2020.pdf").read_bytes() == b"%PDF-fake"
    md = (demo / "articles" / "smith2020.md").read_text(encoding="utf-8")
    assert md == "Converted full text. " * 20
    assert not (demo / "articles" / "smith_paper.pdf").exists()  # staging 已移走
    assert "Converted full text." in scripted.prompts[0]         # 转换文本进线索


def test_propose_pdf_and_manual_clues_merged(tmp_path, monkeypatch):
    """U9：转换文本截 CLUES_CHARS 进线索，手填线索拼接在后。"""
    scripted = ScriptedLLMClient()
    client, _ = make_client(tmp_path)
    _patch(monkeypatch, scripted)
    monkeypatch.setattr("weft.web.routes.cards.extract_text",
                        lambda p: "X" * 300)
    client.post("/p/demo/notes/propose", data={"clues": "额外线索 DOI 10.1/x"},
                files=_PDF_FILES)
    assert "XXX" in scripted.prompts[0]
    assert "补充线索：额外线索 DOI 10.1/x" in scripted.prompts[0]


def test_propose_requires_clues_or_file(tmp_path, monkeypatch):
    client, root = make_client(tmp_path)
    _patch(monkeypatch, ScriptedLLMClient())
    resp = client.post("/p/demo/notes/propose", data={"clues": ""})
    assert resp.status_code == 200 and "至少其一" in resp.text
    assert not (root / "demo" / "metadata" / "notes" / "smith2020.md").exists()


def test_propose_rejects_non_pdf(tmp_path, monkeypatch):
    """U11：非 .pdf 在 staging 之前拒绝，零写入。"""
    client, root = make_client(tmp_path)
    _patch(monkeypatch, ScriptedLLMClient())
    resp = client.post("/p/demo/notes/propose", data={"clues": ""},
                       files={"pdf_file": ("x.md", b"data", "text/markdown")})
    assert resp.status_code == 200 and "E-PDF-SHAPE" in resp.text
    assert not (root / "demo" / "articles").exists()
    assert not (root / "demo" / "metadata" / "notes" / "smith2020.md").exists()


def test_propose_convert_failure_keeps_staging(tmp_path, monkeypatch):
    def _boom(p):
        raise PdfTextError("E-PDF-CONVERT", "PDF 无有效文本层（扫描版？）")

    client, root = make_client(tmp_path)
    _patch(monkeypatch, ScriptedLLMClient())
    monkeypatch.setattr("weft.web.routes.cards.extract_text", _boom)
    resp = client.post("/p/demo/notes/propose", data={"clues": ""},
                       files=_PDF_FILES)
    assert resp.status_code == 200 and "E-PDF-CONVERT" in resp.text
    assert (root / "demo" / "articles" / "smith_paper.pdf").exists()  # 留 staging
    assert not (root / "demo" / "metadata" / "notes" / "smith2020.md").exists()


def test_propose_placement_failure_shows_pdfwarn(tmp_path, monkeypatch):
    """U10：落位失败不回滚卡，?pdfwarn=1 提示，staging 未移走。"""
    client, root = make_client(tmp_path)
    _patch(monkeypatch, ScriptedLLMClient())
    monkeypatch.setattr("weft.web.routes.cards.extract_text",
                        lambda p: "Y" * 300)

    def _boom_move(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr("weft.web.routes.cards.shutil.move", _boom_move)
    resp = client.post("/p/demo/notes/propose", data={"clues": ""},
                       files=_PDF_FILES, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/cards/note/smith2020?pdfwarn=1")
    detail = client.get("/p/demo/cards/note/smith2020?pdfwarn=1")
    assert "PDF 落位失败" in detail.text
    assert (root / "demo" / "metadata" / "notes" / "smith2020.md").exists()
    assert (root / "demo" / "articles" / "smith_paper.pdf").exists()
```

- [ ] **Step 4.2: 跑测试确认失败**

```bash
C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe -m pytest tests/test_web_bib_propose.py -v
```

Expected: `test_propose_page_renders` FAIL（无 file input）+ 6 个新测试 FAIL/ERROR（无 `PdfTextError` 呈现路径、无落位行为——`test_propose_rejects_non_pdf` 等会因路由无视文件而走纯线索路径导致断言失败）。`test_propose_pdf_and_manual_clues_merged` 中 `XXX` 断言此时可能 PASS（手填线索原样进 prompt），属预期。

- [ ] **Step 4.3: 实现路由**

`src/weft/web/routes/cards.py` 顶部 imports 增补：

```python
import shutil
from pathlib import Path
```

fastapi 行改为：

```python
from fastapi import APIRouter, FastAPI, HTTPException, Request, UploadFile
```

weft imports 区增：

```python
from weft.pdftext import (
    CLUES_CHARS,
    PdfTextError,
    extract_text,
    normalize_lf,
    validate_upload_name,
)
```

`bib_propose_post` 整体替换为：

```python
@router.post("/p/{pid}/notes/propose")
async def bib_propose_post(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    form = await request.form()
    clues = str(form.get("clues") or "")
    upload = form.get("pdf_file")
    has_file = isinstance(upload, UploadFile) and bool(upload.filename)
    project = entry.project

    def rerender(error: str):
        return templates.TemplateResponse(
            request, "bib_propose.html",
            {"pid": pid, "action": f"/p/{pid}/notes/propose",
             "cancel_url": f"/p/{pid}/cards/note", "clues": clues, "error": error})

    if not clues.strip() and not has_file:
        return rerender("请上传 PDF 或填写线索（至少其一）。")

    staging: Path | None = None
    full_text = ""
    if has_file:
        try:
            validate_upload_name(upload.filename)
        except PdfTextError as exc:
            return rerender(str(exc))
        staging = project.root / "articles" / Path(upload.filename).name
        staging.parent.mkdir(parents=True, exist_ok=True)
        staging.write_bytes(await upload.read())
        try:
            full_text = extract_text(staging)   # PdfTextError → PDF 留 staging（U3）
        except PdfTextError as exc:
            return rerender(str(exc))

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
        return rerender(str(exc))

    if has_file:
        fields["pdf"] = f"pdfs/{key}.pdf"   # key 定了才回填（设计 §引擎规格）
    write_proposed_cards(project, [("note", fields)])

    if has_file:
        try:
            dest = project.root / "pdfs" / f"{key}.pdf"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.unlink(missing_ok=True)    # U2：同名孤儿归档覆盖语义
            shutil.move(str(staging), str(dest))
            (project.root / "articles" / f"{key}.md").write_text(
                normalize_lf(full_text), encoding="utf-8", newline="\n")
        except OSError:
            return RedirectResponse(f"/p/{pid}/cards/note/{key}?pdfwarn=1",
                                    status_code=303)
    return RedirectResponse(f"/p/{pid}/cards/note/{key}", status_code=303)
```

（`write_proposed_cards` 沿用现有函数内局部导入，不动。）

- [ ] **Step 4.4: 实现模板**

`src/weft/web/templates/bib_propose.html` 的 `<form>` 块整体替换为：

```html
<form method="post" action="{{ action }}" enctype="multipart/form-data">
  <label>PDF 上传（可选：自动提取线索、归档到 pdfs/、生成 articles/&lt;key&gt;.md）
    <input type="file" name="pdf_file" accept=".pdf">
  </label>
  <label>线索（DOI / 标题 / 作者 / 年份 / 摘要，任意组合；上传 PDF 时可作为补充线索）
    <textarea name="clues" rows="6">{{ clues }}</textarea>
  </label>
  <button type="submit" class="btn-primary">生成提案草稿卡</button>
  <a href="{{ cancel_url }}">取消</a>
</form>
```

`src/weft/web/templates/card_detail.html` 在 `bib_flag` 两条 banner 之后增一行：

```html
{% if pdf_warn %}<div class="banner error">PDF 落位失败：原件仍在 articles/ 下；可重新上传提案，或手动移至 pdfs/&lt;key&gt;.pdf 并在卡片表单修正 pdf 路径。</div>{% endif %}
```

`src/weft/web/routes/cards.py` 的 `_render_detail` 上下文 dict（`"bib_flag": ...` 之后）增：

```python
         "pdf_warn": request.query_params.get("pdfwarn"),
```

- [ ] **Step 4.5: 跑测试确认通过**

```bash
C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe -m pytest tests/test_web_bib_propose.py tests/test_web_subnav.py -v
```

Expected: 全部 PASS。

- [ ] **Step 4.6: 提交**

```bash
git add src/weft/web/routes/cards.py src/weft/web/templates/bib_propose.html src/weft/web/templates/card_detail.html tests/test_web_bib_propose.py
git commit -m "feat: 文献提案表单支持 PDF 上传——staging→转换→提案→落卡→归档/收件箱落位（E-PDF-* banner + ?pdfwarn）"
```

---

### Task 5: demo 修正与锁定（U12）

**Files:**
- Modify: `examples/paper-demo/metadata/notes/smith2020.md:4`
- Create: `examples/paper-demo/pdfs/smith2020.pdf`
- Test: `tests/test_validation_warnings.py`（追加 1 个）

- [ ] **Step 5.1: 写失败测试**

`tests/test_validation_warnings.py` 末尾追加测试；模块顶部 import 区补 `import pytest`、`from pathlib import Path`、`from weft.store.loader import load_project`（修正：原片段漏 `import pytest`，demo 缺失时 skip 守卫会 NameError）：

```python
# —— 模块顶部 import 区追加 ——
import pytest
from pathlib import Path

from weft.store.loader import load_project


# —— 文件末尾追加 ——
def test_demo_project_no_pdf_missing():
    """U12：demo 的 smith2020 卡 pdf 路径根相对且文件在库，校验零该提醒。"""
    root = Path(__file__).resolve().parents[1] / "examples" / "paper-demo"
    if not (root / "weft.yaml").exists():
        pytest.skip("demo 项目缺失")
    project, _ = load_project(root)
    assert "W-NOTE-PDF-MISSING" not in _codes(validate_project(project))
```

注意：主仓检出（非 worktree）里的 `smith2020.md` 有未提交改动风险——此测试读的是**当前检出**的 examples；在 worktree 内跑时读 worktree 副本。测试先红的前提是 worktree 内的卡仍指 `../pdfs/`。

- [ ] **Step 5.2: 跑测试确认失败**

```bash
C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe -m pytest tests/test_validation_warnings.py::test_demo_project_no_pdf_missing -v
```

Expected: FAIL（`../pdfs/smith2020.pdf` 不存在 → 提醒在列）。

- [ ] **Step 5.3: 修正 demo 卡路径**

`examples/paper-demo/metadata/notes/smith2020.md` frontmatter 第 4 行：

```yaml
pdf: pdfs/smith2020.pdf
```

- [ ] **Step 5.4: 生成占位 PDF（一次，入库）**

```bash
C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe -c "
from pathlib import Path
import pymupdf
Path('examples/paper-demo/pdfs').mkdir(parents=True, exist_ok=True)
doc = pymupdf.open()
page = doc.new_page()
for i, line in enumerate([
    'Thermally activated catalysis in batch reactors',
    'Smith, Jane and Lee, Kyung',
    'Journal of Thermal Chemistry, 12, 45-58 (2020).',
    'We study thermally activated catalysis mechanisms.',
]):
    page.insert_text((72, 72 + 14 * i), line)
doc.save('examples/paper-demo/pdfs/smith2020.pdf')
doc.close()
"
```

- [ ] **Step 5.5: 跑测试确认通过**

```bash
C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe -m pytest tests/test_validation_warnings.py -v
```

Expected: 全部 PASS（含 demo 锁定测试）。

- [ ] **Step 5.6: 提交**

```bash
git add examples/paper-demo/metadata/notes/smith2020.md examples/paper-demo/pdfs/smith2020.pdf tests/test_validation_warnings.py
git commit -m "fix: demo smith2020 卡 pdf 路径改根相对并入库占位 PDF（U12）+ demo 锁定测试"
```

---

### Task 6: 文档、全量验证与合并

**Files:**
- Modify: `AGENTS.md:41`（红线 5 码表）
- Modify: `docs/roadmap.md`（M4 段）
- Modify: 本计划文档（设计决策回填 + 计数回填）

- [ ] **Step 6.1: AGENTS.md 红线 5 码表增补**

在 `2026-10-12-weft-webui-figures-design.md`（E-FIG-...）条目之后、`；新增码必须进表` 之前插入：

```
、`2026-10-12-weft-pdf-ingest-design.md`（E-PDF-SHAPE / E-PDF-CONVERT / W-NOTE-PDF-MISSING）
```

- [ ] **Step 6.2: roadmap M4 增行**

`docs/roadmap.md` M4 段"WebUI 图表管理 ✅"行之后插入：

```markdown
- 文献 PDF 上传收录 ✅（2026-10-12）：文献提案表单支持 PDF 上传——pymupdf4llm 确定性转文本作线索拟 entry 草案卡，原件归档 `pdfs/<key>.pdf` 自动填卡 `pdf` 字段，转换全文落 `articles/<key>.md` 供 `weft parse --key` 富化 summary；`W-NOTE-PDF-MISSING` 校验提醒。设计见 `docs/superpowers/specs/2026-10-12-weft-pdf-ingest-design.md`。
```

- [ ] **Step 6.3: 全量测试**

```bash
C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe -m pytest tests -q
```

Expected: **769 passed**（744 基线 + pdftext 9 + propose_note 2 + 校验 4 + demo 1 + web 9；含修复循环新增）。将实测计数回填至本计划头部"测试基线"行。

- [ ] **Step 6.4: 设计偏离回填**

执行中任何偏离设计定案之处，回填至本计划文末"设计决策（执行期）"表（初始为空，格式：`| P-D# | 偏离 | 理由 |`）。无偏离则写"无"。

- [ ] **Step 6.5: 提交文档**

```bash
git add AGENTS.md docs/roadmap.md docs/superpowers/plans/2026-10-12-weft-pdf-ingest.md
git commit -m "docs: 文献 PDF 上传收录落地——AGENTS 红线 5 码表 E-PDF-*/W-NOTE-PDF-MISSING、roadmap M4、计划计数回填"
```

- [ ] **Step 6.6: 合回 main 并清理 worktree**

```bash
cd "C:/Users/xingy/Desktop/开发/weft"
git merge pdf-ingest --no-ff -m "feat: 文献 PDF 上传收录——上传→转换→条目提案→落位（pdf-ingest 设计定案）"
git worktree remove .worktrees/pdf-ingest
git branch -d pdf-ingest
C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe -m pip install -e ".[dev,web]"
C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe -m pytest tests -q
```

Expected: 合并干净；合并后全量 **769 passed**。注意主检出有无关未提交改动（`examples/paper-demo/metadata/data/data-01.md`），合并不受影响、不要顺手提交它。

---

## 设计决策（执行期）

| # | 偏离 | 理由 |
|---|---|---|
| P-D1 | `UploadFile` 从 `starlette.datastructures` 导入（计划写 fastapi） | fastapi 的 UploadFile 是 starlette 基类的子类，表单解析只造基类实例，`isinstance(upload, fastapi.UploadFile)` 恒 False → `has_file` 恒 False，上传会被静默忽略（实测定案） |
| P-D2 | `card_detail` GET 改容错加载 `load_entry_or_404`（POST 侧保持严格） | unmanaged 项目（正式配置）提案产生 draft note 卡即触发 E-NOTE-NOT-IN-BIB → 项目 unavailable → 严格闸门 404 → U10 的 `?pdfwarn` banner 永不可达；in-repo 先例 `figures.py:55`、`core.py:178`（"坏项目恰恰最需要这个页面"）；加载级错误（E-PARSE）仍 404；managed 项目 draft 豁免该错误、不受影响 |
| P-D3 | 任务执行顺序：Task 5（demo 修正）提前到 Task 4 之前 | Task 3 新规则正确暴露 demo 坏数据（smith2020 卡 `../pdfs/` 自 de068bf 就错，计划"基线不应有"判断有误）→ 全量暂红 1 条；提前修复恢复绿，避免后续任务带红跑 |
| P-D4 | 空内容 E-PDF-SHAPE 前置拒绝补实现（设计流程序 1 有、计划代码块漏） | Task 4 质量审查发现 0 字节 .pdf 会落 staging 后报误导性 E-PDF-CONVERT 并留垃圾件；修复为 read 后判空 rerender，且判空提到 `articles/` mkdir 之前（最严格零写入口径，`77b3f15`） |
| P-D5 | `validate_upload_name` 拒绝裸 `.pdf` 文件名（无 stem） | Task 1 质量审查发现 `".pdf"` 能穿过校验、下游 staging 会落 `articles/.pdf` 垃圾件（`bfa03ef`） |
| P-D6 | AGENTS.md 安装命令 `.[dev]` → `.[dev,web]` | 照旧文档安装会缺 web extra → pdftext/web 测试静默 skip；Task 1 质量审查建议 |
| P-D7 | 测试计数：计划估 765，实测 769 | Task 1 的 +9 中 1 个是修复新增的参数化用例；Task 4 修复增 3 个测试（空内容拒绝 + 截断行使 + staging 落盘失败） |
| P-D8 | staging 落盘失败增 E-PDF-STAGING 码进表 | 最终整体审查发现 OSError 裸 500 违背设计"任一步失败即 rerender"原则；按红线 5 新码进表 |
| P-D9 | P-D2 的"POST 侧保持严格"修正为审阅面容错（status/edit/rename/list + dashboard） | 用户实测死锁：unmanaged 项目 PDF 提案 draft note 必带 E-NOTE-NOT-IN-BIB → 严格闸门下 dashboard 变"无法加载"、审阅 POST 404——UI 造出的状态 UI 无法修复，`?pdfwarn` banner 可见却无从下手；改为 `load_reviewable_or_404`（project=None 加载级损坏仍 404，红线 6 生成闸门不受影响，card_new/bib_propose/parts/inspire 维持严格）；dashboard.html 的"不可用"徽章分支由死代码转正（unavailable.html 收窄为加载级损坏专用）；E-NOTE-NOT-IN-BIB unmanaged 分支补补救提示语；新增 4 测试（773 passed） |
