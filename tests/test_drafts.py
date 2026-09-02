"""草稿归一化渲染 + 白名单写入（drafts/<section>.md 唯一落盘点）。"""
import pytest

from tests.helpers import build_project
from weft.engine.drafts import render_draft_markdown, write_draft
from weft.models.narrative import NarrativeSection, Node, Use


def _section():
    return NarrativeSection(
        id="sec-01", section="Results", order=1,
        nodes=[Node(id="para-01-01", purpose="describe",
                    uses=[Use(id="fact-01", role="evidence")], status="approved"),
               Node(id="para-01-02", purpose="interpret",
                    uses=[], status="approved")])


def test_render_traceability_comments():
    section = _section()
    paragraphs = {"para-01-01": "第一段。", "para-01-02": "第二段。"}
    out = render_draft_markdown(section, paragraphs, "ab12cd34")
    assert out == (
        "<!-- weft:run=ab12cd34 section=sec-01 -->\n"
        "\n"
        "<!-- weft:node=para-01-01 uses=fact-01 -->\n"
        "第一段。\n"
        "\n"
        "<!-- weft:node=para-01-02 -->\n"
        "第二段。\n"
    )


def test_render_uses_come_from_node_not_draft():
    # 溯源记录节点声明的 uses（weft 侧事实源），与草稿自报无关（决策 9）
    section = _section()
    out = render_draft_markdown(section, {"para-01-01": "第一段。"}, "ab12cd34")
    assert "<!-- weft:node=para-01-01 uses=fact-01 -->" in out


def test_render_skips_undrafted_nodes():
    section = _section()
    out = render_draft_markdown(section, {"para-01-02": "第二段。"}, "ab12cd34")
    assert "para-01-01" not in out
    assert "第二段。" in out


def test_write_draft_path_and_lf(tmp_path):
    project = build_project(root=tmp_path)
    path = write_draft(project, "sec-01", "正文\n")
    assert path == tmp_path / "drafts" / "sec-01.md"
    raw = path.read_bytes()
    assert b"\r" not in raw                     # 固定 LF（同 graphgen 约定）
    assert raw.endswith(b"\n")


def test_write_draft_overwrites(tmp_path):
    project = build_project(root=tmp_path)
    write_draft(project, "sec-01", "旧")
    path = write_draft(project, "sec-01", "新")
    assert path.read_text(encoding="utf-8") == "新"


def test_write_draft_rejects_path_escape(tmp_path):
    project = build_project(root=tmp_path)
    with pytest.raises(ValueError):
        write_draft(project, "../evil", "x")


def test_write_draft_rejects_backslash_escape(tmp_path):
    project = build_project(root=tmp_path)
    with pytest.raises(ValueError):
        write_draft(project, "..\\evil", "x")


def test_write_draft_normalizes_crlf(tmp_path):
    project = build_project(root=tmp_path)
    path = write_draft(project, "sec-01", "line1\r\nline2\r\n")
    assert b"\r" not in path.read_bytes()


def test_render_multiline_paragraph_verbatim():
    section = _section()
    out = render_draft_markdown(section, {"para-01-01": "第一行。\n第二行。"}, "ab12cd34")
    assert "第一行。\n第二行。" in out
    assert out.endswith("第一行。\n第二行。\n")
