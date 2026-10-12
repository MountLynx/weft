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


def ensure_figure_key(key: str) -> None:
    """键名是图片文件名 stem（figures/{key}.png），安全成分规则同 weft new N9（F4）。"""
    if (not key or key.startswith(".") or key.endswith(".")
            or key != key.strip() or _UNSAFE_COMPONENT.search(key)):
        raise FiguresEditError("E-FIG-NAME", f"键名非法：{key!r}")


def next_figure_key(entries: dict[str, FigureEntry], prefix: str) -> str:
    """{prefix}{n:02d}：同前缀数字键取 max+1（同 weft new part 编号语义，F5）。"""
    pat = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    nums = [int(m.group(1)) for k in entries if (m := pat.match(k))]
    return f"{prefix}{max(nums, default=0) + 1:02d}"


def add_entry(entries: dict[str, FigureEntry], key: str, caption: str,
              subfigs: dict[str, str], prefix: str) -> dict[str, FigureEntry]:
    """新键追加尾部（键序即 assemble 编号，F5）；非法键名/冲突 fail-closed 零写入。"""
    if not key:
        key = next_figure_key(entries, prefix)
    ensure_figure_key(key)
    if key in entries:
        raise FiguresEditError("E-FIG-COLLISION", f"键已存在：{key}")
    return {**entries, key: FigureEntry(caption=caption, subfigs=subfigs)}


def parse_subfigs(text: str) -> dict[str, str]:
    """textarea 逐行 `子图号: 说明`，首个冒号切分、空行跳过（F7）；非法 → E-FIG-VALUE。"""
    subfigs: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        sub, sep, caption = line.partition(":")
        sub = sub.strip()
        if not sep or not sub or re.search(r"\s", sub):
            raise FiguresEditError("E-FIG-VALUE", f"子图行格式非法：{line!r}")
        subfigs[sub] = caption.strip()
    return subfigs


def update_entry(entries: dict[str, FigureEntry], key: str, caption: str,
                 subfigs: dict[str, str]) -> dict[str, FigureEntry]:
    """键不可变（F8），只替换 caption/subfigs；键序保持。"""
    if key not in entries:
        raise FiguresEditError("E-FIG-COLLISION", f"键不存在：{key}")
    return {k: (FigureEntry(caption=caption, subfigs=subfigs)
                if k == key else v)
            for k, v in entries.items()}


def remove_entry(entries: dict[str, FigureEntry], key: str,
                 references: dict[str, set[str]]) -> dict[str, FigureEntry]:
    """被任何 data 卡（含 rejected，F6）refs 命中 `{key} ∪ {key+sub}` 即阻断。"""
    if key not in entries:
        raise FiguresEditError("E-FIG-COLLISION", f"键不存在：{key}")
    valid = {key, *(f"{key}{sub}" for sub in entries[key].subfigs)}
    hitting = sorted(cid for cid, refs in references.items() if refs & valid)
    if hitting:
        raise FiguresEditError(
            "E-FIG-IN-USE", f"{'、'.join(hitting)} 引用了 {key}，先解除引用再删除")
    return {k: v for k, v in entries.items() if k != key}


def _dump_scalar(value: str) -> str:
    """简单词原样，含特殊字符走 JSON 双引号（合法 YAML 流标量；同 scaffold 惯例）。"""
    if _PLAIN_YAML.fullmatch(value):
        try:
            if isinstance(yaml.safe_load(value), str):
                return value
        except yaml.YAMLError:
            pass
    return json.dumps(value, ensure_ascii=False)


def write_figures_yaml(root: Path, entries: dict[str, FigureEntry]) -> Path:
    """确定性重写（F2）：键序保持、caption/subfigs 缺省省略、UTF-8 固定 LF。"""
    lines: list[str] = []
    for key, entry in entries.items():
        lines.append(f"{_dump_scalar(key)}:")
        if entry.caption:
            lines.append(f"  caption: {_dump_scalar(entry.caption)}")
        if entry.subfigs:
            lines.append("  subfigs:")
            for sub, cap in entry.subfigs.items():
                lines.append(f"    {_dump_scalar(sub)}: {_dump_scalar(cap)}")
    text = ("\n".join(lines) + "\n") if lines else ""
    path = figures_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path
