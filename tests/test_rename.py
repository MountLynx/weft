"""rename 引擎：计划段校验与引用扫描、应用段落盘同步（rename 设计定案）。"""
from pathlib import Path

import pytest

from weft.rename import RenameError, apply_rename, plan_rename
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


# ---------- 应用段（Task 3） ----------

from tests.helpers import make_minimal_project, write_card
from weft.store.loader import load_project


def test_apply_moves_card_file(tmp_path):
    make_minimal_project(tmp_path)
    project, diags = load_project(tmp_path)
    assert not any(d.is_error for d in diags)
    plan = plan_rename(project, "data-01", "run-60c")
    result = apply_rename(project, plan)
    assert not (tmp_path / "metadata" / "data" / "data-01.md").exists()
    new_text = (tmp_path / "metadata" / "data" / "run-60c.md").read_text(encoding="utf-8")
    assert "id: run-60c" in new_text and "description" in new_text
    # minimal 项目里 fact-01 引用 data-01：改写计划含 1 重命名 + 1 引用同步
    assert [p.name for p in result.written] == ["run-60c.md", "fact-01.md"]
    assert result.bib_status is None


def test_apply_updates_card_refs_and_part_uses(tmp_path):
    make_minimal_project(tmp_path)
    project, _ = load_project(tmp_path)
    part_file = tmp_path / "narrative" / "01-results" / "part-01.md"
    part_file.write_text(part_file.read_text(encoding="utf-8")
                         + "\n审阅备注：正文保留检查。\n", encoding="utf-8")
    plan = plan_rename(project, "fact-01", "temp-rate")
    apply_rename(project, plan)
    project2, diags = load_project(tmp_path)
    assert not any(d.is_error for d in diags)
    assert project2.facts["temp-rate"].statement == "温度提高速率。"
    assert "fact-01" not in project2.card_paths
    node = project2.parts[0].nodes[0]
    assert [(u.id, u.role) for u in node.uses] == [("temp-rate", "evidence")]
    raw = part_file.read_text(encoding="utf-8")
    assert "审阅备注：正文保留检查。" in raw   # part 正文原样保留


def test_apply_updates_cites_and_derived_from_on_note_rename(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "claims" / "cited", "claim-02",
               {"id": "claim-02", "claim_type": "cited", "statement": "引用陈述",
                "cites": ["key2020"], "status": "approved"})
    write_card(tmp_path / "metadata" / "methods", "qpcr",
               {"id": "qpcr", "statement": "m", "protocol": "p",
                "derived_from": ["key2020"], "status": "approved"})
    project, _ = load_project(tmp_path)
    plan = plan_rename(project, "key2020", "key2021")
    assert plan.card_refs == {"claim-02": ["cites"], "qpcr": ["derived_from"]}
    apply_rename(project, plan)
    project2, _ = load_project(tmp_path)
    assert project2.claims["claim-02"].cites == ["key2021"]
    assert project2.methods["qpcr"].derived_from == ["key2021"]


def test_apply_updates_param_method_ref(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "methods", "qpcr",
               {"id": "qpcr", "statement": "m", "protocol": "p", "status": "approved"})
    write_card(tmp_path / "metadata" / "methods" / "params", "p1",
               {"id": "p1", "method": "qpcr", "status": "approved"})
    project, _ = load_project(tmp_path)
    plan = plan_rename(project, "qpcr", "qpcr-3step")
    assert plan.card_refs == {"p1": ["method"]}
    apply_rename(project, plan)
    project2, _ = load_project(tmp_path)
    assert project2.params["p1"].method == "qpcr-3step"
    assert not (tmp_path / "metadata" / "methods" / "qpcr.md").exists()
    assert (tmp_path / "metadata" / "methods" / "qpcr-3step.md").exists()


def test_apply_managed_note_syncs_bib(tmp_path):
    from tests.helpers import make_managed_project
    make_managed_project(tmp_path)
    write_card(tmp_path / "metadata" / "claims" / "cited", "claim-02",
               {"id": "claim-02", "claim_type": "cited", "statement": "引用陈述",
                "cites": ["key2020"], "status": "approved"})
    project, _ = load_project(tmp_path)
    plan = plan_rename(project, "key2020", "key2021")
    assert plan.needs_bib_sync is True
    result = apply_rename(project, plan)
    assert result.bib_status == "bib_updated"
    bib = (tmp_path / "references.bib").read_text(encoding="utf-8")
    assert "key2021" in bib and "key2020" not in bib
