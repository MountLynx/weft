"""首页项目列表与项目总览仪表盘。"""
import pytest

pytest.importorskip("fastapi")

from tests.helpers import write_card
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


def _poison_draft_note(root):
    """unmanaged 项目塞一张提案式 draft note（id 不在 bib）→ E-NOTE-NOT-IN-BIB。"""
    write_card(root / "demo" / "metadata" / "notes", "li2021",
               {"id": "li2021", "summary": "", "status": "draft"})


def test_dashboard_renders_validation_error_project(tmp_path):
    # 校验错误（如 unmanaged 提案 note 不在 bib）的项目仍渲染仪表盘（不可用徽章 +
    # 待审队列指路），只有加载级损坏才是"无法加载"页。
    client, root = make_client(tmp_path)
    _poison_draft_note(root)
    resp = client.get("/p/demo/")
    assert resp.status_code == 200
    assert "无法加载" not in resp.text
    # base.html 主题脚本注释含"不可用"字样，须断言徽章标记本身
    assert 'badge rejected">不可用' in resp.text
    assert "li2021" in resp.text


def test_dashboard_load_error_still_unavailable(tmp_path):
    client, root = make_client(tmp_path)
    write_card(root / "demo" / "metadata" / "data", "oops",
               {"id": "data-01", "status": "approved"})   # 文件名≠id → 加载错误
    resp = client.get("/p/demo/")
    assert resp.status_code == 200 and "无法加载" in resp.text
    assert client.post("/p/demo/cards/fact/fact-01/status",
                       data={"status": "rejected", "comment": ""}).status_code == 404


def test_unknown_project_404(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/p/nope/").status_code == 404
