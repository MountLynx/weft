"""加载后的项目容器：实体卡 + 叙事节 + 图注 + bib/配置 + 路径元数据。"""
from dataclasses import dataclass, field
from pathlib import Path

from weft.models.cards import ClaimCard, DataCard, FactCard, NoteCard
from weft.models.figures import FigureEntry
from weft.models.narrative import NarrativeSection


@dataclass
class Project:
    root: Path
    data_cards: dict[str, DataCard] = field(default_factory=dict)
    facts: dict[str, FactCard] = field(default_factory=dict)
    claims: dict[str, ClaimCard] = field(default_factory=dict)
    notes: dict[str, NoteCard] = field(default_factory=dict)
    sections: list[NarrativeSection] = field(default_factory=list)  # 按 (order, id) 排序
    figures: dict[str, FigureEntry] = field(default_factory=dict)
    bib_keys: set[str] = field(default_factory=set)
    figures_dir: str = "figures"          # weft.yaml figures_dir 可覆盖
    card_paths: dict[str, Path] = field(default_factory=dict)     # 实体 id -> 相对路径
    section_paths: dict[str, Path] = field(default_factory=dict)  # 节 id -> 相对路径
