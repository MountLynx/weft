"""文章 → SpecModule 任务表（p01–p05 链式；parse 设计 §3-§4）。

prompt 起始标记【文章·…】兼作 mock 客户端分流键。mode 分叉：
- literature（文献模式，bib_key 必填）：P2 产 note 摘要；P3 三档判定 note；
  P4 所有 claim 默认 cites=[bib_key]（次级引用语义）。
- decompose（拆解模式）：与 inspire 同规则，不产 note。

p03/p04/p05 的 view 注入沿用 M2 决策 10：flow 只定触发边，{tick} 占位 + inputs 别名。
"""
from typing import Literal

from module_harness import TaskDefinition, Tasklist

Mode = Literal["literature", "decompose"]

_TICK_HARNESS = {
    "p01": "parse_logic",
    "p02": "parse_extract",
    "p03": "parse_review",
    "p04": "parse_match",
    "p05": "parse_cover",
}

_TEMPERATURE = 0.2   # 拆解/审查/匹配都要收敛，不用创作温度

_EXTRACT_DECOMPOSE_SCHEMA = (
    '输出 JSON：{"cards": [{"key": "f1/c1/…临时编号", "kind": "fact|claim",'
    ' "statement": "原子陈述", "placeholder": false, "needs_citation": false}],'
    ' "links": [{"from": "f1", "to": "c1"}]}。'
    "规则：数据表述→fact，观点/论断→claim；"
    "本研究数据与文献值的对比→claim（needs_citation=true），"
    "其中本研究自己的数据表述另拆一张 fact 卡并用 link 支持该对比 claim；"
    "\"xxx/某值\"类占位数据置 placeholder=true；"
    "needs_citation=该论断语义上是否需要文献支撑；links 只表达新 fact 支持新 claim。"
)

_EXTRACT_LITERATURE_SCHEMA = (
    '输出 JSON：{"summary": "结构化文献摘要（研究问题、方法、核心发现、局限；'
    '200-400 字）", "cards": [{"key": "f1/c1/…临时编号", "kind": "fact|claim",'
    ' "statement": "原子陈述", "placeholder": false, "needs_citation": true}],'
    ' "links": [{"from": "f1", "to": "c1"}],'
    ' "entry": {"type": "article|book|inproceedings|…", "title": "本文题名",'
    ' "author": ["姓, 名"], "year": 2020, "journal": "期刊名", "volume": "卷",'
    ' "number": "期", "pages": "45--58", "doi": "…"}}。'
    "规则：summary 以第三人称概括本篇文献（将作为 note 卡的摘要）；"
    "本文的数据表述→fact，本文的发现/结论/论断→claim（needs_citation 通常为 true）；"
    "\"xxx/某值\"类占位数据置 placeholder=true；links 只表达新 fact 支持新 claim；"
    "entry 从原文提取本文书目字段（题名/作者/年份/期刊卷期页/DOI），"
    "只填有依据的，title 与 year 必给，提取不到 entry 就整体省略。"
)

_REVIEW_DECOMPOSE_SCHEMA = (
    '输出 JSON：{"classifications": [{"key": "…", "verdict": "new|conflict|supplement",'
    ' "against": ["现有卡id"], "reason": "理由", "merged_statement": ""}]}。'
    "规则：new=全新；conflict=与现有卡事实矛盾（against 填冲突卡 id，reason 必填）；"
    "supplement=与现有 fact/claim 卡高度相关且略有补充（目标只能是现存 fact/claim 卡，"
    "data/note 是人工维护的输入卡，禁止作为补充目标；against 填目标卡 id，"
    "merged_statement 必填：包含原卡全部信息与补充内容的完整新卡陈述，不得丢失原卡信息）。"
)

_REVIEW_LITERATURE_SCHEMA_TEMPLATE = (
    '输出 JSON：{"classifications": [{"key": "…", "verdict": "new|conflict|supplement",'
    ' "against": ["现有卡id"], "reason": "理由", "merged_statement": ""}],'
    ' "note": {"verdict": "new|supplement|unchanged", "reason": "理由",'
    ' "merged_summary": ""}}。'
    "规则（卡片）：new=全新；conflict=与现有卡事实矛盾（against 填冲突卡 id，reason 必填）；"
    "supplement=目标只能是现存 fact/claim 卡（data/note 是人工维护的输入卡，禁止），"
    "merged_statement 必填且不得丢失原卡信息。"
    "规则（note）：本篇文献的 bib key 是 {bibkey}——若现有卡片摘要索引中已有该 key 的"
    " note 卡，对照其摘要与本次解析的新摘要逐要点比对——有实质新内容→supplement 且"
    " merged_summary 必填（原摘要全部要点 + 新增内容整合，不得丢失原摘要信息）；"
    "无实质新内容→unchanged；索引中没有该 key 的 note 卡→new。"
)

_MATCH_DECOMPOSE_SCHEMA = (
    '输出 JSON：{"fact_data": [{"key": "…", "data_ids": ["现有data卡id"]}],'
    ' "claim_cites": [{"key": "…", "claim_type": "cited|uncited", "cites": ["bib key"],'
    ' "reason": "…"}], "placeholders": [{"text": "占位原文",'
    ' "matched_fact": "现有fact卡id或null"}]}。'
    "规则：fact 至少关联到一张现有 data 卡才可给 data_ids，关联不到就留空数组；"
    "cites 只能取索引中出现的 note/bib key；索引中的 bib key 通常编码了作者与年份"
    "（如 gikonyo2023 = Gikonyo 2023），文章中明确署名引用（如“Gikonyo et al., 2023”）"
    "或以 [@key] 引用的文献，必须在索引中查找对应 key 填入 cites，找不到才留空；"
    "语义上需要文献但索引没有→cited 且 cites 留空，不需要文献→uncited；"
    "占位优先在现有 fact 卡中匹配，没有则 matched_fact=null。"
)

_MATCH_LITERATURE_SCHEMA_TEMPLATE = (
    '输出 JSON：{"fact_data": [{"key": "…", "data_ids": ["现有data卡id"]}],'
    ' "claim_cites": [{"key": "…", "claim_type": "cited|uncited",'
    ' "cites": ["{bibkey}"], "reason": "…"}], "placeholders": [{"text": "占位原文",'
    ' "matched_fact": "现有fact卡id或null"}]}。'
    "规则：本篇文献的 bib key 是 {bibkey}——所有 claim 一律 claim_type=cited 且"
    ' cites=["{bibkey}"]（次级引用语义：引你实际读到的这篇；文中提及的他人工作也先引'
    "本篇，原始出处由人工审阅时调整；确不需引文的个别论断才 uncited）；"
    "fact 至少关联到一张现有 data 卡才可给 data_ids，关联不到就留空数组；"
    "占位优先在现有 fact 卡中匹配，没有则 matched_fact=null。"
)

_COVER_SCHEMA = (
    '输出 JSON：{"coverage": [{"sentence": "原文要点摘录",'
    ' "card_keys": ["覆盖它的草案卡 key"], "covered": true|false, "suggestion": ""}]}。'
    "规则：把文章全文逐要点对账（每个数据点、论断、对比、引用都要核对）；"
    "被至少一张草案卡覆盖→covered=true 并填 card_keys；"
    "没有任何卡覆盖→covered=false 且 suggestion 必填（该补什么卡 / 需补 data / 为何弃置）。"
)


def _logic_prompt(text: str) -> str:
    return (
        "【文章·逻辑核查】\n"
        "任务：审查以下文章的写作逻辑问题（断裂推理、未定义概念、自相矛盾、"
        "跳跃结论）；没有问题就返回空列表。这是建议性检查，不修改文本。\n"
        '输出 JSON：{"issues": ["问题描述", …]}\n'
        f"文章全文：\n{text}"
    )


def _extract_prompt(text: str, mode: Mode) -> str:
    schema = (_EXTRACT_LITERATURE_SCHEMA if mode == "literature"
              else _EXTRACT_DECOMPOSE_SCHEMA)
    return (
        "【文章·卡片拆解】\n"
        "任务：把文章拆解为原子卡片草案（一卡一意，宁可多拆不可混装）。\n"
        + schema + f"\n文章全文：\n{text}"
    )


def _review_prompt(digest: str, mode: Mode, bib_key: str | None) -> str:
    head = (
        "【文章·现有卡审查】\n"
        "任务：对照现有卡片逐张审查草案，穷举比对（不要只看相似的）。\n"
        f"现有卡片摘要索引：\n{digest}\n"
        "待审卡片草案（JSON）：\n{p02}\n"
    )
    if mode == "literature":
        return head + _REVIEW_LITERATURE_SCHEMA_TEMPLATE.replace(
            "{bibkey}", bib_key or "")
    return head + _REVIEW_DECOMPOSE_SCHEMA


def _match_prompt(text: str, digest: str, mode: Mode, bib_key: str | None) -> str:
    if mode == "literature":
        text_line = f"文章全文：\n{text}\n"
    else:
        text_line = (
            f"文章全文（文中 [@key] 形式的显式引用是最强信号：这些 key 必须填入"
            f"最贴切 claim 的 cites，除非该 key 不在索引中）：\n{text}\n"
        )
    head = (
        "【文章·匹配】\n"
        "任务：为草案做三类匹配：fact→现有 data 卡关联；claim 的 cited/uncited "
        "分类与文献匹配；占位表述→现有 fact 卡匹配。\n"
        + text_line +
        f"现有卡片摘要索引：\n{digest}\n"
        "卡片草案（JSON）：\n{p02}\n"
        "审查结论（JSON）：\n{p03}\n"
    )
    if mode == "literature":
        return head + _MATCH_LITERATURE_SCHEMA_TEMPLATE.replace(
            "{bibkey}", bib_key or "")
    return head + _MATCH_DECOMPOSE_SCHEMA


def _cover_prompt(text: str) -> str:
    return (
        "【文章·成卡覆盖】\n"
        "任务：审查拆卡覆盖情况——逐要点核对文章原文是否都被草案卡覆盖，"
        "宁可多报不可漏报。\n"
        f"文章全文：\n{text}\n"
        "卡片草案（JSON）：\n{p02}\n"
        + _COVER_SCHEMA
    )


def build_parse_tasklist(text: str, digest: str, *, mode: Mode,
                         bib_key: str | None = None) -> Tasklist:
    if mode == "literature" and not bib_key:
        raise ValueError("文献模式（literature）需要 bib_key")
    prompts = {
        "p01": _logic_prompt(text),
        "p02": _extract_prompt(text, mode),
        "p03": _review_prompt(digest, mode, bib_key),
        "p04": _match_prompt(text, digest, mode, bib_key),
        "p05": _cover_prompt(text),
    }
    tasks: dict[str, TaskDefinition] = {}
    for tick, prompt in prompts.items():
        kwargs: dict = dict(
            type="harness", harness=_TICK_HARNESS[tick],
            prompt=prompt,
            outputformat={"type": "json_object"},
            temperature=_TEMPERATURE,
        )
        if tick == "p03":
            kwargs["inputs"] = {"p02": "p02"}
        elif tick == "p04":
            kwargs["inputs"] = {"p02": "p02", "p03": "p03"}
        elif tick == "p05":
            kwargs["inputs"] = {"p02": "p02"}
        tasks[tick] = TaskDefinition(**kwargs)
    flow = "[p01] --> p02\np02 --> p03\np03 --> p04\np04 --> p05"
    return Tasklist(tasks=tasks, flow=flow)
