"""叙事节点 → 六节点管线（draft v2）：一次 run 只生成一个段落。

[g 起草（占位符）] → [c1 校验，fix 覆盖] → [l 跨段衔接] → [p 润色] →
[c2 复检（复用 check harness），fix 覆盖] → [f 脚本：占位符确定性填充]
拼接成稿（part→chapter→paper.qmd）归 weft assemble，不在此管线。
prompt 起始标记【draft·…】兼作 mock 客户端分流键。
"""
import json

from module_harness import TaskDefinition, Tasklist

from weft.models.narrative import Node
from weft.store.project import Project

_TEMPERATURE = 0.4

_PLACEHOLDER_RULES = (
    "占位符规则：\n"
    "1. 涉及本段 fact 卡所对应图表的位置写 {{fact-xx}}（xx 用卡 id），"
    "代表此处插入该数据来源图表的字面编号（如 Fig. 1a / Table 1，由系统填充）；\n"
    "2. claim_type=cited 的 claim 被本段陈述时，在其论断处写 {{claim-xx}}，"
    "代表此处插入该 claim 的文献引用（[@key] 由系统填充）；\n"
    "3. claim_type=uncited 的 claim 直接陈述结论，禁止为其写占位符或任何 [@key]；\n"
    "4. 全文禁止出现真实 [@key] 引用与 {{…}} 以外的标记。\n"
)

_CLAIM_CLASS_EXPLAIN = (
    "claim 分类含义：cited=论断需要文献支撑（写 {{claim-xx}} 占位符，"
    "由系统填 [@key]）；uncited=本研究内部推理得到的论断（直接陈述，无需文献）。"
)


def build_node_spec(project: Project, node: Node) -> dict:
    """单节点 → uses bundle：只给 fact/claim 卡自身内容（statement+claim 分类）。

    不传 data/note 派生上下文（生成只需要"这是什么 fact、什么 claim"；
    图表与文献由 f 脚本按占位符确定性填充，用户设计指令）。
    """
    uses = []
    for u in node.uses:
        if u.id in project.facts:
            card = project.facts[u.id]
            if card.status != "approved":
                continue
            uses.append({
                "id": u.id, "role": u.role, "kind": "fact",
                "statement": card.statement,
            })
        elif u.id in project.claims:
            card = project.claims[u.id]
            if card.status != "approved":
                continue
            uses.append({
                "id": u.id, "role": u.role, "kind": "claim",
                "claim_type": card.claim_type,
                "statement": card.statement,
            })
    return {"node": {"id": node.id, "purpose": node.purpose, "logic": node.logic},
            "uses": uses}


def _uses_json(spec: dict) -> str:
    return json.dumps(spec["uses"], ensure_ascii=False, indent=1)


def gen_prompt(overview: str, spec: dict, workflow_core: str) -> str:
    return (
        "【draft·起草】\n"
        f"{workflow_core}\n\n"
        "研究总述（全文背景，用于定位本段位置，不要复述）：\n"
        f"{overview or '（项目未提供研究总述）'}\n\n"
        f"本段任务：purpose={spec['node']['purpose']}；"
        f"logic={spec['node']['logic'] or '（无）'}\n"
        f"本段 uses（已审实体全文 JSON，只准使用这些）：\n{_uses_json(spec)}\n\n"
        f"{_CLAIM_CLASS_EXPLAIN}\n{_PLACEHOLDER_RULES}\n"
        "输出：仅输出段落全文（纯文本，含 {{fact-xx}}/{{claim-xx}} 占位符），无 JSON 无解释。"
    )


def check_prompt(spec: dict, gen_text: str, stage: str) -> str:
    return (
        f"【draft·校验】\n任务（{stage}）：逐项审查并只输出 JSON"
        ' {"verdict": "pass"} 或 {"verdict": "fix", "paragraph": "修正后全文"}。\n'
        "审查项：① 内容与卡片一致（不得引入 uses 之外的事实或改写数据）；"
        "② 覆盖 uses 的全部要点，不遗漏；③ 占位符只使用 uses 内的"
        " {{fact-xx}}/{{claim-xx}}，cited claim 的论断处有占位符、"
        "uncited claim 无占位符；④ 无 [@key]。"
        "通过则 verdict=pass 且只输出 pass；不通过则 verdict=fix 并给出修正后全文"
        "（宁可 fix 不要放过事实偏移）。\n"
        f"uses（JSON）：\n{_uses_json(spec)}\n"
        f"待审段落：\n<<<PARAGRAPH\n{gen_text}\nPARAGRAPH>>>"
    )


def link_prompt(spec: dict, gen_text: str, check_json: str, context: dict) -> str:
    prior = "\n".join(f"- {t}" for t in context.get("prior", [])) or "（无）"
    prev_tail = context.get("prev_tail") or "（无）"
    next_head = context.get("next_head") or "（无）"
    return (
        "【draft·衔接】\n"
        "任务：基于起草稿与审查结论做跨段衔接优化（首尾过渡、指代一致），"
        "不得改变事实内容与占位符。输出：仅输出优化后的段落全文（纯文本，无 JSON）。\n"
        f"本 part 已生成的前文段落：\n{prior}\n"
        f"前一个 part 的末段：{prev_tail}\n"
        f"后一个 part 的首段：{next_head}\n"
        f"起草稿：\n<<<PARAGRAPH\n{gen_text}\nPARAGRAPH>>>\n"
        f"审查结论（JSON，verdict=fix 时以其 paragraph 为准）：\n{check_json}"
    )


def polish_prompt(spec: dict, text: str) -> str:
    return (
        "【draft·润色】\n"
        "任务：学术写作语言润色。重点：① 事实不偏移——数据、结论、限定词"
        "必须与 uses 完全一致，不得加强或弱化；② 学术风格——正式、克制、"
        "逻辑连接清晰；③ 保留全部 {{fact-xx}}/{{claim-xx}} 占位符原样。\n"
        "输出：仅输出润色后的段落全文（纯文本，无 JSON）。\n"
        f"uses（JSON）：\n{_uses_json(spec)}\n"
        f"当前工作文本：\n<<<PARAGRAPH\n{text}\nPARAGRAPH>>>"
    )


def recheck_prompt(spec: dict, text: str) -> str:
    return (
        "【draft·校验】\n任务（润色后复检）：重点防润色引入的事实偏移，"
        "其余同前。只输出 JSON {\"verdict\": \"pass\"} 或 "
        "{\"verdict\": \"fix\", \"paragraph\": \"修正后全文\"}。\n"
        f"uses（JSON）：\n{_uses_json(spec)}\n"
        f"当前工作文本：\n<<<PARAGRAPH\n{text}\nPARAGRAPH>>>"
    )


def build_tasklist(project: Project, node: Node, node_spec: dict,
                   overview: str, workflow_core: str, context: dict) -> Tasklist:
    del project, node  # f 脚本在 run 层经闭包持有；此处只装配 LLM 链
    tasks: dict[str, TaskDefinition] = {
        "g": TaskDefinition(
            type="harness", harness="draft_gen",
            prompt=gen_prompt(overview, node_spec, workflow_core),
            outputformat={"type": "text"}, temperature=_TEMPERATURE),
        "c1": TaskDefinition(
            type="harness", harness="draft_check",
            prompt=check_prompt(node_spec, "{g}", "起草稿审查"),
            outputformat={"type": "json_object"}, temperature=_TEMPERATURE,
            inputs={"g": "g"}),
        "l": TaskDefinition(
            type="harness", harness="draft_link",
            prompt=link_prompt(node_spec, "{g}", "{c1}", context),
            outputformat={"type": "text"}, temperature=_TEMPERATURE,
            inputs={"g": "g", "c1": "c1"}),
        "p": TaskDefinition(
            type="harness", harness="draft_polish",
            prompt=polish_prompt(node_spec, "{l}"),
            outputformat={"type": "text"}, temperature=_TEMPERATURE,
            inputs={"l": "l"}),
        "c2": TaskDefinition(
            type="harness", harness="draft_check",
            prompt=recheck_prompt(node_spec, "{p}"),
            outputformat={"type": "json_object"}, temperature=_TEMPERATURE,
            inputs={"p": "p"}),
        "f": TaskDefinition(
            type="script", script="weft_fill_placeholders",
            inputs={"g": "g", "c1": "c1", "l": "l", "p": "p", "c2": "c2"}),
    }
    flow = "[g] --> c1\nc1 --> l\nl --> p\np --> c2\nc2 --> f"
    return Tasklist(tasks=tasks, flow=flow)


def effective_paragraph(out: dict) -> tuple[str, str | None]:
    """按覆盖链合成有效段落文本；(text, 错误消息)。l/p 为纯文本输出。"""
    from weft.engine.draft_rules import CheckOutput, parse_output
    text = out.get("g")
    if not isinstance(text, str):
        return "", "g 输出不是文本"
    c1, e2 = parse_output(out.get("c1"), CheckOutput, "?", "?")
    if c1 is None:
        return "", f"c1 {e2.message if e2 else ''}"
    if c1.verdict == "fix":
        text = c1.paragraph
    link = out.get("l")
    if isinstance(link, str) and link.strip():
        text = link
    polish = out.get("p")
    if isinstance(polish, str) and polish.strip():
        text = polish
    c2, e3 = parse_output(out.get("c2"), CheckOutput, "?", "?")
    if c2 is None:
        return "", f"c2 {e3.message if e3 else ''}"
    if c2.verdict == "fix":
        text = c2.paragraph
    return text, None
