"""叙事节 → SpecModule spec + tasklist（通道②，代码确定性构造，spec §6.1/6.2）。

spec 形状：
{
  "section": {"id", "title", "order"},
  "task_nodes": {"p01": "para-01-01", ...},   # tick 名 → node id
  "nodes": {"para-01-01": {"purpose", "logic", "uses", "entities": [bundle, ...]}},
}
只收 status: approved 的节点与实体（spec §3.10：生成器只读 approved）。
"""
import json

from module_harness import TaskDefinition, Tasklist

from weft.models.narrative import NarrativeSection
from weft.store.project import Project


def tick_name(index: int) -> str:
    return f"p{index + 1:02d}"


def entity_bundle(project: Project, entity_id: str) -> dict:
    """已审阅实体全文 bundle（spec §6.1）；claim 额外带所引 note 的 summary。

    uses 只准引 fact/claim（spec §2）；note 经 claim.cites 间接进入。
    """
    if entity_id in project.facts:
        fact = project.facts[entity_id]
        return {
            "id": entity_id, "kind": "fact",
            "statement": fact.statement,
            "data": [{"id": d, "description": project.data_cards[d].description,
                      "source": project.data_cards[d].source}
                     for d in fact.data if d in project.data_cards],
        }
    if entity_id in project.claims:
        claim = project.claims[entity_id]
        return {
            "id": entity_id, "kind": "claim",
            "statement": claim.statement,
            "claim_type": claim.claim_type,
            "cites": list(claim.cites),
            "note_summaries": [{"key": k, "summary": project.notes[k].summary}
                               for k in claim.cites if k in project.notes],
        }
    raise ValueError(f"uses 指向非 fact/claim 实体或不存在：{entity_id}")


def build_spec(project: Project, section: NarrativeSection) -> dict:
    approved = [n for n in section.nodes if n.status == "approved"]
    nodes = {}
    for n in approved:
        nodes[n.id] = {
            "purpose": n.purpose,
            "logic": n.logic,
            "uses": [{"id": u.id, "role": u.role} for u in n.uses],
            "entities": [entity_bundle(project, u.id) for u in n.uses],
        }
    return {
        "section": {"id": section.id, "title": section.section, "order": section.order},
        "task_nodes": {tick_name(i): n.id for i, n in enumerate(approved)},
        "nodes": nodes,
    }


def _para_prompt(node_spec: dict) -> str:
    """Layer 3（prompt_extra，追加语义）：本节点的要求与实体全文。"""
    return (
        f"节点 purpose：{node_spec['purpose']}\n"
        f"节点 logic：{node_spec['logic'] or '（无）'}\n"
        "可引用的已审阅实体（JSON，只准使用这些）：\n"
        + json.dumps(node_spec["entities"], ensure_ascii=False, indent=1)
    )


def build_tasklist(spec: dict, *, align: bool) -> Tasklist:
    """p01..pNN 顺序链 --> [AL -->] V。

    harness 层配置（prompt_core 等）在 run.py 注册；这里只给任务级覆盖。
    """
    ticks = list(spec["task_nodes"])
    tasks: dict[str, TaskDefinition] = {}
    for tick in ticks:
        node_spec = spec["nodes"][spec["task_nodes"][tick]]
        tasks[tick] = TaskDefinition(
            type="harness", harness="draft_para",
            prompt=_para_prompt(node_spec),
            outputformat={"type": "json_object"},
            temperature=0.3,
        )
    if align:
        aliases = {f"d{i + 1}": tick for i, tick in enumerate(ticks)}
        tasks["AL"] = TaskDefinition(
            type="harness", harness="align_check",
            prompt="已生成的全部段落（逐段 JSON）：\n"
                   + "\n".join(f"{{{k}}}" for k in aliases),
            inputs=aliases,
        )
    tasks["V"] = TaskDefinition(type="script", script="weft_validate_draft")
    flow_ticks = ticks + (["AL"] if align else []) + ["V"]
    return Tasklist(tasks=tasks, flow=" --> ".join(flow_ticks))
