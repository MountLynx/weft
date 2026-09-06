"""共享 runner：事件序列、结果、缺 approved 节点的失败路径。"""
from pathlib import Path

import pytest

from tests.helpers import make_minimal_project
from weft.engine import DraftError, ScriptedLLMClient
from weft.engine.part_draft import run_part_draft
from weft.store.loader import load_project


def test_event_sequence_and_result(tmp_path: Path):
    root = make_minimal_project(tmp_path)
    project, diags = load_project(root)
    assert not any(d.is_error for d in diags)
    part = project.parts[0]
    events: list = []
    result = run_part_draft(project, part, client=ScriptedLLMClient(),
                            on_event=events.append)
    kinds = [e.kind for e in events]
    assert kinds[0] == "run_started"
    assert kinds.count("node_started") == kinds.count("node_finished") == 1
    assert "draft_written" in kinds
    assert kinds[-1] == "run_finished"
    assert result.paragraphs["para-01-01"]
    assert result.run_id
    assert (root / "drafts" / "sec-01.md").exists()


def test_nothing_to_draft_raises_and_emits_run_failed(tmp_path: Path):
    root = make_minimal_project(tmp_path)
    project, _ = load_project(root)
    part = project.parts[0]
    part.nodes[0].status = "draft"
    events: list = []
    with pytest.raises(DraftError):
        run_part_draft(project, part, client=ScriptedLLMClient(),
                       on_event=events.append)
    assert events[-1].kind == "run_failed"
    assert "E-NOTHING-TO-DRAFT" in events[-1].message
