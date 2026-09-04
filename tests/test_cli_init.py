"""weft init CLI（M4）：从零创建项目骨架。"""
from typer.testing import CliRunner

from weft.cli import app

runner = CliRunner()


def test_cli_init_then_validate(tmp_path):
    target = tmp_path / "demo"
    result = runner.invoke(app, ["init", str(target)])
    assert result.exit_code == 0, result.output
    assert "已创建" in result.output
    assert result.output.count("已创建 ") == 7  # 7 个骨架文件，目录不逐行打印
    validate_result = runner.invoke(app, ["validate", str(target)])
    assert validate_result.exit_code == 0, validate_result.output
    assert "0 个错误，0 个提醒" in validate_result.output


def test_cli_init_nonempty_dir_exits_1(tmp_path):
    target = tmp_path / "demo"
    target.mkdir()
    (target / "user-file.txt").write_text("已有内容", encoding="utf-8")
    result = runner.invoke(app, ["init", str(target)])
    assert result.exit_code == 1
    assert "E-INIT-COLLISION" in result.output
    assert not (target / "_quarto.yml").exists()


def test_cli_init_default_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "_quarto.yml").is_file()
    assert (tmp_path / "narrative" / "01-introduction" / "part-01.md").is_file()
