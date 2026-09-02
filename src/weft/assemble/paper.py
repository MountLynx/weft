"""paper 级拼装（M3 设计 §1-§3）：chapter qmd 原样并入 + References/Figures/Tables。

References 只写 citeproc 定位 div（条目由 Quarto 依 _quarto.yml bibliography 生成，
weft 不生成任何条目）；Figures/Tables 由 figures.yaml 确定性生成，字面编号 = 键序，
不走 crossref（docx 投稿所见即所得；v1 §7"首次出现处插入"已作废）。
"""
from __future__ import annotations

from weft.store.project import Project

_REFERENCES_DIV = "# References {.unnumbered}\n\n::: {#refs}\n:::"
_FIG_PREFIX = "Fig."
_TBL_PREFIX = "Table"
_TBL_KEY = "tbl-"


def _back_matter(project: Project) -> str:
    """References 定位块 +（有则）Figures / Tables 节；figures.yaml 键序即编号。"""
    blocks = [_REFERENCES_DIV]
    fig_keys = [k for k in project.figures if not k.startswith(_TBL_KEY)]
    tbl_keys = [k for k in project.figures if k.startswith(_TBL_KEY)]
    if fig_keys:
        lines = ["# Figures {.unnumbered}", ""]
        for n, key in enumerate(fig_keys, start=1):
            lines += [f"![]({project.figures_dir}/{key}.png)", "",
                      f"**{_FIG_PREFIX} {n}** {project.figures[key].caption}".rstrip(),
                      ""]
        blocks.append("\n".join(lines).rstrip("\n"))
    if tbl_keys:
        lines = ["# Tables {.unnumbered}", ""]
        for n, key in enumerate(tbl_keys, start=1):
            lines += [f"**{_TBL_PREFIX} {n}** {project.figures[key].caption}".rstrip(),
                      ""]
        blocks.append("\n".join(lines).rstrip("\n"))
    return "\n\n".join(blocks)


def assemble_paper(project: Project, chapter_texts: list[str]) -> str:
    """paper.qmd 全文：chapter 正文（目录序、原样并入）+ References/Figures。LF 单尾换行。"""
    body = [text.rstrip("\n") for text in chapter_texts]
    body.append(_back_matter(project))
    return "\n\n".join(body) + "\n"
