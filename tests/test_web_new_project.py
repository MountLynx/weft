"""项目新建（POST /projects/new）：表单展示、创建落盘、冲突 fail-closed、名称守卫。"""
from urllib.parse import quote

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from tests.webutil import make_client
from weft.web import create_app


def test_index_shows_new_project_form(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'action="/projects/new"' in resp.text
    assert 'name="name"' in resp.text
    assert "新建项目" in resp.text


def test_form_visible_on_empty_root(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    client = TestClient(create_app(projects))
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'action="/projects/new"' in resp.text


def test_create_project_success(tmp_path):
    client, projects = make_client(tmp_path)
    resp = client.post("/projects/new", data={"name": "paper-new"},
                       follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/p/paper-new/"
    # 骨架落盘（init_project 载体）
    assert (projects / "paper-new" / "weft.yaml").exists()
    assert (projects / "paper-new" / "metadata").is_dir()
    # 列表出现且零诊断
    listing = client.get("/")
    assert "paper-new" in listing.text
    assert "E: 0 · W: 0" in listing.text
    # 新项目仪表盘可打开
    assert client.get("/p/paper-new/").status_code == 200


def test_create_project_strips_whitespace(tmp_path):
    client, projects = make_client(tmp_path)
    resp = client.post("/projects/new", data={"name": "  spaced  "},
                       follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/p/spaced/"
    assert (projects / "spaced" / "metadata").is_dir()


def test_create_project_chinese_name(tmp_path):
    client, projects = make_client(tmp_path)
    resp = client.post("/projects/new", data={"name": "我的论文"},
                       follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/p/{quote('我的论文', safe='')}/"
    assert (projects / "我的论文" / "metadata").is_dir()
    # percent-encoded 直达新项目仪表盘
    assert client.get(f"/p/{quote('我的论文')}/").status_code == 200
    assert "我的论文" in client.get("/").text


def test_create_project_collision_fail_closed(tmp_path):
    client, projects = make_client(tmp_path)
    before = sorted(str(p.relative_to(projects)) for p in projects.rglob("*"))
    resp = client.post("/projects/new", data={"name": "demo"},
                       follow_redirects=False)
    assert resp.status_code == 200
    assert "新建失败" in resp.text
    assert "未写入任何文件" in resp.text
    after = sorted(str(p.relative_to(projects)) for p in projects.rglob("*"))
    assert before == after


def test_create_project_into_existing_empty_dir(tmp_path):
    client, projects = make_client(tmp_path)
    (projects / "blank").mkdir()
    resp = client.post("/projects/new", data={"name": "blank"},
                       follow_redirects=False)
    assert resp.status_code == 303
    assert (projects / "blank" / "weft.yaml").exists()


@pytest.mark.parametrize("bad", [
    "", "   ",          # 空名（含纯空白）
    ".", "..",          # 路径特殊项
    ".hidden",          # 以 . 开头（工具目录约定）
    "tail.",            # 以 . 结尾（Windows 静默剥离）
    "a/b", "a\\b",      # 路径分隔符
    "con", "COM1",      # Windows 保留设备名（大小写不敏感）
    "x<y", 'x"y',       # Windows 非法字符
    "x" * 101,          # 超长
])
def test_create_project_rejects_invalid_names(tmp_path, bad):
    client, projects = make_client(tmp_path)
    before = {p.name for p in projects.iterdir()}
    resp = client.post("/projects/new", data={"name": bad},
                       follow_redirects=False)
    assert resp.status_code == 200
    assert "新建失败" in resp.text
    assert {p.name for p in projects.iterdir()} == before
