"""内置模板层（M4）：weft init 骨架与 weft new 模板化创建的纯函数层，不依赖 engine / LLM。

复用载体约定不变（v1.1：方法/文献库 = 跨项目拷贝文件）；init 只负责从零建骨架，
new part/card 负责在既有项目内按模板生成空白文件（spec：2026-10-10-weft-new-template-design）。
验收线：init 后 load_project + validate_project 零诊断（0 错误 0 提醒）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path


class InitCollisionError(Exception):
    """目标目录非空（或目标是文件）；骨架零写入（fail-closed）。"""

    def __init__(self, root: Path, entries: list[str]) -> None:
        self.root = root
        self.entries = entries
        super().__init__(f"目标目录非空：{root}（{len(entries)} 个条目）")


class NewNameError(Exception):
    """新建参数含非法路径成分（E-NEW-NAME）。"""

    def __init__(self, arg: str, value: str) -> None:
        self.arg = arg
        self.value = value
        super().__init__(f"参数 {arg} 含非法路径成分：{value!r}")


class NewCollisionError(Exception):
    """新建目标已存在或 id 已被占用（E-NEW-COLLISION）；零写入。"""

    def __init__(self, msg: str, rel: str | None = None) -> None:
        self.rel = rel
        super().__init__(msg)


# ---------------------------------------------------------------- 模板渲染

_UNSAFE_COMPONENT = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_PLAIN_YAML = re.compile(r"[\w][\w \-]*", re.UNICODE)


def _ensure_component(arg: str, value: str) -> None:
    """id/chapter 是落盘路径成分：空、点首尾、空白首尾、分隔符与 Windows 保留字符一律拒绝。"""
    if (not value or value.startswith(".") or value.endswith(".")
            or value != value.strip() or _UNSAFE_COMPONENT.search(value)):
        raise NewNameError(arg, value)


def _yaml_scalar(value: str) -> str:
    """简单词原样（与 init 模板字节一致），含特殊字符时走 JSON 双引号（合法 YAML 流标量）。"""
    if _PLAIN_YAML.fullmatch(value):
        return value
    return json.dumps(value, ensure_ascii=False)


_PART_BODY = """\
# 节点 = 审阅单位；status 改 approved 后 `weft draft {part_id}` 生成草稿。
# 提示：给卡片 frontmatter 标章节标签（chapters: [本章节名]，如 introduction），
# 生成时同章已批卡自动并入「本章素材」，节点 uses 只需列主干实体。
# nodes 示例（uses 引用元数据卡 id，role 常用 evidence / conclusion）：
# nodes:
# - id: para-{nn}-01
#   purpose: describe
#   uses:
#   - id: fact-01
#     role: evidence
#   logic: 本段叙事策略（给 AI 的行文依据）
#   status: draft
nodes: []
---
part id（{part_id}）是 `weft draft` 的寻址单位；正文由生成与拼装流水线产出，不手写在这里。
"""


def render_part_template(part_id: str, section: str) -> str:
    """参数化生成 part 模板（init 骨架与 weft new part 共用，单一来源）。"""
    digits = re.search(r"\d+", part_id)
    nn = digits.group() if digits else "01"
    front = f"id: {part_id}\nsection: {_yaml_scalar(section)}\n"
    return "---\n" + front + _PART_BODY.format(part_id=part_id, nn=nn)


_CARD_TEMPLATES: dict[str, str] = {
    "data": """\
id: {card_id}
status: draft
# chapters: []       # 可选：章节标签（生成时同章已批卡并入本章素材）
# refs: []           # 可选：子图级 Quarto label（fig-01a / tbl-01），需先登记进 metadata/figures.yaml
# source: 数据来源（路径/URL/说明）
# description: 数据说明
""",
    "fact": """\
id: {card_id}
status: draft
data: []             # 必填（至少 1 项）：依赖的 data 卡 id；填好前加载报 E-PARSE
statement: ""        # 必填：事实陈述
# chapters: []       # 可选：章节标签（生成时同章已批卡并入本章素材）
# supports: []       # 可选：支持的 claim 卡 id
""",
    "claim": """\
id: {card_id}
status: draft
claim_type: uncited  # uncited | cited；cited 时 cites 填 bib key（改类型需连同目录迁移）
statement: ""        # 必填：论点陈述
# chapters: []       # 可选：章节标签（生成时同章已批 claim 并入本章素材，可 {{claim-xx}} 引用）
# cites: []          # claim_type: cited 时填 bib key（须已在 assets/references.bib）
""",
    "note": """\
id: {card_id}        # note 卡 id = bib key；须已登记进 assets/references.bib（否则报 E-NOTE-NOT-IN-BIB）
status: draft
# summary: 文献要点（缺省报 W-NOTE-NO-SUMMARY 提醒）
# chapters: []       # 可选：章节标签（生成时同章已批卡并入本章素材背景）
# pdf: 文献 PDF 路径（可选）
# entry: {{}}          # 书目字段；bib managed 模式下 approved + entry 进 references.bib
""",
    "method": """\
id: {card_id}
status: draft
statement: ""        # 必填：方法陈述
protocol: ""         # 必填：操作协议
# chapters: []       # 可选：章节标签（不进素材池，仅组织用）
# derived_from: []   # 可选：方法来源文献 bib key
""",
    "param": """\
id: {card_id}
status: draft
method: ""           # 必填：所属 method 卡 id；悬空报 E-DANGLING-REF
# chapters: []       # 可选：章节标签（不进素材池，仅组织用）
# values: {{}}         # 实验参数键值（每篇不同、逐项核对）
# derived_from: []   # 可选：参数来源文献 bib key
""",
}


def render_card_template(kind: str, card_id: str,
                         chapters: list[str] | None = None) -> str:
    """按种类生成卡片模板（id + status: draft 实体键 + 必填空占位 + 注释示例）。

    --chapter 指定时写入真实 chapters 键；未指定保持注释形态（模板最小）。
    """
    body = _CARD_TEMPLATES[kind].format(card_id=card_id)
    if chapters:
        body += f"chapters: [{', '.join(chapters)}]\n"
    return "---\n" + body + "---\n"


# ---------------------------------------------------------------- 规划纯函数

CARD_KIND_DIRS: dict[str, str] = {
    "data": "metadata/data",
    "fact": "metadata/facts",
    "note": "metadata/notes",
    "method": "metadata/methods",
    "param": "metadata/methods/params",
    "claim": "metadata/claims/uncited",  # 新建 claim 默认 uncited
}

_PART_ID_RE = re.compile(r"^sec-(\d+)$")
_PART_FILE_RE = re.compile(r"^part-(\d+)\.md$")


def plan_new_part(narrative_dir: Path, existing_part_ids, chapter: str,
                  part_id: str | None) -> tuple[Path, str]:
    """计算新 part 落盘路径与最终 id；命名非法/碰撞即抛错，调用方零写入。

    id 缺省时按现有 sec-NN 最大编号 +1（两位零填充）；文件名按目标章节内现有
    part-NN.md 最大编号 +1——两者在构造上都不会与现有条目同名。
    """
    _ensure_component("chapter", chapter)
    ids = set(existing_part_ids)
    if part_id is None:
        nums = [int(m.group(1)) for pid in ids if (m := _PART_ID_RE.match(pid))]
        part_id = f"sec-{max(nums, default=0) + 1:02d}"
    elif not part_id.strip():
        raise NewNameError("--id", part_id)
    if part_id in ids:
        raise NewCollisionError(f"part id {part_id} 已存在")
    chapter_dir = narrative_dir / chapter
    nums = [int(m.group(1)) for p in chapter_dir.glob("*.md")
            if (m := _PART_FILE_RE.match(p.name))]
    target = chapter_dir / f"part-{max(nums, default=0) + 1:02d}.md"
    if target.exists():  # 防御分支：自动编号在构造上不可达（防同名目录等病态条目）
        rel = target.relative_to(narrative_dir.parent).as_posix()
        raise NewCollisionError(f"目标文件已存在：{rel}", rel)
    return target, part_id


def plan_new_card(root: Path, existing_card_ids, kind: str, card_id: str) -> Path:
    """计算新卡片落盘路径（对齐 writer.card_relpath 规范）；非法/碰撞即抛错。"""
    _ensure_component("id", card_id)
    if card_id in set(existing_card_ids):
        raise NewCollisionError(f"卡片 id {card_id} 已存在")
    target = root / CARD_KIND_DIRS[kind] / f"{card_id}.md"
    if target.exists():
        rel = target.relative_to(root).as_posix()
        raise NewCollisionError(f"目标文件已存在：{rel}", rel)
    return target


# ---------------------------------------------------------------- init 骨架

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
bib:
  managed: false            # true：assets/references.bib 由 weft 从已批准文献卡生成（勿手改）
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

_PART_01_MD = render_part_template("sec-01", "Introduction")

_OVERVIEW_MD = """# 研究总述（overview）

<!-- weft draft 的 g 节点会把本文件作为全文背景注入生成提示；
写清研究问题、体系、核心贡献与章节逻辑即可，不必写成正文。 -->

（在此撰写研究总述……）
"""

SCAFFOLD_FILES: dict[str, str] = {
    "_quarto.yml": _QUARTO_YML,
    "overview.md": _OVERVIEW_MD,
    "weft.yaml": _WEFT_YAML,
    "index.qmd": _INDEX_QMD,
    "assets/references.bib": _REFERENCES_BIB,
    "metadata/figures.yaml": _FIGURES_YAML,
    "narrative/01-introduction/part-01.md": _PART_01_MD,
}

# 不随文件派生的空目录：六类卡片目录 + figures（默认 figures_dir）+ 灵感/文章收件箱。
SCAFFOLD_DIRS: tuple[str, ...] = (
    "articles",
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
