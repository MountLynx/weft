"""WebUI 文献提案（bibgen 设计 §8 路径 1）：线索 → entry 草稿卡字段。

单次 LLM 调用（引擎层，红线 1 合规）；落盘由调用方经 card_writer 白名单
写 status: draft 的 note 卡。元数据幻觉风险由人批准闸门兜底（B2）。
"""
from __future__ import annotations

import json

from weft import bibgen
from weft.engine.card_writer import all_card_ids
from weft.models.bib import BibEntryFields

_PROMPT_TEMPLATE = (
    "【文献·条目提案】\n"
    "任务：根据线索提取/拟出这条文献的 BibTeX 书目字段。\n"
    "线索（可能含 DOI、标题、作者、年份、摘要等，也可能不全）：\n{clues}\n\n"
    '输出 JSON：{{"type": "article|book|inproceedings|…", "title": "…",'
    ' "author": ["姓, 名"], "year": 2020, "journal": "…", "volume": "12",'
    ' "number": "…", "pages": "45--58", "doi": "…", "url": "…"}}。\n'
    "规则：只填有依据的字段，没有依据的省略；title 与 year 必给"
    "（实在缺失就按线索最合理拟出，人审把关）；author 每项格式“姓, 名”。"
    "其余 BibTeX 字段（editor/eprint/address 等）放进 \"fields\" 对象，键值均为字符串；"
)


class BibProposeError(Exception):
    """提案失败：LLM 调用失败、输出非 JSON 或不满足 entry schema。"""


def _sink_extras(raw):
    """顶层未知键（LLM 未守 fields 逃生舱约定时）沉入 fields，避免整单报废。

    模型 extra="forbid" 冻结（红线 2），抢救逻辑放引擎层：未知键字符串化后
    挪进 fields 对象；显式 "fields" 条目优先（顶层为兜底，不覆盖）。
    """
    if not isinstance(raw, dict):
        return raw
    extras = {k: raw.pop(k) for k in list(raw)
              if k not in BibEntryFields.model_fields}
    fields = raw.get("fields")
    if not isinstance(fields, dict):   # null/str/list 等坏值丢弃，换新 dict 兜底
        fields = {}
        raw["fields"] = fields
    for k, v in extras.items():
        if v is not None:
            fields.setdefault(k, str(v))
    return raw


async def propose_note(project, clues: str, client) -> tuple[str, dict]:
    """返回（拟分配 key, note 卡 frontmatter 字段 dict）；不落盘。"""
    prompt = _PROMPT_TEMPLATE.format(clues=clues.strip() or "（无）")
    try:
        response = await client.complete(prompt=prompt,
                                         output_format={"type": "json_object"})
    except BibProposeError:
        raise
    except Exception as exc:   # 边界处异常翻译：llm 层 LLMError 等不裸穿（fail-closed 先例）
        raise BibProposeError(f"LLM 调用失败：{exc}") from exc
    try:
        entry = BibEntryFields.model_validate(_sink_extras(json.loads(response.content)))
    except (json.JSONDecodeError, ValueError) as exc:   # ValueError 涵盖 ValidationError
        raise BibProposeError(f"条目提案输出非法（须为 entry JSON）：{exc}") from exc
    key = bibgen.draft_key(bibgen.key_base_from_entry(entry), all_card_ids(project))
    fields = {
        "id": key,
        "status": "draft",
        "summary": "",
        "entry": entry.model_dump(),
        "comment": "来源：AI 条目提案（线索：" + (clues.strip()[:40] or "无") + "…）",
    }
    return key, fields
