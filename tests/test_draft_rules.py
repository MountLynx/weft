"""生成时校验三规则（spec §4 生成时行）+ harness 输出形状解析。"""
from tests.helpers import build_project
from weft.diagnostics import Level
from weft.engine.draft_rules import (
    DraftError,
    DraftRuleError,
    check_node_draft,
    parse_node_draft,
)
from weft.models.cards import ClaimCard
from weft.models.narrative import Node, Use

SEC = "sec-01"
NODE_ID = "para-01-01"


def _node(uses=("fact-01", "claim-01")):
    # claim-01 须在 uses 内：规则 2 的允许集 = 节点所用 claim 的 cites 并集
    # （与 run 层测试 test_engine_run.py 的节点接线一致）
    return Node(id=NODE_ID, purpose="describe",
                uses=[Use(id=u, role="evidence") for u in uses], status="approved")


def _project(bib=("key2020",), claim_cites=("key2020",)):
    return build_project(
        bib_keys=set(bib),
        claims=[ClaimCard(id="claim-01", claim_type="cited", statement="s",
                          cites=list(claim_cites), status="approved")],
    )


def test_parse_ok():
    draft, diag = parse_node_draft(
        {"paragraph": "正文。", "uses": ["fact-01"], "cites": []}, NODE_ID, SEC)
    assert diag is None
    assert draft["paragraph"] == "正文。"


def test_parse_non_dict():
    draft, diag = parse_node_draft("not json", NODE_ID, SEC)
    assert draft is None
    assert diag.code == "E-DRAFT-SHAPE"
    assert diag.path == f"drafts/{SEC}.md"
    assert diag.field == f"{NODE_ID}.output"


def test_parse_empty_paragraph():
    _, diag = parse_node_draft({"paragraph": "  ", "uses": [], "cites": []}, NODE_ID, SEC)
    assert diag.code == "E-DRAFT-SHAPE"


def test_parse_bad_uses_type():
    _, diag = parse_node_draft({"paragraph": "p", "uses": "fact-01", "cites": []}, NODE_ID, SEC)
    assert diag.code == "E-DRAFT-SHAPE"


def test_rule3_uses_beyond_node():
    diags = check_node_draft({"paragraph": "p", "uses": ["claim-99"], "cites": []},
                             _node(), _project(), SEC)
    assert [d.code for d in diags] == ["E-USES-BEYOND-NODE"]
    assert diags[0].level is Level.ERROR


def test_rule1_cite_not_in_bib():
    diags = check_node_draft({"paragraph": "p", "uses": [], "cites": ["nokey"]},
                             _node(), _project(), SEC)
    assert [d.code for d in diags] == ["E-CITE-NOT-IN-BIB"]


def test_rule2_cite_not_in_claim_cites_is_warning():
    # keyother 在 bib 内但不属于 claim-01 的 cites → 纯提醒不阻断
    diags = check_node_draft({"paragraph": "p", "uses": [], "cites": ["keyother"]},
                             _node(), _project(bib=("key2020", "keyother")), SEC)
    assert [d.code for d in diags] == ["W-CITE-NOT-IN-CLAIM"]
    assert diags[0].level is Level.WARNING


def test_rule2_pass_when_cite_belongs_to_claim():
    diags = check_node_draft({"paragraph": "p", "uses": [], "cites": ["key2020"]},
                             _node(), _project(), SEC)
    assert diags == []


def test_error_types():
    _, diag = parse_node_draft(42, NODE_ID, SEC)
    assert isinstance(DraftRuleError(diag), RuntimeError)
    assert isinstance(DraftError("x"), RuntimeError)


def test_missing_uses_cites_keys_do_not_raise():
    draft, _ = parse_node_draft({"paragraph": "p"}, NODE_ID, SEC)
    assert check_node_draft(draft, _node(), _project(), SEC) == []


def test_multiple_violations_accumulate():
    diags = check_node_draft({"paragraph": "p", "uses": ["claim-99"], "cites": ["nokey"]},
                             _node(), _project(), SEC)
    assert [d.code for d in diags] == ["E-USES-BEYOND-NODE", "E-CITE-NOT-IN-BIB"]


def test_rule3_message_uses_kong_when_node_has_no_uses():
    node = _node(uses=())
    diags = check_node_draft({"paragraph": "p", "uses": ["claim-99"], "cites": []},
                             node, _project(), SEC)
    assert "（空）" in diags[0].message


def test_draft_rule_error_str_and_diagnostic():
    _, diag = parse_node_draft(42, NODE_ID, SEC)
    err = DraftRuleError(diag)
    assert err.diagnostic is diag
    assert str(err) == f"[{diag.code}] {diag.path} 字段 {diag.field}: {diag.message}"


def test_rule1_prose_cite_not_in_bib():
    diags = check_node_draft(
        {"paragraph": "结果 [@fact-01] 支持……", "uses": [], "cites": ["key2020"]},
        _node(), _project(), SEC)
    assert [d.code for d in diags] == ["E-CITE-NOT-IN-BIB"]
    assert diags[0].field.endswith("paragraph")


def test_rule2_prose_cite_not_in_claim_cites_is_warning():
    diags = check_node_draft(
        {"paragraph": "如 [@keyother] 所示。", "uses": [], "cites": []},
        _node(), _project(bib=("key2020", "keyother")), SEC)
    assert [d.code for d in diags] == ["W-CITE-NOT-IN-CLAIM"]
    assert diags[0].field.endswith("paragraph")


def test_prose_and_structured_cite_dedup():
    diags = check_node_draft(
        {"paragraph": "见 [@nokey]。", "uses": [], "cites": ["nokey"]},
        _node(), _project(), SEC)
    assert [d.code for d in diags] == ["E-CITE-NOT-IN-BIB"]   # 单条诊断


def test_multi_cite_bracket_form_supported():
    diags = check_node_draft(
        {"paragraph": "见 [@key2020; @keyother]。", "uses": [], "cites": []},
        _node(), _project(bib=("key2020", "keyother")), SEC)
    # key2020 ∈ claim-01.cites → 静默通过；仅 keyother 触发 W（正文通道）
    assert [d.code for d in diags] == ["W-CITE-NOT-IN-CLAIM"]
    assert "keyother" in diags[0].message
    assert diags[0].field.endswith("paragraph")


def test_bare_crossref_not_flagged():
    diags = check_node_draft(
        {"paragraph": "如图 @fig-01a 所示。", "uses": [], "cites": []},
        _node(), _project(), SEC)
    assert diags == []
