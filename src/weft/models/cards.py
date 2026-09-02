"""元数据卡片模型（数据结构 v1，冻结；spec §3.1–3.4、§3.10）。"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ReviewStatus = Literal["draft", "approved", "rejected"]


class _Card(BaseModel):
    """卡片公共字段。未知键一律报错：防 schema 漂移与字段拼写错误。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: ReviewStatus
    comment: str = ""


class DataCard(_Card):
    """data 卡：refs 为子图级 Quarto label（fig-01a / tbl-01），可为空。"""

    refs: list[str] = []
    source: str | None = None
    description: str = ""


class FactCard(_Card):
    """fact 卡。data 为空在模型层即非法（spec §4 错误项）。"""

    data: list[str] = Field(min_length=1)
    statement: str
    supports: list[str] = []


class ClaimCard(_Card):
    """claim 卡：单一类型 + claim_type 属性；cited 时 cites 填 bib key。"""

    claim_type: Literal["uncited", "cited"]
    statement: str
    cites: list[str] = []


class NoteCard(_Card):
    """note 卡：id = bib key。summary 缺省容忍，由校验层提醒。"""

    summary: str = ""
    pdf: str | None = None


class MethodCard(_Card):
    """method 卡（v1.1 §3.1）：无参数操作协议，库级复用载体。

    derived_from 存 bib key（语义同 cites）；slug 命名，并入全局 id 命名空间。
    """

    statement: str
    protocol: str
    derived_from: list[str] = []


class ParamCard(_Card):
    """param 卡（v1.1 §3.2）：本项目的具体实验参数；method 悬空 = 校验错误。

    values 是自由键值（每篇不同、需逐项核对的实验事实）。
    """

    method: str
    values: dict[str, Any] = {}
    derived_from: list[str] = []
