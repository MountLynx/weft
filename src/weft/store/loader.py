"""卡片/叙事/图注/bib/配置的加载（spec §3、§5 store 层）。

加载约定：
- 单卡解析失败、文件名≠id、id 重复、claims 目录不符 → 错误诊断，不中断加载。
- 实体 id 全局唯一（data/fact/claim/note 共用一个命名空间，spec §3.9）。
- 路径统一转成相对项目根的 posix 风格（诊断展示用）。
"""
from __future__ import annotations

import re
from pathlib import Path

import frontmatter
import yaml
from pydantic import ValidationError

from weft.diagnostics import Diagnostic, Level
from weft.models.cards import ClaimCard, DataCard, FactCard, NoteCard
from weft.models.figures import FigureEntry
from weft.models.narrative import NarrativeSection
from weft.store.project import Project

_BIB_ENTRY = re.compile(r"@(?P<etype>[A-Za-z]+)\s*\{\s*(?P<key>[^,\s{}]+)\s*,")
_BIB_IGNORED = {"string", "comment", "preamble"}

_CARD_TYPES = [
    ("data_cards", "metadata/data", DataCard),
    ("facts", "metadata/facts", FactCard),
    ("notes", "metadata/notes", NoteCard),
]


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def load_project(root: Path) -> tuple[Project, list[Diagnostic]]:
    root = root.resolve()
    diagnostics: list[Diagnostic] = []

    if not (root / "_quarto.yml").exists() and not (root / "metadata").is_dir():
        diagnostics.append(Diagnostic(
            Level.ERROR, "E-NOT-A-PROJECT", ".", None,
            f"{root} 不是 weft 项目根目录（缺少 _quarto.yml 与 metadata/）"))
        return Project(root=root), diagnostics

    project = Project(root=root)
    seen_ids: dict[str, str] = {}  # id -> 首次出现的文件（实体共用命名空间）

    _load_cards(root, project, seen_ids, diagnostics)
    _load_narrative(root, project, diagnostics)
    return project, diagnostics


def _load_frontmatter(path: Path) -> tuple[dict | None, str | None]:
    """返回 (metadata, 错误消息)。错误消息非 None 表示 YAML/编码层失败。"""
    try:
        post = frontmatter.load(path)
    except (yaml.YAMLError, UnicodeDecodeError, OSError) as exc:
        # OSError：frontmatter.load 自行开文件，目录/锁文件等 IO 异常也要兜住，
        # 保证单卡失败不中断整体加载。
        return None, f"frontmatter 解析失败：{exc}"
    return post.metadata, None


def _load_cards(root: Path, project: Project, seen_ids: dict[str, str],
                diagnostics: list[Diagnostic]) -> None:
    for attr, rel_dir, model in _CARD_TYPES:
        directory = root / rel_dir
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            _load_card(root, project, seen_ids, diagnostics, attr, model, path)

    claims_dir = root / "metadata" / "claims"
    if claims_dir.is_dir():
        for path in sorted(claims_dir.rglob("*.md")):
            _load_card(root, project, seen_ids, diagnostics, "claims", ClaimCard,
                       path, check_claim_dir=True)


def _load_card(root: Path, project: Project, seen_ids: dict[str, str],
               diagnostics: list[Diagnostic], attr: str, model, path: Path,
               *, check_claim_dir: bool = False) -> None:
    rel = _rel(root, path)
    metadata, error = _load_frontmatter(path)
    if error is not None:
        diagnostics.append(Diagnostic(Level.ERROR, "E-PARSE", rel, None, error))
        return
    try:
        card = model.model_validate(metadata)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(p) for p in first["loc"])
        diagnostics.append(Diagnostic(
            Level.ERROR, "E-PARSE", rel, field or None,
            f"frontmatter 解析失败：{first['msg']}"))
        return

    if check_claim_dir and path.parent.name != card.claim_type:
        diagnostics.append(Diagnostic(
            Level.ERROR, "E-CLAIM-DIR-MISMATCH", rel, "claim_type",
            f"卡片位于 {path.parent.name}/ 目录，但 claim_type 为 {card.claim_type}"))

    if path.stem != card.id:
        diagnostics.append(Diagnostic(
            Level.ERROR, "E-FILENAME-MISMATCH", rel, "id",
            f"文件名 {path.stem} 与 id {card.id} 不一致"))

    if card.id in seen_ids:
        diagnostics.append(Diagnostic(
            Level.ERROR, "E-DUPLICATE-ID", rel, "id",
            f"id {card.id} 重复，首次出现于 {seen_ids[card.id]}"))
        return
    seen_ids[card.id] = rel

    getattr(project, attr)[card.id] = card
    project.card_paths[card.id] = path.relative_to(root)


def _load_narrative(root: Path, project: Project, diagnostics: list[Diagnostic]) -> None:
    directory = root / "narrative"
    if not directory.is_dir():
        return
    seen_sections: dict[str, str] = {}
    seen_nodes: dict[str, str] = {}
    sections: list[NarrativeSection] = []

    for path in sorted(directory.glob("*.md")):
        rel = _rel(root, path)
        metadata, error = _load_frontmatter(path)
        if error is not None:
            diagnostics.append(Diagnostic(Level.ERROR, "E-PARSE", rel, None, error))
            continue
        try:
            section = NarrativeSection.model_validate(metadata)
        except ValidationError as exc:
            first = exc.errors()[0]
            field = ".".join(str(p) for p in first["loc"])
            diagnostics.append(Diagnostic(
                Level.ERROR, "E-PARSE", rel, field or None,
                f"frontmatter 解析失败：{first['msg']}"))
            continue

        if section.id in seen_sections:
            diagnostics.append(Diagnostic(
                Level.ERROR, "E-DUPLICATE-ID", rel, "id",
                f"叙事节 id {section.id} 重复，首次出现于 {seen_sections[section.id]}"))
            continue
        seen_sections[section.id] = rel
        project.section_paths[section.id] = path.relative_to(root)
        sections.append(section)

        for node in section.nodes:
            if node.id in seen_nodes:
                diagnostics.append(Diagnostic(
                    Level.ERROR, "E-DUPLICATE-ID", rel, f"nodes[{node.id}]",
                    f"叙事节点 id {node.id} 重复，首次出现于 {seen_nodes[node.id]}"))
                continue
            seen_nodes[node.id] = rel

    project.sections = sorted(sections, key=lambda s: (s.order, s.id))
