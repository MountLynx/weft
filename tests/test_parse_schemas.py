"""parse 节点输出 schema：summary 可选性、note 三档判定、supplement 校验器。"""
import pytest
from pydantic import ValidationError

from weft.engine.parse.schemas import (
    ArticleClassification,
    ArticleExtractOutput,
    ArticleMatchOutput,
    ArticleReviewOutput,
    NoteReview,
)


def test_extract_summary_defaults_empty():
    out = ArticleExtractOutput(cards=[], links=[])
    assert out.summary == ""


def test_review_note_defaults_to_none():
    out = ArticleReviewOutput(classifications=[])
    assert out.note is None


def test_note_review_supplement_requires_merged_summary():
    with pytest.raises(ValidationError):
        NoteReview(verdict="supplement", merged_summary="   ")
    note = NoteReview(verdict="supplement", merged_summary="原要点 + 新增")
    assert note.verdict == "supplement"


def test_note_review_rejects_bad_verdict():
    with pytest.raises(ValidationError):
        NoteReview(verdict="rebuild")


def test_classification_supplement_requires_merged_statement():
    with pytest.raises(ValidationError):
        ArticleClassification(key="f1", verdict="supplement", against=["fact-01"])
    assert ArticleClassification(
        key="f1", verdict="supplement", against=["fact-01"],
        merged_statement="合并陈述").merged_statement == "合并陈述"


def test_match_output_claim_type_literal():
    with pytest.raises(ValidationError):
        ArticleMatchOutput(claim_cites=[{"key": "c1", "claim_type": "quoted"}])
    out = ArticleMatchOutput.model_validate(
        {"fact_data": [], "claim_cites": [{"key": "c1", "claim_type": "cited",
                                           "cites": ["k1"]}],
         "placeholders": [{"text": "xx", "matched_fact": None}]})
    assert out.placeholders[0].matched_fact is None


def test_extract_entry_optional_and_roundtrip():
    out = ArticleExtractOutput.model_validate({"summary": "s", "entry": {
        "type": "article", "title": "T", "year": 2020, "author": ["A, B"]}})
    assert out.entry.title == "T"
    assert ArticleExtractOutput.model_validate({"summary": "s"}).entry is None
