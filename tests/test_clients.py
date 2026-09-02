"""LLM 客户端选择：ScriptedLLMClient 免 key 管线；真实客户端走 .env/环境变量。"""
import asyncio
import json

import pytest

from weft.engine.clients import ScriptedLLMClient, make_client
from weft.engine.draft_rules import DraftError


def _complete(client, **kwargs):
    return asyncio.run(client.complete(**kwargs))


def test_scripted_returns_draft_shape_and_records_prompt():
    client = ScriptedLLMClient(paragraph="_mock_段。")
    resp = _complete(client, prompt="你是学术写作引擎 weft 的行文器。任务提示",
                     output_format={"type": "json_object"})
    assert json.loads(resp.content) == {"paragraph": "_mock_段。", "uses": [], "cites": []}
    assert client.prompts == ["你是学术写作引擎 weft 的行文器。任务提示"]


def test_scripted_aligned_for_align_prompt():
    client = ScriptedLLMClient()
    resp = _complete(client, prompt="你是对齐检查器。判断当前节点产出是否偏离 spec 目标。")
    assert json.loads(resp.content)["aligned"] is True


def test_scripted_custom_uses_and_cites():
    client = ScriptedLLMClient(uses=["claim-99"], cites=["keyother"])
    resp = _complete(client, prompt="行文器")
    assert json.loads(resp.content)["uses"] == ["claim-99"]


def test_scripted_broken_flag_returns_non_json():
    client = ScriptedLLMClient(broken=True)
    with pytest.raises(json.JSONDecodeError):
        json.loads(_complete(client, prompt="行文器").content)


def test_make_client_mock_returns_scripted():
    assert isinstance(make_client(mock=True), ScriptedLLMClient)


def test_make_client_real_failure_wraps_draft_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)   # 空目录：无 config.json → from_env 报 ValueError
    with pytest.raises(DraftError) as excinfo:
        make_client(mock=False)
    assert "真实 LLM 客户端构造失败" in str(excinfo.value)


def test_align_routing_keyword_matches_builtin_prompt():
    from module_harness.align import ALIGN_CHECK_CONFIG

    assert "你是对齐检查器" in ALIGN_CHECK_CONFIG.prompt_core
