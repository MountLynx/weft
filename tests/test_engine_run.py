"""run_draft v2 端到端（ScriptedLLMClient，免 key、零落盘）：覆盖链 + 填充。"""
import pytest

from tests.helpers import make_minimal_project
from weft.store.loader import load_project
from weft.engine import run as draft_run
from weft.engine.clients import ScriptedLLMClient
from weft.engine.draft_rules import DraftError, DraftRuleError


def test_harnesses_register_with_raised_max_tokens():
    """推理模型思考 token 会耗尽默认 4096 输出上限（e2e 实测 finish=length
    且 content 空）；四个 harness 均须经 api_params 抬高 max_tokens。"""
    recorded = {}

    class StubReg:
        def harness(self, name, cfg):
            recorded[name] = cfg

        def script(self, name):
            return lambda fn: None

    draft_run._register_harnesses(StubReg(), {"prompt_core": "", "temperature": 0.55})
    assert set(recorded) == {"draft_gen", "draft_check", "draft_link",
                             "draft_polish"}
    for cfg in recorded.values():
        assert cfg.api_params == {"max_tokens": 32768}
    # §4.3 温度梯度接线：draft_gen 消费 workflow 温度（v2 曾硬编码 0.4 使梯度失效）
    assert recorded["draft_gen"].temperature == 0.55


def test_run_draft_mock_generates_and_fills(tmp_path):
    project, _ = load_project(make_minimal_project(tmp_path))
    part = project.parts[0]
    result = draft_run.run_draft(project, part, part.nodes[0],
                                 client=ScriptedLLMClient(), overview="总述")
    assert "（mock 段落）" in result.paragraph
    assert "Fig. 1a" in result.paragraph            # fact-01 → data-01 → fig-01a
    assert "{{" not in result.paragraph             # uses 内只有 fact-01，无 claim 占位
    assert result.node_id == "para-01-01"


def test_run_draft_check_fix_overrides(tmp_path):
    project, _ = load_project(make_minimal_project(tmp_path))
    part = project.parts[0]
    client = ScriptedLLMClient(check_fix="修正后 {{fact-01}}。")
    result = draft_run.run_draft(project, part, part.nodes[0], client=client)
    assert result.paragraph.startswith("修正后")
    assert "Fig. 1a" in result.paragraph


def test_run_draft_gen_broken_is_fail_closed(tmp_path):
    project, _ = load_project(make_minimal_project(tmp_path))
    part = project.parts[0]
    with pytest.raises(DraftRuleError, match="E-DRAFT-SHAPE"):
        draft_run.run_draft(project, part, part.nodes[0],
                            client=ScriptedLLMClient(broken=True))


def test_run_draft_infra_failure_maps_to_failed(tmp_path):
    class BoomClient:
        async def complete(self, **kw):
            raise RuntimeError("网络炸了")

    project, _ = load_project(make_minimal_project(tmp_path))
    part = project.parts[0]
    with pytest.raises(DraftError, match="E-DRAFT-FAILED"):
        draft_run.run_draft(project, part, part.nodes[0], client=BoomClient())
