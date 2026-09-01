"""叙事层模型（spec §3.5）：节（section）/ 节点（node）/ 引用（use）。"""
from pydantic import BaseModel, ConfigDict

from weft.models.cards import ReviewStatus


class Use(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    role: str  # 软词表（W-ROLE-VOCAB），模型层放行超集


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    purpose: str  # 软词表（W-PURPOSE-VOCAB）
    uses: list[Use] = []
    logic: str = ""
    status: ReviewStatus
    comment: str = ""


class NarrativeSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    section: str
    order: int
    nodes: list[Node] = []
