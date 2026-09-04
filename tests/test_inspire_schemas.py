"""inspire 节点输出 schema（T1–T4 结构化 JSON 的 pydantic 契约）。"""
import pytest
from pydantic import ValidationError

from weft.engine.inspire.schemas import (
    ExtractOutput,
    LogicOutput,
    MatchOutput,
    ReviewOutput,
)


def test_logic_output_parses_issues():
    out = LogicOutput.model_validate_json('{"issues": ["前后矛盾", "缺主语"]}')
    assert out.issues == ["前后矛盾", "缺主语"]


def test_logic_output_issues_optional():
    assert LogicOutput.model_validate_json("{}").issues == []


def test_extract_output_parses_cards_and_links():
    out = ExtractOutput.model_validate_json(
        '{"cards": [{"key": "f1", "kind": "fact", "statement": "温度升高速率",'
        ' "placeholder": false},'
        ' {"key": "c1", "kind": "claim", "statement": "升温是催化主因",'
        ' "needs_citation": true}],'
        ' "links": [{"from": "f1", "to": "c1"}]}')
    assert [c.key for c in out.cards] == ["f1", "c1"]
    assert out.cards[1].needs_citation is True
    assert out.links[0].from_ == "f1" and out.links[0].to == "c1"


def test_extract_output_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        ExtractOutput.model_validate_json(
            '{"cards": [{"key": "n1", "kind": "note", "statement": "s"}]}')


def test_review_output_rejects_unknown_verdict():
    with pytest.raises(ValidationError):
        ReviewOutput.model_validate_json(
            '{"classifications": [{"key": "f1", "verdict": "duplicate"}]}')


def test_review_output_supplement_requires_merged_statement():
    with pytest.raises(ValidationError):
        ReviewOutput.model_validate_json(
            '{"classifications": [{"key": "f1", "verdict": "supplement",'
            ' "against": ["fact-01"], "reason": "r", "merged_statement": ""}]}')


def test_match_output_parses_all_sections():
    out = MatchOutput.model_validate_json(
        '{"fact_data": [{"key": "f1", "data_ids": ["data-01"]}],'
        ' "claim_cites": [{"key": "c1", "claim_type": "cited",'
        ' "cites": ["smith2020"], "reason": "机制直接对应"}],'
        ' "placeholders": [{"text": "xxx 数据", "matched_fact": null}]}')
    assert out.fact_data[0].data_ids == ["data-01"]
    assert out.claim_cites[0].claim_type == "cited"
    assert out.placeholders[0].matched_fact is None


def test_match_output_rejects_bad_claim_type():
    with pytest.raises(ValidationError):
        MatchOutput.model_validate_json(
            '{"claim_cites": [{"key": "c1", "claim_type": "quoted"}]}')


def test_coverage_output_parses_entries():
    from weft.engine.inspire.schemas import CoverageOutput

    out = CoverageOutput.model_validate_json(
        '{"coverage": ['
        '{"sentence": "de novo 颗粒化 SVI30 150-200", "card_keys": ["c2"],'
        ' "covered": true},'
        '{"sentence": "某未被成卡的对比", "card_keys": [], "covered": false,'
        ' "suggestion": "应成 cited claim（对比文献值）"}]}')
    assert out.coverage[0].covered is True
    assert out.coverage[1].covered is False
    assert "cited claim" in out.coverage[1].suggestion
