"""卡片改名引擎（rename 设计定案）：计划-应用两段式，fail-closed。

计划段零写入：N9 命名合法性、全卡种命名空间碰撞、引用位点穷举扫描；
应用段按 R7 顺序落盘：写新文件 → 删旧文件 → 改写引用卡 → 改写 part → managed bib。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from weft.labels import find_card
from weft.scaffold import NewCollisionError, _ensure_component
from weft.store.project import Project
from weft.store.writer import card_relpath, save_card, save_part


class RenameError(Exception):
    """无码改名错误：旧 id 不存在、新旧 id 相同（R5，CLI 打印 ERROR 行）。"""


@dataclass(frozen=True)
class RenamePlan:
    kind: str
    old_id: str
    new_id: str
    old_rel: str
    new_rel: str
    card_refs: dict[str, list[str]]   # 引用卡 id → 受影响字段（data/supports/cites/method/derived_from）
    card_rels: dict[str, str]         # 引用卡 id → 相对路径（计划打印用）
    part_refs: dict[str, int]         # part id → uses 改写处数
    part_rels: dict[str, str]         # part id → 相对路径（计划打印用）
    needs_bib_sync: bool              # note 改名且 bib_managed（R3）


@dataclass(frozen=True)
class RenameResult:
    written: list[Path]
    bib_status: str | None   # bibgen.sync_managed_bib 返回值（仅 note 改名时有意义）


def _new_rel(card, new_id: str) -> str:
    """新 id 的规范相对路径：借同种卡模型推导（claim 目录随 claim_type）。"""
    return card_relpath(card.model_copy(update={"id": new_id}))


def plan_rename(project: Project, old_id: str, new_id: str) -> RenamePlan:
    found = find_card(project, old_id)
    if found is None:
        raise RenameError(f"项目里不存在卡片：{old_id}")
    kind, card = found
    if old_id == new_id:
        raise RenameError(f"新 id 与原 id 相同：{old_id}")
    _ensure_component("new_id", new_id)
    if new_id in project.card_paths:
        raise NewCollisionError(
            f"id 已被占用：{new_id}（{project.card_paths[new_id].as_posix()}）",
            project.card_paths[new_id].as_posix())

    card_refs: dict[str, list[str]] = {}
    card_rels: dict[str, str] = {}

    def _mark(cid: str, fname: str) -> None:
        if cid == old_id:   # 改名卡自身不进引用改写列表（内容随文件迁移）
            return
        if fname not in card_refs.setdefault(cid, []):
            card_refs[cid].append(fname)
        card_rels[cid] = project.card_paths[cid].as_posix()

    for cid, f in project.facts.items():
        if old_id in f.data:
            _mark(cid, "data")
        if old_id in f.supports:
            _mark(cid, "supports")
    for cid, c in project.claims.items():
        if old_id in c.cites:
            _mark(cid, "cites")
    for cid, m in project.methods.items():
        if old_id in m.derived_from:
            _mark(cid, "derived_from")
    for cid, p in project.params.items():
        if p.method == old_id:
            _mark(cid, "method")
        if old_id in p.derived_from:
            _mark(cid, "derived_from")

    part_refs: dict[str, int] = {}
    part_rels: dict[str, str] = {}
    for part in project.parts:
        n = sum(1 for node in part.nodes for u in node.uses if u.id == old_id)
        if n:
            part_refs[part.id] = n
            part_rels[part.id] = project.part_paths[part.id].as_posix()

    return RenamePlan(kind=kind, old_id=old_id, new_id=new_id,
                      old_rel=project.card_paths[old_id].as_posix(),
                      new_rel=_new_rel(card, new_id),
                      card_refs=card_refs, card_rels=card_rels,
                      part_refs=part_refs, part_rels=part_rels,
                      needs_bib_sync=(kind == "note" and project.bib_managed))


def apply_rename(project: Project, plan: RenamePlan) -> RenameResult:
    """按 R7 顺序落盘：写新文件 → 删旧文件 → 改写引用卡 → 改写 part → managed bib。"""
    written: list[Path] = []
    _kind, card = find_card(project, plan.old_id)
    new_card = card.model_copy(update={"id": plan.new_id})
    written.append(save_card(project.root, new_card, old_rel=plan.old_rel))

    for cid, fields in plan.card_refs.items():
        _ref_kind, ref_card = find_card(project, cid)
        updates: dict = {}
        for fname in fields:
            value = getattr(ref_card, fname)
            if isinstance(value, str):            # param.method 单值
                updates[fname] = plan.new_id
            else:                                 # 列表通道
                updates[fname] = [plan.new_id if v == plan.old_id else v
                                  for v in value]
        written.append(save_card(project.root, ref_card.model_copy(update=updates)))

    for part in project.parts:
        if part.id not in plan.part_refs:
            continue
        new_nodes = [node.model_copy(update={"uses": [
            u.model_copy(update={"id": plan.new_id}) if u.id == plan.old_id else u
            for u in node.uses]})
            if any(u.id == plan.old_id for u in node.uses) else node
            for node in part.nodes]
        save_part(project, part.model_copy(update={"nodes": new_nodes}))
        written.append(project.root / project.part_paths[part.id])

    bib_status = None
    if plan.kind == "note":
        from weft.bibgen import sync_managed_bib
        bib_status = sync_managed_bib(project.root)
    return RenameResult(written=written, bib_status=bib_status)
