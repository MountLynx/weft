"""weft projects 命令组（projects registry 设计 §4）：add/new/list/remove/root。

全部命令经 WEFT_HOME 隔离到 tmp；fail-closed 与零写入是核心断言。
"""
from pathlib import Path

from typer.testing import CliRunner

from tests.helpers import make_minimal_project
from weft.cli import app
from weft.registry import load_registry

runner = CliRunner()


def make_home(tmp_path: Path, monkeypatch) -> Path:
    home = tmp_path / "weft-home"
    monkeypatch.setenv("WEFT_HOME", str(home))
    return home


def entry_names(home: Path) -> list[str]:
    return [p.name for p in load_registry(home / "projects.json").projects]


# ---------- add ----------

def test_add_registers_with_default_name(tmp_path, monkeypatch):
    home = make_home(tmp_path, monkeypatch)
    project = make_minimal_project(tmp_path / "my-paper")
    result = runner.invoke(app, ["projects", "add", str(project)])
    assert result.exit_code == 0, result.output
    assert "已登记 my-paper" in result.output
    assert entry_names(home) == ["my-paper"]


def test_add_name_override(tmp_path, monkeypatch):
    home = make_home(tmp_path, monkeypatch)
    project = make_minimal_project(tmp_path / "dir-name")
    result = runner.invoke(app, ["projects", "add", str(project), "--name", "别名"])
    assert result.exit_code == 0, result.output
    assert entry_names(home) == ["别名"]


def test_add_rejects_non_project(tmp_path, monkeypatch):
    make_home(tmp_path, monkeypatch)
    empty = tmp_path / "empty"
    empty.mkdir()
    result = runner.invoke(app, ["projects", "add", str(empty)])
    assert result.exit_code == 1
    assert "E-REG-NOT-PROJECT" in result.output
    missing = runner.invoke(app, ["projects", "add", str(tmp_path / "ghost")])
    assert missing.exit_code == 1
    assert "E-REG-NOT-PROJECT" in missing.output


def test_add_duplicate_name_exits_1(tmp_path, monkeypatch):
    make_home(tmp_path, monkeypatch)
    first = make_minimal_project(tmp_path / "first")
    second = make_minimal_project(tmp_path / "second")
    assert runner.invoke(app, ["projects", "add", str(first)]).exit_code == 0
    result = runner.invoke(app, ["projects", "add", str(second), "--name", "first"])
    assert result.exit_code == 1
    assert "E-REG-DUP" in result.output


def test_add_duplicate_path_exits_1(tmp_path, monkeypatch):
    make_home(tmp_path, monkeypatch)
    project = make_minimal_project(tmp_path / "demo")
    assert runner.invoke(app, ["projects", "add", str(project)]).exit_code == 0
    result = runner.invoke(app, ["projects", "add", str(project), "--name", "again"])
    assert result.exit_code == 1
    assert "E-REG-PATH-DUP" in result.output


def test_add_invalid_name_exits_1(tmp_path, monkeypatch):
    make_home(tmp_path, monkeypatch)
    project = make_minimal_project(tmp_path / "demo")
    result = runner.invoke(app, ["projects", "add", str(project), "--name", "a/b"])
    assert result.exit_code == 1
    assert "E-REG-NAME" in result.output
    assert entry_names(tmp_path / "weft-home") == []


# ---------- new ----------

def test_new_creates_and_registers(tmp_path, monkeypatch):
    home = make_home(tmp_path, monkeypatch)
    root = tmp_path / "roots"
    result = runner.invoke(
        app, ["projects", "new", "my-paper", "--root", str(root)])
    assert result.exit_code == 0, result.output
    assert (root / "my-paper" / "weft.yaml").is_file()
    assert (root / "my-paper" / "metadata").is_dir()
    assert entry_names(home) == ["my-paper"]
    # 新建项目立即可通过 validate（init 骨架保证）
    validate = runner.invoke(app, ["validate", str(root / "my-paper")])
    assert validate.exit_code == 0, validate.output


def test_new_uses_configured_default_root(tmp_path, monkeypatch):
    home = make_home(tmp_path, monkeypatch)
    root = tmp_path / "papers"
    assert runner.invoke(app, ["projects", "root", str(root)]).exit_code == 0
    result = runner.invoke(app, ["projects", "new", "via-default"])
    assert result.exit_code == 0, result.output
    assert (root / "via-default" / "weft.yaml").is_file()
    show = runner.invoke(app, ["projects", "root"])
    assert show.exit_code == 0
    assert "配置值" in show.output
    assert root.resolve().as_posix() in show.output


def test_new_falls_back_to_home_when_unset(tmp_path, monkeypatch):
    home = make_home(tmp_path, monkeypatch)
    fake_home = tmp_path / "fake-home"
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    result = runner.invoke(app, ["projects", "new", "homey"])
    assert result.exit_code == 0, result.output
    assert (fake_home / "weft-projects" / "homey" / "weft.yaml").is_file()
    assert entry_names(home) == ["homey"]


def test_new_duplicate_name_zero_write(tmp_path, monkeypatch):
    home = make_home(tmp_path, monkeypatch)
    root = tmp_path / "roots"
    assert runner.invoke(
        app, ["projects", "new", "taken", "--root", str(root)]).exit_code == 0
    other = make_minimal_project(tmp_path / "other")
    assert runner.invoke(app, ["projects", "add", str(other)]).exit_code == 0
    result = runner.invoke(
        app, ["projects", "new", "taken", "--root", str(tmp_path / "elsewhere")])
    assert result.exit_code == 1
    assert "E-REG-DUP" in result.output
    assert not (tmp_path / "elsewhere" / "taken").exists()


def test_new_collision_zero_write(tmp_path, monkeypatch):
    make_home(tmp_path, monkeypatch)
    root = tmp_path / "roots"
    target = root / "busy"
    target.mkdir(parents=True)
    (target / "user-file.txt").write_text("已有内容", encoding="utf-8")
    before = sorted(str(p.relative_to(target)) for p in target.rglob("*"))
    result = runner.invoke(
        app, ["projects", "new", "busy", "--root", str(root)])
    assert result.exit_code == 1
    assert "E-INIT-COLLISION" in result.output
    after = sorted(str(p.relative_to(target)) for p in target.rglob("*"))
    assert before == after
    assert entry_names(tmp_path / "weft-home") == []


def test_new_invalid_name_zero_write(tmp_path, monkeypatch):
    make_home(tmp_path, monkeypatch)
    root = tmp_path / "roots"
    result = runner.invoke(
        app, ["projects", "new", "a/b", "--root", str(root)])
    assert result.exit_code == 1
    assert "E-REG-NAME" in result.output
    assert not root.exists()


# ---------- remove ----------

def test_remove_unregisters_but_keeps_files(tmp_path, monkeypatch):
    home = make_home(tmp_path, monkeypatch)
    project = make_minimal_project(tmp_path / "demo")
    assert runner.invoke(app, ["projects", "add", str(project)]).exit_code == 0
    result = runner.invoke(app, ["projects", "remove", "demo"])
    assert result.exit_code == 0, result.output
    assert "已从注册表摘除 demo" in result.output
    assert "本地文件未删除" in result.output
    assert entry_names(home) == []
    # make_minimal_project 的判据文件原样保留（登记/摘除全程不动项目）
    assert (project / "_quarto.yml").is_file()
    assert (project / "metadata").is_dir()


def test_remove_unknown_exits_1(tmp_path, monkeypatch):
    make_home(tmp_path, monkeypatch)
    result = runner.invoke(app, ["projects", "remove", "ghost"])
    assert result.exit_code == 1
    assert "E-REG-UNKNOWN" in result.output


# ---------- list ----------

def test_list_empty_shows_hint(tmp_path, monkeypatch):
    make_home(tmp_path, monkeypatch)
    result = runner.invoke(app, ["projects", "list"])
    assert result.exit_code == 0
    assert "注册表为空" in result.output
    assert "weft projects add" in result.output


def test_list_shows_ok_and_missing(tmp_path, monkeypatch):
    make_home(tmp_path, monkeypatch)
    project = make_minimal_project(tmp_path / "alive")
    assert runner.invoke(app, ["projects", "add", str(project)]).exit_code == 0
    ghost = make_minimal_project(tmp_path / "ghost")
    assert runner.invoke(app, ["projects", "add", str(ghost)]).exit_code == 0
    for child in ghost.iterdir():
        if child.is_dir():
            import shutil
            shutil.rmtree(child)
        else:
            child.unlink()
    result = runner.invoke(app, ["projects", "list"])
    assert result.exit_code == 0
    assert "alive" in result.output
    assert "ok" in result.output
    assert "ghost" in result.output
    assert "missing" in result.output


def test_root_show_when_unset(tmp_path, monkeypatch):
    make_home(tmp_path, monkeypatch)
    fake_home = tmp_path / "fake-home"
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    result = runner.invoke(app, ["projects", "root"])
    assert result.exit_code == 0
    assert "默认值" in result.output
    assert str(fake_home / "weft-projects") in result.output


# ---------- fail-closed：注册表损坏 ----------

def test_malformed_registry_fails_closed(tmp_path, monkeypatch):
    home = make_home(tmp_path, monkeypatch)
    home.mkdir(parents=True)
    (home / "projects.json").write_text("not json {", encoding="utf-8")
    result = runner.invoke(app, ["projects", "list"])
    assert result.exit_code == 1
    assert "E-REG-MALFORMED" in result.output
