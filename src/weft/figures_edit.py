"""figures.yaml 编辑引擎（webui figures 设计定案）：纯函数，WebUI 路由薄封装。

figures.yaml 是人工直接维护的图注注册表；本引擎自读自写磁盘（F12）。
注册表有任何解析错误即拒绝一切写操作（E-FIG-LOAD，F3）——整文件重写
不保留注释、丢弃未知键（F2），若带病重写会静默吞掉 loader 宽松跳过的坏条目。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from pydantic import ValidationError

from weft.models.figures import FigureEntry

FIGURES_REL = "metadata/figures.yaml"

_PLAIN_YAML = re.compile(r"[\w][\w \-]*", re.UNICODE)
_UNSAFE_COMPONENT = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


class FiguresEditError(Exception):
    """figures.yaml 编辑失败（E-FIG-*）；WebUI banner 直接展示 code+message。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code} {message}")


def figures_path(root: Path) -> Path:
    return root / FIGURES_REL


def load_for_edit(root: Path) -> dict[str, FigureEntry]:
    """读 figures.yaml 为键序映射；文件缺失 = 空映射；任何解析失败 → E-FIG-LOAD。"""
    path = figures_path(root)
    if not path.exists():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError, OSError) as exc:
        raise FiguresEditError("E-FIG-LOAD",
                               f"figures.yaml 不是合法 YAML：{exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise FiguresEditError("E-FIG-LOAD", "figures.yaml 顶层必须是映射")
    entries: dict[str, FigureEntry] = {}
    for key, value in raw.items():
        try:
            entries[str(key)] = FigureEntry.model_validate(value or {})
        except ValidationError as exc:
            raise FiguresEditError(
                "E-FIG-LOAD",
                f"图注条目解析失败（{key}）：{exc.errors()[0]['msg']}") from exc
    return entries
