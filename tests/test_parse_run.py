"""parse 管线运行（复用 pipeline 提炼件）：fail-closed、快照位置、双模式注入、超长提醒。"""
import pytest

from weft.engine.parse.run import LONG_TEXT_CHARS, ParseError, run_parse
from tests.helpers import build_project
from weft.models.cards import ClaimCard, DataCard, FactCard, NoteCard

LOGIC_JSON = '{"issues": []}'
EXTRACT_JSON = ('{"summary": "本文研究了搅拌对溶解的影响。",'
                ' "cards": [{"key": "f1", "kind": "fact", "statement": "升温加速"},'
                ' {"key": "c1", "kind": "claim", "statement": "催化是主因",'
                ' "needs_citation": true}], "links": [{"from": "f1", "to": "c1"}]}')
REVIEW_JSON = ('{"classifications": [{"key": "f1", "verdict": "new"},'
               ' {"key": "c1", "verdict": "new"}],'
               ' "note": {"verdict": "new", "reason": "", "merged_summary": ""}}')
MATCH_JSON = ('{"fact_data": [{"key": "f1", "data_ids": ["data-01"]}],'
              ' "claim_cites": [{"key": "c1", "claim_type": "cited",'
              ' "cites": ["key2020"]}], "placeholders": []}')
COVER_JSON = '{"coverage": []}'


class FakeParseClient:
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


def _client(**overrides) -> FakeParseClient:
    responses = {"【文章·逻辑核查】": LOGIC_JSON,
                 "【文章·卡片拆解】": EXTRACT_JSON,
                 "【文章·现有卡审查】": REVIEW_JSON,
                 "【文章·匹配】": MATCH_JSON,
                 "【文章·成卡覆盖】": COVER_JSON}
    responses.update(overrides)
    return FakeParseClient(responses)


def _project(root=None):
    return build_project(root=root,
        data=[DataCard(id="data-01", refs=["fig-01a"], description="速率测量",
                       status="approved")],
        facts=[FactCard(id="fact-01", data=["data-01"], statement="温度提高速率。",
                        status="approved")],
        claims=[ClaimCard(id="claim-01", claim_type="uncited",
                          statement="温度有正效应。", status="approved")],
        notes=[NoteCard(id="key2020", summary="热激活机制。", status="approved")],
        bib_keys={"key2020"})


def test_run_parse_parses_all_node_outputs():
    client = _client()
    result = run_parse(_project(), "一篇关于升温的文章。", client=client)
    assert result.logic.issues == []
    assert result.extract.summary == "本文研究了搅拌对溶解的影响。"
    assert [c.key for c in result.extract.cards] == ["f1", "c1"]
    match_prompt = next(p for p in client.prompts if "【文章·匹配】" in p)
    assert "fact-01" in match_prompt   # digest 注入


def test_literature_mode_injects_bib_key_and_note_review():
    client = _client()
    run_parse(_project(), "文章", client=client, bib_key="key2020")
    match_prompt = next(p for p in client.prompts if "【文章·匹配】" in p)
    assert '"key2020"' in match_prompt          # 次级引用默认值注入
    review_prompt = next(p for p in client.prompts if "【文章·现有卡审查】" in p)
    assert "unchanged" in review_prompt         # note 三档判定指令


def test_run_parse_shape_failure_is_fail_closed():
    client = _client(**{"【文章·匹配】": "这不是 JSON"})
    with pytest.raises(ParseError, match="E-ARTICLE-SHAPE"):
        run_parse(_project(), "文章", client=client)


def test_run_parse_infra_failure_maps_to_failed():
    client = FakeParseClient({}, boom=True)
    with pytest.raises(ParseError, match="E-ARTICLE-FAILED"):
        run_parse(_project(), "文章", client=client)


def test_run_parse_missing_node_output_is_failed():
    full = {"【文章·逻辑核查】": LOGIC_JSON, "【文章·卡片拆解】": EXTRACT_JSON,
            "【文章·现有卡审查】": REVIEW_JSON, "【文章·匹配】": MATCH_JSON,
            "【文章·成卡覆盖】": COVER_JSON}
    client = FakeParseClient({k: v for k, v in full.items() if k != "【文章·匹配】"})
    with pytest.raises(ParseError, match="E-ARTICLE-FAILED"):
        run_parse(_project(), "文章", client=client)


def test_run_persists_checkpoints_and_no_root_residue(tmp_path):
    from module_harness.infra.query import load_snapshot_summary

    project = _project(tmp_path)
    result = run_parse(project, "文章", client=_client(), source="paper.md")
    assert result.run_id == "weft-parse-paper"
    summary = load_snapshot_summary(
        result.run_id, base_dir=project.root / "generated" / "articles" / ".runs")
    assert summary is not None
    assert set(summary["outputs"]) >= {"p01", "p02", "p03", "p04"}
    assert not (project.root / ".specmodule").exists()


def test_run_resumes_from_checkpoint_after_failure(tmp_path):
    project = _project(tmp_path)
    flaky = _client(**{"【文章·匹配】": "这不是 JSON",
                       "【文章·成卡覆盖】": "这不是 JSON"})
    with pytest.raises(ParseError):
        run_parse(project, "文章", client=flaky, source="paper.md")

    second = _client()
    result = run_parse(project, "文章", client=second, source="paper.md")
    assert result.resumed is True
    assert result.match.fact_data[0].data_ids == ["data-01"]
    # 断点续跑：P1–P3 不再调用 LLM
    assert not any("逻辑核查" in p for p in second.prompts)
    assert any("匹配" in p for p in second.prompts)


def test_run_fresh_after_completed_run(tmp_path):
    project = _project(tmp_path)
    run_parse(project, "文章", client=_client(), source="paper.md")
    second = _client()
    result = run_parse(project, "文章", client=second, source="paper.md")
    assert result.resumed is False
    assert len(second.prompts) == 5


def test_run_fresh_restart_when_first_node_failed(tmp_path):
    """P8 分支覆盖：首节点即失败（leading==0）→ 重跑清场全新运行。"""
    project = _project(tmp_path)
    flaky = _client(**{"【文章·逻辑核查】": "这不是 JSON"})
    with pytest.raises(ParseError):
        run_parse(project, "文章", client=flaky, source="paper.md")

    second = _client()
    result = run_parse(project, "文章", client=second, source="paper.md")
    assert result.resumed is False           # 清场重跑，不是续跑
    assert len(second.prompts) == 5          # 全部节点重算


def test_run_rejects_concurrent_rerun(tmp_path, monkeypatch):
    """P8 分支覆盖：上次运行 phase=running 时拒绝并发重跑。"""
    from types import SimpleNamespace

    import weft.engine.pipeline as pipeline_mod

    project = _project(tmp_path)
    flaky = _client(**{"【文章·成卡覆盖】": "这不是 JSON"})
    with pytest.raises(ParseError):
        run_parse(project, "文章", client=flaky, source="paper.md")
    # 中途失败的快照存在（p01–p04 已完成）——把状态查询 stub 成 running
    monkeypatch.setattr(pipeline_mod, "query_run_status",
                        lambda *a, **kw: SimpleNamespace(phase="running"))
    with pytest.raises(ParseError, match="不接受并发重跑"):
        run_parse(project, "文章", client=_client(), source="paper.md")


def test_long_text_warns_but_runs():
    client = _client()
    result = run_parse(_project(), "x" * (LONG_TEXT_CHARS + 1), client=client)
    assert len(result.warnings) == 1
    assert "W-ARTICLE-LONG" in result.warnings[0]
    assert result.run_id   # 管线照常完成（不阻断不分块）
