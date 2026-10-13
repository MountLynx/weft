"""项目新建（POST /api/projects）：创建落盘、冲突 fail-closed、名称守卫。

表单渲染属前端职责（SPA），服务端契约 = JSON 请求/响应 + 零写入失败语义。
"""
import pytest

from fastapi.testclient import TestClient

from tests.webutil import make_client
from weft.web import create_app


def test_create_project_success(tmp_path):
    client, projects = make_client(tmp_path)
    resp = client.post("/api/projects", json={"name": "paper-new"})
    assert resp.status_code == 200 and resp.json()["ok"] is True
    assert resp.json()["pid"] == "paper-new"
    # 骨架落盘（init_project 载体）
    assert (projects / "paper-new" / "weft.yaml").exists()
    assert (projects / "paper-new" / "metadata").is_dir()
    # 列表出现且零诊断
    listing = client.get("/api/projects").json()
    entry = next(e for e in listing["entries"] if e["pid"] == "paper-new")
    assert entry["n_errors"] == 0 and entry["n_warnings"] == 0
    # 新项目仪表盘可打开
    assert client.get("/api/projects/paper-new").status_code == 200


def test_create_project_strips_whitespace(tmp_path):
    client, projects = make_client(tmp_path)
    resp = client.post("/api/projects", json={"name": "  spaced  "})
    assert resp.status_code == 200 and resp.json()["pid"] == "spaced"
    assert (projects / "spaced" / "metadata").is_dir()


def test_create_project_chinese_name(tmp_path):
    client, projects = make_client(tmp_path)
    resp = client.post("/api/projects", json={"name": "我的论文"})
    assert resp.status_code == 200
    assert (projects / "我的论文" / "metadata").is_dir()
    # pid 直达新项目仪表盘
    assert client.get("/api/projects/我的论文").status_code == 200
    listing = client.get("/api/projects").json()
    assert any(e["pid"] == "我的论文" for e in listing["entries"])


def test_create_project_collision_fail_closed(tmp_path):
    client, projects = make_client(tmp_path)
    before = sorted(str(p.relative_to(projects)) for p in projects.rglob("*"))
    resp = client.post("/api/projects", json={"name": "demo"})
    assert resp.status_code == 422
    assert "未写入任何文件" in resp.json()["detail"]
    after = sorted(str(p.relative_to(projects)) for p in projects.rglob("*"))
    assert before == after


def test_create_project_into_existing_empty_dir(tmp_path):
    client, projects = make_client(tmp_path)
    (projects / "blank").mkdir()
    resp = client.post("/api/projects", json={"name": "blank"})
    assert resp.status_code == 200
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
    resp = client.post("/api/projects", json={"name": bad})
    assert resp.status_code == 422
    assert {p.name for p in projects.iterdir()} == before


def test_create_project_location_ignored_in_scan_mode(tmp_path):
    """扫描模式新建只认 projects_root：location 字段无意义但不致错。"""
    client, projects = make_client(tmp_path)
    resp = client.post("/api/projects",
                       json={"name": "scan-only", "location": str(tmp_path / "no")})
    assert resp.status_code == 200
    assert (projects / "scan-only" / "metadata").is_dir()


def test_empty_root_lists_zero_entries(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    client = TestClient(create_app(projects))
    payload = client.get("/api/projects").json()
    assert payload["entries"] == [] and payload["registry_mode"] is False
    assert payload["projects_root"] == str(projects.resolve())
