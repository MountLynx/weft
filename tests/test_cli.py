from typer.testing import CliRunner

from weft.cli import app
from tests.helpers import make_minimal_project, write_card

runner = CliRunner()


def test_validate_clean_project(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["validate", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "0 个错误，0 个提醒" in result.output


def test_validate_error_exits_1(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "facts", "fact-02",
               {"id": "fact-02", "data": ["data-99"], "statement": "s",
                "status": "draft"})
    result = runner.invoke(app, ["validate", str(tmp_path)])
    assert result.exit_code == 1
    assert "E-DANGLING-REF" in result.output
    assert "1 个错误" in result.output


def test_validate_warning_only_exits_0(tmp_path):
    make_minimal_project(tmp_path)
    # claim-02：cited 且 cites 空 → 纯提醒
    write_card(tmp_path / "metadata" / "claims" / "cited", "claim-02",
               {"id": "claim-02", "claim_type": "cited", "statement": "s",
                "status": "draft"})
    result = runner.invoke(app, ["validate", str(tmp_path)])
    assert result.exit_code == 0
    assert "W-CLAIM-CITED-NO-CITES" in result.output
    assert "0 个错误" in result.output


def test_validate_not_a_project(tmp_path):
    result = runner.invoke(app, ["validate", str(tmp_path)])
    assert result.exit_code == 1
    assert "E-NOT-A-PROJECT" in result.output
    assert "1 个错误，0 个提醒" in result.output
