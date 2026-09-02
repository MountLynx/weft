"""测试公共工具：文件层写入 helper + 内存 Project 构造 helper。"""
from __future__ import annotations

from pathlib import Path

import frontmatter
import yaml

from weft.models.cards import (
    ClaimCard,
    DataCard,
    FactCard,
    MethodCard,
    NoteCard,
    ParamCard,
)
from weft.models.figures import FigureEntry
from weft.models.narrative import NarrativePart, Node, Use
from weft.store.project import Project


def write_card(directory: Path, name: str, meta: dict, body: str = "") -> Path:
    """写一张 Markdown+frontmatter 卡片，文件名 = name.md。"""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.md"
    path.write_text(frontmatter.dumps(frontmatter.Post(body, **meta)), encoding="utf-8")
    return path


def write_yaml(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def make_minimal_project(root: Path) -> Path:
    """最小合法项目：1 data + 1 fact + 1 uncited claim + 1 note + figures/bib/叙事节。

    校验干净（0 错误 0 提醒）：claim 被支持、实体全部可达、图注被引用、图文件存在。
    """
    write_card(root / "metadata" / "data", "data-01",
               {"id": "data-01", "refs": ["fig-01a"], "status": "approved"})
    write_card(root / "metadata" / "facts", "fact-01",
               {"id": "fact-01", "data": ["data-01"], "statement": "温度提高速率。",
                "supports": ["claim-01"], "status": "approved"})
    write_card(root / "metadata" / "claims" / "uncited", "claim-01",
               {"id": "claim-01", "claim_type": "uncited", "statement": "温度有正效应。",
                "status": "approved"})
    write_card(root / "metadata" / "notes", "key2020",
               {"id": "key2020", "summary": "文献概括。", "status": "approved"})
    write_yaml(root / "metadata" / "figures.yaml",
               {"fig-01": {"caption": "速率曲线", "subfigs": {"a": "60°C"}}})
    write_yaml(root / "_quarto.yml", {"project": {"type": "default"},
                                      "bibliography": "references.bib"})
    (root / "references.bib").write_text(
        "@article{key2020,\n  title = {T},\n  year = {2020},\n}\n", encoding="utf-8")
    write_card(root / "narrative" / "01-results", "part-01",
               {"id": "sec-01", "section": "Results",
                "nodes": [{"id": "para-01-01", "purpose": "describe",
                           "uses": [{"id": "fact-01", "role": "evidence"}],
                           "status": "approved"}]})
    (root / "figures").mkdir(exist_ok=True)
    (root / "figures" / "fig-01a.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return root


def build_project(root: Path | None = None, *, data=None, facts=None, claims=None,
                  notes=None, methods=None, params=None, parts=None, figures=None,
                  bib_keys=None, figures_dir: str = "figures") -> Project:
    """在内存中直接构造 Project（validation/graphgen 单测用，不落盘）。"""
    root = root or Path(".")
    project = Project(root=root, figures_dir=figures_dir)
    project.data_cards = {c.id: c for c in (data or [])}
    project.facts = {c.id: c for c in (facts or [])}
    project.claims = {c.id: c for c in (claims or [])}
    project.notes = {c.id: c for c in (notes or [])}
    project.methods = {c.id: c for c in (methods or [])}
    project.params = {c.id: c for c in (params or [])}
    project.parts = list(parts or [])
    project.figures = dict(figures or {})
    project.bib_keys = set(bib_keys or set())
    for cards in (project.data_cards, project.facts, project.claims, project.notes,
                  project.methods, project.params):
        for cid in cards:
            project.card_paths.setdefault(cid, Path(f"metadata/{cid}.md"))
    for part in project.parts:
        project.part_paths.setdefault(part.id, Path(f"narrative/01-results/{part.id}.md"))
        project.part_chapters.setdefault(part.id, "01-results")
    return project
