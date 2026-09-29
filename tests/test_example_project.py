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
    # v1.1 §7 回归：样例迁移后 draft --mock/assemble 链路（validate/graph 由兄弟测试覆盖）
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
    paper = (work / "paper.qmd").read_text(encoding="utf-8")
    assert "# References {.unnumbered}" in paper and "# Figures {.unnumbered}" in paper


def test_sample_assemble_paper_qmd_matches_golden(tmp_path):
    # M3 验收：正文 + References + Figures/Tables 三部分、字节确定（黄金比对；
    # golden 侧做 CRLF→LF 归一，防 Windows autocrlf 检出差异）
    work = _copy_sample(tmp_path)
    (work / "drafts").mkdir()
    (work / "drafts" / "sec-03.md").write_text(
        "<!-- weft:node=para-03-01 uses=fact-01 -->\n"
        "60 °C 的初始反应速率比 25 °C 高 42%（[@smith2020]）。\n", encoding="utf-8")
    (work / "drafts" / "sec-04.md").write_text(
        "<!-- weft:node=para-04-01 -->\n结果与热激活催化机制的解释一致。\n",
        encoding="utf-8")
    result = runner.invoke(app, ["assemble", str(work)])
    assert result.exit_code == 0, result.output
    raw = (work / "paper.qmd").read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    golden = (GOLDEN / "paper.qmd").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert raw.decode("utf-8") == golden


def test_paper_demo_is_managed_with_generated_bib():
    from weft import bibgen
    from weft.store.loader import load_project
    project, diags = load_project(SAMPLE)
    assert project.bib_managed is True
    bib_text = (SAMPLE / "assets" / "references.bib").read_text(encoding="utf-8")
    assert bib_text.startswith("%")            # 生成物头注释
    assert bib_text == bibgen.render_bib(project)   # 与真源字节一致（不 stale）


def test_paper_demo_bib_keys_unchanged():
    from weft.store.loader import load_project
    project, diags = load_project(SAMPLE)
    assert project.bib_keys == {"smith2020", "doe2021"}
    assert not any(d.is_error for d in diags)
