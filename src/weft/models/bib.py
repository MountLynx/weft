"""书目字段模型（bibgen 设计 §4，红线 2 加法演进登记处）。

NoteCard.entry 可选嵌套：managed 模式下已批准 note 卡是 bib 的真源
（spec 2026-09-29-weft-bibgen §2）。加法演进：旧卡不含 entry 照常加载，无需数据迁移。
"""
from pydantic import BaseModel, ConfigDict

BIB_TYPES = frozenset({
    "article", "book", "inproceedings", "incollection", "phdthesis",
    "mastersthesis", "techreport", "manual", "misc", "online", "unpublished",
})


class BibEntryFields(BaseModel):
    """BibTeX 条目书目字段；必填仅 title/year，缺省字段渲染时跳过。"""

    model_config = ConfigDict(extra="forbid")

    type: str = "article"
    title: str
    author: list[str] = []
    year: str | int
    journal: str | None = None
    booktitle: str | None = None
    publisher: str | None = None
    volume: str | None = None
    number: str | None = None
    pages: str | None = None
    doi: str | None = None
    url: str | None = None
    fields: dict[str, str] = {}   # 逃生舱：其余 BibTeX 字段原样透传
