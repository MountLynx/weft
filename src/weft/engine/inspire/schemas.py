"""inspire 节点输出 schema：T1–T4 结构化 JSON 的 pydantic 契约（inspire 设计 §4）。

AI 输出一律经这些模型校验，非法即 E-INSPIRE-SHAPE 整链不落盘。
拟建卡不带真实 id（临时 key f1/c1，A1 统一分配，见计划 D2）。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LogicOutput(BaseModel):
    """T1 逻辑核查（建议性，不阻断；输出格式仍须合法）。"""

    issues: list[str] = []


class _Link(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str


class ProposedCard(BaseModel):
    key: str
    kind: Literal["fact", "claim"]
    statement: str
    placeholder: bool = False
    needs_citation: bool = False


class ExtractOutput(BaseModel):
    """T2 卡片拆解：拟建卡 + 新卡内部连接（link from=fact key, to=claim key）。"""

    cards: list[ProposedCard] = []
    links: list[_Link] = []


class Classification(BaseModel):
    key: str
    verdict: Literal["new", "conflict", "supplement"]
    against: list[str] = []   # 相关/冲突/被补充的现有卡 id
    reason: str = ""
    merged_statement: str = ""  # supplement 必填：完整新卡陈述（原卡信息+补充）

    @model_validator(mode="after")
    def _supplement_needs_merge(self) -> "Classification":
        if self.verdict == "supplement" and not self.merged_statement.strip():
            raise ValueError("supplement 必须给出 merged_statement（完整新卡陈述）")
        return self


class ReviewOutput(BaseModel):
    classifications: list[Classification] = []


class FactMatch(BaseModel):
    key: str
    data_ids: list[str] = []


class ClaimMatch(BaseModel):
    key: str
    claim_type: Literal["cited", "uncited"]
    cites: list[str] = []
    reason: str = ""


class PlaceholderMatch(BaseModel):
    text: str
    matched_fact: str | None = None


class MatchOutput(BaseModel):
    """T4 匹配：fact→data 关联；claim 分类与文献匹配；占位→现有 fact。"""

    fact_data: list[FactMatch] = []
    claim_cites: list[ClaimMatch] = []
    placeholders: list[PlaceholderMatch] = []
