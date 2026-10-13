"""节点编辑：uses 成对编辑、悬空引用阻断——JSON API 版。"""
from weft.store.loader import load_project
from tests.webutil import make_client


def test_node_edit_payload(tmp_path):
    client, _ = make_client(tmp_path)
    payload = client.get("/api/projects/demo/parts/sec-01/nodes/para-01-01").json()
    assert payload["values"]["use_id"] == ["fact-01"]
    assert payload["values"]["use_role"] == ["evidence"]
    assert "evidence" in payload["role_vocab"]
    # 实体速查（前端 datalist + 摘要展示）
    assert "fact-01" in payload["entity_ids"]
    assert "温度提高速率。" in payload["entity_labels"]["fact-01"]


def test_node_edit_updates_uses(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.patch("/api/projects/demo/parts/sec-01/nodes/para-01-01", json={
        "purpose": "describe", "logic": "改后的逻辑。",
        "uses": [{"id": "fact-01", "role": "evidence"},
                 {"id": "claim-01", "role": "conclusion"}],
        "status": "approved", "comment": ""})
    assert resp.status_code == 200 and resp.json()["ok"] is True
    project, diags = load_project(root / "demo")
    assert not any(d.is_error for d in diags)
    node = next(n for p in project.parts for n in p.nodes if n.id == "para-01-01")
    assert [(u.id, u.role) for u in node.uses] == [("fact-01", "evidence"),
                                                   ("claim-01", "conclusion")]
    assert node.logic == "改后的逻辑。"


def test_node_edit_dangling_use_blocked(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.patch("/api/projects/demo/parts/sec-01/nodes/para-01-01", json={
        "purpose": "describe", "logic": "",
        "uses": [{"id": "fact-99", "role": "evidence"}],
        "status": "approved", "comment": ""})
    assert resp.status_code == 422
    assert "fact-99" in resp.json()["errors"]["uses"]   # 回显，未落盘
    project, _ = load_project(root / "demo")
    node = next(n for p in project.parts for n in p.nodes if n.id == "para-01-01")
    assert [u.id for u in node.uses] == ["fact-01"]


def test_node_edit_payload_entity_ids_cover_all_kinds(tmp_path):
    client, root = make_client(tmp_path)
    from tests.helpers import write_card
    write_card(root / "demo" / "metadata" / "methods", "m-x",
               {"id": "m-x", "statement": "方法 m。", "protocol": "p",
                "status": "approved"})
    write_card(root / "demo" / "metadata" / "methods" / "params", "p-tol",
               {"id": "p-tol", "method": "m-x", "values": {"tol": "5%"},
                "status": "draft"})
    payload = client.get("/api/projects/demo/parts/sec-01/nodes/para-01-01").json()
    assert "p-tol" in payload["entity_ids"]
