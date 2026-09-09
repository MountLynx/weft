"""令牌化主题架构守卫（2026-09-09 webui 样式设计 §3/§6/§8）。

三条守卫：
1. /static/themes/academic.css 路由可达且是合法主题文件；
2. base.html 渲染含防闪脚本、主题 <link> 与切换控件；
3. 主题文件只允许令牌声明（拦截组件选择器混入，"主题 = 纯令牌文件"约定）。
"""
import re
from pathlib import Path

import weft.web
from tests.webutil import make_client

_STATIC = Path(weft.web.__file__).parent / "static"


def test_academic_theme_css_served(tmp_path):
    client, _ = make_client(tmp_path)
    r = client.get("/static/themes/academic.css")
    assert r.status_code == 200
    assert 'data-theme="academic"' in r.text


def test_base_page_has_theme_infrastructure(tmp_path):
    client, _ = make_client(tmp_path)
    html = client.get("/").text
    assert "/static/themes/academic.css" in html      # 主题 <link>
    assert "weft-theme" in html                        # 防闪内联脚本读 localStorage 键
    assert "theme-toggle" in html                      # 顶栏切换控件
    assert "data-theme" in html                        # 防闪脚本设置 documentElement.dataset.theme


def test_theme_file_contains_only_token_declarations():
    css = (_STATIC / "themes" / "academic.css").read_text(encoding="utf-8")
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)          # 去注释
    body = body.replace('[data-theme="academic"]', "")        # 去主题选择器
    body = body.replace("{", "").replace("}", "")
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    assert lines, "主题文件不能为空"
    bad = [ln for ln in lines if not ln.startswith("--")]
    assert not bad, f"主题文件混入非令牌声明: {bad}"
