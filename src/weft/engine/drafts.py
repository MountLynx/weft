"""草稿归一化写入：drafts/<section>.md + HTML 溯源注释（spec §6.5）。

路径白名单：本模块是 M2 唯一把 AI 产物落盘的地方，路径硬编码为
root/drafts/<section_id>.md，不接受调用方传入路径；section_id 再过一次
逃逸检查（纵深防御，id 正常来自 loader 校验过的叙事节）。
溯源注释的 uses 取节点声明的 uses（决策 9），不取草稿自报值。
"""
from pathlib import Path

from weft.models.narrative import NarrativeSection
from weft.store.project import Project


def render_draft_markdown(section: NarrativeSection, paragraphs_by_node: dict[str, str],
                          run_id: str) -> str:
    """段落顺序 = 节内 nodes 顺序；未生成节点（draft/rejected）跳过。"""
    lines = [f"<!-- weft:run={run_id} section={section.id} -->", ""]
    for node in section.nodes:
        paragraph = paragraphs_by_node.get(node.id)
        if paragraph is None:
            continue
        uses = ",".join(u.id for u in node.uses)
        comment = f"<!-- weft:node={node.id} uses={uses} -->" if uses \
            else f"<!-- weft:node={node.id} -->"
        if len(lines) > 2:
            lines.append("")  # 节点块之间空一行（末尾只留单个换行）
        lines += [comment, paragraph]
    return "\n".join(lines) + "\n"


def write_draft(project: Project, section_id: str, content: str) -> Path:
    drafts_dir = project.root / "drafts"
    path = drafts_dir / f"{section_id}.md"
    if path.resolve().parent != drafts_dir.resolve():
        raise ValueError(f"非法 section id（路径逃逸）：{section_id}")
    drafts_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return path
