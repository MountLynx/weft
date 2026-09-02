"""叙事 part → SpecModule spec + tasklist（通道②，代码确定性构造；v1.1 §3.5/§4.4）。

spec 形状：
{
  "part": {"id", "title"},
  "workflow": "results",
  "task_nodes": {"p01": "para-01-01", ...},   # tick 名 → node id
  "nodes": {"para-01-01": {"purpose", "logic", "uses", "entities": [bundle, ...]}},
}
只收 status: approved 的节点与实体（§3.10）；uses 目标含 method/param（§3.5）。
"""
import json

from module_harness import TaskDefinition, Tasklist

from weft.models.narrative import NarrativePart
from weft.store.project import Project
from weft.workflow import WORKFLOW_SPECS


def tick_name(index: int) -> str:
    return f"p{index + 1:02d}"


def entity_bundle(project: Project, entity_id: str) -> dict:
    """已审阅实体全文 bundle（§6.1）；claim 带所引 note 的 summary；
    method 带 protocol；param 带 values 与 method 概要（v1.1 §3.5）。"""
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
    if entity_id in project.methods:
        method = project.methods[entity_id]
        return {
            "id": entity_id, "kind": "method",
            "statement": method.statement,
            "protocol": method.protocol,
            "derived_from": list(method.derived_from),
        }
    if entity_id in project.params:
        param = project.params[entity_id]
        method = project.methods.get(param.method)
        if method is not None and method.status != "approved":
            method = None   # §3.10：未审 method 的 protocol 不得进 prompt
        return {
            "id": entity_id, "kind": "param",
            "values": dict(param.values),
            "method": {"id": param.method,
                       "statement": method.statement if method else "",
                       "protocol": method.protocol if method else ""},
        }
    raise ValueError(f"uses 指向不支持的实体类型或不存在：{entity_id}")


def build_spec(project: Project, part: NarrativePart,
               workflow: str = "results") -> dict:
    def _approved(eid: str) -> bool:
        for cards in (project.facts, project.claims, project.methods,
                      project.params):
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
        "workflow": workflow,
        "task_nodes": {tick_name(i): n.id for i, n in enumerate(approved)},
        "nodes": nodes,
    }


def _para_prompt(node_spec: dict, preceding_ticks: list[str]) -> str:
    """Layer 3（prompt_extra，追加语义）：节点要求 + 实体全文 + part 内前文。"""
    prompt = (
        f"节点 purpose：{node_spec['purpose']}\n"
        f"节点 logic：{node_spec['logic'] or '（无）'}\n"
        "可引用的已审阅实体（JSON，只准使用这些）：\n"
        + json.dumps(node_spec["entities"], ensure_ascii=False, indent=1)
    )
    if preceding_ticks:
        prompt += ("\n前文已生成的段落（本 part 内，仅供衔接，不得复述）：\n"
                   + "\n".join(f"{{{t}}}" for t in preceding_ticks))
    return prompt


def build_tasklist(spec: dict, *, align: bool) -> Tasklist:
    """p01..pNN 顺序链 --> [AL -->] V；part 内前文经 inputs 别名注入（决策 10）。

    harness 层配置（prompt_core 等）在 run.py 按工作流注册；这里给任务级
    温度与 inputs 覆盖。flow 多行化（tickflow 起始标记行只允许一条边）。
    """
    temperature = WORKFLOW_SPECS[spec.get("workflow", "results")]["temperature"]
    ticks = list(spec["task_nodes"])
    tasks: dict[str, TaskDefinition] = {}
    for i, tick in enumerate(ticks):
        node_spec = spec["nodes"][spec["task_nodes"][tick]]
        preceding = ticks[:i]
        kwargs: dict = dict(
            type="harness", harness="draft_para",
            prompt=_para_prompt(node_spec, preceding),
            outputformat={"type": "json_object"},
            temperature=temperature,
        )
        if preceding:
            kwargs["inputs"] = {t: t for t in preceding}
        tasks[tick] = TaskDefinition(**kwargs)
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
