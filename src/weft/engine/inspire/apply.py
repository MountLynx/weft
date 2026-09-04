"""A1 聚合（inspire 设计 §4）：节点输出 → 落盘三件套。

纯脚本无 LLM。落盘规则（设计 §4"落盘自洽闭包"）：
- fact 至少关联到一张现有 data 卡才落盘，否则丢弃并进报告（宁可少落）；
- claim.supports 只解析为本次随之落盘的 fact id（悬空不可能出现，按构造保证）；
- 补充卡 = 完整新卡提案（结构化字段机械继承原卡，statement 用 LLM 合并结果），
  落 inspirations/proposals/，不动既有卡；
- 任何前置校验失败在首次写盘前抛出，磁盘零残留。
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from weft.engine.inspire.cards import write_proposal, write_proposed_cards
from weft.engine.inspire.schemas import (
    ExtractOutput,
    LogicOutput,
    MatchOutput,
    ReviewOutput,
)
from weft.store.project import Project


@dataclass
class ApplyOutcome:
    written_cards: list[Path] = field(default_factory=list)
    proposals: list[Path] = field(default_factory=list)
    report: Path | None = None
    notes: list[str] = field(default_factory=list)   # 丢弃/缺口提示（CLI 逐行 WARN）


def _next_id(used: set[str], prefix: str) -> str:
    n = 1
    while f"{prefix}-{n:02d}" in used:
        n += 1
    card_id = f"{prefix}-{n:02d}"
    used.add(card_id)
    return card_id


def _all_ids(project: Project) -> set[str]:
    used: set[str] = set()
    for table in (project.data_cards, project.facts, project.claims,
                  project.notes, project.methods, project.params):
        used.update(table)
    return used


def apply_inspiration(project: Project, *, source: Path, logic: LogicOutput,
                      extract: ExtractOutput, review: ReviewOutput,
                      match: MatchOutput) -> ApplyOutcome:
    root = project.root
    inspirations = root / "inspirations"
    if source.parent != inspirations or not source.is_file():
        raise ValueError(f"灵感文件必须在 {inspirations} 下：{source}")

    cls_by_key = {c.key: c for c in review.classifications}
    fact_match = {m.key: m for m in match.fact_data}
    claim_match = {m.key: m for m in match.claim_cites}
    used = _all_ids(project)
    outcome = ApplyOutcome()
    contradictions: list[str] = []

    # —— 前置校验（任何失败在写盘前抛出）——
    for card in extract.cards:
        cls = cls_by_key.get(card.key)
        if cls is not None and cls.verdict == "supplement":
            if not cls.against:
                raise ValueError(f"草案 {card.key} 标记 supplement 但未给目标卡")
            target = cls.against[0]
            if target not in project.facts and target not in project.claims:
                raise ValueError(f"补充目标卡不存在：{target}")
    archive = inspirations / "processed" / source.name
    if archive.exists():
        raise ValueError(f"归档重名，拒绝覆盖：{archive}")

    # —— id 分配 ——
    landing_facts: dict[str, str] = {}    # 临时 key → 真实 fact id
    fact_data: dict[str, list[str]] = {}
    landing_claims: dict[str, str] = {}
    claim_needs: dict[str, bool] = {}
    supplement_specs: list[tuple[str, str]] = []   # (目标卡 id, 临时 key)

    for card in extract.cards:
        cls = cls_by_key.get(card.key)
        verdict = cls.verdict if cls is not None else "new"
        if verdict == "supplement":
            supplement_specs.append((cls.against[0], card.key))
            continue
        if card.kind == "fact":
            matched = fact_match.get(card.key)
            data_ids = [d for d in (matched.data_ids if matched else [])
                        if d in project.data_cards]
            if not data_ids:
                outcome.notes.append(
                    f"草案 {card.key}（fact）未关联到任何 data 卡，未落盘——需补充 data 关联")
                continue
            landing_facts[card.key] = _next_id(used, "fact")
            fact_data[card.key] = data_ids
        else:
            landing_claims[card.key] = _next_id(used, "claim")
            claim_needs[card.key] = card.needs_citation

    # —— 内部连接（只在两端的卡都落盘时解析）；支持方向落在 fact.supports 上 ——
    fact_supports: dict[str, list[str]] = {k: [] for k in landing_facts}
    for link in extract.links:
        if link.from_ in landing_facts and link.to in landing_claims:
            fact_supports[link.from_].append(landing_claims[link.to])

    # —— 构建并写草稿卡 ——
    entries: list[tuple[str, dict]] = []
    for card in extract.cards:
        cls = cls_by_key.get(card.key)
        verdict = cls.verdict if cls is not None else "new"
        origin = f"灵感 {source.name}"
        if card.key in landing_facts:
            entries.append(("fact", {
                "id": landing_facts[card.key], "status": "draft",
                "data": fact_data[card.key], "statement": card.statement,
                "supports": fact_supports[card.key],
                "comment": f"来源：{origin}（草案 {card.key}）",
            }))
        elif card.key in landing_claims:
            m = claim_match.get(card.key)
            claim_type = m.claim_type if m is not None else (
                "cited" if claim_needs[card.key] else "uncited")
            cites = [k for k in (m.cites if m is not None else [])
                     if k in project.bib_keys]
            if m is not None and m.claim_type == "cited" and not cites:
                outcome.notes.append(
                    f"claim {landing_claims[card.key]} 分类 cited 但无文献匹配——缺文献"
                    + (f"（{m.reason}）" if m.reason else ""))
            if verdict == "conflict":
                against = "、".join(cls.against) or "（未指名）"
                contradictions.append(
                    f"{landing_claims[card.key]} ↔ {against}：{cls.reason}")
            entries.append(("claim", {
                "id": landing_claims[card.key], "status": "draft",
                "claim_type": claim_type, "statement": card.statement,
                "cites": cites,
                "comment": f"来源：{origin}（草案 {card.key}）",
            }))

    outcome.written_cards = write_proposed_cards(project, entries)

    # —— 替换提案（结构化字段机械继承原卡，statement 用合并结果）——
    for target, key in supplement_specs:
        cls = cls_by_key[key]
        original = project.facts.get(target) or project.claims[target]
        fields = original.model_dump()
        fields["statement"] = cls.merged_statement
        fields["status"] = "draft"
        fields["comment"] = f"取代 {target}（灵感补充，来源：{source.name}；{cls.reason}）"
        outcome.proposals.append(write_proposal(project, target, fields))

    # —— 原文归档 ——
    archive.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(archive))

    # —— 报告 ——
    report = root / "generated" / "inspirations" / f"{source.stem}-report.md"
    outcome.report = _write_report(report, source, logic, contradictions,
                                   outcome.written_cards, outcome.proposals,
                                   match, outcome.notes)
    return outcome


def _write_report(report: Path, source: Path, logic: LogicOutput,
                  contradictions: list[str], cards: list[Path],
                  proposals: list[Path], match: MatchOutput,
                  notes: list[str]) -> Path:
    lines = [f"# 灵感处理报告：{source.name}", ""]
    lines += ["## 逻辑核查（建议性）", ""]
    lines += [f"- {issue}" for issue in logic.issues] or ["- （无）"]
    lines += ["", "## 矛盾（需人工仲裁）", ""]
    lines += [f"- {c}" for c in contradictions] or ["- （无）"]
    lines += ["", "## 新建草稿卡", ""]
    lines += [f"- {p.relative_to(report.parents[2]).as_posix()}" for p in cards] \
        or ["- （无）"]
    lines += ["", "## 替换提案（审后 `weft replace <目标卡id>` 应用）", ""]
    lines += [f"- {p.as_posix()}" for p in proposals] or ["- （无）"]
    lines += ["", "## 匹配与缺口", ""]
    for m in match.claim_cites:
        if m.claim_type == "cited" and not m.cites:
            lines.append(f"- 缺文献：{m.key}（{m.reason or '未说明'}）")
    for p in match.placeholders:
        if p.matched_fact:
            lines.append(f"- 占位“{p.text}”匹配现有卡 {p.matched_fact}")
        else:
            lines.append(f"- 占位“{p.text}”无匹配 fact——需补充")
    if not any(m.claim_type == "cited" and not m.cites for m in match.claim_cites) \
            and not match.placeholders:
        lines.append("- （无）")
    lines += ["", "## 丢弃与提示", ""]
    lines += [f"- {n}" for n in notes] or ["- （无）"]
    lines.append("")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return report
