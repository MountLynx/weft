"""rename 引擎：计划段校验与引用扫描、应用段落盘同步（rename 设计定案）。"""
from pathlib import Path

import pytest

from weft.rename import RenameError, plan_rename
from weft.scaffold import NewCollisionError, NewNameError
from weft.models.cards import (
    ClaimCard, DataCard, FactCard, MethodCard, NoteCard, ParamCard,
)
from weft.models.narrative import NarrativePart, Node, Use
from weft.store.writer import card_relpath
from tests.helpers import build_project


def _project(**overrides):
    base = dict(
        data=[DataCard(id="data-01", status="approved", description="测量值")],
        facts=[FactCard(id="fact-01", data=["data-01"], statement="s",
                        supports=["claim-01"], status="approved"),
               FactCard(id="fact-02", data=["data-01", "data-02"], statement="t",
                        status="approved")],
        claims=[ClaimCard(id="claim-01", claim_type="uncited", statement="c",
                          status="approved")],
        parts=[NarrativePart(id="sec-01", section="R", nodes=[
            Node(id="para-01-01", purpose="describe",
                 uses=[Use(id="fact-01", role="evidence")], status="approved")]),
        ],
    )
    base.update(overrides)
    project = build_project(**base)
    # build_project 填的是假想路径（metadata/<id>.md）；本测试断言真实 rel，按规范重填
    for table in (project.data_cards, project.facts, project.claims,
                  project.notes, project.methods, project.params):
        for card in table.values():
            project.card_paths[card.id] = Path(card_relpath(card))
    return project


def test_plan_reports_target_refs_and_rels():
    plan = plan_rename(_project(), "data-01", "arrhenius-60c")
    assert (plan.kind, plan.old_id, plan.new_id) == ("data", "data-01", "arrhenius-60c")
    assert plan.old_rel == "metadata/data/data-01.md"
    assert plan.new_rel == "metadata/data/arrhenius-60c.md"
    assert plan.card_refs == {"fact-01": ["data"], "fact-02": ["data"]}
    assert plan.card_rels == {"fact-01": "metadata/facts/fact-01.md",
                              "fact-02": "metadata/facts/fact-02.md"}
    assert plan.part_refs == {}   # 节点 uses 只直接引用 fact/claim/method/param；data 经 fact 间接可达
    assert plan.part_rels == {}
    assert plan.needs_bib_sync is False


def test_plan_part_refs_for_fact_rename():
    plan = plan_rename(_project(), "fact-01", "temp-rate")
    assert plan.card_refs == {}
    assert plan.part_refs == {"sec-01": 1}
    assert plan.part_rels == {"sec-01": "narrative/01-results/sec-01.md"}


def test_plan_aggregates_fields_per_card():
    plan = plan_rename(_project(
        facts=[FactCard(id="fact-01", data=["data-01"], statement="s",
                        supports=["data-01"], status="approved")]),
        "data-01", "d1")
    assert plan.card_refs == {"fact-01": ["data", "supports"]}


def test_plan_old_missing_raises():
    with pytest.raises(RenameError, match="不存在"):
        plan_rename(_project(), "ghost", "x")


def test_plan_same_id_raises():
    with pytest.raises(RenameError, match="相同"):
        plan_rename(_project(), "data-01", "data-01")


@pytest.mark.parametrize("bad", ["../x", "a/b", "", ".x", "x.", " x", "a:b\\c"])
def test_plan_unsafe_new_id_raises(bad):
    with pytest.raises(NewNameError):
        plan_rename(_project(), "data-01", bad)


def test_plan_collision_raises():
    with pytest.raises(NewCollisionError):
        plan_rename(_project(), "data-01", "fact-01")
