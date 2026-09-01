import pytest
from pydantic import ValidationError

from weft.models.figures import FigureEntry
from weft.models.narrative import NarrativeSection, Node, Use


def test_section_parses_spec_example():
    section = NarrativeSection.model_validate({
        "id": "sec-03",
        "section": "Results",
        "order": 3,
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
    assert section.nodes[0].uses[1].role == "conclusion"
    assert section.nodes[0].logic == "先主结果，再补充次要结果"


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


def test_section_order_is_int():
    with pytest.raises(ValidationError):
        NarrativeSection(id="sec-03", section="Results", order="third")


def test_figure_entry_defaults():
    entry = FigureEntry.model_validate({"caption": "总图注"})
    assert entry.subfigs == {}


def test_figure_entry_ignores_unknown_keys():
    # figures.yaml 人工直接维护，解析宽松：未知键忽略
    entry = FigureEntry.model_validate({"caption": "c", "typo": 1})
    assert entry.caption == "c"
