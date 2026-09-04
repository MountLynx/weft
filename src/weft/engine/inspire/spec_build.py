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
}

_TEMPERATURE = 0.2   # 拆解/审查/匹配都要收敛，不用创作温度

_EXTRACT_SCHEMA = (
    '输出 JSON：{"cards": [{"key": "f1/c1/…临时编号", "kind": "fact|claim",'
    ' "statement": "原子陈述", "placeholder": false, "needs_citation": false}],'
    ' "links": [{"from": "f1", "to": "c1"}]}。'
    "规则：数据表述→fact，观点/论断→claim；\"xxx/某值\"类占位数据置 placeholder=true；"
    "needs_citation=该论断语义上是否需要文献支撑；links 只表达新 fact 支持新 claim。"
)

_REVIEW_SCHEMA = (
    '输出 JSON：{"classifications": [{"key": "…", "verdict": "new|conflict|supplement",'
    ' "against": ["现有卡id"], "reason": "理由", "merged_statement": ""}]}。'
    "规则：new=全新；conflict=与现有卡事实矛盾（against 填冲突卡 id，reason 必填）；"
    "supplement=与现有卡高度相关且略有补充（against 填目标卡 id，"
    "merged_statement 必填：包含原卡全部信息与补充内容的完整新卡陈述，不得丢失原卡信息）。"
)

_MATCH_SCHEMA = (
    '输出 JSON：{"fact_data": [{"key": "…", "data_ids": ["现有data卡id"]}],'
    ' "claim_cites": [{"key": "…", "claim_type": "cited|uncited", "cites": ["bib key"],'
    ' "reason": "…"}], "placeholders": [{"text": "占位原文", "matched_fact": "现有fact卡id或null"}]}。'
    "规则：fact 至少关联到一张现有 data 卡才可给 data_ids，关联不到就留空数组；"
    "cites 只能取索引中出现的 note/bib key，语义上需要文献但找不到→cited 且 cites 留空，"
    "不需要文献→uncited；占位优先在现有 fact 卡中匹配，没有则 matched_fact=null。"
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


def _match_prompt(digest: str) -> str:
    return (
        "【灵感·匹配】\n"
        "任务：为草案做三类匹配：fact→现有 data 卡关联；claim 的 cited/uncited "
        "分类与文献匹配；占位表述→现有 fact 卡匹配。\n"
        f"现有卡片摘要索引：\n{digest}\n"
        "卡片草案（JSON）：\n{t02}\n"
        "审查结论（JSON）：\n{t03}\n"
        + _MATCH_SCHEMA
    )


def build_inspire_tasklist(inspiration_text: str, digest: str) -> Tasklist:
    prompts = {
        "t01": _logic_prompt(inspiration_text),
        "t02": _extract_prompt(inspiration_text),
        "t03": _review_prompt(digest),
        "t04": _match_prompt(digest),
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
        tasks[tick] = TaskDefinition(**kwargs)
    flow = "[t01] --> t02\nt02 --> t03\nt03 --> t04"
    return Tasklist(tasks=tasks, flow=flow)
