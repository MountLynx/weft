"""weft draft 命令：校验闸门、节查找、mock 端到端。"""
from typer.testing import CliRunner

from weft.cli import app
from tests.helpers import make_minimal_project, write_card

runner = CliRunner()


def test_draft_section_not_found(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["draft", "sec-99", str(tmp_path)])
    assert result.exit_code == 1
    assert "E-SECTION-NOT-FOUND" in result.output


def test_draft_nothing_approved(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "narrative", "02-intro",
               {"id": "sec-02", "section": "Intro", "order": 2,
                "nodes": [{"id": "para-02-01", "purpose": "describe",
                           "uses": [], "status": "draft"}]})
    result = runner.invoke(app, ["draft", "sec-02", str(tmp_path)])
    assert result.exit_code == 1
    assert "E-NOTHING-TO-DRAFT" in result.output


def test_draft_validation_errors_block(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "facts", "fact-02",
               {"id": "fact-02", "data": ["data-99"], "statement": "s",
                "status": "draft"})
    result = runner.invoke(app, ["draft", "sec-01", str(tmp_path)])
    assert result.exit_code == 1
    assert "拒绝生成" in result.output
    assert not (tmp_path / "drafts" / "sec-01.md").exists()


def test_draft_mock_writes_traceable_file(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["draft", "sec-01", "--mock", str(tmp_path)])
    assert result.exit_code == 0, result.output
    out = (tmp_path / "drafts" / "sec-01.md").read_text(encoding="utf-8")
    assert "<!-- weft:run=" in out
    assert "<!-- weft:node=para-01-01 uses=fact-01 -->" in out
    assert "（mock 段落）正文。" in out
    assert "已写入 drafts/sec-01.md" in result.output


def test_draft_mock_no_align_flag(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["draft", "sec-01", "--mock", "--no-align",
                                 str(tmp_path)])
    assert result.exit_code == 0, result.output


def test_draft_skips_non_approved_nodes(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "narrative", "01-results",
               {"id": "sec-01", "section": "Results", "order": 1,
                "nodes": [
                    {"id": "para-01-01", "purpose": "describe",
                     "uses": [{"id": "fact-01", "role": "evidence"}],
                     "status": "approved"},
                    {"id": "para-01-02", "purpose": "interpret",
                     "uses": [{"id": "claim-01", "role": "conclusion"}],
                     "status": "draft"},
                ]})
    result = runner.invoke(app, ["draft", "sec-01", "--mock", str(tmp_path)])
    assert result.exit_code == 0, result.output
    out = (tmp_path / "drafts" / "sec-01.md").read_text(encoding="utf-8")
    assert "para-01-01" in out
    assert "para-01-02" not in out
