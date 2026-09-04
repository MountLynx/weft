"""digest 摘要索引（inspire 设计 §3）：Project → 紧凑文本，LLM 穷举比对底料。"""
from weft.digest import build_digest
from weft.models.cards import (
    ClaimCard,
    DataCard,
    FactCard,
    MethodCard,
    NoteCard,
    ParamCard,
)
from weft.models.figures import FigureEntry
from weft.store.project import Project
from tests.helpers import build_project


def _full_project() -> Project:
    return build_project(
        data=[DataCard(id="data-01", refs=["fig-01a"], source="实验 A",
                       description="速率测量", status="approved")],
        facts=[FactCard(id="fact-01", data=["data-01"], statement="温度提高速率。",
                        supports=["claim-01"], status="approved")],
        claims=[ClaimCard(id="claim-01", claim_type="cited",
                          statement="温度有正效应。", cites=["smith2020"],
                          status="draft")],
        notes=[NoteCard(id="smith2020", summary="热激活催化机制。",
                        status="approved")],
        methods=[MethodCard(id="qpcr", statement="定量 PCR。",
                            protocol="三步循环。", status="approved")],
        params=[ParamCard(id="p-anneal", method="qpcr",
                          values={"cycles": 35}, status="draft")],
        figures={"fig-01": FigureEntry(caption="速率曲线", subfigs={"a": "60°C"})},
        bib_keys={"smith2020"},
    )


def test_digest_empty_project_renders_header_only():
    text = build_digest(Project(root=__import__("pathlib").Path(".")))
    assert "data-01" not in text


def test_digest_contains_all_card_types():
    text = build_digest(_full_project())
    assert "data-01" in text and "速率测量" in text and "fig-01a" in text
    assert "fact-01" in text and "温度提高速率。" in text and "claim-01" in text
    assert "claim-01" in text and "cited" in text and "smith2020" in text
    assert "热激活催化机制。" in text          # note summary 全文
    assert "qpcr" in text and "cycles" in text
    assert "速率曲线" in text                 # figures 图题


def test_digest_marks_card_status():
    text = build_digest(_full_project())
    assert "draft" in text   # claim-01 是 draft，status 必须可见


def test_digest_is_deterministic():
    assert build_digest(_full_project()) == build_digest(_full_project())
