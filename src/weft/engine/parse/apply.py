"""A1 聚合（parse 设计 §4–§5）：节点输出 → 落盘。

纯脚本无 LLM。落盘规则同 inspire（宁可少落，不可落出坏项目）+ note 三档判定：
- fact 至少关联到一张现有 data 卡才落盘，否则丢弃并进报告；
- claim.supports 只解析为本次随之落盘的 fact id（按构造保证无悬空）；
- note（文献模式）：new → 写草稿卡；supplement → 完整新 note 提案；unchanged → 零写入；
- 任何前置校验失败在首次写盘前抛出，磁盘零残留。
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from weft.engine.card_writer import (
    _safe_id,
    all_card_ids,
    next_card_id,
    write_proposal,
    write_proposed_cards,
)
from weft.engine.parse.schemas import (
    ArticleCoverageOutput,
    ArticleExtractOutput,
    ArticleLogicOutput,
    ArticleMatchOutput,
    ArticleReviewOutput,
)
from weft.engine.pipeline import _slug
from weft.store.project import Project


@dataclass
class ArticleApplyOutcome:
    written_cards: list[Path] = field(default_factory=list)
    proposals: list[Path] = field(default_factory=list)
    report: Path | None = None
    notes: list[str] = field(default_factory=list)   # 丢弃/缺口提示（CLI 逐行 WARN）


def apply_article(project: Project, *, source: Path, logic: ArticleLogicOutput,
                  extract: ArticleExtractOutput, review: ArticleReviewOutput,
                  match: ArticleMatchOutput, coverage: ArticleCoverageOutput,
                  bib_key: str | None = None) -> ArticleApplyOutcome:
    root = project.root
    articles = root / "articles"
    if source.parent != articles or not source.is_file():
        raise ValueError(f"文章文件必须在 {articles} 下：{source}")

    literature = bib_key is not None
    if literature and bib_key not in project.bib_keys:
        raise ValueError(f"[E-ARTICLE-KEY] --key 不在 bib 中：{bib_key}")
    if literature:
        _safe_id(bib_key)   # 病态 bib key（含 / 或 ..）写卡中途才炸会破坏零残留，前置拦截

    # —— note 判定一致性（先于一切写盘，计划 P4）——
    note_review = review.note
    if literature and note_review is None:
        raise ValueError("[E-ARTICLE-SHAPE] 文献模式 P3 未输出 note 判定")
    if literature:
        existing_note = project.notes.get(bib_key)
        if note_review.verdict == "new" and existing_note is not None:
            raise ValueError(
                f"[E-ARTICLE-SHAPE] note 判定 new，但 {bib_key} 已存在（与索引不一致）")
        if (note_review.verdict in ("supplement", "unchanged")
                and existing_note is None):
            raise ValueError(
                f"[E-ARTICLE-SHAPE] note 判定 {note_review.verdict}，"
                f"但 {bib_key} 不存在（与索引不一致）")

    cls_by_key = {c.key: c for c in review.classifications}
    fact_match = {m.key: m for m in match.fact_data}
    claim_match = {m.key: m for m in match.claim_cites}
    used = all_card_ids(project)
    outcome = ArticleApplyOutcome()
    contradictions: list[str] = []

    # —— 前置处理：非法 supplement 降级为 new（同 inspire：模型会拿 data 卡当目标）——
    demoted: set[str] = set()
    claimed_targets: set[str] = set()
    for card in extract.cards:
        cls = cls_by_key.get(card.key)
        if cls is not None and cls.verdict == "supplement":
            target = cls.against[0] if cls.against else None
            if target is None or (target not in project.facts
                                  and target not in project.claims):
                demoted.add(card.key)
                outcome.notes.append(
                    f"草案 {card.key} 的补充目标 {target or '（未填）'} "
                    "不是现存 fact/claim 卡，降级为新建草稿卡")
            elif target in claimed_targets:
                demoted.add(card.key)
                outcome.notes.append(
                    f"草案 {card.key} 的补充目标 {target} 已有先到的提案，"
                    "降级为新建草稿卡（两条补充需人工合并）")
            else:
                claimed_targets.add(target)
    archive = articles / "processed" / source.name
    if archive.exists():
        raise ValueError(f"归档重名，拒绝覆盖：{archive}")

    def _verdict(key: str) -> str:
        if key in demoted:
            return "new"
        cls = cls_by_key.get(key)
        return cls.verdict if cls is not None else "new"

    # —— id 分配 ——
    landing_facts: dict[str, str] = {}    # 临时 key → 真实 fact id
    fact_data: dict[str, list[str]] = {}
    landing_claims: dict[str, str] = {}
    claim_needs: dict[str, bool] = {}
    supplement_specs: list[tuple[str, str]] = []   # (目标卡 id, 临时 key)

    for card in extract.cards:
        verdict = _verdict(card.key)
        if verdict == "supplement":
            supplement_specs.append((cls_by_key[card.key].against[0], card.key))
            continue
        if card.kind == "fact":
            matched = fact_match.get(card.key)
            data_ids = [d for d in (matched.data_ids if matched else [])
                        if d in project.data_cards]
            if not data_ids:
                outcome.notes.append(
                    f"草案 {card.key}（fact）未关联到任何 data 卡，未落盘——需补充 data 关联")
                continue
            landing_facts[card.key] = next_card_id(used, "fact")
            fact_data[card.key] = data_ids
        else:
            landing_claims[card.key] = next_card_id(used, "claim")
            claim_needs[card.key] = card.needs_citation

    # —— 内部连接（只在两端的卡都落盘时解析）；支持方向落在 fact.supports 上 ——
    fact_supports: dict[str, list[str]] = {k: [] for k in landing_facts}
    for link in extract.links:
        if link.from_ in landing_facts and link.to in landing_claims:
            fact_supports[link.from_].append(landing_claims[link.to])

    # —— 构建草稿卡（fact/claim + 文献模式的 note）——
    entries: list[tuple[str, dict]] = []
    note_lines: list[str] = []
    note_proposal: tuple[str, dict] | None = None
    for card in extract.cards:
        verdict = _verdict(card.key)
        origin = f"文章 {source.name}"
        if card.key in landing_facts:
            entries.append(("fact", {
                "id": landing_facts[card.key], "status": "draft",
                "data": fact_data[card.key], "statement": card.statement,
                "supports": fact_supports[card.key],
                "comment": f"来源：{origin}（草案 {card.key}）",
            }))
        elif card.key in landing_claims:
            cls = cls_by_key.get(card.key)
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

    if literature:
        if note_review.verdict == "new":
            note_fields = {
                "id": bib_key, "status": "draft",
                "summary": extract.summary,
                "comment": f"来源：文章 {source.name}（解析摘要）",
            }
            if extract.entry is not None:
                note_fields["entry"] = extract.entry.model_dump()
            entries.append(("note", note_fields))
            note_lines.append(
                f"- 新建 note 卡 `metadata/notes/{bib_key}.md`（draft，审后 approve）")
            if not extract.summary.strip():
                outcome.notes.append(
                    f"note {bib_key} 解析摘要为空——落盘后需人工补充 summary")
        elif note_review.verdict == "supplement":
            fields = project.notes[bib_key].model_dump()
            fields["summary"] = note_review.merged_summary
            fields["status"] = "draft"
            fields["comment"] = (f"取代 {bib_key}（文章补充，来源：{source.name}；"
                                 f"{note_review.reason}）")
            note_proposal = (bib_key, fields)
            note_lines.append(
                f"- 补充提案 `inspirations/proposals/{bib_key}.md`"
                "（审后 `weft replace <目标卡id>` 应用）")
        else:
            note_lines.append(f"- 无实质更新，维持原 note 卡 {bib_key}")
            outcome.notes.append(f"note {bib_key} 无实质更新，维持原卡")

    outcome.written_cards = write_proposed_cards(project, entries)

    # —— 替换提案（结构化字段机械继承原卡；计划 P4：全部在草稿卡后、归档前）——
    for target, key in supplement_specs:
        cls = cls_by_key[key]
        original = project.facts.get(target) or project.claims[target]
        fields = original.model_dump()
        fields["statement"] = cls.merged_statement
        fields["status"] = "draft"
        fields["comment"] = f"取代 {target}（文章补充，来源：{source.name}；{cls.reason}）"
        outcome.proposals.append(write_proposal(project, target, fields))
    if note_proposal is not None:
        outcome.proposals.append(
            write_proposal(project, note_proposal[0], note_proposal[1]))

    # —— 原文归档 ——
    archive.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(archive))

    # —— 报告 ——
    report = root / "generated" / "articles" / f"{_slug(source.name)}-report.md"
    outcome.report = _write_article_report(
        report, source, logic, contradictions, outcome.written_cards,
        outcome.proposals, match, outcome.notes, coverage, note_lines)
    return outcome


def _write_article_report(report: Path, source: Path, logic: ArticleLogicOutput,
                          contradictions: list[str], cards: list[Path],
                          proposals: list[Path], match: ArticleMatchOutput,
                          notes: list[str], coverage: ArticleCoverageOutput,
                          note_lines: list[str]) -> Path:
    lines = [f"# 文章解析报告：{source.name}", ""]
    lines += ["## 逻辑核查（建议性）", ""]
    lines += [f"- {issue}" for issue in logic.issues] or ["- （无）"]
    lines += ["", "## note 判定", ""]
    lines += note_lines or ["- （拆解模式，不产 note）"]
    lines += ["", "## 矛盾（需人工仲裁）", ""]
    lines += [f"- {c}" for c in contradictions] or ["- （无）"]
    lines += ["", "## 新建草稿卡", ""]
    lines += [f"- {p.relative_to(report.parents[2]).as_posix()}" for p in cards] \
        or ["- （无）"]
    lines += ["", "## 替换提案（审后 `weft replace <目标卡id>` 应用）", ""]
    lines += [f"- {p.relative_to(report.parents[2]).as_posix()}"
              for p in proposals] or ["- （无）"]
    lines += ["", "## claim 分类与依据", ""]
    lines += [f"- {m.key}: {m.claim_type}"
              + (f" cites={','.join(m.cites)}" if m.cites else "")
              + (f"（{m.reason}）" if m.reason else "")
              for m in match.claim_cites] or ["- （无）"]
    lines += ["", "## fact→data 关联建议", ""]
    lines += [f"- {m.key}: data={','.join(m.data_ids) or '（未匹配——需补充）'}"
              for m in match.fact_data] or ["- （无）"]
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
    lines += ["", "## 成卡覆盖审查", ""]
    missed = [c for c in coverage.coverage if not c.covered]
    lines.append(f"- 覆盖 {len(coverage.coverage) - len(missed)}"
                 f"/{len(coverage.coverage)} 个要点")
    for c in missed:
        lines.append(f"- 未成卡：“{c.sentence}”——{c.suggestion}")
    lines += ["", "## 丢弃与提示", ""]
    lines += [f"- {n}" for n in notes] or ["- （无）"]
    lines.append("")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return report
