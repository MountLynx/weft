"""run_draft 端到端（ScriptedLLMClient，免 key、零落盘）。"""
import pytest

from tests.helpers import build_project
from weft.engine.clients import ScriptedLLMClient
from weft.engine.draft_rules import DraftRuleError
from weft.engine.run import DraftError, run_draft
from weft.models.cards import ClaimCard, FactCard
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
