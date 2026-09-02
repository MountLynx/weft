"""weft assemble 命令：校验闸门、strict 报错、lenient 配置、端到端写入。"""
from typer.testing import CliRunner

from weft.cli import app
from tests.helpers import make_minimal_project, write_card, write_yaml

runner = CliRunner()


def _approved_draft(tmp_path) -> None:
    make_minimal_project(tmp_path)
    (tmp_path / "drafts").mkdir()
    (tmp_path / "drafts" / "sec-01.md").write_text(
        "<!-- weft:node=para-01-01 uses=fact-01 -->\n第一段正文。\n", encoding="utf-8")


def test_assemble_writes_part_and_chapter_qmd(tmp_path):
    _approved_draft(tmp_path)
    result = runner.invoke(app, ["assemble", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "generated/01-results/part-01.qmd" in result.output
    assert "generated/01-results.qmd" in result.output
    assert "已写入 paper.qmd" in result.output


def test_assemble_strict_missing_draft_exits_1(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["assemble", str(tmp_path)])
    assert result.exit_code == 1
    assert "E-ASSEMBLE-MISSING-DRAFT" in result.output
    assert not (tmp_path / "generated").exists()


def test_assemble_lenient_via_weft_yaml(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "narrative" / "01-results", "part-01",
               {"id": "sec-01", "section": "Results",
                "nodes": [
                    {"id": "para-01-01", "purpose": "describe",
                     "uses": [{"id": "fact-01", "role": "evidence"}],
                     "status": "approved"},
                    {"id": "para-01-02", "purpose": "interpret", "uses": [],
                     "status": "approved"}]})
    (tmp_path / "drafts").mkdir()
    (tmp_path / "drafts" / "sec-01.md").write_text(
        "<!-- weft:node=para-01-01 -->\n只有第一段。\n", encoding="utf-8")
    write_yaml(tmp_path / "weft.yaml", {"assemble_mode": "lenient"})
    result = runner.invoke(app, ["assemble", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "generated" / "01-results" / "part-01.qmd").exists()


def test_assemble_blocked_by_validation_errors(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "facts", "fact-02",
               {"id": "fact-02", "data": ["data-99"], "statement": "s",
                "status": "draft"})
    result = runner.invoke(app, ["assemble", str(tmp_path)])
    assert result.exit_code == 1
    assert "拒绝拼装" in result.output
