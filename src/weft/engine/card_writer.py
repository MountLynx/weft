"""受控写入器（红线 4）：AI 产物唯二落盘点（inspire / parse 两管线共用）。

- 草稿卡：metadata/facts|claims/<claim_type>|notes/<id>.md（status: draft，进现有审阅流）
- 替换提案：inspirations/proposals/<目标卡id>.md（metadata 扫描路径外，不撞 id）

与 engine/drafts.py 同纪律：路径不接受调用方传入，id 过逃逸检查，固定 LF。
id 分配（next_card_id / all_card_ids）是两管线 A1 聚合的真重复公用件（计划 P1）。
"""
from __future__ import annotations

from pathlib import Path

import frontmatter

from weft.store.project import Project

PROPOSALS_DIR = ("inspirations", "proposals")


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _safe_id(card_id: str) -> None:
    if not card_id or Path(card_id).name != card_id or card_id in (".", ".."):
        raise ValueError(f"非法卡 id（路径逃逸）：{card_id}")


def _card_path(project: Project, kind: str, fields: dict) -> Path:
    _safe_id(fields["id"])
    if kind == "fact":
        return project.root / "metadata" / "facts" / f"{fields['id']}.md"
    if kind == "claim":
        claim_type = fields["claim_type"]
        if claim_type not in ("cited", "uncited"):
            raise ValueError(f"非法 claim_type：{claim_type}")
        return (project.root / "metadata" / "claims" / claim_type
                / f"{fields['id']}.md")
    if kind == "note":
        return project.root / "metadata" / "notes" / f"{fields['id']}.md"
    raise ValueError(f"不支持的卡类型：{kind}")


def _write_card(path: Path, fields: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post("", **fields)
    path.write_text(_normalize(frontmatter.dumps(post)),
                    encoding="utf-8", newline="\n")
    return path


def write_proposed_cards(project: Project,
                         entries: list[tuple[str, dict]]) -> list[Path]:
    """批量写草稿卡；entries = [(kind, frontmatter 字段)]，kind ∈ fact|claim|note。"""
    return [_write_card(_card_path(project, kind, fields), fields)
            for kind, fields in entries]


def write_proposal(project: Project, target_id: str, fields: dict) -> Path:
    """写替换提案（完整新卡，id = 目标卡 id）。"""
    _safe_id(target_id)
    if fields.get("id") != target_id:
        raise ValueError(f"提案卡 id {fields.get('id')} 与目标卡 {target_id} 不一致")
    path = project.root.joinpath(*PROPOSALS_DIR) / f"{target_id}.md"
    return _write_card(path, fields)


def all_card_ids(project: Project) -> set[str]:
    """全部既有卡 id（六类卡全局唯一命名空间）。"""
    used: set[str] = set()
    for table in (project.data_cards, project.facts, project.claims,
                  project.notes, project.methods, project.params):
        used.update(table)
    return used


def next_card_id(used: set[str], prefix: str) -> str:
    """前缀-序号分配（fact-01 / claim-01…）；used 原地更新防重。"""
    n = 1
    while f"{prefix}-{n:02d}" in used:
        n += 1
    card_id = f"{prefix}-{n:02d}"
    used.add(card_id)
    return card_id
