"""WebUI 文献提案路由（bibgen 设计 §8 路径 1）。"""
import pytest

pytest.importorskip("fastapi")

from weft.engine.clients import ScriptedLLMClient
from weft.pdftext import PdfTextError
from weft.store.loader import load_project
from tests.webutil import make_client


def _patch(monkeypatch, client_obj):
    monkeypatch.setattr("weft.web.routes.cards.make_client",
                        lambda mock, project_root=None: client_obj)


def test_propose_page_renders(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/notes/propose")
    assert resp.status_code == 200
    assert 'name="clues"' in resp.text and "draft" in resp.text
    assert 'type="file"' in resp.text
    assert 'enctype="multipart/form-data"' in resp.text


def test_propose_creates_draft_note(tmp_path, monkeypatch):
    client, root = make_client(tmp_path)
    scripted = ScriptedLLMClient()
    _patch(monkeypatch, scripted)
    resp = client.post("/p/demo/notes/propose", data={"clues": "Smith 2020 催化"},
                       follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/cards/note/smith2020")
    assert "Smith 2020 催化" in scripted.prompts[0]     # 线索进了 prompt
    project, _ = load_project(root / "demo")
    card = project.notes["smith2020"]
    assert card.status == "draft" and card.entry.title == "Thermally activated catalysis"


def test_propose_conflict_suffix(tmp_path, monkeypatch):
    client, root = make_client(tmp_path)
    bib = root / "demo" / "references.bib"
    bib.write_text(bib.read_text(encoding="utf-8")
                   + "@article{smith2020,\n  title = {S},\n  year = {2020},\n}\n",
                   encoding="utf-8")
    (root / "demo" / "metadata" / "notes" / "smith2020.md").write_text(
        "---\nid: smith2020\nsummary: 占位\nstatus: approved\n---\n", encoding="utf-8")
    _patch(monkeypatch, ScriptedLLMClient())
    resp = client.post("/p/demo/notes/propose", data={"clues": "Smith 2020"},
                       follow_redirects=False)
    assert resp.headers["location"].endswith("/cards/note/smith2020a")


def test_propose_invalid_json_rerenders(tmp_path, monkeypatch):
    class _Bad:
        async def complete(self, **kwargs):
            from llm.client import LLMResponse
            return LLMResponse(content="不是 JSON", usage={}, finish_reason="end_turn")

    client, root = make_client(tmp_path)
    _patch(monkeypatch, _Bad())
    resp = client.post("/p/demo/notes/propose", data={"clues": "x"})
    assert resp.status_code == 200 and "条目提案输出非法" in resp.text
    assert not (root / "demo" / "metadata" / "notes" / "smith2020.md").exists()


def test_propose_invalid_schema_rerenders(tmp_path, monkeypatch):
    class _NoYear:
        async def complete(self, **kwargs):
            from llm.client import LLMResponse
            return LLMResponse(content='{"title": "T"}', usage={},
                               finish_reason="end_turn")

    client, root = make_client(tmp_path)
    _patch(monkeypatch, _NoYear())
    resp = client.post("/p/demo/notes/propose", data={"clues": "x"})
    assert resp.status_code == 200 and "条目提案输出非法" in resp.text


def test_propose_make_client_failure_rerenders(tmp_path, monkeypatch):
    """LLM 配置缺失：make_client 的 DraftError 呈现为页面错误而非 500（T9 质量审查）。"""
    from weft.engine.draft_rules import DraftError

    def _boom(mock, project_root=None):
        raise DraftError("真实 LLM 客户端构造失败（检查 config.json / .env）：无配置")

    client, root = make_client(tmp_path)
    monkeypatch.setattr("weft.web.routes.cards.make_client", _boom)
    resp = client.post("/p/demo/notes/propose", data={"clues": "x"})
    assert resp.status_code == 200 and "config.json" in resp.text
    assert not (root / "demo" / "metadata" / "notes" / "smith2020.md").exists()


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


def test_propose_clues_truncated_to_clues_chars(tmp_path, monkeypatch):
    """U9：转换文本超 CLUES_CHARS 时截断后才进线索。"""
    from weft.pdftext import CLUES_CHARS

    scripted = ScriptedLLMClient()
    client, _ = make_client(tmp_path)
    _patch(monkeypatch, scripted)
    monkeypatch.setattr("weft.web.routes.cards.extract_text",
                        lambda p: "Z" * (CLUES_CHARS + 500))
    client.post("/p/demo/notes/propose", data={"clues": ""},
                files=_PDF_FILES)
    assert "Z" * CLUES_CHARS in scripted.prompts[0]
    assert "Z" * (CLUES_CHARS + 1) not in scripted.prompts[0]


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


def test_propose_rejects_empty_pdf(tmp_path, monkeypatch):
    """设计流程序 1：空内容在 staging 之前拒绝（E-PDF-SHAPE），零写入。"""
    client, root = make_client(tmp_path)
    _patch(monkeypatch, ScriptedLLMClient())
    resp = client.post("/p/demo/notes/propose", data={"clues": ""},
                       files={"pdf_file": ("empty.pdf", b"", "application/pdf")})
    assert resp.status_code == 200 and "E-PDF-SHAPE" in resp.text
    assert not (root / "demo" / "articles").exists()
    assert not (root / "demo" / "metadata" / "notes" / "smith2020.md").exists()


def test_propose_staging_write_failure_rerenders(tmp_path, monkeypatch):
    """staging 落盘失败（磁盘/文件名）呈现 E-PDF-STAGING banner，不 500、零后续状态。"""
    client, root = make_client(tmp_path)
    _patch(monkeypatch, ScriptedLLMClient())

    def _boom(self, data):
        raise OSError("disk full")

    monkeypatch.setattr("pathlib.Path.write_bytes", _boom)
    resp = client.post("/p/demo/notes/propose", data={"clues": ""},
                       files=_PDF_FILES)
    assert resp.status_code == 200 and "E-PDF-STAGING" in resp.text
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
