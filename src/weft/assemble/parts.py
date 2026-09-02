"""part 级 qmd 拼装：drafts/<part>.md 的已批准段落 → 确定性 qmd 文本。

溯源注释只属于 drafts（决策 11）：拼装时按 weft:node 注释切块取段落，
输出不含任何 weft 注释。
"""
from __future__ import annotations

import re

from weft.models.narrative import NarrativePart
from weft.store.project import Project

_NODE_MARK = re.compile(r"<!--\s*weft:node=([A-Za-z0-9_-]+)[^>]*-->")


def parse_draft_paragraphs(text: str) -> dict[str, str]:
    """从草稿的 weft:node 注释提取 节点id → 段落；run 头注释与空块忽略。"""
    paragraphs: dict[str, str] = {}
    marks = list(_NODE_MARK.finditer(text))
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        paragraph = text[mark.end():end].strip()
        if paragraph:
            paragraphs[mark.group(1)] = paragraph
    return paragraphs


def load_part_paragraphs(project: Project, part_id: str) -> dict[str, str]:
    path = project.root / "drafts" / f"{part_id}.md"
    if not path.exists():
        return {}
    return parse_draft_paragraphs(path.read_text(encoding="utf-8"))


def assemble_part(part: NarrativePart, paragraphs: dict[str, str],
                  *, heading_level: int) -> str | None:
    """part 标题（级别=目录深度+1）+ approved 节点的段落（按节点序）。

    无段落可拼（无 approved 节点或全缺草稿）返回 None——调用方跳过该 part。
    lenient 语义在参数层自然成立：缺草稿的节点不在 paragraphs 里即被跳过。
    """
    lines = [f"{'#' * heading_level} {part.section}", ""]
    count = 0
    for node in part.nodes:
        if node.status != "approved":
            continue
        paragraph = paragraphs.get(node.id)
        if paragraph is None:
            continue
        if count:
            lines.append("")
        lines.append(paragraph)
        count += 1
    if not count:
        return None
    return "\n".join(lines) + "\n"
