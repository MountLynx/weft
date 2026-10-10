"""weft new 命令组：模板化创建空白叙事 part 与元数据卡片。"""
import frontmatter

from weft.scaffold import render_card_template, render_part_template

# init 脚手架改造前 _PART_01_MD 的原文（逐字节黄金，防 render_part_template 派生漂移）
_INIT_PART_GOLDEN = """\
---
id: sec-01
section: Introduction
# 节点 = 审阅单位；status 改 approved 后 `weft draft sec-01` 生成草稿。
# nodes 示例（uses 引用元数据卡 id，role 常用 evidence / conclusion）：
# nodes:
# - id: para-01-01
#   purpose: describe
#   uses:
#   - id: fact-01
#     role: evidence
#   logic: 本段叙事策略（给 AI 的行文依据）
#   status: draft
nodes: []
---
part id（sec-01）是 `weft draft` 的寻址单位；正文由生成与拼装流水线产出，不手写在这里。
"""


def test_render_part_template_matches_init_scaffold():
    assert render_part_template("sec-01", "Introduction") == _INIT_PART_GOLDEN


def test_render_part_template_parametrized():
    text = render_part_template("sec-12", "Related Work")
    assert "id: sec-12" in text
    assert "section: Related Work" in text
    assert "# - id: para-12-01" in text
    assert "`weft draft sec-12`" in text
    assert "part id（sec-12）" in text


def test_render_part_template_quotes_yaml_unsafe_section():
    text = render_part_template("sec-02", "Methods: overview")
    assert 'section: "Methods: overview"' in text
    parsed = frontmatter.loads(text)
    assert parsed["section"] == "Methods: overview"


def test_render_part_template_no_digits_defaults_example_nn():
    text = render_part_template("sec-intro", "引言")
    assert "# - id: para-01-01" in text
    assert "section: 引言" in text


def test_render_card_template_roundtrip():
    required = {
        "data": set(),
        "fact": {"data", "statement"},
        "claim": {"claim_type", "statement"},
        "note": set(),
        "method": {"statement", "protocol"},
        "param": {"method"},
    }
    for kind, extra in required.items():
        text = render_card_template(kind, "x-01")
        meta = frontmatter.loads(text)
        assert meta["id"] == "x-01", kind
        assert meta["status"] == "draft", kind
        assert extra <= set(meta.metadata), (kind, sorted(meta.metadata))
