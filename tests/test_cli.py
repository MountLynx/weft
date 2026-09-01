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


def test_graph_blocked_by_errors(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "notes", "ghostkey",
               {"id": "ghostkey", "summary": "s", "status": "draft"})
    result = runner.invoke(app, ["graph", str(tmp_path)])
    assert result.exit_code == 1
    assert "E-NOTE-NOT-IN-BIB" in result.output
    assert "拒绝生成" in result.output
    assert not (tmp_path / "generated").exists()  # 错误路径连目录都不该建


def test_graph_writes_outputs(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["graph", str(tmp_path)])
    assert result.exit_code == 0, result.output
    for name in ("graph.json", "used-metadata.json", "orphans.md"):
        assert (tmp_path / "generated" / name).exists()
    assert "generated/graph.json" in result.output
    assert "generated/used-metadata.json" in result.output
    assert "generated/orphans.md" in result.output


def test_graph_prints_warnings_after_writes(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "claims" / "cited", "claim-02",
               {"id": "claim-02", "claim_type": "cited", "statement": "s",
                "status": "draft"})
    result = runner.invoke(app, ["graph", str(tmp_path)])
    assert result.exit_code == 0, result.output
    warn_pos = result.output.index("W-CLAIM-CITED-NO-CITES")
    write_pos = result.output.index("已写入 generated/orphans.md")
    assert write_pos < warn_pos


def test_graph_generated_occupied_by_file(tmp_path):
    make_minimal_project(tmp_path)
    (tmp_path / "generated").write_text("占位", encoding="utf-8")
    result = runner.invoke(app, ["graph", str(tmp_path)])
    assert result.exit_code == 1
    assert "无法写入" in result.output


def test_review_lists_draft_items(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "data", "data-02",
               {"id": "data-02", "refs": [], "status": "draft"})
    result = runner.invoke(app, ["review", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "data-02" in result.output
    assert "metadata/data/data-02.md" in result.output
    # approved 的叙事节点不出现
    assert "para-01-01" not in result.output


def test_review_empty_when_all_approved(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["review", str(tmp_path)])
    assert result.exit_code == 0
    assert "（无）" in result.output


def test_review_reports_load_errors(tmp_path):
    # 非项目目录：加载失败直接报错退出
    result = runner.invoke(app, ["review", str(tmp_path)])
    assert result.exit_code == 1
    assert "E-NOT-A-PROJECT" in result.output
