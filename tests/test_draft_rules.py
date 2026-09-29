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
    assert "Fig. 1a; Fig. 1b" in text
    assert "Table 1" in text
    assert "[@key2020]" in text
    assert reminders == []


def test_fill_claim_cites_use_single_quarto_bracket():
    """多键引用必须合并为单个 [@a; @b] 引用块：写成 ([@a]; [@b]) 会被
    citeproc 渲染成双层括号（e2e 实测 docx）。"""
    proj = build_project(
        data=[DataCard(id="data-01", refs=["fig-01a"], description="d",
                       status="approved")],
        facts=[FactCard(id="fact-01", data=["data-01"], statement="s",
                        status="approved")],
        claims=[ClaimCard(id="claim-01", claim_type="cited", statement="c",
                          cites=["key2020", "doe2021"], status="approved")],
        figures={"fig-01": FigureEntry(caption="c")},
        bib_keys={"key2020", "doe2021"},
    )
    text, _ = fill_placeholders(
        "结论成立 {{claim-01}}。", _node("claim-01"), "sec-01", proj)
    assert text == "结论成立 [@key2020; @doe2021]。"


def test_fill_empty_cites_warns():
    text, reminders = fill_placeholders(
        "图 {{fact-01}} 文献 {{claim-02}}。",
        _node("fact-01", "claim-02"), "sec-01", _project())
    assert "{{" not in text and "([" not in text
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


def test_fill_collapses_double_parens_around_cites():
    """引用填充为 [@key] 块后不产生额外括号；模型自包的括号原样保留
    （渲染时括号由 citeproc 生成，草稿文本不叠加）。"""
    for wrapped in ("对比成立({{claim-01}})。", "对比成立（{{claim-01}}）。",
                    "对比成立 {{claim-01}}。"):
        text, _ = fill_placeholders(
            wrapped, _node("claim-01"), "sec-01", _project())
        assert "[@key2020]" in text
        assert "((" not in text and "))" not in text


def test_fill_dedupes_repeated_placeholders_and_tidies_residue():
    """e2e 实测：模型同段把同一占位符写两遍（(Fig. 1a; Fig. 1a)）、
    占位符移除后留下"句末空格"残迹（MBGS-S .）→ 去重 + 残迹清理兜底。"""
    node = _node("fact-01", "fact-01", "claim-02")
    text, _ = fill_placeholders(
        "如图 {{fact-01}} 与 {{fact-01}} 所示 ({{fact-01}}; {{fact-01}})；"
        "结论 {{claim-02}} .",
        node, "sec-01", _project())
    assert text.count("Fig. 1a") == 1
    assert "Fig. 1a; Fig. 1b" in text
    assert not text.rstrip().endswith(" .")
    assert "  " not in text and " ." not in text and " )" not in text


def test_fill_dedupe_space_separated_duplicates():
    """e2e 实测（results 第 3 轮）：模型以空格重复占位符 "( {{f}} {{f}} )"，
    去重后不得残留 " )"。"""
    text, _ = fill_placeholders(
        " SVI evidence ({{fact-01}} {{fact-01}}).",
        _node("fact-01", "fact-01"), "sec-01", _project())
    assert "(Fig. 1a; Fig. 1b)." in text
    assert " )" not in text and "( " not in text


def test_fill_dedupes_hallucinated_literal_figure_labels():
    """e2e 实测（results 第 4 轮）：c1 在 fix 文本里自行写出字面图号
    "(Fig. 1a)" 并与占位符并列 → 填充后合并括注并去重。"""
    text, _ = fill_placeholders(
        "SVI30 was 79.2 mL/g (Fig. 1a) ({{fact-01}}).",
        _node("fact-01"), "sec-01", _project())
    assert text == "SVI30 was 79.2 mL/g (Fig. 1a; Fig. 1b)."

    text, _ = fill_placeholders(
        "SVI30 was 79.2 mL/g (Fig. 1a; Fig. 1a).",
        _node("fact-01"), "sec-01", _project())
    assert text == "SVI30 was 79.2 mL/g (Fig. 1a)."
