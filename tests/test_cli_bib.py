"""weft bib sync（bibgen 设计 §5 CLI）。"""
from typer.testing import CliRunner

from weft import bibgen
from weft.cli import app
from weft.store.loader import load_project
from tests.helpers import (
    make_managed_project,
    make_minimal_project,
    write_card,
    write_yaml,
)

runner = CliRunner()


def _fresh_bib(root):
    project, _ = load_project(root)
    (root / "references.bib").write_text(bibgen.render_bib(project), encoding="utf-8")


def test_sync_rejects_unmanaged(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["bib", "sync", str(tmp_path)])
    assert result.exit_code == 1 and "bib.managed" in result.output


def test_sync_writes_managed_bib(tmp_path):
    make_managed_project(tmp_path)
    result = runner.invoke(app, ["bib", "sync", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "已写入 references.bib（1 条" in result.output
    content = (tmp_path / "references.bib").read_text(encoding="utf-8")
    assert content.startswith("%") and "@article{key2020" in content


def test_check_stale_exits_1(tmp_path):
    make_managed_project(tmp_path)
    _fresh_bib(tmp_path)
    with open(tmp_path / "references.bib", "a", encoding="utf-8") as f:
        f.write("% 手改\n")
    result = runner.invoke(app, ["bib", "sync", str(tmp_path), "--check"])
    assert result.exit_code == 1 and "W-BIB-STALE" in result.output


def test_check_fresh_exits_0(tmp_path):
    make_managed_project(tmp_path)
    _fresh_bib(tmp_path)
    result = runner.invoke(app, ["bib", "sync", str(tmp_path), "--check"])
    assert result.exit_code == 0 and "一致（1 条）" in result.output


def test_sync_value_error_exits_1_without_write(tmp_path):
    make_managed_project(tmp_path)
    write_card(tmp_path / "metadata" / "notes", "key2020",
               {"id": "key2020", "summary": "s", "status": "approved",
                "entry": {"type": "article", "title": "{T", "year": 2020}})
    before = (tmp_path / "references.bib").read_text(encoding="utf-8")
    result = runner.invoke(app, ["bib", "sync", str(tmp_path)])
    assert result.exit_code == 1 and "E-BIB-VALUE" in result.output
    assert (tmp_path / "references.bib").read_text(encoding="utf-8") == before


def test_sync_bootstraps_missing_bib(tmp_path):
    """managed 项目 bib 文件缺失：sync 负责创建而非被 load 闸挡死（T6 质量审查）。"""
    make_managed_project(tmp_path)
    (tmp_path / "references.bib").unlink()
    result = runner.invoke(app, ["bib", "sync", str(tmp_path)])
    assert result.exit_code == 0, result.output
    content = (tmp_path / "references.bib").read_text(encoding="utf-8")
    assert content.startswith("%") and "@article{key2020" in content


def test_sync_shape_error_two_files(tmp_path):
    make_managed_project(tmp_path)
    (tmp_path / "manual.bib").write_text("@article{x1,\n title = {X},\n year = {1},\n}\n",
                                         encoding="utf-8")
    write_yaml(tmp_path / "_quarto.yml",
               {"project": {"type": "default"},
                "bibliography": ["references.bib", "manual.bib"]})
    result = runner.invoke(app, ["bib", "sync", str(tmp_path)])
    assert result.exit_code == 1 and "E-BIB-SHAPE" in result.output


def test_sync_reports_bib_cfg_error(tmp_path):
    make_managed_project(tmp_path)
    write_yaml(tmp_path / "weft.yaml", {"bib": {"managed": True, "maneged": False}})
    result = runner.invoke(app, ["bib", "sync", str(tmp_path)])
    assert result.exit_code == 1 and "E-BIB-SHAPE" in result.output


def test_check_missing_bib_exits_1_clean(tmp_path):
    """--check 不负责创建：缺文件时报 E-BIB-MISSING 而非崩溃（T6 质量审查补充）。"""
    make_managed_project(tmp_path)
    (tmp_path / "references.bib").unlink()
    result = runner.invoke(app, ["bib", "sync", str(tmp_path), "--check"])
    assert result.exit_code == 1 and "E-BIB-MISSING" in result.output
    assert type(result.exception) is SystemExit  # 清洁退出而非 traceback 崩溃
