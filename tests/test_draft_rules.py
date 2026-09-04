"""f 脚本核心：占位符确定性填充（图表字面编号 / [@cites]）与越界硬规则。"""
import pytest

from tests.helpers import build_project
from weft.diagnostics import Level
from weft.engine.draft_rules import (
    DraftRuleError,
    CheckOutput,
    GenOutput,
    fill_placeholders,
    parse_output,
)
from weft.models.cards import ClaimCard, DataCard, FactCard
from weft.models.figures import FigureEntry
from weft.models.narrative import Node, Use


def _project():
    return build_project(
        data=[DataCard(id="data-01", refs=["fig-01a", "fig-01b"],
                       description="速率", status="approved"),
              DataCard(id="data-02", refs=["tbl-01"], description="汇总",
                       status="approved")],
        facts=[FactCard(id="fact-01", data=["data-01"], statement="s1",
                        supports=["claim-01"], status="approved"),
               FactCard(id="fact-02", data=["data-02"], statement="s2",
                        status="approved")],
        claims=[ClaimCard(id="claim-01", claim_type="cited", statement="c1",
                          cites=["key2020"], status="approved"),
                ClaimCard(id="claim-02", claim_type="cited", statement="c2",
                          cites=[], status="approved")],
        figures={"fig-01": FigureEntry(caption="速率曲线"),
                 "tbl-01": FigureEntry(caption="汇总表")},
        bib_keys={"key2020"},
    )


def _node(*uses):
    return Node(id="para-01-01", purpose="describe",
                uses=[Use(id=u, role="evidence") for u in uses],
                status="approved")


def test_fill_fact_label_and_claim_cites():
    text, reminders = fill_placeholders(
        "速率见图 {{fact-01}}；汇总见 {{fact-02}}；结论成立 {{claim-01}}。",
        _node("fact-01", "fact-02", "claim-01"), "sec-01", _project())
    assert "Fig. 1a；Fig. 1b" in text
    assert "Table 1" in text
    assert "（[@key2020]）" in text
    assert reminders == []


def test_fill_empty_cites_warns():
    text, reminders = fill_placeholders(
        "图 {{fact-01}} 文献 {{claim-02}}。",
        _node("fact-01", "claim-02"), "sec-01", _project())
    assert "{{" not in text and "（[" not in text
    assert any("W-CITES-EMPTY" in r for r in reminders)


def test_fill_placeholder_outside_uses_raises():
    with pytest.raises(DraftRuleError) as exc:
        fill_placeholders("越界 {{fact-02}}。", _node("fact-01"),
                          "sec-01", _project())
    assert exc.value.diagnostic.code == "E-DRAFT-USES"


def test_fill_bad_bib_raises():
    proj = _project()
    with pytest.raises(DraftRuleError) as exc:
        fill_placeholders("引 [@ghost2020] {{claim-01}}。",
                          _node("claim-01"), "sec-01", proj)
    assert exc.value.diagnostic.code == "E-CITE-NOT-IN-BIB"


def test_parse_output_shapes():
    ok, diag = parse_output({"paragraph": "x"}, GenOutput, "n", "s")
    assert ok.paragraph == "x" and diag is None
    bad, diag = parse_output({"verdict": "fix"}, CheckOutput, "n", "s")
    assert bad is None and diag.code == "E-DRAFT-SHAPE"
    assert diag.level == Level.ERROR
    ok, _ = parse_output({"verdict": "pass"}, CheckOutput, "n", "s")
    assert ok.verdict == "pass"
