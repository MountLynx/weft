"""诊断 payload、文件预览白名单/穿越防护、图谱 payload 与再生成。"""
from tests.webutil import make_client


def test_diagnostics_payload_lists_codes(tmp_path):
    client, root = make_client(tmp_path)
    from tests.helpers import write_card
    write_card(root / "demo" / "metadata" / "notes", "li2021",
               {"id": "li2021", "summary": "s", "status": "draft", "entry":
                {"type": "article", "title": "T", "year": 2021}})
    payload = client.get("/api/projects/demo/diagnostics").json()
    levels = {d["level"] for d in payload["diagnostics"]}
    assert levels <= {"error", "warning"}
    assert any(d["code"] == "E-NOTE-NOT-IN-BIB" for d in payload["diagnostics"])
    err = next(d for d in payload["diagnostics"] if d["is_error"])
    assert {"level", "code", "path", "field", "message", "is_error"} <= set(err)


def test_files_preview_and_traversal(tmp_path):
    client, root = make_client(tmp_path)
    (root / "demo" / "drafts").mkdir()
    (root / "demo" / "drafts" / "sec-01.md").write_text("<!-- weft:run=x -->\n正文",
                                                        encoding="utf-8")
    resp = client.get("/api/projects/demo/file", params={"path": "drafts/sec-01.md"})
    assert resp.status_code == 200
    assert "正文" in resp.json()["text"]
    assert client.get("/api/projects/demo/file",
                      params={"path": "../metadata/facts/fact-01.md"}).status_code == 404
    assert client.get("/api/projects/demo/file",
                      params={"path": "metadata/facts/fact-01.md"}).status_code == 404


def test_graph_payload_and_regenerate(tmp_path):
    client, root = make_client(tmp_path)
    payload = client.get("/api/projects/demo/graph").json()
    assert payload["graph"] is None            # 初始无 graph.json → 前端出"生成图谱"
    resp = client.post("/api/projects/demo/graph/regenerate")
    assert resp.status_code == 200 and resp.json()["ok"] is True
    assert (root / "demo" / "generated" / "graph.json").exists()
    payload2 = client.get("/api/projects/demo/graph").json()
    assert payload2["graph"] is not None       # nodes/edges 数据可供 cytoscape 渲染
