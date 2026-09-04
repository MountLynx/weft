"""apply 聚合（A1）：id 分配、落盘闭包、矛盾/补充处置、原文归档、报告。"""
from pathlib import Path

import pytest

from weft.engine.inspire.apply import apply_inspiration
from weft.engine.inspire.schemas import (
    ClaimMatch,
    Classification,
    ExtractOutput,
    FactMatch,
    LogicOutput,
    MatchOutput,
    PlaceholderMatch,
    ProposedCard,
    ReviewOutput,
    _Link,
)
from tests.helpers import make_minimal_project, write_card
from weft.store.loader import load_project


def _extract() -> ExtractOutput:
    return ExtractOutput.model_validate({
        "cards": [
            {"key": "f1", "kind": "fact", "statement": "搅拌加速溶解。"},
            {"key": "c1", "kind": "claim", "statement": "搅拌是主要因素。",
             "needs_citation": True},
        ],
        "links": [{"from": "f1", "to": "c1"}],
    })


def _review(**overrides) -> ReviewOutput:
    base = {"classifications": [
        {"key": "f1", "verdict": "new"},
        {"key": "c1", "verdict": "new"},
    ]}
    base["classifications"].extend(overrides.get("extra", []))
    return ReviewOutput.model_validate(base)


def _match() -> MatchOutput:
    return MatchOutput.model_validate({
        "fact_data": [{"key": "f1", "data_ids": ["data-01"]}],
        "claim_cites": [{"key": "c1", "claim_type": "cited",
                         "cites": ["key2020"], "reason": "机制相关"}],
    })


def _apply(root: Path, *, extract=None, review=None, match=None,
           logic=None, source_name="idea.md"):
    source = root / "inspirations" / source_name
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("随手记内容", encoding="utf-8")
    project, diags = load_project(make_minimal_project(root))
    assert not any(d.is_error for d in diags)
    return apply_inspiration(
        project, source=source,
        logic=logic or LogicOutput(),
        extract=extract or _extract(),
        review=review if review is not None else _review(),
        match=match or _match())


def test_apply_assigns_ids_writes_and_archives(tmp_path):
    outcome = _apply(tmp_path)
    fact_path = tmp_path / "metadata" / "facts" / "fact-02.md"
    claim_path = tmp_path / "metadata" / "claims" / "cited" / "claim-02.md"
    assert fact_path in outcome.written_cards
    assert claim_path in outcome.written_cards
    assert "id: fact-02" in fact_path.read_text(encoding="utf-8")
    assert "data:" in fact_path.read_text(encoding="utf-8")
    claim_text = claim_path.read_text(encoding="utf-8")
    assert "cites" in claim_text and "key2020" in claim_text
    assert "supports" not in claim_text          # ClaimCard 无 supports 字段（extra=forbid）
    fact_text = fact_path.read_text(encoding="utf-8")
    assert "claim-02" in fact_text               # 支持方向在 fact.supports 上
    assert (tmp_path / "inspirations" / "processed" / "idea.md").is_file()
    assert not (tmp_path / "inspirations" / "idea.md").exists()
    assert outcome.report.is_file()
    assert "idea-report" in outcome.report.name
    report_text = outcome.report.read_text(encoding="utf-8")
    assert "- metadata/facts/fact-02.md" in report_text   # 路径以项目根为基准


def test_apply_ids_skip_global_namespace_collisions(tmp_path):
    write_card(tmp_path / "metadata" / "facts", "fact-02",
               {"id": "fact-02", "data": ["data-01"], "statement": "已有",
                "status": "approved"})
    outcome = _apply(tmp_path)
    assert (tmp_path / "metadata" / "facts" / "fact-03.md") in outcome.written_cards


def test_apply_drops_fact_without_data_match(tmp_path):
    match = MatchOutput.model_validate({
        "claim_cites": [{"key": "c1", "claim_type": "uncited"}]})
    outcome = _apply(tmp_path, match=match)
    assert not (tmp_path / "metadata" / "facts" / "fact-02.md").exists()
    claim_path = tmp_path / "metadata" / "claims" / "uncited" / "claim-02.md"
    assert claim_path.is_file()   # claim 仍落盘，supports 被摘除
    assert "fact-02" not in claim_path.read_text(encoding="utf-8")
    assert any("data" in note for note in outcome.notes)
    assert outcome.report.read_text(encoding="utf-8").count("需补充") >= 1


def test_apply_conflict_card_written_and_reported(tmp_path):
    review = _review(extra=[{"key": "c1", "verdict": "conflict",
                             "against": ["claim-01"], "reason": "方向相反"}])
    _apply(tmp_path, review=review)
    assert (tmp_path / "metadata" / "claims" / "cited" / "claim-02.md").is_file()
    report = (tmp_path / "generated" / "inspirations" / "idea-report.md"
              ).read_text(encoding="utf-8")
    assert "claim-01" in report and "方向相反" in report


def test_apply_supplement_creates_proposal_with_original_fields(tmp_path):
    review = _review(extra=[{"key": "f1", "verdict": "supplement",
                             "against": ["fact-01"],
                             "merged_statement": "温度提高速率，且随搅拌增强。",
                             "reason": "补充搅拌维度"}])
    outcome = _apply(tmp_path, review=review)
    assert not (tmp_path / "metadata" / "facts" / "fact-02.md").exists()
    proposal = tmp_path / "inspirations" / "proposals" / "fact-01.md"
    assert proposal in outcome.proposals and proposal.is_file()
    text = proposal.read_text(encoding="utf-8")
    assert "id: fact-01" in text and "draft" in text
    assert "温度提高速率，且随搅拌增强。" in text
    assert "data-01" in text                       # 原卡结构化字段机械继承
    assert "取代 fact-01" in text


def test_apply_demotes_supplement_with_invalid_target(tmp_path):
    """supplement 目标不存在或不是 fact/claim 卡 → 降级为 new 草稿卡 + WARN。

    e2e 实测：真实模型会把 fact 草案标 supplement、against 填 data 卡；
    整链 fail-closed 拒绝固然安全，但重跑四节点成本高，无歧义误分类降级即可。
    """
    review = _review(extra=[{"key": "f1", "verdict": "supplement",
                             "against": ["data-01"],
                             "merged_statement": "x"}])
    outcome = _apply(tmp_path, review=review)
    assert (tmp_path / "metadata" / "facts" / "fact-02.md") in outcome.written_cards
    assert not (tmp_path / "inspirations" / "proposals" / "data-01.md").exists()
    assert any("降级" in note for note in outcome.notes)
    review2 = _review(extra=[{"key": "f1", "verdict": "supplement",
                              "against": ["fact-99"], "merged_statement": "x"}])
    outcome2 = _apply(tmp_path / "second", review=review2)
    assert (tmp_path / "second" / "metadata" / "facts" / "fact-02.md") \
        in outcome2.written_cards
    assert any("降级" in note for note in outcome2.notes)


def test_apply_report_carries_logic_and_placeholder_sections(tmp_path):
    match = MatchOutput.model_validate({
        "fact_data": [{"key": "f1", "data_ids": ["data-01"]}],
        "claim_cites": [{"key": "c1", "claim_type": "cited", "cites": []}],
        "placeholders": [{"text": "xxx%", "matched_fact": None}],
    })
    logic = LogicOutput(issues=["后半句缺少主语"])
    outcome = _apply(tmp_path, logic=logic, match=match)
    report = outcome.report.read_text(encoding="utf-8")
    assert "后半句缺少主语" in report
    assert "xxx%" in report and "需补充" in report
    assert any("缺文献" in note or "cited" in note for note in outcome.notes)


def test_apply_duplicate_supplement_targets_keeps_first(tmp_path):
    """两个草案补充同一目标卡 → 先到先得，后者降级为新建卡并提示（不静默覆盖）。"""
    review = _review(extra=[
        {"key": "c1", "verdict": "supplement", "against": ["claim-01"],
         "merged_statement": "温度有正效应，且随搅拌增强。", "reason": "补充A"},
        {"key": "f1", "verdict": "supplement", "against": ["claim-01"],
         "merged_statement": "另一角度的补充。", "reason": "补充B"},
    ])
    match = MatchOutput.model_validate({
        "fact_data": [{"key": "f1", "data_ids": ["data-01"]}],
        "claim_cites": [{"key": "c1", "claim_type": "uncited"}]})
    outcome = _apply(tmp_path, review=review, match=match)
    proposal = tmp_path / "inspirations" / "proposals" / "claim-01.md"
    assert proposal in outcome.proposals
    # 先到者胜：拆解顺序里 f1 在前，f1 的补充成为提案
    assert "另一角度的补充" in proposal.read_text(encoding="utf-8")
    assert any("降级" in n for n in outcome.notes)
    # 后者（c1）降级为新建草稿卡
    assert (tmp_path / "metadata" / "claims" / "uncited" / "claim-02.md").is_file()
