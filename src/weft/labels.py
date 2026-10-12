"""实体语义标签（编号 → 内容摘要）：review / graph / show / WebUI 共用展示层。

纯数据层：只读 Project，不做 IO、不 import llm。key 字段映射沿用 WebUI 卡片
列表页既有约定（设计 D2）：param 的 key 字段是 method（引用 id），param 本就
slug 命名，不另造约定。
"""
from __future__ import annotations

from weft.store.project import Project

# kind → Project 属性名（models/cards.py 六类卡；web/common.py 同源导入）
KIND_ATTRS = {"data": "data_cards", "fact": "facts", "claim": "claims",
              "note": "notes", "method": "methods", "param": "params"}

KEY_FIELD = {"data": "description", "fact": "statement", "claim": "statement",
             "note": "summary", "method": "statement", "param": "method"}


def cap(text: str, limit: int = 40) -> str:
    """展示截断：超长加省略号（惯例同 digest._cap，上限按终端行宽取小）。"""
    return text if len(text) <= limit else text[:limit] + "…"


def find_card(project: Project, eid: str) -> tuple[str, object] | None:
    """按 id 找卡（六类全局命名空间）；未命中返回 None。"""
    for kind, attr in KIND_ATTRS.items():
        card = getattr(project, attr).get(eid)
        if card is not None:
            return kind, card
    return None


def entity_digest(project: Project, eid: str, limit: int = 40) -> str:
    """实体语义摘要（key 字段截断）；未命中或为空 → ""。"""
    found = find_card(project, eid)
    if found is None:
        return ""
    kind, card = found
    return cap(getattr(card, KEY_FIELD[kind], "") or "", limit)


def label_map(project: Project, ids) -> dict[str, str]:
    """批量 id → 摘要（模板一次注入）。"""
    return {eid: entity_digest(project, eid) for eid in ids}
