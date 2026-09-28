"""parse 管线节点输出 schema：P1–P5 结构化 JSON 的 pydantic 契约（parse 设计 §4）。

与 inspire schemas 平行（两管线独立演进：summary、note 三档判定为 parse 专属）。
AI 输出一律经这些模型校验，非法即 E-ARTICLE-SHAPE 整链不落盘。
拟建卡不带真实 id（临时 key f1/c1，A1 统一分配）。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ArticleLogicOutput(BaseModel):
    """P1 逻辑核查（建议性，不阻断；输出格式仍须合法）。"""

    issues: list[str] = []


class _Link(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str


class ArticleProposedCard(BaseModel):
    key: str
    kind: Literal["fact", "claim"]
    statement: str
    placeholder: bool = False
    needs_citation: bool = False


class ArticleExtractOutput(BaseModel):
    """P2 拆解：拟建卡 + 内部连接；summary 仅文献模式有值（结构化文献摘要）。"""

    cards: list[ArticleProposedCard] = []
    links: list[_Link] = []
    summary: str = ""


class ArticleClassification(BaseModel):
    key: str
    verdict: Literal["new", "conflict", "supplement"]
    against: list[str] = []   # 相关/冲突/被补充的现有卡 id
    reason: str = ""
    merged_statement: str = ""  # supplement 必填：完整新卡陈述

    @model_validator(mode="after")
    def _supplement_needs_merge(self) -> "ArticleClassification":
        if self.verdict == "supplement" and not self.merged_statement.strip():
            raise ValueError("supplement 必须给出 merged_statement（完整新卡陈述）")
        return self


class NoteReview(BaseModel):
    """note 三档判定（parse 设计 §5）：new=直落 / supplement=提案 / unchanged=不动。"""

    verdict: Literal["new", "supplement", "unchanged"]
    reason: str = ""
    merged_summary: str = ""  # supplement 必填：原摘要全部要点 + 新增整合

    @model_validator(mode="after")
    def _supplement_needs_merge(self) -> "NoteReview":
        if self.verdict == "supplement" and not self.merged_summary.strip():
            raise ValueError("supplement 必须给出 merged_summary（整合后的完整摘要）")
        return self


class ArticleReviewOutput(BaseModel):
    """P3 对照审查：卡片分类 + note 三档（拆解模式 note=None）。"""

    classifications: list[ArticleClassification] = []
    note: NoteReview | None = None


class ArticleFactMatch(BaseModel):
    key: str
    data_ids: list[str] = []


class ArticleClaimMatch(BaseModel):
    key: str
    claim_type: Literal["cited", "uncited"]
    cites: list[str] = []
    reason: str = ""


class ArticlePlaceholderMatch(BaseModel):
    text: str
    matched_fact: str | None = None


class ArticleMatchOutput(BaseModel):
    """P4 匹配：fact→data 关联；claim 分类与 cites；占位→现有 fact。"""

    fact_data: list[ArticleFactMatch] = []
    claim_cites: list[ArticleClaimMatch] = []
    placeholders: list[ArticlePlaceholderMatch] = []


class ArticleCoverageEntry(BaseModel):
    sentence: str              # 原文要点（摘录）
    card_keys: list[str] = []  # 覆盖该要点的草案卡 key
    covered: bool = True
    suggestion: str = ""       # covered=False 时：处理建议


class ArticleCoverageOutput(BaseModel):
    """P5 覆盖审查：逐要点对账文章原文与草案卡，漏卡可见。"""

    coverage: list[ArticleCoverageEntry] = []
