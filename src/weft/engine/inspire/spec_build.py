"""灵感 → SpecModule 任务表（t01–t04 链式；inspire 设计 §4）。

prompt 起始标记【灵感·…】兼作 mock 客户端分流键（计划 D5）。
t03/t04 的 view 注入沿用 M2 决策 10：flow 只定触发边，{tick} 占位 + inputs 别名。
"""
from module_harness import TaskDefinition, Tasklist

_TICK_HARNESS = {
    "t01": "inspire_logic",
    "t02": "inspire_extract",
    "t03": "inspire_review",
    "t04": "inspire_match",
    "t05": "inspire_cover",
}

_TEMPERATURE = 0.2   # 拆解/审查/匹配都要收敛，不用创作温度

_EXTRACT_SCHEMA = (
    '输出 JSON：{"cards": [{"key": "f1/c1/…临时编号", "kind": "fact|claim",'
    ' "statement": "原子陈述", "placeholder": false, "needs_citation": false}],'
    ' "links": [{"from": "f1", "to": "c1"}]}。'
    "规则：数据表述→fact，观点/论断→claim；"
    "本研究数据与文献值的对比→claim（needs_citation=true），"
    "其中本研究自己的数据表述另拆一张 fact 卡并用 link 支持该对比 claim；"
    "\"xxx/某值\"类占位数据置 placeholder=true；"
    "needs_citation=该论断语义上是否需要文献支撑；links 只表达新 fact 支持新 claim。"
)

_REVIEW_SCHEMA = (
    '输出 JSON：{"classifications": [{"key": "…", "verdict": "new|conflict|supplement",'
    ' "against": ["现有卡id"], "reason": "理由", "merged_statement": ""}]}。'
    "规则：new=全新；conflict=与现有卡事实矛盾（against 填冲突卡 id，reason 必填）；"
    "supplement=与现有 fact/claim 卡高度相关且略有补充（目标只能是现存 fact/claim 卡，"
    "data/note 是人工维护的输入卡，禁止作为补充目标；against 填目标卡 id，"
    "merged_statement 必填：包含原卡全部信息与补充内容的完整新卡陈述，不得丢失原卡信息）。"
)

_MATCH_SCHEMA = (
    '输出 JSON：{"fact_data": [{"key": "…", "data_ids": ["现有data卡id"]}],'
    ' "claim_cites": [{"key": "…", "claim_type": "cited|uncited", "cites": ["bib key"],'
    ' "reason": "…"}], "placeholders": [{"text": "占位原文", "matched_fact": "现有fact卡id或null"}]}。'
    "规则：fact 至少关联到一张现有 data 卡才可给 data_ids，关联不到就留空数组；"
    "cites 只能取索引中出现的 note/bib key；索引中的 bib key 通常编码了作者与年份"
    "（如 gikonyo2023 = Gikonyo 2023），灵感中明确署名引用（如“Gikonyo et al., 2023”）"
    "或以 [@key] 引用的文献，必须在索引中查找对应 key 填入 cites，找不到才留空；"
    "语义上需要文献但索引没有→cited 且 cites 留空，不需要文献→uncited；"
    "占位优先在现有 fact 卡中匹配，没有则 matched_fact=null。"
)


def _logic_prompt(text: str) -> str:
    return (
        "【灵感·逻辑核查】\n"
        "任务：审查以下灵感笔记的写作逻辑问题（断裂推理、未定义概念、自相矛盾、"
        "跳跃结论）；没有问题就返回空列表。这是建议性检查，不修改文本。\n"
        '输出 JSON：{"issues": ["问题描述", …]}\n'
        f"灵感全文：\n{text}"
    )


def _extract_prompt(text: str) -> str:
    return (
        "【灵感·卡片拆解】\n"
        "任务：把灵感笔记拆解为原子卡片草案（一卡一意，宁可多拆不可混装）。\n"
        + _EXTRACT_SCHEMA + f"\n灵感全文：\n{text}"
    )


def _review_prompt(digest: str) -> str:
    return (
        "【灵感·现有卡审查】\n"
        "任务：对照现有卡片逐张审查草案，穷举比对（不要只看相似的）。\n"
        f"现有卡片摘要索引：\n{digest}\n"
        "待审卡片草案（JSON）：\n{t02}\n"
        + _REVIEW_SCHEMA
    )


def _match_prompt(inspiration_text: str, digest: str) -> str:
    return (
        "【灵感·匹配】\n"
        "任务：为草案做三类匹配：fact→现有 data 卡关联；claim 的 cited/uncited "
        "分类与文献匹配；占位表述→现有 fact 卡匹配。\n"
        f"灵感全文（文中 [@key] 形式的显式引用是最强信号：这些 key 必须填入"
        f"最贴切 claim 的 cites，除非该 key 不在索引中）：\n{inspiration_text}\n"
        f"现有卡片摘要索引：\n{digest}\n"
        "卡片草案（JSON）：\n{t02}\n"
        "审查结论（JSON）：\n{t03}\n"
        + _MATCH_SCHEMA
    )


_COVER_SCHEMA = (
    '输出 JSON：{"coverage": [{"sentence": "原文要点摘录", "card_keys": ["覆盖它的草案卡 key"],'
    ' "covered": true|false, "suggestion": ""}]}。'
    "规则：把灵感全文逐要点对账（每个数据点、论断、对比、引用都要核对）；"
    "被至少一张草案卡覆盖→covered=true 并填 card_keys；"
    "没有任何卡覆盖→covered=false 且 suggestion 必填（该补什么卡 / 需补 data / 为何弃置）。"
)


def _cover_prompt(inspiration_text: str) -> str:
    return (
        "【灵感·成卡覆盖】\n"
        "任务：审查拆卡覆盖情况——逐要点核对灵感原文是否都被草案卡覆盖，"
        "宁可多报不可漏报。\n"
        f"灵感全文：\n{inspiration_text}\n"
        "卡片草案（JSON）：\n{t02}\n"
        + _COVER_SCHEMA
    )


def build_inspire_tasklist(inspiration_text: str, digest: str) -> Tasklist:
    prompts = {
        "t01": _logic_prompt(inspiration_text),
        "t02": _extract_prompt(inspiration_text),
        "t03": _review_prompt(digest),
        "t04": _match_prompt(inspiration_text, digest),
        "t05": _cover_prompt(inspiration_text),
    }
    tasks: dict[str, TaskDefinition] = {}
    for tick, prompt in prompts.items():
        kwargs: dict = dict(
            type="harness", harness=_TICK_HARNESS[tick],
            prompt=prompt,
            outputformat={"type": "json_object"},
            temperature=_TEMPERATURE,
        )
        if tick == "t03":
            kwargs["inputs"] = {"t02": "t02"}
        elif tick == "t04":
            kwargs["inputs"] = {"t02": "t02", "t03": "t03"}
        elif tick == "t05":
            kwargs["inputs"] = {"t02": "t02"}
        tasks[tick] = TaskDefinition(**kwargs)
    flow = "[t01] --> t02\nt02 --> t03\nt03 --> t04\nt04 --> t05"
    return Tasklist(tasks=tasks, flow=flow)
