"""叙事工作台：part 清单、面板 payload、节点审阅、workflow 覆盖——JSON API 版。"""
from weft.store.loader import load_project
from tests.webutil import make_client


def test_parts_list_payload(tmp_path):
    client, _ = make_client(tmp_path)
    payload = client.get("/api/projects/demo/parts").json()
    assert payload["first"] == "sec-01"
    assert payload["parts"][0]["id"] == "sec-01"
    assert payload["parts"][0]["n_nodes"] == 1


def test_part_panel_payload(tmp_path):
    client, _ = make_client(tmp_path)
    payload = client.get("/api/projects/demo/parts/sec-01").json()
    node = payload["nodes"][0]
    assert node["id"] == "para-01-01" and node["status"] == "approved"
    assert node["uses"] == [{"id": "fact-01", "role": "evidence"}]
    assert "workflow_vocab" in payload and "draft_text" in payload


def test_part_panel_use_labels_show_digest(tmp_path):
    client, _ = make_client(tmp_path)
    payload = client.get("/api/projects/demo/parts/sec-01").json()
    # fact-01（statement 温度提高速率。）被 para-01-01 使用（labels 为裸摘要）
    assert payload["use_labels"]["fact-01"] == "温度提高速率。"


def test_node_review_updates_file(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/api/projects/demo/parts/sec-01/nodes/para-01-01/status",
                       json={"status": "rejected", "comment": "逻辑不对"})
    assert resp.status_code == 200 and resp.json()["ok"] is True
    project, diags = load_project(root / "demo")
    assert not any(d.is_error for d in diags)
    node = next(n for p in project.parts for n in p.nodes if n.id == "para-01-01")
    assert node.status == "rejected" and node.comment == "逻辑不对"


def test_unknown_part_404(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/api/projects/demo/parts/sec-99").status_code == 404


def test_part_workflow_override_updates_file(tmp_path):
    """part 级 workflow 显式覆盖（webui 设计 §5，词表同 CLI）；空值 = 清除。"""
    client, root = make_client(tmp_path)
    resp = client.post("/api/projects/demo/parts/sec-01/workflow",
                       json={"workflow": "methods"})
    assert resp.status_code == 200 and resp.json()["part"]["workflow"] == "methods"
    project, diags = load_project(root / "demo")
    assert not any(d.is_error for d in diags)
    part = next(p for p in project.parts if p.id == "sec-01")
    assert part.workflow == "methods"
    # 清空恢复自动路由
    client.post("/api/projects/demo/parts/sec-01/workflow", json={"workflow": ""})
    project2, _ = load_project(root / "demo")
    part2 = next(p for p in project2.parts if p.id == "sec-01")
    assert part2.workflow is None


def test_node_review_returns_refreshed_panel(tmp_path):
    """POST 返回刷新后的面板 payload（替代旧 htmx 片段交换）。"""
    client, _ = make_client(tmp_path)
    resp = client.post("/api/projects/demo/parts/sec-01/nodes/para-01-01/status",
                       json={"status": "approved"})
    body = resp.json()
    assert body["ok"] is True and body["nodes"][0]["status"] == "approved"


def test_node_review_preserves_comment_when_absent(tmp_path):
    client, root = make_client(tmp_path)
    client.post("/api/projects/demo/parts/sec-01/nodes/para-01-01/status",
                json={"status": "approved", "comment": "备注一"})
    client.post("/api/projects/demo/parts/sec-01/nodes/para-01-01/status",
                json={"status": "rejected"})
    project, _ = load_project(root / "demo")
    node = next(n for p in project.parts for n in p.nodes if n.id == "para-01-01")
    assert node.status == "rejected"
    assert node.comment == "备注一"
