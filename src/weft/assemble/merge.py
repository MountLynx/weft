"""chapter 级 qmd 合并 + 项目根 paper.qmd 拼装：目录序遍历，heading 层级 chapter→#、子节→##/###（v1.1 §4.4；M3 设计 §1）。

标题文本 = 目录名剥数字前缀、分隔符转空格；显示编号由 Quarto 负责
（内部标识/显示形式分离）。输出固定 LF，字节级确定。
"""
from __future__ import annotations

import re
from pathlib import Path

from weft.assemble.parts import assemble_part, load_part_paragraphs
from weft.assemble.paper import assemble_paper
from weft.diagnostics import Diagnostic, Level
from weft.store.project import Project

_NUM_PREFIX = re.compile(r"^[\d\s._-]+")


def heading_text(name: str) -> str:
    """目录名 → 标题文本：剥数字前缀，`-`/`_` 转空格。"""
    return _NUM_PREFIX.sub("", name).replace("-", " ").replace("_", " ").strip()


def assemble_project(project: Project, *,
                     mode: str = "strict") -> tuple[list[Path], list[Diagnostic]]:
    """全项目拼装：part qmd（镜像 narrative 树）+ chapter 级合并 qmd + 项目根 paper.qmd。

    paper.qmd 恒产出（含 strict 报错时的部分 chapter）；strict（默认）下
    approved 节点缺已批准草稿段 → E-ASSEMBLE-MISSING-DRAFT，
    该 part 跳过、其余照常（决策 13）；lenient 只跳缺段节点。
    返回 (写入路径, 诊断)，paper 路径在 written 末尾。
    """
    diags: list[Diagnostic] = []
    written: list[Path] = []
    gen_root = project.root / "generated"
    chapter_texts: dict[str, list[tuple[tuple[str, ...], str]]] = {}

    for part in project.parts:
        rel = project.part_paths[part.id]
        rel_qmd = rel.with_suffix(".qmd")
        components = rel_qmd.parts[1:]          # 去掉 narrative/，含文件名
        dirs = components[:-1]                  # 目录组件：章 + 各级子节
        paragraphs = load_part_paragraphs(project, part.id)
        missing = [n.id for n in part.nodes
                   if n.status == "approved" and n.id not in paragraphs]
        if missing and mode == "strict":
            diags.append(Diagnostic(
                Level.ERROR, "E-ASSEMBLE-MISSING-DRAFT", rel.as_posix(),
                missing[0],
                f"approved 节点 {missing[0]} 没有已批准草稿段"
                "（strict 模式；lenient 经 weft.yaml assemble_mode 配置）"))
            continue
        heading_level = len(dirs) + 1           # 章=#、一级子节=##、part 再下一级
        qmd = assemble_part(part, paragraphs, heading_level=heading_level)
        if qmd is None:
            continue
        out_path = gen_root.joinpath(*components)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(qmd, encoding="utf-8", newline="\n")
        written.append(out_path)
        chapter_texts.setdefault(dirs[0], []).append((dirs[1:], qmd))

    chapter_bodies: dict[str, str] = {}
    for chapter, entries in chapter_texts.items():
        lines = [f"# {heading_text(chapter)}", ""]
        seen_dirs: set[tuple[str, ...]] = set()
        for sub_path, qmd in entries:
            for depth in range(1, len(sub_path) + 1):
                prefix = sub_path[:depth]
                if prefix not in seen_dirs:
                    seen_dirs.add(prefix)
                    lines += [f"{'#' * (depth + 1)} {heading_text(prefix[-1])}", ""]
            lines.append(qmd.rstrip("\n"))
            lines.append("")
        chapter_text = "\n".join(lines) + "\n"
        chapter_path = gen_root / f"{chapter}.qmd"
        chapter_path.write_text(chapter_text, encoding="utf-8", newline="\n")
        written.append(chapter_path)
        chapter_bodies[chapter] = chapter_text

    paper_path = project.root / project.paper_file
    paper_path.write_text(assemble_paper(project, list(chapter_bodies.values())),
                          encoding="utf-8", newline="\n")
    written.append(paper_path)

    diags.sort(key=lambda d: (d.path, d.code, d.field or ""))
    return written, diags
