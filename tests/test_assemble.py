"""assemble：part qmd 拼装、目录序合并、heading 层级映射（v1.1 §4.4）。"""
from pathlib import Path

from weft.assemble import assemble_project
from weft.assemble.parts import assemble_part, parse_draft_paragraphs
from weft.models.narrative import NarrativePart, Node
from weft.store.loader import load_project
from tests.helpers import write_card


def _tree_project(tmp_path: Path) -> None:
    # metadata/ 必须存在，否则 load_project 报 E-NOT-A-PROJECT；assemble 不跑校验，
    # 一张 data 卡足够让项目成立且加载诊断干净
    write_card(tmp_path / "metadata" / "data", "data-01",
               {"id": "data-01", "refs": [], "status": "approved"})
    write_card(tmp_path / "narrative" / "01-results" / "01-startup", "part-01",
               {"id": "sec-01", "section": "SNDPR 启动性能",
                "nodes": [{"id": "para-01-01", "purpose": "describe", "uses": [],
                           "status": "approved"}]})


def test_parse_draft_paragraphs_extracts_nodes():
    text = ("<!-- weft:run=ab part=sec-01 -->\n\n"
            "<!-- weft:node=para-01-01 uses=fact-01 -->\n第一段。\n\n"
            "<!-- weft:node=para-01-02 -->\n第二段。\n")
    assert parse_draft_paragraphs(text) == {"para-01-01": "第一段。",
                                            "para-01-02": "第二段。"}


def test_assemble_part_heading_level_and_skips_unapproved():
    part = NarrativePart(id="sec-01", section="启动性能", nodes=[
        Node(id="para-01-01", purpose="describe", status="approved"),
        Node(id="para-01-02", purpose="describe", status="draft"),
    ])
    qmd = assemble_part(part, {"para-01-01": "第一段。"}, heading_level=3)
    assert qmd == "### 启动性能\n\n第一段。\n"


def test_assemble_part_empty_returns_none():
    part = NarrativePart(id="sec-01", section="T", nodes=[
        Node(id="para-01-01", purpose="describe", status="draft")])
    assert assemble_part(part, {}, heading_level=2) is None


def test_assemble_project_writes_tree_and_chapter_merge(tmp_path):
    _tree_project(tmp_path)
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    (drafts / "sec-01.md").write_text(
        "<!-- weft:run=ab part=sec-01 -->\n\n"
        "<!-- weft:node=para-01-01 uses=fact-01 -->\n第一段正文。\n",
        encoding="utf-8")
    project, diagnostics = load_project(tmp_path)
    assert diagnostics == []
    written, asm_diags = assemble_project(project)
    assert asm_diags == []
    # part 标题级别 = 目录深度+1（两级目录 → ###）；chapter 合并按目录序补 #/##
    assert [p.relative_to(tmp_path).as_posix() for p in written] == [
        "generated/01-results/01-startup/part-01.qmd",
        "generated/01-results.qmd"]
    part_qmd = tmp_path / "generated" / "01-results" / "01-startup" / "part-01.qmd"
    assert part_qmd.read_text(encoding="utf-8") == "### SNDPR 启动性能\n\n第一段正文。\n"
    merged = (tmp_path / "generated" / "01-results.qmd").read_text(encoding="utf-8")
    assert merged == ("# results\n\n## startup\n\n"
                      "### SNDPR 启动性能\n\n第一段正文。\n\n")
    raw = part_qmd.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")


def test_strict_missing_draft_errors_and_writes_nothing(tmp_path):
    # 混合夹具：sec-01 两个 approved 节点（para-01-01 有草段、para-01-02 缺），
    # 健康 sec-02 照常拼装——钉住 strict 报首缺节点、sec-01 整体跳过、其余 part 照常
    write_card(tmp_path / "metadata" / "data", "data-01",
               {"id": "data-01", "refs": [], "status": "approved"})
    write_card(tmp_path / "narrative" / "01-results" / "01-startup", "part-01",
               {"id": "sec-01", "section": "SNDPR 启动性能",
                "nodes": [
                    {"id": "para-01-01", "purpose": "describe", "uses": [],
                     "status": "approved"},
                    {"id": "para-01-02", "purpose": "interpret", "uses": [],
                     "status": "approved"}]})
    write_card(tmp_path / "narrative" / "01-results", "part-02",
               {"id": "sec-02", "section": "总览",
                "nodes": [{"id": "para-02-01", "purpose": "describe", "uses": [],
                           "status": "approved"}]})
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    (drafts / "sec-01.md").write_text(
        "<!-- weft:node=para-01-01 -->\n第一段有草稿。\n", encoding="utf-8")
    (drafts / "sec-02.md").write_text(
        "<!-- weft:node=para-02-01 -->\n健康段落。\n", encoding="utf-8")
    project, _ = load_project(tmp_path)
    written, asm_diags = assemble_project(project, mode="strict")
    assert [d.code for d in asm_diags] == ["E-ASSEMBLE-MISSING-DRAFT"]
    assert asm_diags[0].path == "narrative/01-results/01-startup/part-01.md"
    assert asm_diags[0].field == "para-01-02"   # 首个缺段节点，而非有草稿的那个
    assert written == [tmp_path / "generated" / "01-results" / "part-02.qmd",
                       tmp_path / "generated" / "01-results.qmd"]
    # sec-01 整体跳过：无 part qmd、chapter 合并无其子节标题
    assert not (tmp_path / "generated" / "01-results" / "01-startup").exists()
    merged = (tmp_path / "generated" / "01-results.qmd").read_text(encoding="utf-8")
    assert merged == "# results\n\n## 总览\n\n健康段落。\n\n"


def test_lenient_missing_draft_assembles_available_paragraphs(tmp_path):
    # v1 §7 语义：lenient 只跳缺段节点；part 标题级别 = 单层目录 +1 → ##
    write_card(tmp_path / "metadata" / "data", "data-01",
               {"id": "data-01", "refs": [], "status": "approved"})
    write_card(tmp_path / "narrative" / "01-results", "part-01",
               {"id": "sec-01", "section": "结果",
                "nodes": [
                    {"id": "para-01-01", "purpose": "describe", "uses": [],
                     "status": "approved"},
                    {"id": "para-01-02", "purpose": "interpret", "uses": [],
                     "status": "approved"}]})
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    (drafts / "sec-01.md").write_text(
        "<!-- weft:node=para-01-01 -->\n只有第一段。\n", encoding="utf-8")
    project, _ = load_project(tmp_path)
    written, asm_diags = assemble_project(project, mode="lenient")
    assert asm_diags == []
    assert (tmp_path / "generated" / "01-results" / "part-01.qmd").read_text(
        encoding="utf-8") == "## 结果\n\n只有第一段。\n"
    assert [p.name for p in written] == ["part-01.qmd", "01-results.qmd"]
