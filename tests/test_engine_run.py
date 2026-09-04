"""run_draft 端到端（ScriptedLLMClient，免 key、零落盘）。"""
import pytest

from tests.helpers import build_project
from weft.engine.clients import ScriptedLLMClient
from weft.engine.draft_rules import DraftRuleError
from weft.engine.run import DraftError, run_draft
from weft.models.cards import ClaimCard, FactCard, MethodCard, ParamCard
from weft.models.narrative import NarrativePart, Node, Use

SEC = "sec-01"


def _project(bib=("key2020",), claim_cites=("key2020",)):
    return build_project(
        facts=[FactCard(id="fact-01", status="approved", data=["data-01"],
                        statement="温度提高速率。")],
        claims=[ClaimCard(id="claim-01", claim_type="cited", status="approved",
                          statement="s", cites=list(claim_cites))],
        bib_keys=set(bib),
    )


def _section(n_approved=2):
    nodes = [
        Node(id=f"para-01-{i:02d}", purpose="describe",
             uses=[Use(id="fact-01", role="evidence"),
                   Use(id="claim-01", role="conclusion")],
             logic="", status="approved")
        for i in range(1, n_approved + 1)
    ]
    return NarrativePart(id=SEC, section="Results", nodes=nodes)


def test_run_draft_end_to_end_two_paragraphs():
    result = run_draft(_project(), _section(), client=ScriptedLLMClient())
    assert set(result.drafts_by_node) == {"para-01-01", "para-01-02"}
    assert result.drafts_by_node["para-01-01"]["paragraph"] == "（mock 段落）正文。"
    assert len(result.run_id) == 8
    assert result.reminders == []


def test_run_draft_prompt_carries_entities():
    client = ScriptedLLMClient()
    run_draft(_project(), _section(n_approved=1), client=client)
    para_prompts = [p for p in client.prompts if "对齐检查器" not in p]
    assert len(para_prompts) == 1
    assert "温度提高速率。" in para_prompts[0]      # 实体全文注入（决策 8）


def test_run_draft_collects_soft_reminders():
    client = ScriptedLLMClient(cites=["keyother"])
    result = run_draft(_project(bib=("key2020", "keyother")),
                       _section(n_approved=1), client=client)
    assert any("W-CITE-NOT-IN-CLAIM" in r for r in result.reminders)


def test_run_draft_hard_rule_aborts():
    client = ScriptedLLMClient(uses=["claim-99"])
    with pytest.raises(DraftRuleError) as excinfo:
        run_draft(_project(), _section(n_approved=1), client=client)
    assert excinfo.value.diagnostic.code == "E-USES-BEYOND-NODE"


def test_run_draft_broken_output_shape():
    with pytest.raises(DraftRuleError) as excinfo:
        run_draft(_project(), _section(n_approved=1),
                  client=ScriptedLLMClient(broken=True))
    assert excinfo.value.diagnostic.code == "E-DRAFT-SHAPE"


def test_run_draft_without_align_skips_align_node():
    client = ScriptedLLMClient()
    run_draft(_project(), _section(n_approved=1), client=client, align=False)
    assert not any("对齐检查器" in p for p in client.prompts)


def test_run_draft_infrastructure_failure_wraps_draft_error():
    from llm.client import LLMError

    class _DeadClient:
        async def complete(self, **kwargs):
            raise LLMError("网络超时")

    with pytest.raises(DraftError) as excinfo:
        run_draft(_project(), _section(n_approved=1), client=_DeadClient())
    assert "E-DRAFT-FAILED" in str(excinfo.value)


def test_run_draft_align_rejection_fails_run():
    client = ScriptedLLMClient(aligned=False)
    with pytest.raises(DraftError) as excinfo:
        run_draft(_project(), _section(n_approved=1), client=client)
    assert "对齐检查未通过" in str(excinfo.value)


def test_run_draft_nothing_to_draft():
    section = NarrativePart(id=SEC, section="Results", nodes=[])
    with pytest.raises(DraftError) as excinfo:
        run_draft(_project(), section, client=ScriptedLLMClient())
    assert "E-NOTHING-TO-DRAFT" in str(excinfo.value)


def test_run_draft_methods_workflow_routes_prompt_and_skips_cites():
    project = build_project(
        methods=[MethodCard(id="qpcr", statement="qPCR 定量", protocol="1. 提取",
                            status="approved")],
        params=[ParamCard(id="qpcr-main", method="qpcr",
                          values={"instrument": "QS5"}, status="approved")],
        bib_keys=set())
    part = NarrativePart(id=SEC, section="Methods", nodes=[
        Node(id="para-01-01", purpose="describe",
             uses=[Use(id="qpcr-main", role="evidence")], status="approved")])
    client = ScriptedLLMClient(cites=["ghost2020"])
    result = run_draft(project, part, client=client, align=False,
                       workflow="methods")
    assert result.reminders == []                 # methods 裁剪引文规则
    assert "操作协议" in client.prompts[0]        # methods prompt_core 路由
    assert "1. 提取" in client.prompts[0]         # param bundle 内嵌 method 概要


def test_run_draft_results_workflow_keeps_cite_reminder():
    # ghost2020 在 bib（规则 1 过）但不在 claim cites（规则 2 提醒）——
    # results 工作流保留软提醒（对照 methods 版本：同一 ghost cite 静默通过）。
    client = ScriptedLLMClient(cites=["ghost2020"])
    result = run_draft(_project(bib=("key2020", "ghost2020")),
                       _section(n_approved=1),
                       client=client, align=False, workflow="results")
    assert any("W-CITE-NOT-IN-CLAIM" in r for r in result.reminders)


def test_run_draft_passes_preceding_paragraph_to_successor():
    # Task 7 评审约定：前文 JSON 经 view 注入的端到端证据——p02 渲染后的
    # prompt 里应出现 p01 的输出文本（ScriptedLLMClient 收到的已是渲染后 prompt）
    client = ScriptedLLMClient()
    run_draft(_project(), _section(n_approved=2), client=client, align=False)
    assert len(client.prompts) == 2
    assert "（mock 段落）正文。" in client.prompts[1]


def test_draft_harnesses_raise_max_tokens():
    """推理模型思考 token 会耗尽默认 4096 输出上限（e2e 实测 finish=length
    且 content 空）；draft/align harness 均须经 api_params 抬高 max_tokens。"""
    from weft.engine import run as draft_run

    recorded = {}

    class StubReg:
        def harness(self, name, cfg):
            recorded[name] = cfg

        def script(self, name):
            return lambda fn: None

    draft_run._register_harnesses(StubReg(), {"prompt_core": "", "temperature": 0.5}, align=True)
    assert "draft_para" in recorded and "align_check" in recorded
    for name in ("draft_para", "align_check"):
        assert recorded[name].api_params == {"max_tokens": 32768}
