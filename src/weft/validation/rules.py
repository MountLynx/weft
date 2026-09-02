"""§4 校验规则。store 层结构诊断（解析/重复/目录）不在本模块。

软词表（spec §3.5）：purpose/role 允许超集，超词表只提醒。
rejected 卡片跳过全部提醒；错误不受豁免（见计划设计决策 2）。
"""
from __future__ import annotations

from weft.diagnostics import Diagnostic, Level
from weft.graphgen.index import build_index
from weft.store.project import Project
from weft.workflow import WORKFLOW_VOCAB

PURPOSE_VOCAB = {"describe", "interpret", "compare", "transition"}
ROLE_VOCAB = {"evidence", "conclusion", "comparison", "background", "counterpoint"}


def _card_rel(project: Project, entity_id: str) -> str:
    return project.card_paths[entity_id].as_posix()


def _part_rel(project: Project, part_id: str) -> str:
    return project.part_paths[part_id].as_posix()


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
    for part in project.parts:
        rel = _part_rel(project, part.id)
        for node in part.nodes:
            for use in node.uses:
                if use.id not in project.facts and use.id not in project.claims \
                        and use.id not in project.methods \
                        and use.id not in project.params:
                    out.append(Diagnostic(
                        Level.ERROR, "E-DANGLING-REF", rel,
                        f"nodes[{node.id}].uses",
                        f"uses 必须指向 fact/claim/method/param，"
                        f"但 {use.id} 不是已存在的实体"))
    for pid, param in project.params.items():
        rel = _card_rel(project, pid)
        if param.method not in project.methods:
            out.append(Diagnostic(Level.ERROR, "E-DANGLING-REF", rel, "method",
                                  f"param 引用了不存在的 method id：{param.method}"))
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


def _check_derived_from_in_bib(project: Project) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for mid, method in project.methods.items():
        for key in method.derived_from:
            if key not in project.bib_keys:
                out.append(Diagnostic(Level.ERROR, "E-DERIVED-FROM-NOT-IN-BIB",
                                      _card_rel(project, mid), "derived_from",
                                      f"derived_from key 不在 bib 中：{key}"))
    for pid, param in project.params.items():
        for key in param.derived_from:
            if key not in project.bib_keys:
                out.append(Diagnostic(Level.ERROR, "E-DERIVED-FROM-NOT-IN-BIB",
                                      _card_rel(project, pid), "derived_from",
                                      f"derived_from key 不在 bib 中：{key}"))
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


def _check_claims(project: Project) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    supported = {cid
                 for fact in project.facts.values()
                 if fact.status != "rejected"
                 for cid in fact.supports}
    for clid, claim in project.claims.items():
        if claim.status == "rejected":
            continue
        rel = _card_rel(project, clid)
        if claim.claim_type == "cited" and not claim.cites:
            out.append(Diagnostic(Level.WARNING, "W-CLAIM-CITED-NO-CITES", rel,
                                  "cites", "claim_type 为 cited 但 cites 为空（缺引文提醒）"))
        if claim.claim_type == "uncited" and clid not in supported:
            out.append(Diagnostic(Level.WARNING, "W-CLAIM-UNSUPPORTED", rel, None,
                                  "uncited claim 没有任何非 rejected 的 fact 支持它"))
    return out


def _check_figures_files(project: Project) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    fig_dir = project.root / project.figures_dir
    referenced: set[str] = set()
    for card in project.data_cards.values():
        if card.status == "rejected":
            continue
        for ref in card.refs:
            referenced.add(ref)
            # 表格（tbl-*）是排版产物不是图片文件，不检查 figures/ 目录
            if ref.startswith("fig-") \
                    and not (fig_dir / f"{ref}.png").exists() \
                    and not (fig_dir / f"{ref}.pdf").exists():
                out.append(Diagnostic(
                    Level.WARNING, "W-FIGURE-FILE-MISSING", _card_rel(project, card.id),
                    "refs", f"图文件缺失：{project.figures_dir}/{ref}.png|pdf"))
    for key, entry in project.figures.items():
        used = key in referenced or any(f"{key}{sub}" in referenced for sub in entry.subfigs)
        if not used:
            out.append(Diagnostic(Level.WARNING, "W-FIGURE-UNUSED",
                                  "metadata/figures.yaml", key,
                                  f"figures.yaml 中的图没有被任何 data 卡引用：{key}"))
    return out


def _check_orphans(project: Project) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for eid, entry in build_index(project)["entities"].items():
        if entry["kind"] == "note" or entry["status"] == "rejected":
            continue
        if not entry["referenced_by"]["nodes"]:
            out.append(Diagnostic(Level.WARNING, "W-ORPHAN", _card_rel(project, eid),
                                  None, "孤儿实体：未被任何叙事节点引用（含间接可达）"))
    return out


def _check_notes_summary(project: Project) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for nid, note in project.notes.items():
        if note.status != "rejected" and not note.summary.strip():
            out.append(Diagnostic(Level.WARNING, "W-NOTE-NO-SUMMARY",
                                  _card_rel(project, nid), "summary",
                                  "note 缺少 summary（该引文处 AI 只能凭 bib 条目行文）"))
    return out


def _check_note_cards_exist(project: Project) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for clid, claim in project.claims.items():
        if claim.status == "rejected":
            continue
        for key in claim.cites:
            if key in project.bib_keys and key not in project.notes:
                out.append(Diagnostic(Level.WARNING, "W-NOTE-MISSING",
                                      _card_rel(project, clid), "cites",
                                      f"引文 {key} 在 bib 中但没有 note 卡"
                                      "（该引文处 AI 只能凭 bib 条目行文）"))
    for mid, method in project.methods.items():
        if method.status == "rejected":
            continue
        for key in method.derived_from:
            if key in project.bib_keys and key not in project.notes:
                out.append(Diagnostic(Level.WARNING, "W-NOTE-MISSING",
                                      _card_rel(project, mid), "derived_from",
                                      f"引文 {key} 在 bib 中但没有 note 卡"
                                      "（该引文处 AI 只能凭 bib 条目行文）"))
    for pid, param in project.params.items():
        if param.status == "rejected":
            continue
        for key in param.derived_from:
            if key in project.bib_keys and key not in project.notes:
                out.append(Diagnostic(Level.WARNING, "W-NOTE-MISSING",
                                      _card_rel(project, pid), "derived_from",
                                      f"引文 {key} 在 bib 中但没有 note 卡"
                                      "（该引文处 AI 只能凭 bib 条目行文）"))
    return out


def _check_vocab(project: Project) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for part in project.parts:
        rel = _part_rel(project, part.id)
        for node in part.nodes:
            if node.status == "rejected":
                continue
            if node.purpose not in PURPOSE_VOCAB:
                out.append(Diagnostic(
                    Level.WARNING, "W-PURPOSE-VOCAB", rel,
                    f"nodes[{node.id}].purpose",
                    f"purpose 不在词表 {sorted(PURPOSE_VOCAB)}：{node.purpose}"))
            for i, use in enumerate(node.uses):
                if use.role not in ROLE_VOCAB:
                    out.append(Diagnostic(
                        Level.WARNING, "W-ROLE-VOCAB", rel,
                        f"nodes[{node.id}].uses[{i}].role",
                        f"role 不在词表 {sorted(ROLE_VOCAB)}：{use.role}"))
    return out


def _check_workflow(project: Project) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for part in project.parts:
        if part.workflow and part.workflow not in WORKFLOW_VOCAB:
            out.append(Diagnostic(
                Level.ERROR, "E-WORKFLOW-UNKNOWN",
                project.part_paths[part.id].as_posix(), "workflow",
                f"workflow 不在词表 {sorted(WORKFLOW_VOCAB)}：{part.workflow}"))
    return out


def validate_project(project: Project) -> list[Diagnostic]:
    """交叉校验，返回错误在前（按路径/码排序）的全部诊断。"""
    diagnostics: list[Diagnostic] = []
    diagnostics += _check_dangling_refs(project)
    diagnostics += _check_cites_in_bib(project)
    diagnostics += _check_derived_from_in_bib(project)
    diagnostics += _check_notes_in_bib(project)
    diagnostics += _check_refs_in_figures(project)
    diagnostics += _check_claims(project)
    diagnostics += _check_figures_files(project)
    diagnostics += _check_orphans(project)
    diagnostics += _check_notes_summary(project)
    diagnostics += _check_note_cards_exist(project)
    diagnostics += _check_vocab(project)
    diagnostics += _check_workflow(project)

    order = {Level.ERROR: 0, Level.WARNING: 1}
    diagnostics.sort(key=lambda d: (order[d.level], d.path, d.code, d.field or ""))
    return diagnostics
