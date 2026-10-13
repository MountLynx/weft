"""项目列表 payload 与项目总览仪表盘 payload。"""
import pytest

from tests.helpers import write_card
from tests.webutil import make_client


def test_index_lists_projects(tmp_path):
    client, _ = make_client(tmp_path)
    payload = client.get("/api/projects").json()
    pids = [e["pid"] for e in payload["entries"]]
    assert pids == ["demo"]
    assert payload["entries"][0]["n_cards"] == 4


def test_dashboard_shows_stats_and_queue(tmp_path):
    client, _ = make_client(tmp_path)
    payload = client.get("/api/projects/demo").json()
    assert payload["available"] is True
    assert payload["kind_counts"]["fact"] == 1
    assert payload["n_parts"] == 1
    assert payload["bib_managed"] is False
    # 最小项目全部 approved → 待审队列为空
    assert payload["review_queue"] == []
    assert payload["status_counts"].get("approved", 0) >= 4


def test_dashboard_surfaces_validation_error_project(tmp_path):
    # 校验错误（如 unmanaged 提案 note 不在 bib）的项目仍返回仪表盘（available=False +
    # 待审队列指路），只有加载级损坏才是 available=False 且 project 为 None 的形态。
    client, root = make_client(tmp_path)
    write_card(root / "demo" / "metadata" / "notes", "li2021",
               {"id": "li2021", "summary": "", "status": "draft"})
    payload = client.get("/api/projects/demo").json()
    assert payload["available"] is False
    assert any(d["code"] == "E-NOTE-NOT-IN-BIB" for d in payload["diagnostics"])
    assert any(q["id"] == "li2021" and q["type"] == "card"
               for q in payload["review_queue"])


def test_dashboard_load_error_still_unavailable(tmp_path):
    client, root = make_client(tmp_path)
    write_card(root / "demo" / "metadata" / "data", "oops",
               {"id": "data-01", "status": "approved"})   # 文件名≠id → 加载错误
    payload = client.get("/api/projects/demo").json()
    assert payload["available"] is False and payload.get("review_queue") is None
    assert any(d["is_error"] for d in payload["diagnostics"])
    # 审阅面拒绝（加载级损坏无卡表可查）
    assert client.post("/api/projects/demo/cards/fact/fact-01/status",
                       json={"status": "rejected", "comment": ""}).status_code == 404


def test_unknown_project_404(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/api/projects/nope")
    assert resp.status_code == 404 and "项目不存在" in resp.json()["detail"]
