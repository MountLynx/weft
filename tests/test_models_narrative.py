import pytest
from pydantic import ValidationError

from weft.models.figures import FigureEntry
from weft.models.narrative import NarrativePart, Node, Use


def test_part_parses_v1_1_example():
    part = NarrativePart.model_validate({
        "id": "part-startup-01",
        "section": "SNDPR 启动性能",
        "workflow": "results",
        "nodes": [
            {
                "id": "para-03-01",
                "purpose": "describe",
                "uses": [
                    {"id": "fact-01", "role": "evidence"},
                    {"id": "claim-01", "role": "conclusion"},
                ],
                "logic": "先主结果，再补充次要结果",
                "status": "draft",
                "comment": "",
            }
        ],
    })
    assert part.nodes[0].uses[1].role == "conclusion"
    assert part.workflow == "results"


def test_part_workflow_defaults_to_none():
    part = NarrativePart(id="p1", section="T")
    assert part.workflow is None
    assert part.nodes == []


def test_retired_order_field_rejected():
    # v1.1 §4.2：order 退役，extra=forbid 使旧文件 fail-closed（先跑迁移脚本）
    with pytest.raises(ValidationError):
        NarrativePart(id="p1", section="T", order=1)


def test_node_defaults():
    node = Node(id="para-03-01", purpose="describe", status="approved")
    assert node.uses == []
    assert node.logic == ""


def test_node_requires_status():
    with pytest.raises(ValidationError):
        Node(id="para-03-01", purpose="describe")


def test_use_requires_role():
    with pytest.raises(ValidationError):
        Use(id="fact-01")


def test_use_role_is_free_string():
    # role/purpose 是软词表：模型层放行任意字符串，词表校验在 validation 层
    use = Use(id="fact-01", role="vibe")
    assert use.role == "vibe"


def test_figure_entry_defaults():
    entry = FigureEntry.model_validate({"caption": "总图注"})
    assert entry.subfigs == {}


def test_figure_entry_ignores_unknown_keys():
    entry = FigureEntry.model_validate({"caption": "c", "typo": 1})
    assert entry.caption == "c"
