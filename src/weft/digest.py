"""卡片摘要索引（inspire 设计 §3）：Project → 紧凑文本，供 LLM 穷举比对。

纯数据层，不 import llm；内存现算、不落盘。id 排序输出保证确定性。
"""
from __future__ import annotations

import json

from weft.models.cards import ClaimCard, FactCard
from weft.store.project import Project


def _joined(values: list[str]) -> str:
    return ",".join(values) if values else "-"


def _cap(text: str, limit: int = 240) -> str:
    """摘要索引只留前缀：digest 是比对索引不是全文（全文在卡片里）。

    真实 Zotero abstract 每条上千字符，全量入索引会撑爆上下文
    （实测 267 卡 ≈ 41 万字符 ≈ 13.7 万 token）。
    """
    return text if len(text) <= limit else text[:limit] + "…"


def _fact_line(fid: str, fact: FactCard) -> str:
    return (f"{fid} | {fact.status} | {fact.statement}"
            f" | data={_joined(fact.data)} | supports={_joined(fact.supports)}")


def _claim_line(cid: str, claim: ClaimCard) -> str:
    return (f"{cid} | {claim.status} | {claim.claim_type} | {claim.statement}"
            f" | cites={_joined(claim.cites)}")


def build_digest(project: Project) -> str:
    """全部卡片与图注的紧凑清单；空段省略。"""
    sections: list[tuple[str, list[str]]] = [
        ("data", [
            f"{did} | {card.status} | 描述：{card.description or '（无）'}"
            f" | 来源：{card.source or '（无）'} | refs={_joined(card.refs)}"
            for did, card in sorted(project.data_cards.items())]),
        ("fact", [_fact_line(fid, f) for fid, f in sorted(project.facts.items())]),
        ("claim", [_claim_line(cid, c) for cid, c in sorted(project.claims.items())]),
        ("note", [
            f"{nid} | {n.status} | {_cap(n.summary or '（无摘要）')}"
            for nid, n in sorted(project.notes.items())]),
        ("method", [
            f"{mid} | {m.status} | {m.statement}"
            f" | derived_from={_joined(m.derived_from)}"
            for mid, m in sorted(project.methods.items())]),
        ("param", [
            f"{pid} | {p.status} | method={p.method}"
            f" | values={json.dumps(p.values, ensure_ascii=False, sort_keys=True)}"
            for pid, p in sorted(project.params.items())]),
        ("figure", [
            f"{key} | {entry.caption}" + (f"（子图: {entry.subfigs}）"
                                          if entry.subfigs else "")
            for key, entry in sorted(project.figures.items())]),
        ("bib", sorted(project.bib_keys)),
    ]
    sections = [(name, lines) for name, lines in sections]
    blocks = [f"== {name} ==\n" + "\n".join(lines)
              for name, lines in sections if lines]
    return "\n".join(blocks)
