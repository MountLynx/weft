"""全局项目注册表（projects registry 设计 §3）：加载/保存/原子写、fail-closed、双唯一、默认根。"""
import json
from datetime import datetime
from pathlib import Path

import pytest

from weft.diagnostics import Level
from weft.registry import (
    RegistryData,
    RegistryError,
    load_registry,
    register_project,
    registry_path,
    resolve_default_root,
    save_registry,
    unregister_project,
    validate_project_name,
)
from weft.store.loader import is_weft_project


# ---------- 位置与环境 ----------

def test_registry_path_honors_weft_home(tmp_path, monkeypatch):
    monkeypatch.setenv("WEFT_HOME", str(tmp_path / "custom-home"))
    assert registry_path() == tmp_path / "custom-home" / "projects.json"


def test_registry_path_default_home():
    assert registry_path() == Path.home() / ".weft" / "projects.json"


# ---------- 加载与失败语义 ----------

def test_load_missing_file_returns_empty(tmp_path):
    reg = load_registry(tmp_path / "nonexistent" / "projects.json")
    assert reg.version == 1
    assert reg.projects == []
    assert reg.default_root is None


def test_save_creates_parent_dirs(tmp_path):
    target = tmp_path / "a" / "b" / "projects.json"
    save_registry(RegistryData(), target)
    assert target.exists()


def test_save_load_roundtrip_unicode(tmp_path):
    target = tmp_path / "projects.json"
    reg = RegistryData(default_root="D:/weft-projects")
    register_project(reg, "我的论文", Path("C:/papers/我的论文"))
    save_registry(reg, target)
    loaded = load_registry(target)
    assert loaded.default_root == "D:/weft-projects"
    assert loaded.projects[0].name == "我的论文"
    assert loaded.projects[0].path == "C:/papers/我的论文"


def test_save_writes_lf_ascii_raw(tmp_path):
    target = tmp_path / "projects.json"
    reg = RegistryData()
    register_project(reg, "中文项目", Path("C:/papers/中文"))
    save_registry(reg, target)
    raw = target.read_bytes()
    assert b"\r\n" not in raw
    assert "中文项目".encode("utf-8") in raw  # ensure_ascii=False，人可读
    assert json.loads(raw.decode("utf-8"))["version"] == 1


def test_save_leaves_no_tmp_leftover(tmp_path):
    target = tmp_path / "projects.json"
    save_registry(RegistryData(), target)
    assert {p.name for p in tmp_path.iterdir()} == {"projects.json"}


def test_registered_at_iso_seconds(tmp_path):
    reg = RegistryData()
    entry = register_project(reg, "demo", tmp_path / "demo")
    assert datetime.fromisoformat(entry.registered_at).strftime("%Y-%m-%dT%H:%M:%S") \
        == entry.registered_at


@pytest.mark.parametrize("payload", [
    "not json {",
    "[]",                                   # 顶层不是对象
    json.dumps({"version": 1, "projects": "nope"}),
    json.dumps({"version": 1, "projects": [], "bogus": 1}),   # 多余字段
    json.dumps({"version": 2, "projects": []}),               # 版本过新
    json.dumps({"version": 1, "projects": [{"name": "a"}]}),  # 条目缺字段
])
def test_load_malformed_fails_closed(tmp_path, payload):
    target = tmp_path / "projects.json"
    target.write_text(payload, encoding="utf-8")
    with pytest.raises(RegistryError) as excinfo:
        load_registry(target)
    diag = excinfo.value.diagnostic()
    assert diag.is_error
    assert diag.code == "E-REG-MALFORMED"
    assert diag.path == str(target)


# ---------- 名称校验（web 与 CLI 共享实现） ----------

@pytest.mark.parametrize("raw,clean", [("  spaced  ", "spaced"), ("我的论文", "我的论文"),
                                       ("paper-01", "paper-01")])
def test_validate_name_ok(raw, clean):
    assert validate_project_name(raw) == (clean, None)


@pytest.mark.parametrize("bad", [
    "", "   ", ".", "..", ".hidden", "tail.",
    "a/b", "a\\b", "x<y", 'x"y', "x:y",
    "con", "COM1", "x" * 101,
])
def test_validate_name_rejected(bad):
    name, error = validate_project_name(bad)
    assert error is not None


# ---------- 登记 / 摘除 ----------

def test_register_appends_and_persists(tmp_path):
    target = tmp_path / "projects.json"
    reg = load_registry(target)
    entry = register_project(reg, "demo", tmp_path / "demo")
    save_registry(reg, target)
    assert entry.path == (tmp_path / "demo").resolve().as_posix()
    loaded = load_registry(target)
    assert [p.name for p in loaded.projects] == ["demo"]


def test_register_duplicate_name_fails(tmp_path):
    reg = RegistryData()
    register_project(reg, "demo", tmp_path / "demo")
    with pytest.raises(RegistryError) as excinfo:
        register_project(reg, "demo", tmp_path / "other")
    assert excinfo.value.diagnostic().code == "E-REG-DUP"
    assert len(reg.projects) == 1


def test_register_duplicate_path_fails(tmp_path):
    reg = RegistryData()
    register_project(reg, "first", tmp_path / "demo")
    with pytest.raises(RegistryError) as excinfo:
        register_project(reg, "second", tmp_path / "demo")
    assert excinfo.value.diagnostic().code == "E-REG-PATH-DUP"


def test_register_invalid_name_fails(tmp_path):
    reg = RegistryData()
    with pytest.raises(RegistryError) as excinfo:
        register_project(reg, "a/b", tmp_path / "x")
    assert excinfo.value.diagnostic().code == "E-REG-NAME"
    assert reg.projects == []


def test_unregister_removes_only_table_row(tmp_path):
    reg = RegistryData()
    register_project(reg, "demo", tmp_path / "demo")
    entry = unregister_project(reg, "demo")
    assert entry.name == "demo"
    assert reg.projects == []
    with pytest.raises(RegistryError) as excinfo:
        unregister_project(reg, "demo")
    assert excinfo.value.diagnostic().code == "E-REG-UNKNOWN"


# ---------- 默认根三级回退的末两级 ----------

def test_resolve_default_root_configured(tmp_path):
    reg = RegistryData(default_root="D:/papers")
    assert resolve_default_root(reg) == Path("D:/papers")


def test_resolve_default_root_fallback_home(tmp_path):
    reg = RegistryData()
    assert resolve_default_root(reg, home=tmp_path) == tmp_path / "weft-projects"


# ---------- 项目判据（loader 单一实现） ----------

def test_is_weft_project_metadata_dir(tmp_path):
    (tmp_path / "metadata").mkdir()
    assert is_weft_project(tmp_path)


def test_is_weft_project_quarto_only(tmp_path):
    (tmp_path / "_quarto.yml").write_text("project: {}\n", encoding="utf-8")
    assert is_weft_project(tmp_path)


def test_is_weft_project_negative(tmp_path):
    assert not is_weft_project(tmp_path)
    assert not is_weft_project(tmp_path / "missing")
