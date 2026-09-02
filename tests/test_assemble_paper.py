"""paper 级拼装：References refs div、Figures/Tables 字面编号、chapter 原样并入（M3 设计 §1-§3）。"""
from tests.helpers import build_project
from weft.assemble.paper import assemble_paper
from weft.models.figures import FigureEntry


def test_back_matter_figures_tables_literal_numbering():
    # 键序即编号（非字典序）：fig-02 先出现 → Fig. 1；tbl-* 前缀分流入 Tables
    project = build_project(figures={
        "fig-02": FigureEntry(caption="第二图"),
        "fig-01": FigureEntry(caption="第一图"),
        "tbl-01": FigureEntry(caption="第一表"),
    })
    paper = assemble_paper(project, [])
    assert paper == (
        "# References {.unnumbered}\n\n::: {#refs}\n:::\n\n"
        "# Figures {.unnumbered}\n\n"
        "![](figures/fig-02.png)\n\n**Fig. 1** 第二图\n\n"
        "![](figures/fig-01.png)\n\n**Fig. 2** 第一图\n\n"
        "# Tables {.unnumbered}\n\n**Table 1** 第一表\n"
    )


def test_back_matter_refs_div_only_when_no_figures():
    project = build_project()
    assert assemble_paper(project, []) == (
        "# References {.unnumbered}\n\n::: {#refs}\n:::\n")


def test_assemble_paper_chapters_joined_in_given_order():
    # chapter 原样并入（rstrip 尾换行后单空行分隔），References 殿后
    project = build_project()
    paper = assemble_paper(project, ["# results\n\n正文一。\n",
                                     "# discussion\n\n正文二。\n"])
    assert paper == ("# results\n\n正文一。\n\n"
                     "# discussion\n\n正文二。\n\n"
                     "# References {.unnumbered}\n\n::: {#refs}\n:::\n")


def test_figures_dir_override_and_empty_caption():
    project = build_project(figures={"fig-01": FigureEntry()},
                            figures_dir="assets/figs")
    paper = assemble_paper(project, [])
    assert "![](assets/figs/fig-01.png)" in paper
    assert "**Fig. 1**\n" in paper      # 空 caption rstrip 兜底，不留尾随空格
