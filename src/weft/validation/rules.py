"""§4 校验规则。store 层结构诊断（解析/重复/目录）不在本模块。

软词表（spec §3.5）：purpose/role 允许超集，超词表只提醒。
rejected 卡片跳过全部提醒；错误不受豁免（见计划设计决策 2）。
"""
from __future__ import annotations

from weft.diagnostics import Diagnostic, Level
from weft.store.project import Project

PURPOSE_VOCAB = {"describe", "interpret", "compare", "transition"}
ROLE_VOCAB = {"evidence", "conclusion", "comparison", "background", "counterpoint"}


def _card_rel(project: Project, entity_id: str) -> str:
    return project.card_paths[entity_id].as_posix()


def _section_rel(project: Project, section_id: str) -> str:
    return project.section_paths[section_id].as_posix()


def _check_dangling_refs(project: Project) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for fid, fact in project.facts.items():
        rel = _card_rel(project, fid)
        for did in fact.data:
            if did not in project.data_cards:
                out.append(Diagnostic(Level.ERROR, "E-DANGLING-REF", rel, "data",
                                      f"fact 引用了不存在的 data id：{did}"))
        for cid in fact.supports:
            if cid not in project.claims:
                out.append(Diagnostic(Level.ERROR, "E-DANGLING-REF", rel, "supports",
                                      f"fact 引用了不存在的 claim id：{cid}"))
    for section in project.sections:
        rel = _section_rel(project, section.id)
        for node in section.nodes:
            for use in node.uses:
                if use.id not in project.facts and use.id not in project.claims:
                    out.append(Diagnostic(
                        Level.ERROR, "E-DANGLING-REF", rel,
                        f"nodes[{node.id}].uses",
                        f"uses 必须指向 fact/claim，但 {use.id} 不是已存在的 fact/claim"))
    return out


def _check_cites_in_bib(project: Project) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for clid, claim in project.claims.items():
        for key in claim.cites:
            if key not in project.bib_keys:
                out.append(Diagnostic(Level.ERROR, "E-CITES-NOT-IN-BIB",
                                      _card_rel(project, clid), "cites",
                                      f"cites key 不在 bib 中：{key}"))
    return out


def _check_notes_in_bib(project: Project) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for nid in project.notes:
        if nid not in project.bib_keys:
            out.append(Diagnostic(Level.ERROR, "E-NOTE-NOT-IN-BIB",
                                  _card_rel(project, nid), "id",
                                  f"note 的 id（bib key）不在 bib 中：{nid}"))
    return out


def _valid_refs(project: Project) -> set[str]:
    """合法 ref = figures.yaml 顶层键 ∪ 键+子图后缀（fig-01 + a → fig-01a）。"""
    refs = set(project.figures)
    for key, entry in project.figures.items():
        refs |= {f"{key}{sub}" for sub in entry.subfigs}
    return refs


def _check_refs_in_figures(project: Project) -> list[Diagnostic]:
    valid = _valid_refs(project)
    out: list[Diagnostic] = []
    for did, card in project.data_cards.items():
        for ref in card.refs:
            if ref not in valid:
                out.append(Diagnostic(Level.ERROR, "E-REFS-NOT-IN-FIGURES",
                                      _card_rel(project, did), "refs",
                                      f"refs 编号不在 figures.yaml 中：{ref}"))
    return out


def validate_project(project: Project) -> list[Diagnostic]:
    """交叉校验，返回错误在前（按路径/码排序）的全部诊断。"""
    diagnostics: list[Diagnostic] = []
    diagnostics += _check_dangling_refs(project)
    diagnostics += _check_cites_in_bib(project)
    diagnostics += _check_notes_in_bib(project)
    diagnostics += _check_refs_in_figures(project)

    order = {Level.ERROR: 0, Level.WARNING: 1}
    diagnostics.sort(key=lambda d: (order[d.level], d.path, d.code, d.field or ""))
    return diagnostics
