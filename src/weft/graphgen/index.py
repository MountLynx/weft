"""反向索引与 narrative 正向可达性（纯函数，不写文件；spec §5 graphgen 层）。

可达语义（v1.1 §3.5）：种子 = 叙事节点 uses 直接引用的 fact/claim/method/param；
扩展边 = fact.data → data、fact.supports → claim、param.method → method。
derived_from（method/param → bib key）与 claim.cites 一样进 note 的反向边。
"""
from __future__ import annotations

from weft.store.project import Project

_PLURAL = {"data": "data", "fact": "facts", "claim": "claims",
           "method": "methods", "param": "params"}

_REVERSE_KEYS = ("facts", "claims", "methods", "params", "nodes")


def _kind(entities: dict, eid: str) -> str | None:
    entry = entities.get(eid)
    return entry["kind"] if entry else None


def _edge(entities: dict, target_id: str, field: str, source_id: str,
          expected_kind: str) -> None:
    if _kind(entities, target_id) == expected_kind:
        entities[target_id]["referenced_by"][field].append(source_id)


def build_index(project: Project) -> dict:
    """全量反向索引（含 rejected；消费方自行过滤）。

    referenced_by.facts  : data ← fact.data / claim ← fact.supports
    referenced_by.claims : note ← claim.cites
    referenced_by.params : method ← param.method；note ← param.derived_from
    referenced_by.methods: note ← method.derived_from
    referenced_by.nodes  : 正向可达的叙事节点（fact/claim/method/param 为直接 uses；
                           data 与被 supports 的 claim 经 fact、method 经 param 间接可达）
    """
    entities: dict[str, dict] = {}
    for kind, cards in (("data", project.data_cards), ("fact", project.facts),
                        ("claim", project.claims), ("note", project.notes),
                        ("method", project.methods), ("param", project.params)):
        for cid, card in cards.items():
            entities[cid] = {"kind": kind, "status": card.status,
                             "referenced_by": {k: [] for k in _REVERSE_KEYS}}

    for fid, fact in project.facts.items():
        for did in fact.data:
            _edge(entities, did, "facts", fid, "data")
        for clid in fact.supports:
            _edge(entities, clid, "facts", fid, "claim")
    for clid, claim in project.claims.items():
        for key in claim.cites:
            _edge(entities, key, "claims", clid, "note")
    for pid, param in project.params.items():
        _edge(entities, param.method, "params", pid, "method")
        for key in param.derived_from:
            _edge(entities, key, "params", pid, "note")
    for mid, method in project.methods.items():
        for key in method.derived_from:
            _edge(entities, key, "methods", mid, "note")

    for section in project.sections:
        for node in section.nodes:
            for use in node.uses:
                if _kind(entities, use.id) in ("fact", "claim", "method", "param"):
                    entities[use.id]["referenced_by"]["nodes"].append(node.id)

    # 间接可达：data / 被 supports 的 claim 继承 fact 的节点；method 继承 param 的节点
    for fid, fact in project.facts.items():
        fact_nodes = entities[fid]["referenced_by"]["nodes"]
        if not fact_nodes:
            continue
        for did in fact.data:
            if _kind(entities, did) == "data":
                entities[did]["referenced_by"]["nodes"].extend(fact_nodes)
        for clid in fact.supports:
            if _kind(entities, clid) == "claim":
                entities[clid]["referenced_by"]["nodes"].extend(fact_nodes)
    for pid, param in project.params.items():
        param_nodes = entities[pid]["referenced_by"]["nodes"]
        if param_nodes and _kind(entities, param.method) == "method":
            entities[param.method]["referenced_by"]["nodes"].extend(param_nodes)

    for entry in entities.values():
        entry["referenced_by"] = {k: sorted(set(v))
                                  for k, v in entry["referenced_by"].items()}

    return {"version": 2, "entities": entities}


def used_ids(project: Project) -> dict[str, list[str]]:
    """narrative 正向可达的实体（按类别；note 不参与，叙事不直接引用 note）。"""
    index = build_index(project)
    used: dict[str, list[str]] = {k: [] for k in
                                  ("data", "facts", "claims", "methods", "params")}
    for eid, entry in index["entities"].items():
        if entry["kind"] != "note" and entry["referenced_by"]["nodes"]:
            used[_PLURAL[entry["kind"]]].append(eid)
    for ids in used.values():
        ids.sort()
    return used


def orphan_ids(project: Project) -> dict[str, list[str]]:
    """used 的反集（排除 rejected 与 note）。"""
    index = build_index(project)
    orphans: dict[str, list[str]] = {k: [] for k in
                                     ("data", "facts", "claims", "methods", "params")}
    for eid, entry in index["entities"].items():
        if entry["kind"] == "note" or entry["status"] == "rejected":
            continue
        if not entry["referenced_by"]["nodes"]:
            orphans[_PLURAL[entry["kind"]]].append(eid)
    for ids in orphans.values():
        ids.sort()
    return orphans
