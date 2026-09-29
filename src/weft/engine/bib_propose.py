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
)


class BibProposeError(Exception):
    """提案失败：LLM 输出非 JSON 或不满足 entry schema。"""


async def propose_note(project, clues: str, client) -> tuple[str, dict]:
    """返回（拟分配 key, note 卡 frontmatter 字段 dict）；不落盘。"""
    prompt = _PROMPT_TEMPLATE.format(clues=clues.strip() or "（无）")
    response = await client.complete(prompt=prompt)
    try:
        entry = BibEntryFields.model_validate(json.loads(response.content))
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
