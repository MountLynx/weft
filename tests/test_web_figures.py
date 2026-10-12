"""figures.yaml WebUI 路由测试（webui figures 设计定案）。

夹具项目（webutil→helpers.make_minimal_project）：figures.yaml 含 fig-01
（caption 速率曲线、子图 a），data-01 refs=[fig-01a]，figures/fig-01a.png 存在。
"""
import pytest

pytest.importorskip("fastapi")

from tests.helpers import write_yaml
from tests.webutil import make_client


def test_figures_page_lists_entries(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/figures")
    assert resp.status_code == 200
    assert "fig-01" in resp.text and "速率曲线" in resp.text
    assert 'href="/p/demo/cards/data/data-01"' in resp.text   # 引用卡链接
    assert "文件缺失" not in resp.text                          # fig-01a.png 存在
    assert "未被引用" not in resp.text                          # data-01 引用着
    assert 'href="/p/demo/figures"' in resp.text               # 子导航"图表"


def test_figures_page_markers(tmp_path):
    client, projects = make_client(tmp_path)
    write_yaml(projects / "demo" / "metadata" / "figures.yaml",
               {"fig-01": {"caption": "速率曲线", "subfigs": {"a": "60°C"}},
                "fig-02": {"caption": "没人用的图"}})
    resp = client.get("/p/demo/figures")
    assert resp.status_code == 200
    assert "文件缺失" in resp.text       # fig-02 无 png/pdf
    assert "未被引用" in resp.text       # 无 data 卡引用 fig-02


def test_figures_unknown_project_404(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/p/nope/figures").status_code == 404


def test_broken_yaml_list_viewable(tmp_path):
    """F3：figures.yaml 坏 → 页面仍 200，banner 指认 E-FIG-LOAD，转只读。"""
    client, projects = make_client(tmp_path)
    (projects / "demo" / "metadata" / "figures.yaml").write_text(
        "fig-01: [unclosed\n", encoding="utf-8")
    resp = client.get("/p/demo/figures")
    assert resp.status_code == 200
    assert "E-FIG-LOAD" in resp.text
    assert "新增图注条目" not in resp.text
