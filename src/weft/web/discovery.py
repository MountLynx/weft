"""项目条目来源（webui 设计 §2 + projects registry 设计 §5）：两模式统一体检入口。

扫描模式：projects_root 一级子目录中识别（判据 = 子目录含 metadata/，现状不变）。
注册表模式：全局注册表逐条探测（判据 = loader 的 is_weft_project，R3）。
损坏项目不阻断列表（available=False / missing，红线 3 精神）。
每次请求重读：单用户场景项目小，保证永远新鲜（设计决策 D7 / R7）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from weft.diagnostics import Diagnostic
from weft.store.loader import is_weft_project, load_project
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
    missing: bool = False  # 注册表条目位置失联（环境状态，非错误；R9）

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
    """扫描模式：现状行为不变（只认含 metadata/ 的一级子目录）。"""
    if not root.is_dir():
        return []
    pairs = [(child.name, child) for child in sorted(root.iterdir())
             if child.is_dir() and (child / "metadata").is_dir()]
    return collect_projects(pairs)


def registry_projects() -> list[ProjectEntry]:
    """注册表模式列表：实时读表 + 逐条探测；表损坏时抛 RegistryError（调用方呈现）。"""
    from weft.registry import load_registry

    reg = load_registry()
    pairs: list[tuple[str, Path]] = []
    entries: list[ProjectEntry] = []
    for item in reg.projects:
        try:
            path = Path(item.path)
            usable = path.is_dir() and is_weft_project(path)
        except (OSError, ValueError):
            # 手改注册表塞入病态路径值（null 字节等）：条目转 missing，不让单条炸掉整页
            path, usable = Path(), False
        if usable:
            pairs.append((item.name, path))
        else:
            entries.append(ProjectEntry(pid=item.name, path=path,
                                        available=False, missing=True))
    entries.extend(collect_projects(pairs))
    entries.sort(key=lambda e: e.pid)
    return entries


def collect_projects(entries: list[tuple[str, Path]]) -> list[ProjectEntry]:
    """统一体检入口：按 (pid, 路径) 对逐条 load + validate（两模式共用）。"""
    return [_inspect(pid, path) for pid, path in sorted(entries)]


def _inspect(pid: str, path: Path) -> ProjectEntry:
    project, load_diags = load_project(path)
    if any(d.is_error for d in load_diags):
        return ProjectEntry(pid=pid, path=path, available=False,
                            diagnostics=load_diags)
    diagnostics = load_diags + validate_project(project)
    return ProjectEntry(pid=pid, path=path,
                        available=not any(d.is_error for d in diagnostics),
                        diagnostics=diagnostics, project=project)
