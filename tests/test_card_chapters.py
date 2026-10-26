"""卡片章节标签（chapters）与本章素材生成（card-chapters 设计 §2–§6）。

覆盖：schema 加性扩展往返、extra=forbid 不松动、W-CHAPTER-VOCAB 四态、
素材选取/提示注入/占位符闸门、introduction 端到端、CLI --chapter。
"""
import pytest
from typer.testing import CliRunner

from tests.helpers import build_project, make_minimal_project, write_card
from weft.models.cards import ClaimCard, NoteCard
from weft.models.narrative import NarrativePart, Node, Use
from weft.store.loader import load_project
from weft.store.writer import save_card
from weft.validation import validate_project
from weft.workflow import normalize_chapter

runner = CliRunner()


# ---------- T1 schema 与校验 ----------

def test_card_chapters_roundtrip(tmp_path):
    """默认 []；显式列表；写盘-加载往返；claim 换目录迁移不丢 chapters。"""
    assert ClaimCard(id="claim-01", claim_type="cited", statement="s",
                     status="draft").chapters == []
    card = ClaimCard.model_validate({
        "id": "claim-01", "claim_type": "cited", "statement": "s",
        "chapters": ["introduction", "discussion"], "status": "approved"})
    assert card.chapters == ["introduction", "discussion"]

    root = make_minimal_project(tmp_path)
    project, _ = load_project(root)
    claim = project.claims["claim-01"].model_copy(
        update={"chapters": ["01-results"], "claim_type": "cited",
                "cites": ["key2020"]})
    save_card(root, claim, old_rel=project.card_paths["claim-01"].as_posix())
    reloaded, diags = load_project(root)
    assert not any(d.is_error for d in diags)
    assert reloaded.claims["claim-01"].chapters == ["01-results"]
    assert not (root / "metadata" / "claims" / "uncited" / "claim-01.md").exists()


def test_chapters_extra_forbid_unchanged(tmp_path):
    """防漂移语义不松动：单数 chapter 键仍是未知键 → E-PARSE 转诊断。"""
    root = make_minimal_project(tmp_path)
    write_card(root / "metadata" / "claims" / "uncited", "claim-09",
               {"id": "claim-09", "claim_type": "uncited", "statement": "s",
                "chapter": ["results"], "status": "draft"})
    project, diags = load_project(root)
    assert any(d.code == "E-PARSE" for d in diags)
    assert "claim-09" not in project.claims


def test_normalize_chapter():
    assert normalize_chapter("01-introduction") == "introduction"
    assert normalize_chapter("Introduction") == "introduction"
    assert normalize_chapter(" 03_results ") == "results"
    assert normalize_chapter("02-Methods") == "methods"
    assert normalize_chapter("results") == "results"


def test_validate_chapter_vocab():
    """未知标签 W-CHAPTER-VOCAB；归一化匹配豁免；rejected 豁免；无章节项目豁免。"""
    def _project(parts):
        return build_project(
            claims=[ClaimCard(id="claim-01", claim_type="uncited",
                              statement="s", chapters=["Results"],
                              status="approved"),
                    ClaimCard(id="claim-02", claim_type="uncited",
                              statement="s", chapters=["intro"],
                              status="approved"),
                    ClaimCard(id="claim-03", claim_type="uncited",
                              statement="s", chapters=["intro"],
                              status="rejected")],
            notes=[NoteCard(id="key2020", summary="文献。",
                            chapters=["introduction"], status="approved")],
            parts=parts)

    part = NarrativePart(id="sec-01", section="Results", nodes=[])
    diags = validate_project(_project([part]))
    warns = [(d.code, d.field) for d in diags
             if d.code == "W-CHAPTER-VOCAB"]
    # claim-01 归一化匹配（大小写无关）；claim-03 rejected 豁免；
    # claim-02（intro）与 key2020（introduction）都不匹配 01-results → 各提醒一次
    assert ("W-CHAPTER-VOCAB", "chapters") in warns
    assert len(warns) == 2

    # 项目没有任何叙事章节：全量豁免（先标后建章是正常流）
    diags = validate_project(_project([]))
    assert not any(d.code == "W-CHAPTER-VOCAB" for d in diags)


# ---------- T2 本章素材生成 ----------

def _materials_project():
    return build_project(
        claims=[ClaimCard(id="claim-a", claim_type="cited", statement="背景论断。",
                          cites=["key2020"], chapters=["introduction"],
                          status="approved"),
                ClaimCard(id="claim-b", claim_type="cited", statement="草稿论断。",
                          cites=["key2020"], chapters=["introduction"],
                          status="draft"),
                ClaimCard(id="claim-c", claim_type="cited", statement="别章论断。",
                          cites=["key2020"], chapters=["results"],
                          status="approved")],
        notes=[NoteCard(id="key2020", summary="文献要点。", status="approved"),
               NoteCard(id="doe2021", summary="引言专用要点。",
                        chapters=["Introduction"], status="approved"),
               NoteCard(id="empty2022", summary="",
                        chapters=["introduction"], status="approved")],
        bib_keys={"key2020", "doe2021"})


def test_collect_chapter_materials():
    from weft.engine.spec_build import collect_chapter_materials

    mats = collect_chapter_materials(_materials_project(), "01-introduction")
    assert [c["id"] for c in mats["claims"]] == ["claim-a"]
    assert mats["claims"][0]["note_summaries"] == [{"key": "key2020",
                                                    "summary": "文献要点。"}]
    assert [n["key"] for n in mats["notes"]] == ["doe2021"]
    # draft/rejected、章节不匹配、空 summary 全部排除
    assert "claim-b" not in [c["id"] for c in mats["claims"]]
    assert "claim-c" not in [c["id"] for c in mats["claims"]]
    assert "empty2022" not in [n["key"] for n in mats["notes"]]


def test_build_node_spec_materials():
    from weft.engine.spec_build import build_node_spec, gen_prompt, check_prompt

    project = _materials_project()
    node = Node(id="para-01", purpose="describe", status="approved")
    spec = build_node_spec(project, node)
    assert "materials" not in spec
    prompt = gen_prompt("总述", spec, "核心")
    assert "本章素材" not in prompt          # 无素材 prompt 零变化（H8）

    mats = {"claims": [{"id": "claim-a", "claim_type": "cited",
                        "statement": "背景论断。", "cites": ["key2020"],
                        "note_summaries": []}],
            "notes": [{"key": "doe2021", "summary": "引言专用要点。"}]}
    spec = build_node_spec(project, node, materials=mats)
    assert spec["materials"] == mats
    prompt = gen_prompt("总述", spec, "核心")
    assert "本章素材" in prompt and "背景论断。" in prompt
    check = check_prompt(spec, "正文", "起草稿审查")
    assert "本章素材" in check and "引言专用要点。" in check


def test_fill_placeholders_materials():
    from weft.engine.draft_rules import DraftRuleError, fill_placeholders

    project = _materials_project()
    project.card_paths.setdefault("claim-a", "metadata/claims/cited/claim-a.md")
    node = Node(id="para-01", purpose="describe", status="approved",
                uses=[Use(id="claim-x", role="background")])
    # 素材 claim 占位符合法 → [@key]；uses 之外、素材之外的 id 仍越界
    text, _ = fill_placeholders("见 {{claim-a}}。", node, "sec-01", project,
                                material_ids={"claim-a"})
    assert "[@key2020]" in text
    with pytest.raises(DraftRuleError, match="E-DRAFT-USES"):
        fill_placeholders("见 {{claim-b}}。", node, "sec-01", project,
                          material_ids={"claim-a"})
    # note key 不是合法占位符目标（H10：引用须经 claim.cites）
    with pytest.raises(DraftRuleError, match="E-DRAFT-USES"):
        fill_placeholders("见 {{claim-doe2021}}。", node, "sec-01", project,
                          material_ids={"claim-a"})


def test_run_draft_filters_materials_by_node_uses(tmp_path):
    """run_draft per-node 过滤：节点 uses 已含的 claim 不重复进素材段。"""
    from weft.engine import run as draft_run
    from weft.engine.clients import ScriptedLLMClient

    project = _materials_project()
    project.part_chapters["sec-01"] = "01-introduction"
    part = NarrativePart(id="sec-01", section="Introduction", nodes=[])
    project.parts = [part]
    node = Node(id="para-01", purpose="describe", status="approved",
                uses=[Use(id="claim-a", role="background")])
    client = ScriptedLLMClient()
    draft_run.run_draft(project, part, node, client=client, workflow="introduction",
                        materials={"claims": [
                            {"id": "claim-a", "claim_type": "cited",
                             "statement": "背景论断。", "cites": ["key2020"],
                             "note_summaries": []},
                            {"id": "claim-c", "claim_type": "cited",
                             "statement": "别章论断。", "cites": ["key2020"],
                             "note_summaries": []}],
                            "notes": []})
    gen = client.prompts[0]
    assert "别章论断。" in gen                 # 同章素材在提示里
    assert gen.count('"id": "claim-a"') == 1   # uses 已含 → 不重复进素材


def test_run_draft_introduction_materials_end_to_end(tmp_path):
    """introduction part 端到端：uses 主干 + 同章标签卡自动并入，引注确定性填充。"""
    from weft.engine import run as draft_run
    from weft.engine.clients import ScriptedLLMClient

    project = _materials_project()
    project.part_chapters["sec-intro"] = "01-introduction"
    part = NarrativePart(
        id="sec-intro", section="Introduction",
        nodes=[Node(id="para-intro-01", purpose="describe", status="approved",
                    uses=[Use(id="claim-a", role="background")])])
    project.parts = [part]
    client = ScriptedLLMClient()
    result = draft_run.run_draft(project, part, part.nodes[0], client=client,
                                 workflow="introduction",
                                 overview="研究总述",
                                 materials={"claims": [
                                     {"id": "claim-a", "claim_type": "cited",
                                      "statement": "背景论断。",
                                      "cites": ["key2020"],
                                      "note_summaries": []}],
                                     "notes": [{"key": "doe2021",
                                                "summary": "引言专用要点。"}]})
    # mock 起草对 prompt 中全部 claim id 写占位符；素材 claim 填充出 [@key]
    assert "[@key2020]" in result.paragraph
    assert "为论文引言" in client.prompts[0]   # introduction prompt_core 被使用


# ---------- T3 CLI ----------

def test_new_card_chapter_option(tmp_path):
    from weft.cli import app
    from tests.helpers import make_minimal_project as _mk

    root = _mk(tmp_path)
    result = runner.invoke(app, ["new", "card", "claim", "claim-09",
                                 "--chapter", "introduction",
                                 "--chapter", "discussion", str(root)])
    assert result.exit_code == 0, result.output
    project, diags = load_project(root)
    assert not any(d.is_error for d in diags)
    assert project.claims["claim-09"].chapters == ["introduction", "discussion"]
