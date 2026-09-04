"""LLM 客户端选择：ScriptedLLMClient 免 key 管线；真实客户端走 .env/环境变量。"""
import asyncio
import json

import pytest

from weft.engine.clients import ScriptedLLMClient, make_client
from weft.engine.draft_rules import DraftError


def _complete(client, **kwargs):
    return asyncio.run(client.complete(**kwargs))


def test_scripted_gen_extracts_ids_and_emits_placeholders():
    client = ScriptedLLMClient(paragraph="_mock_段。")
    prompt = ('【draft·起草】\nuses：\n[{"id": "fact-01", "kind": "fact"},'
              '{"id": "claim-01", "kind": "claim"}]')
    resp = _complete(client, prompt=prompt)
    assert resp.content == "_mock_段。{{fact-01}}{{claim-01}}"   # v2：g 输出纯文本


def test_scripted_check_pass_and_fix():
    client = ScriptedLLMClient()
    assert json.loads(_complete(
        client, prompt="【draft·校验】审查")["content"]
        if False else _complete(client, prompt="【draft·校验】审查").content
    ) == {"verdict": "pass"}
    fixer = ScriptedLLMClient(check_fix="修正 {{fact-01}}。")
    payload = json.loads(_complete(fixer, prompt="【draft·校验】").content)
    assert payload["verdict"] == "fix" and "fact-01" in payload["paragraph"]


def test_scripted_link_and_polish_echo_delimited_text():
    client = ScriptedLLMClient()
    prompt = "【draft·衔接】\n当前工作文本：\n<<<PARAGRAPH\n工作文本。\nPARAGRAPH>>>"
    assert _complete(client, prompt=prompt).content == "工作文本。"
    prompt2 = "【draft·润色】\n<<<PARAGRAPH\n润色前。\nPARAGRAPH>>>"
    assert _complete(client, prompt=prompt2).content == "润色前。"


def test_scripted_inspire_branches_still_work():
    client = ScriptedLLMClient(logic_issues=["x"])
    assert json.loads(_complete(client, prompt="【灵感·逻辑核查】y").content) == \
        {"issues": ["x"]}
    assert "cards" in _complete(client, prompt="【灵感·卡片拆解】y").content
    assert json.loads(_complete(client, prompt="【灵感·成卡覆盖】y").content) == \
        {"coverage": []}


def test_make_client_mock_and_real_error(tmp_path):
    assert isinstance(make_client(True), ScriptedLLMClient)
    with pytest.raises(DraftError, match="真实 LLM 客户端构造失败"):
        make_client(False, project_root=tmp_path)
