"""bib 渲染器（bibgen 设计 §5-§6）：approved+entry 的 note 卡 → references.bib。

纯确定性代码（不 import llm，红线 1 无涉）：同输入 → 字节级同输出。
全量原子重写 + key 排序 + 静态头注释（无时间戳）→ diff 友好，
stale 检测退化为一次字节比较。bib 是派生快照，真源在 note 卡（BBT 思想）。
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from weft.models.bib import BibEntryFields
from weft.store.loader import _BIB_ENTRY, _BIB_IGNORED   # P-D3：复用 key 提取正则
from weft.store.project import Project

BIB_HEADER = """\
% ----------------------------------------------------------
% 此文件由 weft 自动生成（weft.yaml: bib.managed = true）。
% 真源：metadata/notes/ 中 status: approved 且带 entry 的文献卡。
% 请勿手改——手改内容会在下次同步时丢失。新增文献请建文献卡。
% ----------------------------------------------------------
"""

_FIELD_ORDER = ("title", "author", "year", "journal", "booktitle", "publisher",
                "volume", "number", "pages", "doi", "url")


class BibValueError(Exception):
    """entry 字段值花括号不平衡（E-BIB-VALUE）：写盘前抛出，磁盘零残留。"""


def managed_target(project: Project) -> Path:
    """managed 生成目标 = _quarto.yml bibliography 指向的唯一文件。"""
    return project.root / project.bib_files[0]


def bib_keys_in(text: str) -> set[str]:
    return {m.group("key") for m in _BIB_ENTRY.finditer(text)
            if m.group("etype").lower() not in _BIB_IGNORED}


def _fmt(value) -> str:
    text = str(value)
    if text.count("{") != text.count("}"):
        raise BibValueError(f"字段值花括号不平衡：{text}")
    return text


def render_entry(note) -> str:
    entry: BibEntryFields = note.entry
    lines = [f"@{entry.type}{{{note.id},"]
    for name in _FIELD_ORDER:
        value = getattr(entry, name)
        if value is None or value == "" or value == []:
            continue
        if name == "author":
            rendered = " and ".join(_fmt(a) for a in value)
        else:
            rendered = _fmt(value)
        lines.append(f"  {name} = {{{rendered}}},")
    for name in sorted(entry.fields):
        lines.append(f"  {name} = {{{_fmt(entry.fields[name])}}},")
    lines[-1] = lines[-1].rstrip(",")
    lines.append("}")
    return "\n".join(lines)


def render_bib(project: Project) -> str:
    blocks = [render_entry(n) for n in sorted(
        (n for n in project.notes.values()
         if n.status == "approved" and n.entry is not None), key=lambda n: n.id)]
    if not blocks:
        return BIB_HEADER
    return BIB_HEADER + "\n" + "\n\n".join(blocks) + "\n"


def sync_bib(project: Project) -> tuple[Path, dict[str, int]]:
    """渲染并原子写入目标文件；返回 (路径, {added, removed, total})。"""
    target = managed_target(project)
    content = render_bib(project)          # 先渲染后写盘：BibValueError 时磁盘零残留
    old_text = target.read_text(encoding="utf-8") if target.exists() else ""
    old_keys, new_keys = bib_keys_in(old_text), bib_keys_in(content)
    stats = {"added": len(new_keys - old_keys), "removed": len(old_keys - new_keys),
             "total": len(new_keys)}
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    os.replace(tmp, target)
    return target, stats


def bib_is_stale(project: Project) -> bool:
    """managed 且目标文件 ≠ 确定性渲染。文件缺失不算 stale（E-BIB-MISSING 管辖）。"""
    target = managed_target(project)
    if not target.exists():
        return False
    return target.read_text(encoding="utf-8") != render_bib(project)


def key_base_from_entry(entry: BibEntryFields) -> str:
    """citekey 草稿基座：第一作者姓 + 年份；无作者用题名首词；再退 ref（设计 §6）。"""
    if entry.author:
        word = entry.author[0].split(",")[0]
    else:
        word = entry.title.split()[0].strip("\"'(),.") if entry.title else ""
    base = re.sub(r"[^A-Za-z0-9]", "", word).lower() or "ref"
    return f"{base}{entry.year}"


def _excel(n: int) -> str:
    letters = ""
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(ord("a") + rem) + letters
    return letters


def draft_key(base: str, used: set[str]) -> str:
    """冲突确定性后缀 a/b/c…（BBT excelColumn 思想）；used 原地更新防重。"""
    candidate = base
    n = 0
    while candidate in used:
        n += 1
        candidate = f"{base}{_excel(n)}"
    used.add(candidate)
    return candidate
