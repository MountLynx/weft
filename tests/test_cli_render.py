"""weft render 命令：默认参数与 paper_file 传参、--to 透传、错误退出码、加载闸门。"""
from typer.testing import CliRunner

from weft.cli import app
from weft.render import QuartoNotFoundError, QuartoRenderError
from tests.helpers import make_minimal_project, write_yaml

runner = CliRunner()


def test_render_invokes_wrapper_with_defaults(monkeypatch, tmp_path):
    make_minimal_project(tmp_path)
    seen = {}

    def fake_render(root, *, paper_file, to):
        seen["root"] = root
        seen["paper_file"] = paper_file
        seen["to"] = to
        return root / "paper.docx"

    monkeypatch.setattr("weft.render.render_paper", fake_render)
    result = runner.invoke(app, ["render", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "已生成 paper.docx" in result.output
    assert seen["paper_file"] == "paper.qmd"
    assert seen["to"] == "docx"
    assert seen["root"] == tmp_path.resolve()   # load_project 内部 resolve


def test_render_uses_paper_file_config(monkeypatch, tmp_path):
    make_minimal_project(tmp_path)
    write_yaml(tmp_path / "weft.yaml", {"paper_file": "manuscript.qmd"})
    seen = {}

    def fake_render(root, *, paper_file, to):
        seen["paper_file"] = paper_file
        return root / "manuscript.docx"

    monkeypatch.setattr("weft.render.render_paper", fake_render)
    result = runner.invoke(app, ["render", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert seen["paper_file"] == "manuscript.qmd"


def test_render_to_option_passthrough(monkeypatch, tmp_path):
    make_minimal_project(tmp_path)
    seen = {}

    def fake_render(root, *, paper_file, to):
        seen["to"] = to
        return root / "paper.html"

    monkeypatch.setattr("weft.render.render_paper", fake_render)
    result = runner.invoke(app, ["render", "--to", "html", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert seen["to"] == "html"


def test_render_quarto_missing_exits_1(monkeypatch, tmp_path):
    make_minimal_project(tmp_path)

    def fake_render(root, *, paper_file, to):
        raise QuartoNotFoundError("未找到 quarto 可执行文件")

    monkeypatch.setattr("weft.render.render_paper", fake_render)
    result = runner.invoke(app, ["render", str(tmp_path)])
    assert result.exit_code == 1
    assert "ERROR 未找到 quarto 可执行文件" in result.output


def test_render_error_exits_1_with_detail(monkeypatch, tmp_path):
    make_minimal_project(tmp_path)

    def fake_render(root, *, paper_file, to):
        raise QuartoRenderError("quarto render 失败（退出码 1）：boom")

    monkeypatch.setattr("weft.render.render_paper", fake_render)
    result = runner.invoke(app, ["render", str(tmp_path)])
    assert result.exit_code == 1
    assert "boom" in result.output


def test_render_load_errors_exits_1(tmp_path):
    result = runner.invoke(app, ["render", str(tmp_path)])
    assert result.exit_code == 1
    assert "E-NOT-A-PROJECT" in result.output
