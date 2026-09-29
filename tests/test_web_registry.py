"""注册表模式 WebUI（projects registry 设计 §5）：列表、失联灰显、新建登记闭环、损坏横幅。

扫描模式回归由既有 test_web_* 全套守护，本文件只覆盖注册表模式增量。
"""
from pathlib import Path
from urllib.parse import quote

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from tests.helpers import make_minimal_project
from weft.registry import load_registry, register_project, save_registry
from weft.web import create_app


def make_projects_root(tmp_path: Path) -> Path:
    projects = tmp_path / "projects"
    projects.mkdir(exist_ok=True)
    return projects


def setup_weft_home(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEFT_HOME", str(tmp_path / "weft-home"))


def register_from_env(name: str, path: Path) -> None:
    """模拟 CLI 侧登记（同一条注册表文件，serve 每请求实时读）。"""
    reg = load_registry()
    register_project(reg, name, path)
    save_registry(reg)


def set_default_root(path: Path) -> None:
    reg = load_registry()
    reg.default_root = path.resolve().as_posix()
    save_registry(reg)


def registry_entry_names() -> list[str]:
    return [p.name for p in load_registry().projects]


# ---------- 列表与详情 ----------

def test_registry_mode_lists_registered_project(tmp_path, monkeypatch):
    setup_weft_home(tmp_path, monkeypatch)
    projects = make_projects_root(tmp_path)
    register_from_env("demo", make_minimal_project(projects / "demo"))
    client = TestClient(create_app(use_registry=True))

    resp = client.get("/")
    assert resp.status_code == 200
    assert "demo" in resp.text
    assert "可用" in resp.text
    assert "注册表：" in resp.text
    assert 'href="/p/demo/"' in resp.text
    assert client.get("/p/demo/").status_code == 200


def test_registry_mode_empty_state(tmp_path, monkeypatch):
    setup_weft_home(tmp_path, monkeypatch)
    make_projects_root(tmp_path)
    client = TestClient(create_app(use_registry=True))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "注册表为空" in resp.text
    assert 'action="/projects/new"' in resp.text


def test_registry_mode_missing_entry_greyed(tmp_path, monkeypatch):
    setup_weft_home(tmp_path, monkeypatch)
    make_projects_root(tmp_path)
    register_from_env("ghost", tmp_path / "no" / "such" / "dir")
    client = TestClient(create_app(use_registry=True))

    resp = client.get("/")
    assert resp.status_code == 200
    assert "位置失联" in resp.text
    assert 'href="/p/ghost/"' not in resp.text
    # 直达 URL 也 404（missing 不是可用项目）
    assert client.get("/p/ghost/").status_code == 404


def test_cli_registration_visible_without_restart(tmp_path, monkeypatch):
    setup_weft_home(tmp_path, monkeypatch)
    projects = make_projects_root(tmp_path)
    client = TestClient(create_app(use_registry=True))
    assert "late-add" not in client.get("/").text
    # serve 启动后 CLI 登记（R7：每请求实时读注册表）
    register_from_env("late-add", make_minimal_project(projects / "late-add"))
    assert "late-add" in client.get("/").text


# ---------- 新建项目（创建 + 登记闭环） ----------

def test_new_project_creates_and_registers(tmp_path, monkeypatch):
    setup_weft_home(tmp_path, monkeypatch)
    projects = make_projects_root(tmp_path)
    set_default_root(projects)
    client = TestClient(create_app(use_registry=True))

    resp = client.post("/projects/new", data={"name": "fresh"},
                       follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/p/fresh/"
    assert (projects / "fresh" / "metadata").is_dir()
    assert registry_entry_names() == ["fresh"]
    assert client.get("/p/fresh/").status_code == 200


def test_new_project_explicit_location(tmp_path, monkeypatch):
    setup_weft_home(tmp_path, monkeypatch)
    make_projects_root(tmp_path)
    elsewhere = tmp_path / "elsewhere-root"
    client = TestClient(create_app(use_registry=True))

    resp = client.post("/projects/new",
                       data={"name": "over-there", "location": str(elsewhere)},
                       follow_redirects=False)
    assert resp.status_code == 303
    assert (elsewhere / "over-there" / "weft.yaml").is_file()
    assert registry_entry_names() == ["over-there"]


def test_new_project_default_root_unset_errors(tmp_path, monkeypatch):
    setup_weft_home(tmp_path, monkeypatch)
    make_projects_root(tmp_path)
    fake_home = tmp_path / "fake-home"
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    client = TestClient(create_app(use_registry=True))

    resp = client.post("/projects/new", data={"name": "x"})
    assert resp.status_code == 200
    assert "新建失败" in resp.text
    assert "weft projects root" in resp.text
    # 不允许悄悄落进 ~/weft-projects
    assert not (fake_home / "weft-projects").exists()
    assert registry_entry_names() == []


def test_new_project_duplicate_name_fail_closed(tmp_path, monkeypatch):
    setup_weft_home(tmp_path, monkeypatch)
    projects = make_projects_root(tmp_path)
    register_from_env("demo", make_minimal_project(projects / "demo"))
    client = TestClient(create_app(use_registry=True))

    before = sorted(str(p.relative_to(projects)) for p in projects.rglob("*"))
    resp = client.post("/projects/new", data={"name": "demo"})
    assert resp.status_code == 200
    assert "新建失败" in resp.text
    after = sorted(str(p.relative_to(projects)) for p in projects.rglob("*"))
    assert before == after
    assert registry_entry_names() == ["demo"]


def test_new_project_collision_zero_write(tmp_path, monkeypatch):
    setup_weft_home(tmp_path, monkeypatch)
    projects = make_projects_root(tmp_path)
    set_default_root(projects)
    busy = projects / "busy"
    busy.mkdir()
    (busy / "user-file.txt").write_text("已有内容", encoding="utf-8")
    client = TestClient(create_app(use_registry=True))

    before = sorted(str(p.relative_to(busy)) for p in busy.rglob("*"))
    resp = client.post("/projects/new", data={"name": "busy"})
    assert resp.status_code == 200
    assert "新建失败" in resp.text
    assert "未写入任何文件" in resp.text
    after = sorted(str(p.relative_to(busy)) for p in busy.rglob("*"))
    assert before == after
    assert registry_entry_names() == []


# ---------- 注册表损坏 ----------

def test_malformed_registry_error_banner(tmp_path, monkeypatch):
    setup_weft_home(tmp_path, monkeypatch)
    home = tmp_path / "weft-home"
    home.mkdir(parents=True)
    (home / "projects.json").write_text("not json {", encoding="utf-8")
    client = TestClient(create_app(use_registry=True))

    resp = client.get("/")
    assert resp.status_code == 200
    assert "E-REG-MALFORMED" in resp.text


# ---------- 审查修复补充 ----------

def test_new_project_rejects_invalid_name(tmp_path, monkeypatch):
    """表单非法名（E-REG-NAME 场景）：错误文案 + 零写入（审查 Minor 5a）。"""
    setup_weft_home(tmp_path, monkeypatch)
    projects = make_projects_root(tmp_path)
    set_default_root(projects)
    client = TestClient(create_app(use_registry=True))
    resp = client.post("/projects/new", data={"name": "a/b"})
    assert resp.status_code == 200
    assert "新建失败" in resp.text
    assert registry_entry_names() == []
    assert not (projects / "a").exists()


def test_scan_mode_does_not_touch_registry(tmp_path, monkeypatch):
    """扫描模式（含其新建表单）不读写注册表（审查 Minor 5b 回归守护）。"""
    setup_weft_home(tmp_path, monkeypatch)
    projects = make_projects_root(tmp_path)
    make_minimal_project(projects / "demo")
    client = TestClient(create_app(projects))
    assert client.get("/").status_code == 200
    resp = client.post("/projects/new", data={"name": "scan-made"},
                       follow_redirects=False)
    assert resp.status_code == 303
    assert load_registry().projects == []


def test_probe_survives_pathological_path(tmp_path, monkeypatch):
    """手改注册表塞入病态路径（null 字节）：条目转 missing 而非 500（审查 Minor 3）。"""
    from weft.registry import RegistryData, RegistryEntry, save_registry
    from weft.web.discovery import registry_projects

    setup_weft_home(tmp_path, monkeypatch)
    save_registry(RegistryData(projects=[
        RegistryEntry(name="bad", path="x\x00y", registered_at="2026-09-29T00:00:00")]))
    entries = registry_projects()
    assert [e.pid for e in entries] == ["bad"]
    assert entries[0].missing is True
