"""M1 验收：样例项目跑通三条命令，graph 产物与黄金文件一致。"""
import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from weft.cli import app

runner = CliRunner()
SAMPLE = Path(__file__).parent.parent / "examples" / "paper-demo"
GOLDEN = Path(__file__).parent / "golden"


def _copy_sample(tmp_path: Path) -> Path:
    work = tmp_path / "proj"
    shutil.copytree(SAMPLE, work)
    return work


def test_sample_validates_clean(tmp_path):
    work = _copy_sample(tmp_path)
    result = runner.invoke(app, ["validate", str(work)])
    assert result.exit_code == 0, result.output
    assert "0 个错误，0 个提醒" in result.output


def test_sample_graph_matches_golden(tmp_path):
    work = _copy_sample(tmp_path)
    result = runner.invoke(app, ["graph", str(work)])
    assert result.exit_code == 0, result.output
    for name in ("graph.json", "used-metadata.json"):
        actual = json.loads((work / "generated" / name).read_text(encoding="utf-8"))
        golden = json.loads((GOLDEN / name).read_text(encoding="utf-8"))
        assert actual == golden, name


def test_sample_review_lists_drafts(tmp_path):
    work = _copy_sample(tmp_path)
    result = runner.invoke(app, ["review", str(work)])
    assert result.exit_code == 0, result.output
    assert "claim-03" in result.output
    assert "sec-03/para-03-02" in result.output
    assert "sec-04/para-04-02" in result.output
