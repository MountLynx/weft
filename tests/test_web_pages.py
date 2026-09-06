"""首页项目列表与项目总览仪表盘。"""
import pytest

pytest.importorskip("fastapi")

from tests.webutil import make_client


def test_index_lists_projects(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "demo" in resp.text and "weft" in resp.text


def test_dashboard_shows_stats_and_queue(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/", follow_redirects=False)
    assert resp.status_code == 200
    assert "待审阅" in resp.text and "诊断" in resp.text


def test_unknown_project_404(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/p/nope/").status_code == 404
