"""weft new 命令组：模板化创建空白叙事 part 与元数据卡片。"""
import frontmatter
import pytest

from weft.scaffold import (
    NewCollisionError,
    NewNameError,
    init_project,
    plan_new_card,
    plan_new_part,
    render_card_template,
    render_part_template,
)

# init 脚手架改造前 _PART_01_MD 的原文（逐字节黄金，防 render_part_template 派生漂移）
_INIT_PART_GOLDEN = """\
---
id: sec-01
section: Introduction
# 节点 = 审阅单位；status 改 approved 后 `weft draft sec-01` 生成草稿。
# nodes 示例（uses 引用元数据卡 id，role 常用 evidence / conclusion）：
# nodes:
# - id: para-01-01
#   purpose: describe
#   uses:
#   - id: fact-01
#     role: evidence
#   logic: 本段叙事策略（给 AI 的行文依据）
#   status: draft
nodes: []
---
part id（sec-01）是 `weft draft` 的寻址单位；正文由生成与拼装流水线产出，不手写在这里。
"""


def test_render_part_template_matches_init_scaffold():
    assert render_part_template("sec-01", "Introduction") == _INIT_PART_GOLDEN


def test_render_part_template_parametrized():
    text = render_part_template("sec-12", "Related Work")
    assert "id: sec-12" in text
    assert "section: Related Work" in text
    assert "# - id: para-12-01" in text
    assert "`weft draft sec-12`" in text
    assert "part id（sec-12）" in text


def test_render_part_template_quotes_yaml_unsafe_section():
    text = render_part_template("sec-02", "Methods: overview")
    assert 'section: "Methods: overview"' in text
    parsed = frontmatter.loads(text)
    assert parsed["section"] == "Methods: overview"


def test_render_part_template_no_digits_defaults_example_nn():
    text = render_part_template("sec-intro", "引言")
    assert "# - id: para-01-01" in text
    assert "section: 引言" in text


def test_render_card_template_roundtrip():
    required = {
        "data": set(),
        "fact": {"data", "statement"},
        "claim": {"claim_type", "statement"},
        "note": set(),
        "method": {"statement", "protocol"},
        "param": {"method"},
    }
    for kind, extra in required.items():
        text = render_card_template(kind, "x-01")
        meta = frontmatter.loads(text)
        assert meta["id"] == "x-01", kind
        assert meta["status"] == "draft", kind
        assert extra <= set(meta.metadata), (kind, sorted(meta.metadata))


# ---------------------------------------------------------------- 规划纯函数

@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "p"
    init_project(root)
    return root


def test_plan_new_part_auto_numbering(project):
    target, pid = plan_new_part(project / "narrative", set(), "02-methods", None)
    assert pid == "sec-01"  # 现有集合无 sec-NN 匹配时从 01 起
    assert target == project / "narrative" / "02-methods" / "part-01.md"


def test_plan_new_part_auto_increments_past_existing(project):
    target, pid = plan_new_part(
        project / "narrative", {"sec-01", "sec-02"}, "01-introduction", None)
    assert pid == "sec-03"
    assert target.name == "part-02.md"  # 章节内已有 part-01.md（init 骨架）


def test_plan_new_part_explicit_id(project):
    target, pid = plan_new_part(
        project / "narrative", {"sec-01"}, "01-introduction", "sec-background")
    assert pid == "sec-background"
    assert target.name == "part-02.md"


def test_plan_new_part_id_collision(project):
    with pytest.raises(NewCollisionError):
        plan_new_part(project / "narrative", {"sec-01"}, "01-introduction", "sec-01")


def test_plan_new_part_file_numbering_skips_nonconforming(project):
    (project / "narrative" / "02-x").mkdir()
    (project / "narrative" / "02-x" / "part-05.md").write_text(
        "---\nid: sec-05\nsection: t\nnodes: []\n---\n", encoding="utf-8")
    target, pid = plan_new_part(project / "narrative", {"sec-05"}, "02-x", None)
    assert pid == "sec-06"
    assert target.name == "part-06.md"  # 文件名编号取现有 part-(\d+).md 的 max+1


@pytest.mark.parametrize("bad", ["../evil", "", "a/b", "a\b", ".", "..", " x", "x ", "x.", ".x", "a:b"])
def test_plan_new_part_bad_chapter(project, bad):
    with pytest.raises(NewNameError):
        plan_new_part(project / "narrative", set(), bad, None)


def test_plan_new_part_blank_explicit_id(project):
    with pytest.raises(NewNameError):
        plan_new_part(project / "narrative", set(), "02-x", "   ")


def test_plan_new_card_targets(project):
    from weft.scaffold import CARD_KIND_DIRS

    for kind, directory in CARD_KIND_DIRS.items():
        target = plan_new_card(project, set(), kind, "x-01")
        assert target == project / directory / "x-01.md"


def test_plan_new_card_id_collision(project):
    with pytest.raises(NewCollisionError):
        plan_new_card(project, {"fact-01"}, "fact", "fact-01")


@pytest.mark.parametrize("bad", ["", "a/b", "..", ".hid", "x.", "a:b"])
def test_plan_new_card_bad_id(project, bad):
    with pytest.raises(NewNameError):
        plan_new_card(project, set(), "fact", bad)


# ---------------------------------------------------------------- CLI

from typer.testing import CliRunner

from weft.cli import app
from weft.store.loader import load_project
from weft.validation import validate_project

runner = CliRunner()


def _load(root):
    return load_project(root)


def test_cli_new_part_success(project):
    result = runner.invoke(app, ["new", "part", "02-methods", "Methods", str(project)])
    assert result.exit_code == 0, result.output
    assert "已创建 narrative/02-methods/part-01.md" in result.output
    assert (project / "narrative" / "02-methods" / "part-01.md").is_file()
    project2, diags = _load(project)
    # auto id 全局编号：init 骨架已有 sec-01，新 part 拿 sec-02（文件名才是章节内编号）
    part = next(p for p in project2.parts if p.id == "sec-02")
    assert part.section == "Methods"
    assert not [d for d in diags if d.is_error]


def test_cli_new_part_auto_numbering_in_existing_chapter(project):
    result = runner.invoke(app, ["new", "part", "01-introduction", "背景", str(project)])
    assert result.exit_code == 0, result.output
    assert (project / "narrative" / "01-introduction" / "part-02.md").is_file()
    project2, _ = _load(project)
    assert {p.id for p in project2.parts} == {"sec-01", "sec-02"}


def test_cli_new_part_explicit_id(project):
    result = runner.invoke(
        app, ["new", "part", "02-methods", "Methods", "--id", "sec-methods", str(project)])
    assert result.exit_code == 0, result.output
    project2, _ = _load(project)
    assert any(p.id == "sec-methods" for p in project2.parts)


def test_cli_new_part_id_collision_exit_1(project):
    result = runner.invoke(
        app, ["new", "part", "01-introduction", "X", "--id", "sec-01", str(project)])
    assert result.exit_code == 1
    assert "E-NEW-COLLISION" in result.output


@pytest.mark.parametrize("bad", ["../evil", "a/b", ""])
def test_cli_new_part_bad_chapter_exit_1(project, bad):
    result = runner.invoke(app, ["new", "part", bad, "X", str(project)])
    assert result.exit_code == 1
    assert "E-NEW-NAME" in result.output


def test_cli_new_card_all_kinds(project):
    from weft.scaffold import CARD_KIND_DIRS

    ids = {"data": "data-01", "fact": "fact-01", "claim": "claim-01",
           "note": "smith2020", "method": "method-dft", "param": "param-dft"}
    for kind, cid in ids.items():
        result = runner.invoke(app, ["new", "card", kind, cid, str(project)])
        assert result.exit_code == 0, (kind, result.output)
        assert (project / CARD_KIND_DIRS[kind] / f"{cid}.md").is_file()
    project2, _ = _load(project)
    assert project2.data_cards["data-01"].status == "draft"
    assert project2.claims["claim-01"].claim_type == "uncited"
    assert "smith2020" in project2.notes
    # 文件名 = id（loader 的 E-FILENAME-MISMATCH 无诊断即一致）
    names = {p.name for p in (project / "metadata").rglob("*.md")}
    assert "fact-01.md" in names and "smith2020.md" in names


def test_cli_new_card_fact_stub_yields_one_eparse(project):
    runner.invoke(app, ["new", "card", "fact", "fact-09", str(project)])
    _, diags = _load(project)
    errors = [d for d in diags if d.is_error]
    assert len(errors) == 1
    assert errors[0].code == "E-PARSE"
    assert errors[0].field == "data"


def test_cli_new_card_param_stub_yields_dangling(project):
    runner.invoke(app, ["new", "card", "param", "param-01", str(project)])
    project2, diags = _load(project)
    diags = diags + validate_project(project2)
    assert any(d.code == "E-DANGLING-REF" and d.field == "method" for d in diags)


def test_cli_new_card_data_stub_clean(project):
    runner.invoke(app, ["new", "card", "data", "data-01", str(project)])
    project2, diags = _load(project)
    diags = diags + validate_project(project2)
    assert not [d for d in diags if d.is_error]


def test_cli_new_card_note_stub_yields_not_in_bib(project):
    runner.invoke(app, ["new", "card", "note", "key2020", str(project)])
    project2, diags = _load(project)
    diags = diags + validate_project(project2)
    assert any(d.code == "E-NOTE-NOT-IN-BIB" and d.field == "id" for d in diags)


def test_cli_new_card_id_collision_exit_1(project):
    runner.invoke(app, ["new", "card", "data", "data-01", str(project)])
    result = runner.invoke(app, ["new", "card", "fact", "data-01", str(project)])
    assert result.exit_code == 1
    assert "E-NEW-COLLISION" in result.output


def test_cli_new_card_bad_id_exit_1(project):
    result = runner.invoke(app, ["new", "card", "fact", "a/b", str(project)])
    assert result.exit_code == 1
    assert "E-NEW-NAME" in result.output


def test_cli_new_card_unknown_kind_rejected(project):
    result = runner.invoke(app, ["new", "card", "story", "s-01", str(project)])
    assert result.exit_code != 0
