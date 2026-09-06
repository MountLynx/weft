"""叙事工作台：页签、part 面板、节点审阅、workflow 覆盖。"""
import pytest

pytest.importorskip("fastapi")

from weft.store.loader import load_project
from tests.webutil import make_client


def test_parts_page_renders_tabs(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/parts")
    assert resp.status_code == 200
    assert "sec-01" in resp.text and "para-01-01" in resp.text


def test_part_panel_partial(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/parts/sec-01")
    assert resp.status_code == 200
    assert "para-01-01" in resp.text and "approved" in resp.text


def test_node_review_updates_file(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/parts/sec-01/nodes/para-01-01/status",
                       data={"status": "rejected", "comment": "逻辑不对"},
                       follow_redirects=False)
    assert resp.status_code == 303
    project, diags = load_project(root / "demo")
    assert not any(d.is_error for d in diags)
    node = next(n for p in project.parts for n in p.nodes if n.id == "para-01-01")
    assert node.status == "rejected" and node.comment == "逻辑不对"


def test_unknown_part_404(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/p/demo/parts/sec-99").status_code == 404


def test_part_workflow_override_updates_file(tmp_path):
    """part 级 workflow 显式路由覆盖（webui 设计 §5，词表同 CLI）。"""
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/parts/sec-01/workflow",
                       data={"workflow": "methods"}, follow_redirects=False)
    assert resp.status_code == 303
    project, diags = load_project(root / "demo")
    assert not any(d.is_error for d in diags)
    part = next(p for p in project.parts if p.id == "sec-01")
    assert part.workflow == "methods"
    # 清空恢复自动路由
    client.post("/p/demo/parts/sec-01/workflow", data={"workflow": ""})
    project2, _ = load_project(root / "demo")
    part2 = next(p for p in project2.parts if p.id == "sec-01")
    assert part2.workflow is None
