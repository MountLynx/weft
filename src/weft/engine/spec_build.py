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
    "4. 占位符只是括注位置，不是句子成分：不得充当主语、宾语或谓语"
    "（占位符被系统替换或移除后，句子必须仍然语法完整）；\n"
    "5. 同一占位符在本段只写一次，不要为同一图表或同一文献重复书写；\n"
    "6. 禁止自行写出字面图号/表号（Fig. 1a、Table 1 等）——真实编号由系统填充；\n"
    "7. 全文禁止出现真实 [@key] 引用与 {{…}} 以外的标记。\n"
)

_CLAIM_CLASS_EXPLAIN = (
    "claim 分类含义：cited=论断需要文献支撑（写 {{claim-xx}} 占位符，"
    "由系统填 [@key]）；uncited=本研究内部推理得到的论断（直接陈述，无需文献）。"
)


def _ref_view(label: str, project: Project) -> dict:
    """ref label → 图注视图（设计 §6.1 实体全文含 caption）：figures.yaml 顺
    fact→data→refs 取 caption/子图说明；悬空 ref 只留 label，不造空字段。"""
    view: dict = {"label": label}
    for key, entry in project.figures.items():
        if label.startswith(key):
            if entry.caption:
                view["caption"] = entry.caption
            suffix = label[len(key):]
            if suffix and suffix in entry.subfigs:
                view["subfig"] = entry.subfigs[suffix]
            break
    return view


def build_node_spec(project: Project, node: Node) -> dict:
    """单节点 → uses 实体全文 bundle（只收 approved；fact 附 data 描述与图注，
    claim 带分类与 note 摘要）。"""
    uses = []
    for u in node.uses:
        if u.id in project.facts:
            card = project.facts[u.id]
            if card.status != "approved":
                continue
            uses.append({
                "id": u.id, "role": u.role, "kind": "fact",
                "statement": card.statement,
                "data": [{"id": d, "description": project.data_cards[d].description,
                          "refs": [_ref_view(r, project)
                                   for r in project.data_cards[d].refs]}
                         for d in card.data if d in project.data_cards],
            })
        elif u.id in project.claims:
            card = project.claims[u.id]
            if card.status != "approved":
                continue
            uses.append({
                "id": u.id, "role": u.role, "kind": "claim",
                "claim_type": card.claim_type,
                "statement": card.statement,
                "cites": list(card.cites),
                "note_summaries": [{"key": k, "summary": project.notes[k].summary}
                                   for k in card.cites if k in project.notes],
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


_CONSISTENCY_BASIS = (
    "一致性基准 = uses 实体全文 + 节点 logic（两者共同构成本段合法素材来源；"
    "method/param 管线的协议与参数全部承载于节点 logic，同样是一致性基准）。"
)

def check_prompt(spec: dict, gen_text: str, stage: str) -> str:
    return (
        f"【draft·校验】\n任务（{stage}）：逐项审查并只输出 JSON"
        ' {"verdict": "pass"} 或 {"verdict": "fix", "paragraph": "修正后全文"}。\n'
        "审查项：① 内容与 uses 实体及节点 logic 一致"
        "（不得引入两者之外的事实，不得改写数据与数值）；"
        "② 覆盖 uses 与节点 logic 的全部要点，不遗漏；"
        "③ 占位符只使用 uses 内的"
        " {{fact-xx}}/{{claim-xx}}、同一占位符只出现一次、且只是括注位置"
        "（替换或移除后句子仍完整），cited claim 的论断处有占位符、"
        "uncited claim 无占位符；"
        "④ 无 [@key]，也不得自行写出字面图表编号"
        "（如 Fig. 1a / Table 1）——真实编号只能由系统经占位符填充，"
        "正文出现字面图表编号即为违规。"
        "若段落忠实、完整地展开了 uses 实体与节点 logic 的要点，判 pass；"
        "不通过则 verdict=fix 并给出修正后全文（fix 的 paragraph 必须是完整的修正段落，"
        "不得留空——无法给出修正全文时宁可通过不判 fix；"
        "宁可 fix 不要放过事实偏移）。\n"
        f"{_CONSISTENCY_BASIS}\n"
        f"uses（JSON）：\n{_uses_json(spec)}\n"
        f"节点 logic：{spec['node']['logic'] or '（无）'}\n"
        f"待审段落：\n<<<PARAGRAPH\n{gen_text}\nPARAGRAPH>>>"
    )


def link_prompt(spec: dict, gen_text: str, check_json: str, context: dict) -> str:
    prior = "\n".join(f"- {t}" for t in context.get("prior", [])) or "（无）"
    prev_tail = context.get("prev_tail") or "（无）"
    next_head = context.get("next_head") or "（无）"
    methods_note = ""
    if context.get("workflow") == "methods":
        methods_note = (
            "本段是方法学描述：不要添加承接性开头或与前后文的论证过渡"
            "（如 To address this gap / Building on this），"
            "以直接的陈述句开头，只在不自然处做最小调整。\n")
    return (
        "【draft·衔接】\n"
        "任务：基于起草稿与审查结论做跨段衔接优化（首尾过渡、指代一致），"
        "不得改变事实内容与占位符。输出：仅输出优化后的段落全文（纯文本，无 JSON）。\n"
        f"{methods_note}"
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
        "必须与 uses 及节点 logic 完全一致，不得加强或弱化；"
        "② 学术风格——正式、克制、逻辑连接清晰；"
        "③ 保留全部 {{fact-xx}}/{{claim-xx}} 占位符原样。\n"
        "输出：仅输出润色后的段落全文（纯文本，无 JSON）。\n"
        f"uses（JSON）：\n{_uses_json(spec)}\n"
        f"节点 logic：{spec['node']['logic'] or '（无）'}\n"
        f"当前工作文本：\n<<<PARAGRAPH\n{text}\nPARAGRAPH>>>"
    )


def recheck_prompt(spec: dict, text: str) -> str:
    return (
        "【draft·校验】\n任务（润色后复检）：重点防润色引入的事实偏移。"
        "只输出 JSON {\"verdict\": \"pass\"} 或 "
        "{\"verdict\": \"fix\", \"paragraph\": \"修正后全文\"}。\n"
        f"{_CONSISTENCY_BASIS}\n"
        "审查项与起草稿审查相同：内容与 uses 实体及节点 logic 一致"
        "（不得引入两者之外的事实，不得改写数据与数值）；"
        "正文不得出现字面图表编号（Fig. 1a / Table 1 等由系统经占位符填充）；"
        "若段落忠实，判 pass；verdict=fix 时 paragraph 必须是完整的修正段落，不得留空。\n"
        f"uses（JSON）：\n{_uses_json(spec)}\n"
        f"节点 logic：{spec['node']['logic'] or '（无）'}\n"
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
