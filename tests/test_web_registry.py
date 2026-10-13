"""注册表模式 API（projects registry 设计 §5）：列表、失联条目、新建登记闭环、表损坏。

扫描模式回归由其余 test_web_* 守护，本文件只覆盖注册表模式增量。
"""
from pathlib import Path

from fastapi.testclient import TestClient

from tests.helpers import make_minimal_project
from weft.registry import load_registry, register_project, save_registry
from weft.web import create_app


def make_projects_root(tmp_path: Path) -> Path:
    projects = tmp_path / "projects"
    projects.mkdir(exist_ok=True)
    return projects


def setup_weft_home(tmp_path, monkeypatch) -> None:
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

    payload = client.get("/api/projects").json()
    assert payload["registry_mode"] is True and payload["registry_path"]
    entry = next(e for e in payload["entries"] if e["pid"] == "demo")
    assert entry["available"] is True and entry["n_errors"] == 0
    assert client.get("/api/projects/demo").status_code == 200


def test_registry_mode_empty_state(tmp_path, monkeypatch):
    setup_weft_home(tmp_path, monkeypatch)
    make_projects_root(tmp_path)
    client = TestClient(create_app(use_registry=True))
    payload = client.get("/api/projects").json()
    assert payload["entries"] == [] and payload["registry_mode"] is True


def test_registry_mode_missing_entry_greyed(tmp_path, monkeypatch):
    setup_weft_home(tmp_path, monkeypatch)
    make_projects_root(tmp_path)
    register_from_env("ghost", tmp_path / "no" / "such" / "dir")
    client = TestClient(create_app(use_registry=True))

    payload = client.get("/api/projects").json()
    entry = next(e for e in payload["entries"] if e["pid"] == "ghost")
    assert entry["missing"] is True and entry["available"] is False
    # 直达也 404（missing 不是可用项目）
    assert client.get("/api/projects/ghost").status_code == 404


def test_cli_registration_visible_without_restart(tmp_path, monkeypatch):
    setup_weft_home(tmp_path, monkeypatch)
    projects = make_projects_root(tmp_path)
    client = TestClient(create_app(use_registry=True))
    assert client.get("/api/projects").json()["entries"] == []
    # serve 启动后 CLI 登记（R7：每请求实时读注册表）
    register_from_env("late-add", make_minimal_project(projects / "late-add"))
    pids = [e["pid"] for e in client.get("/api/projects").json()["entries"]]
    assert pids == ["late-add"]


# ---------- 新建项目（创建 + 登记闭环） ----------

def test_new_project_creates_and_registers(tmp_path, monkeypatch):
    setup_weft_home(tmp_path, monkeypatch)
    projects = make_projects_root(tmp_path)
    set_default_root(projects)
    client = TestClient(create_app(use_registry=True))

    resp = client.post("/api/projects", json={"name": "fresh"})
    assert resp.status_code == 200 and resp.json()["pid"] == "fresh"
    assert (projects / "fresh" / "metadata").is_dir()
    assert registry_entry_names() == ["fresh"]
    assert client.get("/api/projects/fresh").status_code == 200


def test_new_project_explicit_location(tmp_path, monkeypatch):
    setup_weft_home(tmp_path, monkeypatch)
    make_projects_root(tmp_path)
    elsewhere = tmp_path / "elsewhere-root"
    client = TestClient(create_app(use_registry=True))

    resp = client.post("/api/projects",
                       json={"name": "over-there", "location": str(elsewhere)})
    assert resp.status_code == 200
    assert (elsewhere / "over-there" / "weft.yaml").is_file()
    assert registry_entry_names() == ["over-there"]


def test_new_project_default_root_unset_errors(tmp_path, monkeypatch):
    setup_weft_home(tmp_path, monkeypatch)
    make_projects_root(tmp_path)
    fake_home = tmp_path / "fake-home"
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    client = TestClient(create_app(use_registry=True))

    resp = client.post("/api/projects", json={"name": "x"})
    assert resp.status_code == 422
    assert "weft projects root" in resp.json()["detail"]
    # 不允许悄悄落进 ~/weft-projects
    assert not (fake_home / "weft-projects").exists()
    assert registry_entry_names() == []


def test_new_project_duplicate_name_fail_closed(tmp_path, monkeypatch):
    setup_weft_home(tmp_path, monkeypatch)
    projects = make_projects_root(tmp_path)
    register_from_env("demo", make_minimal_project(projects / "demo"))
    client = TestClient(create_app(use_registry=True))

    before = sorted(str(p.relative_to(projects)) for p in projects.rglob("*"))
    resp = client.post("/api/projects", json={"name": "demo"})
    assert resp.status_code == 422
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
    resp = client.post("/api/projects", json={"name": "busy"})
    assert resp.status_code == 422
    assert "未写入任何文件" in resp.json()["detail"]
    after = sorted(str(p.relative_to(busy)) for p in busy.rglob("*"))
    assert before == after
    assert registry_entry_names() == []


# ---------- 注册表损坏 ----------

def test_malformed_registry_error_surface(tmp_path, monkeypatch):
    setup_weft_home(tmp_path, monkeypatch)
    home = tmp_path / "weft-home"
    home.mkdir(parents=True)
    (home / "projects.json").write_text("not json {", encoding="utf-8")
    client = TestClient(create_app(use_registry=True))

    payload = client.get("/api/projects").json()
    assert "E-REG-MALFORMED" in payload["reg_error"]


# ---------- 审查修复补充 ----------

def test_new_project_rejects_invalid_name(tmp_path, monkeypatch):
    """表单非法名（E-REG-NAME 场景）：错误 + 零写入（审查 Minor 5a）。"""
    setup_weft_home(tmp_path, monkeypatch)
    projects = make_projects_root(tmp_path)
    set_default_root(projects)
    client = TestClient(create_app(use_registry=True))
    resp = client.post("/api/projects", json={"name": "a/b"})
    assert resp.status_code == 422
    assert registry_entry_names() == []
    assert not (projects / "a").exists()


def test_scan_mode_does_not_touch_registry(tmp_path, monkeypatch):
    """扫描模式（含新建）不读写注册表（审查 Minor 5b 回归守护）。"""
    setup_weft_home(tmp_path, monkeypatch)
    projects = make_projects_root(tmp_path)
    make_minimal_project(projects / "demo")
    client = TestClient(create_app(projects))
    assert client.get("/api/projects").status_code == 200
    resp = client.post("/api/projects", json={"name": "scan-made"})
    assert resp.status_code == 200
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
