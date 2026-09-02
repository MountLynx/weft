"""叙事层模型（v1.1 §4.2）：part（生产与组装单位）/ 节点（审阅单位）/ 引用。"""
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


class NarrativePart(BaseModel):
    """part 文件：位置由目录路径 + 文件名前缀决定，order 已退役（v1.1 §4.2）。

    workflow 为显式路由覆盖（词表校验在 validation 层 E-WORKFLOW-UNKNOWN）。
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    section: str
    workflow: str | None = None
    nodes: list[Node] = []
