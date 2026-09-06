"""卡片列表、详情与审阅（status/comment 写回）。"""
import pytest

pytest.importorskip("fastapi")

from weft.store.loader import load_project
from tests.webutil import make_client


def test_cards_overview_and_list(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/p/demo/cards").status_code == 200
    resp = client.get("/p/demo/cards/fact")
    assert resp.status_code == 200 and "fact-01" in resp.text


def test_card_detail_renders(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/cards/fact/fact-01")
    assert resp.status_code == 200
    assert "fact-01" in resp.text and "温度提高速率" in resp.text


def test_unknown_kind_404(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/p/demo/cards/bogus").status_code == 404
    assert client.get("/p/demo/cards/fact/fact-99").status_code == 404


def test_review_updates_file(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/cards/fact/fact-01/status",
                       data={"status": "rejected", "comment": "表述有误"},
                       follow_redirects=False)
    assert resp.status_code == 303
    project, diags = load_project(root / "demo")
    assert not any(d.is_error for d in diags)
    assert project.facts["fact-01"].status == "rejected"
    assert project.facts["fact-01"].comment == "表述有误"


def test_review_invalid_status_400(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/cards/fact/fact-01/status",
                       data={"status": "bogus", "comment": ""})
    assert resp.status_code == 400
    project, _ = load_project(root / "demo")
    assert project.facts["fact-01"].status == "approved"
