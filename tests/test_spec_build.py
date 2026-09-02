"""叙事 part → spec + tasklist（通道②）的确定性构造。"""
import pytest

from module_harness import HarnessConfig, HarnessRegistry, OutputFormat, TasklistValidator

from tests.helpers import build_project
from weft.engine.spec_build import build_spec, build_tasklist, entity_bundle
from weft.models.cards import (
    ClaimCard,
    DataCard,
    FactCard,
    MethodCard,
    NoteCard,
    ParamCard,
)
from weft.models.narrative import NarrativePart, Node, Use


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
    return NarrativePart(id="sec-01", section="Results",
                            nodes=[approved, draft])


def test_build_spec_filters_non_approved():
    spec = build_spec(_project(), _section())
    assert set(spec["nodes"]) == {"para-01-01"}
    assert spec["task_nodes"] == {"p01": "para-01-01"}
    assert spec["part"] == {"id": "sec-01", "title": "Results"}


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
    assert tasklist.flow == "[p01] --> AL\nAL --> V"   # 多行：tickflow 起始标记行只允许一条边
    assert tasklist.tasks["p01"].harness == "draft_para"
    assert tasklist.tasks["p01"].outputformat == {"type": "json_object"}
    assert tasklist.tasks["AL"].harness == "align_check"
    assert tasklist.tasks["AL"].inputs == {"spec": "{spec}", "tasklist": "{tasklist}",
                                           "node": "{node}", "d1": "p01"}
    assert tasklist.tasks["V"].script == "weft_validate_draft"


def test_build_tasklist_flow_without_align():
    tasklist = build_tasklist(build_spec(_project(), _section()), align=False)
    assert tasklist.flow == "[p01] --> V"
    assert "AL" not in tasklist.tasks


def test_para_prompt_embeds_entity_json():
    tasklist = build_tasklist(build_spec(_project(), _section()), align=False)
    prompt = tasklist.tasks["p01"].prompt
    assert "describe" in prompt
    assert "先主结果" in prompt
    assert "温度提高速率。" in prompt       # 实体全文进 prompt
    assert "文献概括。" in prompt           # claim 所引 note 的 summary 进 prompt


def test_build_spec_filters_draft_entities():
    project = _project()
    project.facts["fact-draft"] = FactCard(id="fact-draft", status="draft",
                                           data=["data-01"], statement="草稿事实。")
    section = NarrativePart(
        id="sec-01", section="Results",
        nodes=[Node(id="para-01-01", purpose="describe",
                    uses=[Use(id="fact-draft", role="evidence"),
                          Use(id="fact-01", role="evidence")],
                    status="approved")])
    spec = build_spec(project, section)
    node = spec["nodes"]["para-01-01"]
    assert node["uses"] == [{"id": "fact-01", "role": "evidence"}]   # draft 实体被过滤
    assert [e["id"] for e in node["entities"]] == ["fact-01"]


def test_approved_node_empty_uses():
    section = NarrativePart(
        id="sec-01", section="Results",
        nodes=[Node(id="para-01-01", purpose="describe", uses=[], status="approved")])
    spec = build_spec(_project(), section)
    node = spec["nodes"]["para-01-01"]
    assert node["uses"] == []
    assert node["entities"] == []
    tasklist = build_tasklist(spec, align=False)
    assert tasklist.flow == "[p01] --> V"


def test_tasklist_passes_real_validator():
    """Task 3 → Task 6 契约：构造出的 tasklist 通过真实 SpecModule validator。"""
    def _stub_registry() -> HarnessRegistry:
        reg = HarnessRegistry(llm_client=None)
        reg.harness("draft_para", HarnessConfig(
            prompt_core="写段落。{spec}", output_format=OutputFormat(type="json_object")))
        reg.harness("align_check", HarnessConfig(
            prompt_core="对齐检查。{spec}", output_format=OutputFormat(type="json_object")))

        @reg.script("weft_validate_draft")
        def _validate(view) -> dict:
            return {}
        return reg

    section = NarrativePart(
        id="sec-01", section="Results",
        nodes=[Node(id="para-01-01", purpose="describe", uses=[], status="approved"),
               Node(id="para-01-02", purpose="interpret", uses=[], status="approved")])
    tasklist = build_tasklist(build_spec(_project(), section), align=True)
    errors = TasklistValidator.validate(tasklist, _stub_registry())
    assert errors == []


def _part():
    approved = Node(id="para-01-01", purpose="describe",
                    uses=[Use(id="fact-01", role="evidence"),
                          Use(id="claim-01", role="conclusion")],
                    logic="先主结果", status="approved")
    draft = Node(id="para-01-02", purpose="interpret", uses=[], status="draft")
    return NarrativePart(id="sec-01", section="Results",
                         nodes=[approved, draft])


def _project_with_methods():
    project = _project()
    project.methods["qpcr"] = MethodCard(id="qpcr", statement="qPCR 定量",
                                         protocol="1. 提取 DNA\n2. 体系配置与扩增",
                                         status="approved")
    project.params["qpcr-main"] = ParamCard(id="qpcr-main", method="qpcr",
                                            values={"instrument": "QuantStudio 5"},
                                            status="approved")
    return project


def test_entity_bundle_method_carries_protocol():
    bundle = entity_bundle(_project_with_methods(), "qpcr")
    assert bundle == {"id": "qpcr", "kind": "method", "statement": "qPCR 定量",
                      "protocol": "1. 提取 DNA\n2. 体系配置与扩增",
                      "derived_from": []}


def test_entity_bundle_param_carries_values_and_method_summary():
    # §3.3：method.protocol + param.values 一起进 prompt——param bundle 内嵌 method 概要
    bundle = entity_bundle(_project_with_methods(), "qpcr-main")
    assert bundle["kind"] == "param"
    assert bundle["values"] == {"instrument": "QuantStudio 5"}
    assert bundle["method"] == {"id": "qpcr", "statement": "qPCR 定量",
                                "protocol": "1. 提取 DNA\n2. 体系配置与扩增"}


def test_build_spec_filters_draft_methods():
    # §3.10 延续：approved 过滤覆盖 method/param
    project = _project_with_methods()
    project.methods["m-draft"] = MethodCard(id="m-draft", statement="草稿",
                                            protocol="x", status="draft")
    part = NarrativePart(id="sec-01", section="R", nodes=[
        Node(id="para-01-01", purpose="describe",
             uses=[Use(id="m-draft", role="evidence"),
                   Use(id="qpcr", role="evidence")], status="approved")])
    node = build_spec(project, part)["nodes"]["para-01-01"]
    assert [e["id"] for e in node["entities"]] == ["qpcr"]


def test_preceding_paragraph_alias_injection():
    # v1.1 §4.4：part 内前文经 inputs 别名注入后续段落；首段无前文
    part = NarrativePart(id="sec-01", section="R", nodes=[
        Node(id="para-01-01", purpose="describe", uses=[], status="approved"),
        Node(id="para-01-02", purpose="interpret", uses=[], status="approved")])
    tasklist = build_tasklist(build_spec(_project(), part), align=False)
    p01, p02 = tasklist.tasks["p01"], tasklist.tasks["p02"]
    assert "前文" not in p01.prompt
    assert not p01.inputs
    assert "{p01}" in p02.prompt
    assert "仅供衔接，不得复述" in p02.prompt
    assert p02.inputs == {"p01": "p01"}


def test_temperature_follows_workflow():
    part = NarrativePart(id="sec-01", section="M", nodes=[
        Node(id="para-01-01", purpose="describe", uses=[], status="approved")])
    tasklist = build_tasklist(build_spec(_project(), part, "methods"), align=False)
    assert tasklist.tasks["p01"].temperature == 0.2
