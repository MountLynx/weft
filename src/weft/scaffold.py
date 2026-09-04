"""项目骨架生成（M4）：weft init 的纯函数层，不依赖 engine / LLM。

复用载体约定不变（v1.1：方法/文献库 = 跨项目拷贝文件）；本模块只负责从零建骨架。
验收线：init 后 load_project + validate_project 零诊断（0 错误 0 提醒）。
"""
from __future__ import annotations

from pathlib import Path


class InitCollisionError(Exception):
    """目标目录非空（或目标是文件）；骨架零写入（fail-closed）。"""

    def __init__(self, root: Path, entries: list[str]) -> None:
        self.root = root
        self.entries = entries
        super().__init__(f"目标目录非空：{root}（{len(entries)} 个条目）")


_QUARTO_YML = """\
project:
  type: default

bibliography: assets/references.bib

# 投稿资源就位后取消注释（assets/ 约定：references.bib / style.csl / template.docx）：
# csl: assets/style.csl
# format:
#   docx:
#     reference-doc: assets/template.docx
"""

_WEFT_YAML = """\
# weft 项目配置：全部键可省略，以下注释即默认值。
# figures_dir: figures      # 图表目录（data 卡 refs 指向其中的 Quarto label）
# assemble_mode: strict     # strict | lenient：part 拼装失败是否阻断 assemble
# paper_file: paper.qmd     # assemble 拼装产物（weft render 的渲染对象）
"""

_INDEX_QMD = """\
---
title: "未命名论文"
---

正文不写在这里：`weft assemble` 把已批准草稿拼装进 paper.qmd，`weft render` 渲染 paper.qmd。
"""

_REFERENCES_BIB = """\
@comment{文献库：note 卡 id = bib key；claim.cites / method.derived_from 引用此处 key。}
"""

_FIGURES_YAML = """\
# 图注注册表：键 = Quarto label（data 卡 refs 引用；assemble 据此生成 Figures/Tables 字面编号）。
# 示例：
# fig-01:
#   caption: 图题（可含误差线等说明）
#   subfigs:
#     a: 子图 a 的说明
"""

_PART_01_MD = """\
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

SCAFFOLD_FILES: dict[str, str] = {
    "_quarto.yml": _QUARTO_YML,
    "weft.yaml": _WEFT_YAML,
    "index.qmd": _INDEX_QMD,
    "assets/references.bib": _REFERENCES_BIB,
    "metadata/figures.yaml": _FIGURES_YAML,
    "narrative/01-introduction/part-01.md": _PART_01_MD,
}

# 不随文件派生的空目录：六类卡片目录 + figures（默认 figures_dir）+ 灵感收件箱。
SCAFFOLD_DIRS: tuple[str, ...] = (
    "figures",
    "inspirations",
    "metadata/data",
    "metadata/facts",
    "metadata/notes",
    "metadata/methods",
    "metadata/params",
    "metadata/claims/cited",
    "metadata/claims/uncited",
)


def init_project(root: Path) -> list[Path]:
    """在 root 生成最小合法项目骨架，返回创建的文件路径（相对 root 派生，顺序稳定）。

    root 不存在则创建（含父目录）；已存在且为空 → 原地生成；
    已存在且非空（或本身是文件）→ 抛 InitCollisionError，不写入任何文件。
    """
    root = Path(root)
    if root.is_dir():
        entries = sorted(p.name for p in root.iterdir())
        if entries:
            raise InitCollisionError(root, entries)
    elif root.exists():
        raise InitCollisionError(root, [root.name])
    else:
        root.mkdir(parents=True)

    for rel in SCAFFOLD_DIRS:
        (root / rel).mkdir(parents=True, exist_ok=True)

    created: list[Path] = []
    for rel, content in SCAFFOLD_FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        created.append(path)
    return created
