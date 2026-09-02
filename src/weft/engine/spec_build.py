"""叙事 part → SpecModule spec + tasklist（通道②，代码确定性构造，spec §6.1/6.2）。

spec 形状：
{
  "part": {"id", "title"},
  "task_nodes": {"p01": "para-01-01", ...},   # tick 名 → node id
  "nodes": {"para-01-01": {"purpose", "logic", "uses", "entities": [bundle, ...]}},
}
只收 status: approved 的节点与实体（spec §3.10：生成器只读 approved）。
"""
import json

from module_harness import TaskDefinition, Tasklist

from weft.models.narrative import NarrativePart
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


def build_spec(project: Project, part: NarrativePart) -> dict:
    def _approved(eid: str) -> bool:
        for cards in (project.facts, project.claims):
            card = cards.get(eid)
            if card is not None:
                return card.status == "approved"
        return False

    approved = [n for n in part.nodes if n.status == "approved"]
    nodes = {}
    for n in approved:
        usable = [u for u in n.uses if _approved(u.id)]
        nodes[n.id] = {
            "purpose": n.purpose,
            "logic": n.logic,
            "uses": [{"id": u.id, "role": u.role} for u in usable],
            "entities": [entity_bundle(project, u.id) for u in usable],
        }
    return {
        "part": {"id": part.id, "title": part.section},
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
    """p01..pNN 顺序链 --> [AL -->] V，flow 多行化（tickflow 每行只允许一条边）。

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
            inputs={"spec": "{spec}", "tasklist": "{tasklist}", "node": "{node}",
                    **aliases},
        )
    # V 的 view 键来自 TaskDefinition.inputs（flow 只定触发边，不注入 view）；
    # 逐 tick 声明为自引用输入，V 脚本才能 view[tick].value 读各段输出。
    tasks["V"] = TaskDefinition(type="script", script="weft_validate_draft",
                                inputs={tick: tick for tick in ticks})
    chain = ticks + (["AL"] if align else []) + ["V"]
    lines = [f"[{chain[0]}] --> {chain[1]}"]
    lines += [f"{chain[i]} --> {chain[i + 1]}" for i in range(1, len(chain) - 1)]
    return Tasklist(tasks=tasks, flow="\n".join(lines))
