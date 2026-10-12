"""weft rename：一条命令改名 + 冲突审查 + 全部位点同步。"""
from typer.testing import CliRunner

from weft.cli import app
from tests.helpers import make_minimal_project, write_card

runner = CliRunner()


def test_rename_success_syncs_references(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["rename", "fact-01", "temp-rate", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "改写计划：" in result.output
    assert "重命名  metadata/facts/fact-01.md → metadata/facts/temp-rate.md" in result.output
    assert "narrative/01-results/part-01.md（uses 1 处）" in result.output
    assert "✓ 2 个文件已更新" in result.output
    assert (tmp_path / "metadata" / "facts" / "temp-rate.md").exists()
    assert not (tmp_path / "metadata" / "facts" / "fact-01.md").exists()


def test_rename_dry_run_writes_nothing(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["rename", "fact-01", "temp-rate",
                                 str(tmp_path), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "(dry-run，未写入)" in result.output
    assert (tmp_path / "metadata" / "facts" / "fact-01.md").exists()
    assert not (tmp_path / "metadata" / "facts" / "temp-rate.md").exists()


def test_rename_collision_exits_1(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["rename", "fact-01", "claim-01", str(tmp_path)])
    assert result.exit_code == 1
    assert "E-NEW-COLLISION" in result.output
    assert (tmp_path / "metadata" / "facts" / "fact-01.md").exists()


def test_rename_unsafe_name_exits_1(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["rename", "fact-01", "../x", str(tmp_path)])
    assert result.exit_code == 1
    assert "E-NEW-NAME" in result.output
    assert (tmp_path / "metadata" / "facts" / "fact-01.md").exists()


def test_rename_unknown_old_exits_1(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["rename", "ghost", "x", str(tmp_path)])
    assert result.exit_code == 1
    assert "ERROR 项目里不存在卡片：ghost" in result.output


def test_rename_load_error_refuses(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "facts", "broken",
               {"id": "broken", "data": [], "statement": "s", "status": "draft"})
    result = runner.invoke(app, ["rename", "fact-01", "temp-rate", str(tmp_path)])
    assert result.exit_code == 1
    assert "E-PARSE" in result.output
    assert (tmp_path / "metadata" / "facts" / "fact-01.md").exists()
    assert not (tmp_path / "metadata" / "facts" / "temp-rate.md").exists()
