"""weft show：卡片速览（语义字段全文 + 被引用关系）。"""
from typer.testing import CliRunner

from weft.cli import app
from tests.helpers import make_minimal_project, write_card

runner = CliRunner()


def test_show_prints_card_overview(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["show", "fact-01", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "# fact-01（fact 卡，approved）— metadata/facts/fact-01.md" in result.output
    assert "statement: 温度提高速率。" in result.output
    assert "data: data-01" in result.output
    assert "supports: claim-01" in result.output
    assert "被引用:" in result.output
    assert "nodes: para-01-01" in result.output


def test_show_without_backrefs(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "data", "data-02",
               {"id": "data-02", "refs": [], "status": "draft"})
    result = runner.invoke(app, ["show", "data-02", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "被引用: （无）" in result.output


def test_show_unknown_id_exits_1(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["show", "ghost", str(tmp_path)])
    assert result.exit_code == 1
    assert "ERROR 项目中不存在实体：ghost" in result.output


def test_show_reports_load_errors(tmp_path):
    result = runner.invoke(app, ["show", "x", str(tmp_path)])
    assert result.exit_code == 1
    assert "E-NOT-A-PROJECT" in result.output
