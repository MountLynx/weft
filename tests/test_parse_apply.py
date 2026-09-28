"""parse A1 聚合：note 三档、落盘闭包、归档、报告、一致性 fail-closed。"""
import pytest

from weft.engine.parse.apply import apply_article
from weft.engine.parse.schemas import (
    ArticleClaimMatch,
    ArticleClassification,
    ArticleCoverageOutput,
    ArticleExtractOutput,
    ArticleFactMatch,
    ArticleLogicOutput,
    ArticleMatchOutput,
    ArticleProposedCard,
    ArticleReviewOutput,
    NoteReview,
)
from tests.helpers import build_project, write_card
from weft.models.cards import ClaimCard, DataCard, FactCard, NoteCard


def _project(root=None, *, with_note=True):
    project = build_project(root=root,
        data=[DataCard(id="data-01", refs=["fig-01a"], description="速率测量",
                       status="approved")],
        facts=[FactCard(id="fact-01", data=["data-01"], statement="温度提高速率。",
                        status="approved")],
        claims=[ClaimCard(id="claim-01", claim_type="uncited",
                          statement="温度有正效应。", status="approved")],
        notes=[NoteCard(id="key2020", summary="旧摘要。", status="approved")]
              if with_note else [],
        bib_keys={"key2020"})
    if root is not None and with_note:
        # 既有 note 卡须真实在盘：supplement/unchanged 档断言"原卡不动"读的是盘上文件
        # （计划原文疏漏：build_project 纯内存，不落盘）
        write_card(root / "metadata" / "notes", "key2020",
                   {"id": "key2020", "summary": "旧摘要。", "status": "approved"})
    return project


def _extract(summary="新解析的摘要。"):
    return ArticleExtractOutput(
        summary=summary,
        cards=[ArticleProposedCard(key="f1", kind="fact", statement="搅拌加速溶解"),
               ArticleProposedCard(key="c1", kind="claim", statement="搅拌是主因",
                                   needs_citation=True)],
        links=[])


def _review(note=None, classifications=None):
    return ArticleReviewOutput(
        classifications=classifications
        or [ArticleClassification(key="f1", verdict="new"),
            ArticleClassification(key="c1", verdict="new")],
        note=note)


def _match():
    return ArticleMatchOutput(
        fact_data=[ArticleFactMatch(key="f1", data_ids=["data-01"])],
        claim_cites=[ArticleClaimMatch(key="c1", claim_type="cited",
                                       cites=["key2020"])],
        placeholders=[])


def _source(tmp_path, name="paper.md", text="一篇关于搅拌的文章。"):
    path = tmp_path / "articles" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _apply(project, source, *, note=None, bib_key="key2020", extract=None,
           review=None, match=None):
    return apply_article(project, source=source,
                         logic=ArticleLogicOutput(),
                         extract=extract or _extract(),
                         review=review or _review(note=note),
                         match=match or _match(),
                         coverage=ArticleCoverageOutput(),
                         bib_key=bib_key)


def test_literature_new_note_lands_draft_card(tmp_path):
    source = _source(tmp_path)
    project = _project(tmp_path, with_note=False)
    outcome = _apply(project, source, note=NoteReview(verdict="new"))
    note_path = tmp_path / "metadata" / "notes" / "key2020.md"
    assert note_path in outcome.written_cards and note_path.is_file()
    text = note_path.read_text(encoding="utf-8")
    assert "status: draft" in text and "新解析的摘要。" in text


def test_literature_supplement_writes_proposal_only(tmp_path):
    source = _source(tmp_path)
    project = _project(tmp_path)   # key2020 已存在
    note = NoteReview(verdict="supplement", reason="新版补了实验",
                      merged_summary="旧摘要。新版补充：实验细节。")
    outcome = _apply(project, source, note=note)
    old_text = (tmp_path / "metadata" / "notes" / "key2020.md").read_text(encoding="utf-8")
    assert "旧摘要。" in old_text and "实验细节" not in old_text   # 既有卡不动
    proposal = tmp_path / "inspirations" / "proposals" / "key2020.md"
    assert proposal in outcome.proposals and proposal.is_file()
    proposal_text = proposal.read_text(encoding="utf-8")
    assert "实验细节" in proposal_text and "取代 key2020" in proposal_text


def test_literature_unchanged_zero_note_writes(tmp_path):
    source = _source(tmp_path)
    project = _project(tmp_path)
    outcome = _apply(project, source, note=NoteReview(verdict="unchanged"))
    note_text = (tmp_path / "metadata" / "notes" / "key2020.md").read_text(encoding="utf-8")
    assert "旧摘要。" in note_text                      # 原卡不动
    assert not (tmp_path / "inspirations" / "proposals" / "key2020.md").exists()
    assert any("维持原卡" in n for n in outcome.notes)
    assert (tmp_path / "articles" / "processed" / "paper.md").is_file()  # 原文照常归档


def test_literature_missing_note_review_is_shape_error(tmp_path):
    source = _source(tmp_path)
    project = _project(tmp_path, with_note=False)
    with pytest.raises(ValueError, match="E-ARTICLE-SHAPE"):
        _apply(project, source, note=None)
    assert source.exists()   # fail-closed：零写盘


def test_note_verdict_inconsistent_with_project_is_shape_error(tmp_path):
    source = _source(tmp_path)
    project = _project(tmp_path)   # key2020 已存在
    with pytest.raises(ValueError, match="E-ARTICLE-SHAPE"):
        _apply(project, source, note=NoteReview(verdict="new"))
    assert source.exists()


def test_bib_key_must_be_in_bib(tmp_path):
    source = _source(tmp_path)
    project = _project(tmp_path)
    with pytest.raises(ValueError, match="E-ARTICLE-KEY"):
        _apply(project, source, bib_key="ghostkey")
    assert source.exists()


def test_fact_without_data_match_not_landed(tmp_path):
    source = _source(tmp_path)
    project = _project(tmp_path, with_note=False)
    match = ArticleMatchOutput(
        fact_data=[ArticleFactMatch(key="f1", data_ids=[])],
        claim_cites=[ArticleClaimMatch(key="c1", claim_type="cited",
                                       cites=["key2020"])],
        placeholders=[])
    outcome = _apply(project, source, note=NoteReview(verdict="new"), match=match)
    landed = {p.name for p in outcome.written_cards}
    assert "fact-02.md" not in landed          # 闭包拦截：宁可少落
    assert "claim-02.md" in landed
    assert any("需补充 data 关联" in n for n in outcome.notes)


def test_claim_conflict_recorded_in_report(tmp_path):
    source = _source(tmp_path)
    project = _project(tmp_path, with_note=False)
    review = _review(note=NoteReview(verdict="new"), classifications=[
        ArticleClassification(key="f1", verdict="new"),
        ArticleClassification(key="c1", verdict="conflict", against=["claim-01"],
                              reason="方向相反")])
    outcome = _apply(project, source, note=NoteReview(verdict="new"), review=review)
    report = outcome.report.read_text(encoding="utf-8")
    assert "方向相反" in report and "claim-02" in report


def test_card_supplement_demoted_when_target_missing(tmp_path):
    source = _source(tmp_path)
    project = _project(tmp_path, with_note=False)
    review = _review(note=NoteReview(verdict="new"), classifications=[
        ArticleClassification(key="f1", verdict="supplement", against=["data-01"],
                              merged_statement="合并陈述")])
    outcome = _apply(project, source, note=NoteReview(verdict="new"), review=review)
    assert any("降级为新建草稿卡" in n for n in outcome.notes)


def test_source_must_be_in_articles(tmp_path):
    project = _project(tmp_path)
    outside = tmp_path / "elsewhere.md"
    outside.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="articles"):
        _apply(project, outside, note=NoteReview(verdict="new"))


def test_report_sections_written(tmp_path):
    source = _source(tmp_path)
    project = _project(tmp_path, with_note=False)
    outcome = _apply(project, source, note=NoteReview(verdict="new"))
    report = outcome.report.read_text(encoding="utf-8")
    for section in ("## note 判定", "## claim 分类与依据", "## fact→data 关联建议",
                    "## 成卡覆盖审查", "## 丢弃与提示"):
        assert section in report
    assert outcome.report == tmp_path / "generated" / "articles" / "paper-report.md"
