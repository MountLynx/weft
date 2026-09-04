"""inspire 管线运行（通道②零残留）：四节点顺序、fail-closed、输出解析。"""
import pytest

from weft.engine.inspire.run import InspireError, run_inspire
from weft.store.project import Project
from tests.helpers import build_project
from weft.models.cards import ClaimCard, DataCard, FactCard, NoteCard

LOGIC_JSON = '{"issues": ["跳跃结论"]}'
EXTRACT_JSON = ('{"cards": [{"key": "f1", "kind": "fact", "statement": "升温加速"},'
                ' {"key": "c1", "kind": "claim", "statement": "催化是主因",'
                ' "needs_citation": true}], "links": [{"from": "f1", "to": "c1"}]}')
REVIEW_JSON = ('{"classifications": [{"key": "f1", "verdict": "new"},'
               ' {"key": "c1", "verdict": "conflict", "against": ["claim-01"],'
               ' "reason": "方向相反"}]}')
MATCH_JSON = ('{"fact_data": [{"key": "f1", "data_ids": ["data-01"]}],'
              ' "claim_cites": [{"key": "c1", "claim_type": "cited",'
              ' "cites": []}], "placeholders": []}')


class FakeInspireClient:
    """按 prompt 标记分流的假客户端（tests 层豁免分层）。"""

    def __init__(self, responses: dict[str, str], boom: bool = False):
        self.responses = responses
        self.boom = boom
        self.prompts: list[str] = []

    async def complete(self, **kwargs):
        prompt = kwargs.get("prompt") or ""
        self.prompts.append(prompt)
        if self.boom:
            raise RuntimeError("网络炸了")
        for marker, content in self.responses.items():
            if marker in prompt:
                from llm.client import LLMResponse
                return LLMResponse(content=content, usage={}, finish_reason="end_turn")
        raise AssertionError(f"未预期的 prompt：{prompt[:60]}")


def _client(**overrides) -> FakeInspireClient:
    responses = {"【灵感·逻辑核查】": LOGIC_JSON,
                 "【灵感·卡片拆解】": EXTRACT_JSON,
                 "【灵感·现有卡审查】": REVIEW_JSON,
                 "【灵感·匹配】": MATCH_JSON}
    responses.update(overrides)
    return FakeInspireClient(responses)


def _project(root=None) -> Project:
    return build_project(root=root, 
        data=[DataCard(id="data-01", refs=["fig-01a"], description="速率测量",
                       status="approved")],
        facts=[FactCard(id="fact-01", data=["data-01"], statement="温度提高速率。",
                        status="approved")],
        claims=[ClaimCard(id="claim-01", claim_type="uncited",
                          statement="温度有正效应。", status="approved")],
        notes=[NoteCard(id="key2020", summary="热激活机制。", status="approved")],
        bib_keys={"key2020"})


def test_harnesses_register_with_raised_max_tokens():
    """真实推理模型思考 token 会耗尽默认 4096 输出上限（e2e 实测 finish=length
    且 content 空）；inspire harness 必须经 api_params 抬高 max_tokens。"""
    from weft.engine.inspire import run as inspire_run

    recorded = []

    class StubReg:
        def harness(self, name, cfg):
            recorded.append((name, cfg))

    inspire_run._register_harnesses(StubReg())
    assert [name for name, _ in recorded] == list(inspire_run._HARNESS_CORES)
    for _, cfg in recorded:
        assert cfg.api_params == {"max_tokens": 32768}


def test_run_inspire_parses_all_node_outputs():
    client = _client()
    result = run_inspire(_project(), "随手记：升温加速。", client=client)
    assert result.logic.issues == ["跳跃结论"]
    assert [c.key for c in result.extract.cards] == ["f1", "c1"]
    assert result.review.classifications[1].verdict == "conflict"
    assert result.match.fact_data[0].data_ids == ["data-01"]
    review_prompt = next(p for p in client.prompts if "现有卡审查" in p)
    assert "fact-01" in review_prompt and "热激活机制。" in review_prompt  # digest 注入


def test_run_inspire_shape_failure_is_fail_closed():
    client = _client(**{"【灵感·匹配】": "这不是 JSON"})
    with pytest.raises(InspireError, match="E-INSPIRE-SHAPE"):
        run_inspire(_project(), "随手记", client=client)


def test_run_inspire_infra_failure_maps_to_failed():
    client = FakeInspireClient({}, boom=True)
    with pytest.raises(InspireError, match="E-INSPIRE-FAILED"):
        run_inspire(_project(), "随手记", client=client)


def test_run_inspire_missing_node_output_is_failed():
    responses = {"【灵感·逻辑核查】": LOGIC_JSON, "【灵感·卡片拆解】": EXTRACT_JSON,
                 "【灵感·现有卡审查】": REVIEW_JSON, "【灵感·匹配】": MATCH_JSON}
    client = FakeInspireClient({k: v for k, v in responses.items()
                                if k != "【灵感·匹配】"})
    with pytest.raises(InspireError, match="E-INSPIRE-FAILED"):
        run_inspire(_project(), "随手记", client=client)


def _runs_dir(project: Project):
    from module_harness.query import load_snapshot_summary
    return project.root / "generated" / "inspirations" / ".runs"


def test_run_persists_checkpoints_and_no_root_residue(tmp_path):
    """persist 接入：快照落 generated/inspirations/.runs/，项目根零 .specmodule。"""
    from module_harness.query import load_snapshot_summary

    project = _project(tmp_path)
    result = run_inspire(project, "随手记", client=_client(), source="idea.md")
    assert result.module_id == "weft-inspire-idea"
    summary = load_snapshot_summary(
        result.module_id, base_dir=_runs_dir(project))
    assert summary is not None
    assert set(summary["outputs"]) >= {"t01", "t02", "t03", "t04"}
    assert not (project.root / ".specmodule").exists()


def test_run_resumes_from_checkpoint_after_failure(tmp_path):
    """t04 失败后重跑同一灵感：只补跑失败节点，已完成节点不重算。"""
    project = _project(tmp_path)
    flaky = _client(**{"【灵感·匹配】": "这不是 JSON"})
    with pytest.raises(InspireError):
        run_inspire(project, "随手记", client=flaky, source="idea.md")

    second = _client()
    result = run_inspire(project, "随手记", client=second, source="idea.md")
    assert result.resumed is True
    assert result.match.fact_data[0].data_ids == ["data-01"]
    # 断点续跑：T1–T3 不再调用 LLM
    assert not any("逻辑核查" in p for p in second.prompts)
    assert any("匹配" in p for p in second.prompts)


def test_run_fresh_after_completed_run(tmp_path):
    """成功后的同灵感重跑 = 全新运行（清场重跑，不续跑）。"""
    project = _project(tmp_path)
    run_inspire(project, "随手记", client=_client(), source="idea.md")
    second = _client()
    result = run_inspire(project, "随手记", client=second, source="idea.md")
    assert result.resumed is False
    assert len([p for p in second.prompts]) == 4
