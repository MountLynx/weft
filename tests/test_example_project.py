"""M1 验收：样例项目跑通三条命令，graph 产物与黄金文件一致。"""
import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from weft.cli import app
from tests.helpers import write_yaml

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


def test_sample_draft_mock_end_to_end(tmp_path):
    work = _copy_sample(tmp_path)
    result = runner.invoke(app, ["draft", "sec-03", "--mock", str(work)])
    assert result.exit_code == 0, result.output
    out = (work / "drafts" / "sec-03.md").read_text(encoding="utf-8")
    assert "<!-- weft:node=para-03-01 uses=fact-01,claim-01 -->" in out
    assert "para-03-02" not in out        # draft 节点不生成


def test_sample_draft_then_assemble_full_chain(tmp_path):
    # v1.1 §7 回归：样例迁移后 validate/graph/draft --mock/assemble 全链路
    work = _copy_sample(tmp_path)
    assert runner.invoke(app, ["draft", "sec-03", "--mock", str(work)]).exit_code == 0
    # sec-04 的 para-04-01 approved 但无草稿 → strict 会报错；lenient 跳过
    write_yaml(work / "weft.yaml", {"assemble_mode": "lenient"})
    result = runner.invoke(app, ["assemble", str(work)])
    assert result.exit_code == 0, result.output
    part_qmd = work / "generated" / "03-results" / "part-01.qmd"
    assert part_qmd.exists()
    merged = (work / "generated" / "03-results.qmd").read_text(encoding="utf-8")
    assert "# results" in merged and "## Results" in merged
