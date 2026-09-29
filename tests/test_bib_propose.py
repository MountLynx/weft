"""engine bib_propose（bibgen 设计 §8 路径 1）：线索→entry 草稿卡字段，不落盘。"""
import asyncio

import pytest
from llm.client import LLMResponse

from tests.helpers import build_project
from weft.engine.bib_propose import BibProposeError, propose_note
from weft.engine.clients import ScriptedLLMClient
from weft.models.cards import NoteCard


def _project_with(*ids):
    return build_project(notes=[NoteCard.model_validate({"id": i, "status": "approved"})
                                for i in ids])


def test_propose_note_happy_path():
    project = _project_with("key2020")
    key, fields = asyncio.run(
        propose_note(project, "DOI 10.1/x；Smith 2020 热激活催化", ScriptedLLMClient()))
    assert key == "smith2020"
    assert fields["status"] == "draft"
    assert fields["entry"]["title"] == "Thermally activated catalysis"
    assert fields["entry"]["author"] == ["Smith, Jane"]
    assert "Smith 2020" in fields["comment"]


def test_propose_note_conflict_suffix():
    project = _project_with("key2020", "smith2020")
    key, _ = asyncio.run(propose_note(project, "Smith 2020", ScriptedLLMClient()))
    assert key == "smith2020a"


def test_propose_note_key_fallback_title():
    class _NoAuthorClient:
        async def complete(self, **kwargs):
            return LLMResponse(
                content='{"title": "Thermally activated catalysis", "year": 2020}',
                usage={}, finish_reason="end_turn")

    key, _ = asyncio.run(propose_note(_project_with("key2020"), "无作者的线索",
                                      _NoAuthorClient()))
    assert key == "thermally2020"


def test_propose_note_invalid_json():
    class _BadClient:
        async def complete(self, **kwargs):
            return LLMResponse(content="不是 JSON", usage={}, finish_reason="end_turn")

    with pytest.raises(BibProposeError):
        asyncio.run(propose_note(_project_with("key2020"), "x", _BadClient()))


def test_propose_note_invalid_schema():
    class _NoYearClient:
        async def complete(self, **kwargs):
            return LLMResponse(content='{"title": "T"}', usage={},
                               finish_reason="end_turn")

    with pytest.raises(BibProposeError):
        asyncio.run(propose_note(_project_with("key2020"), "x", _NoYearClient()))


def test_propose_note_llm_error_translated():
    class _BoomClient:
        async def complete(self, **kwargs):
            raise RuntimeError("网络抖动")

    with pytest.raises(BibProposeError, match="LLM 调用失败"):
        asyncio.run(propose_note(_project_with("key2020"), "x", _BoomClient()))


def test_propose_note_fields_passthrough():
    class _FieldsClient:
        async def complete(self, **kwargs):
            return LLMResponse(
                content='{"title": "T", "year": 2020, "editor": "Ed, Itor"}',
                usage={}, finish_reason="end_turn")

    _, fields = asyncio.run(propose_note(_project_with("key2020"), "x", _FieldsClient()))
    assert fields["entry"]["fields"] == {"editor": "Ed, Itor"}
