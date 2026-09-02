"""生成时校验三规则（spec §4 生成时行）+ harness 输出形状解析。"""
import pytest

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
