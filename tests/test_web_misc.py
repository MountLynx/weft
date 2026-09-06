"""graph 页与生成按钮、诊断表、文件预览与穿越防护。"""
import pytest

pytest.importorskip("fastapi")

from tests.webutil import make_client


def test_diagnostics_lists_codes(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/diagnostics")
    assert resp.status_code == 200
    assert "错误" in resp.text and "提醒" in resp.text


def test_files_preview_and_traversal(tmp_path):
    client, root = make_client(tmp_path)
    (root / "demo" / "drafts").mkdir()
    (root / "demo" / "drafts" / "sec-01.md").write_text("<!-- weft:run=x -->\n正文",
                                                        encoding="utf-8")
    resp = client.get("/p/demo/files/drafts/sec-01.md")
    assert resp.status_code == 200 and "正文" in resp.text
    assert client.get("/p/demo/files/%2E%2E/metadata/facts/fact-01.md").status_code == 404
    assert client.get("/p/demo/files/metadata/facts/fact-01.md").status_code == 404


def test_graph_page_and_regenerate(tmp_path):
    client, root = make_client(tmp_path)
    page = client.get("/p/demo/graph")
    assert page.status_code == 200
    assert "生成图谱" in page.text          # 初始无 graph.json
    resp = client.post("/p/demo/graph/regenerate", follow_redirects=False)
    assert resp.status_code == 303
    assert (root / "demo" / "generated" / "graph.json").exists()
    page2 = client.get("/p/demo/graph")
    assert "cytoscape" in page2.text
