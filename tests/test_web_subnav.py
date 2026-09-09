"""项目子导航（subnav）：全站持久版块导航、活动态、无 part 收缩、快捷入口退役。"""
import re
import shutil

import pytest

pytest.importorskip("fastapi")

from tests.webutil import make_client


def _active_link(html: str, href: str) -> bool:
    return re.search(
        rf'<a class="subnav-link active"[^>]*href="{re.escape(href)}"', html) is not None


def _plain_link(html: str, href: str) -> bool:
    return re.search(
        rf'<a class="subnav-link"[^>]*href="{re.escape(href)}"', html) is not None


def test_dashboard_subnav_has_all_sections(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/")
    assert resp.status_code == 200
    assert 'class="subnav"' in resp.text
    for slug in ("", "parts", "cards", "graph", "inspire", "diagnostics"):
        assert f'href="/p/demo/{slug}"' in resp.text
    assert _active_link(resp.text, "/p/demo/")       # 总览高亮
    assert _plain_link(resp.text, "/p/demo/cards")   # 其余为普通态
    assert "快捷入口" not in resp.text               # 裸链接段落被子导航取代


def test_subnav_active_follows_section(tmp_path):
    client, _ = make_client(tmp_path)
    cases = [
        ("/p/demo/parts", "/p/demo/parts"),
        ("/p/demo/cards/data", "/p/demo/cards"),
        ("/p/demo/graph", "/p/demo/graph"),
        ("/p/demo/inspire", "/p/demo/inspire"),
        ("/p/demo/diagnostics", "/p/demo/diagnostics"),
    ]
    for url, active_href in cases:
        resp = client.get(url)
        assert resp.status_code == 200, url
        assert _active_link(resp.text, active_href), url
        assert 'aria-current="page"' in resp.text, url


def test_index_has_no_subnav(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'class="subnav"' not in resp.text


def test_narrative_link_hidden_without_parts(tmp_path):
    client, projects = make_client(tmp_path)
    shutil.rmtree(projects / "demo" / "narrative")
    resp = client.get("/p/demo/")
    assert resp.status_code == 200
    assert 'class="subnav"' in resp.text
    assert 'href="/p/demo/parts"' not in resp.text
    assert client.get("/p/demo/parts").status_code == 404


def test_cards_kind_tabs_live_in_content_not_topnav(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/cards/data")
    assert resp.status_code == 200
    topnav = re.search(r'<nav class="topnav">.*?</nav>', resp.text, re.S).group(0)
    assert "/p/demo/cards/" not in topnav            # 深色全局栏回归纯全局内容
    assert '<a class="tab active"' in resp.text      # 当前卡种 tab 高亮
    assert 'href="/p/demo/cards/data"' in resp.text  # 卡种链接在内容区
