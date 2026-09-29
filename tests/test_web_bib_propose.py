"""WebUI 文献提案路由（bibgen 设计 §8 路径 1）。"""
import pytest

pytest.importorskip("fastapi")

from weft.engine.clients import ScriptedLLMClient
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
