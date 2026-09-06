"""项目扫描（webui 设计 §2）：projects_root 一级子目录中识别 weft 论文项目。

识别判据 = 子目录含 metadata/。损坏项目不阻断列表（available=False，红线 3 精神）。
每次请求重扫：单用户演示场景项目小，保证永远新鲜（设计决策 D7）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from weft.diagnostics import Diagnostic
from weft.store.loader import load_project
from weft.store.project import Project
from weft.validation import validate_project

_KIND_ATTRS = (("data", "data_cards"), ("fact", "facts"), ("claim", "claims"),
               ("note", "notes"), ("method", "methods"), ("param", "params"))


@dataclass
class ProjectEntry:
    pid: str
    path: Path
    available: bool
    diagnostics: list[Diagnostic] = field(default_factory=list)
    project: Project | None = None

    @property
    def n_cards(self) -> int:
        if self.project is None:
            return 0
        return sum(len(getattr(self.project, attr)) for _, attr in _KIND_ATTRS)

    @property
    def n_errors(self) -> int:
        return sum(1 for d in self.diagnostics if d.is_error)

    @property
    def n_warnings(self) -> int:
        return sum(1 for d in self.diagnostics if not d.is_error)


def scan_projects(root: Path) -> list[ProjectEntry]:
    entries: list[ProjectEntry] = []
    if not root.is_dir():
        return entries
    for child in sorted(root.iterdir()):
        if not child.is_dir() or not (child / "metadata").is_dir():
            continue
        entries.append(_inspect(child))
    return entries


def _inspect(path: Path) -> ProjectEntry:
    project, load_diags = load_project(path)
    if any(d.is_error for d in load_diags):
        return ProjectEntry(pid=path.name, path=path, available=False,
                            diagnostics=load_diags)
    diagnostics = load_diags + validate_project(project)
    return ProjectEntry(pid=path.name, path=path,
                        available=not any(d.is_error for d in diagnostics),
                        diagnostics=diagnostics, project=project)
