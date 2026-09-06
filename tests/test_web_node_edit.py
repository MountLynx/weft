"""节点编辑：uses 成对编辑、悬空引用阻断。"""
import pytest

pytest.importorskip("fastapi")

from weft.store.loader import load_project
from tests.webutil import make_client


def test_node_edit_form_renders(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/parts/sec-01/nodes/para-01-01")
    assert resp.status_code == 200
    assert "fact-01" in resp.text and "evidence" in resp.text


def test_node_edit_updates_uses(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/parts/sec-01/nodes/para-01-01", data={
        "purpose": "describe", "logic": "改后的逻辑。",
        "use_id": ["fact-01", "claim-01"], "use_role": ["evidence", "conclusion"],
        "status": "approved", "comment": ""}, follow_redirects=False)
    assert resp.status_code == 303
    project, diags = load_project(root / "demo")
    assert not any(d.is_error for d in diags)
    node = next(n for p in project.parts for n in p.nodes if n.id == "para-01-01")
    assert [(u.id, u.role) for u in node.uses] == [("fact-01", "evidence"),
                                                   ("claim-01", "conclusion")]
    assert node.logic == "改后的逻辑。"


def test_node_edit_dangling_use_blocked(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/parts/sec-01/nodes/para-01-01", data={
        "purpose": "describe", "logic": "",
        "use_id": ["fact-99"], "use_role": ["evidence"],
        "status": "approved", "comment": ""})
    assert resp.status_code == 200 and "fact-99" in resp.text   # 回显，未落盘
    project, _ = load_project(root / "demo")
    node = next(n for p in project.parts for n in p.nodes if n.id == "para-01-01")
    assert [u.id for u in node.uses] == ["fact-01"]
