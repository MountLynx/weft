"""加载后的项目容器：实体卡 + 叙事 part + 图注 + bib/配置 + 路径元数据。"""
from dataclasses import dataclass, field
from pathlib import Path

from weft.models.cards import (
    ClaimCard,
    DataCard,
    FactCard,
    MethodCard,
    NoteCard,
    ParamCard,
)
from weft.models.figures import FigureEntry
from weft.models.narrative import NarrativePart


@dataclass
class Project:
    root: Path
    data_cards: dict[str, DataCard] = field(default_factory=dict)
    facts: dict[str, FactCard] = field(default_factory=dict)
    claims: dict[str, ClaimCard] = field(default_factory=dict)
    notes: dict[str, NoteCard] = field(default_factory=dict)
    methods: dict[str, MethodCard] = field(default_factory=dict)
    params: dict[str, ParamCard] = field(default_factory=dict)
    parts: list[NarrativePart] = field(default_factory=list)  # 按相对路径字典序
    figures: dict[str, FigureEntry] = field(default_factory=dict)
    bib_keys: set[str] = field(default_factory=set)
    figures_dir: str = "figures"          # weft.yaml figures_dir 可覆盖
    card_paths: dict[str, Path] = field(default_factory=dict)   # 实体 id -> 相对路径
    part_paths: dict[str, Path] = field(default_factory=dict)   # part id -> 相对路径
    part_chapters: dict[str, str] = field(default_factory=dict)  # part id -> 第一级目录名
