"""卡片/叙事文件写回（spec §5 store 层"保存"职责补齐；webui 设计 §4.2）。

只服务"人写"场景（WebUI 审阅与编辑）。AI 产物落盘白名单不受影响（红线 4）。
写入固定 LF（落盘前归一化 CRLF）。claim 的 claim_type 决定目录（loader 强制一致），
save_card 按卡当前字段计算规范路径；old_rel 不同即为迁移，旧文件删除。
"""
from __future__ import annotations

from pathlib import Path

import frontmatter

from weft.models.cards import (
    ClaimCard,
    DataCard,
    FactCard,
    MethodCard,
    NoteCard,
    ParamCard,
)
from weft.models.narrative import NarrativePart
from weft.store.project import Project

_CARD_DIRS = [(DataCard, "metadata/data"), (FactCard, "metadata/facts"),
              (NoteCard, "metadata/notes"), (MethodCard, "metadata/methods"),
              (ParamCard, "metadata/params")]


def card_relpath(card) -> str:
    """卡片规范相对路径（posix）；文件名 = id（spec §3.9）。"""
    if isinstance(card, ClaimCard):
        return f"metadata/claims/{card.claim_type}/{card.id}.md"
    for model, directory in _CARD_DIRS:
        if isinstance(card, model):
            return f"{directory}/{card.id}.md"
    raise TypeError(f"未知卡片类型：{type(card).__name__}")


def _dump(card) -> str:
    text = frontmatter.dumps(frontmatter.Post("", **card.model_dump()))
    return text.replace("\r\n", "\n").replace("\r", "\n")


def save_card(root: Path, card, *, old_rel: str | None = None) -> Path:
    """写回卡片；claim_type 变更（old_rel 与新路径不同）时迁移文件。"""
    rel = card_relpath(card)
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dump(card), encoding="utf-8", newline="\n")
    if old_rel is not None and old_rel != rel:
        (root / old_rel).unlink()
    return path


def create_card(root: Path, card) -> Path:
    path = root / card_relpath(card)
    if path.exists():
        raise FileExistsError(f"卡片已存在：{card_relpath(card)}")
    return save_card(root, card)


def next_card_id(project: Project, prefix: str) -> str:
    """下一可用实体 id：全局唯一命名空间，两位零填充进位（spec §3.9）。"""
    used = set(project.card_paths)
    n = 1
    while f"{prefix}-{n:02d}" in used:
        n += 1
    return f"{prefix}-{n:02d}"


def save_part(project: Project, part: NarrativePart) -> Path:
    """叙事 part 写回：frontmatter 重序列化为 part.model_dump()，正文原样保留。"""
    path = project.root / project.part_paths[part.id]
    body = frontmatter.load(path).content  # 1.3.0：正文属性是 content（无 .body）
    text = frontmatter.dumps(frontmatter.Post(body, **part.model_dump()))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    path.write_text(text, encoding="utf-8", newline="\n")
    return path
