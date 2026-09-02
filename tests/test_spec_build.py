"""叙事节 → spec + tasklist（通道②）的确定性构造。"""
import pytest

from tests.helpers import build_project
from weft.engine.spec_build import build_spec, build_tasklist, entity_bundle
from weft.models.cards import ClaimCard, DataCard, FactCard, NoteCard
from weft.models.narrative import NarrativeSection, Node, Use


def _project():
    return build_project(
        data=[DataCard(id="data-01", status="approved", refs=[],
                       source="../../data/run3.csv", description="速率测量")],
        facts=[FactCard(id="fact-01", status="approved", data=["data-01"],
                        statement="温度提高速率。")],
        claims=[ClaimCard(id="claim-01", claim_type="cited", status="approved",
                          statement="温度有正效应。", cites=["key2020"])],
        notes=[NoteCard(id="key2020", status="approved", summary="文献概括。")],
        bib_keys={"key2020"},
    )


def _section():
    approved = Node(id="para-01-01", purpose="describe",
                    uses=[Use(id="fact-01", role="evidence"),
                          Use(id="claim-01", role="conclusion")],
                    logic="先主结果", status="approved")
    draft = Node(id="para-01-02", purpose="interpret", uses=[], status="draft")
    return NarrativeSection(id="sec-01", section="Results", order=1,
                            nodes=[approved, draft])


def test_build_spec_filters_non_approved():
    spec = build_spec(_project(), _section())
    assert set(spec["nodes"]) == {"para-01-01"}
    assert spec["task_nodes"] == {"p01": "para-01-01"}
    assert spec["section"] == {"id": "sec-01", "title": "Results", "order": 1}


def test_entity_bundle_fact_carries_data_description():
    bundle = entity_bundle(_project(), "fact-01")
    assert bundle["kind"] == "fact"
    assert bundle["statement"] == "温度提高速率。"
    assert bundle["data"] == [{"id": "data-01", "description": "速率测量",
                               "source": "../../data/run3.csv"}]


def test_entity_bundle_claim_carries_cites_and_note_summaries():
    bundle = entity_bundle(_project(), "claim-01")
    assert bundle["claim_type"] == "cited"
    assert bundle["cites"] == ["key2020"]
    assert bundle["note_summaries"] == [{"key": "key2020", "summary": "文献概括。"}]


def test_entity_bundle_rejects_note_and_unknown():
    project = _project()
    with pytest.raises(ValueError):
        entity_bundle(project, "key2020")   # uses 只准 fact/claim（spec §2）
    with pytest.raises(ValueError):
        entity_bundle(project, "ghost")


def test_build_tasklist_flow_with_align():
    tasklist = build_tasklist(build_spec(_project(), _section()), align=True)
    assert tasklist.flow == "p01 --> AL --> V"
    assert tasklist.tasks["p01"].harness == "draft_para"
    assert tasklist.tasks["p01"].outputformat == {"type": "json_object"}
    assert tasklist.tasks["AL"].harness == "align_check"
    assert tasklist.tasks["AL"].inputs == {"d1": "p01"}
    assert tasklist.tasks["V"].script == "weft_validate_draft"


def test_build_tasklist_flow_without_align():
    tasklist = build_tasklist(build_spec(_project(), _section()), align=False)
    assert tasklist.flow == "p01 --> V"
    assert "AL" not in tasklist.tasks


def test_para_prompt_embeds_entity_json():
    tasklist = build_tasklist(build_spec(_project(), _section()), align=False)
    prompt = tasklist.tasks["p01"].prompt
    assert "describe" in prompt
    assert "先主结果" in prompt
    assert "温度提高速率。" in prompt       # 实体全文进 prompt
    assert "文献概括。" in prompt           # claim 所引 note 的 summary 进 prompt
