"""bib 渲染器（bibgen 设计 §5-§6）：approved+entry 的 note 卡 → references.bib。

纯确定性代码（不 import llm，红线 1 无涉）：同输入 → 字节级同输出。
全量原子重写 + key 排序 + 静态头注释（无时间戳）→ diff 友好，
stale 检测退化为一次字节比较。bib 是派生快照，真源在 note 卡（BBT 思想）。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
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
        if name in _FIELD_ORDER:
            raise BibValueError(f"条目 {note.id} 的 fields 与标准字段冲突：{name}")
        lines.append(f"  {name} = {{{_fmt(entry.fields[name])}}},")
    if len(lines) == 1:
        raise BibValueError(f"条目 {note.id} 无可渲染字段（title/year 为空）")
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
    try:
        tmp.write_text(content, encoding="utf-8", newline="\n")
        os.replace(tmp, target)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
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
        word = (entry.title.split() or [""])[0].strip("\"'(),.") if entry.title else ""
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


def sync_managed_bib(project_root) -> str | None:
    """managed 模式 bib 重渲（P-D1）；非 managed / bib 不唯一 → None，失败 → "bib_error"。

    自 webui 路由上移共用（rename 设计 R8）：web 审阅/编辑与 weft rename 共用同一实现。
    """
    from weft.store.loader import load_project

    project, _ = load_project(project_root)
    if not project.bib_managed or len(project.bib_files) != 1:
        return None
    try:
        sync_bib(project)
    except (BibValueError, OSError, UnicodeDecodeError):
        return "bib_error"
    return "bib_updated"


class BibModeError(Exception):
    """切换/修复动作前置失败（E-BIB-MODE）：操作异常码，非项目状态诊断（bib-mode-fix 设计 §3.1）。"""


@dataclass
class SwitchPlan:
    """模式切换预检报告（零写入；bib-mode-fix 设计 §3.2）。"""

    to_managed: bool
    from_managed: bool
    bib_files: list[str]
    hand_only_entries: list[str]   # bib 中无 approved+entry 卡覆盖的 key：managed 化后下次 sync 消失
    notes_not_in_bib: list[str]    # 非 rejected note 中 id 不在 bib：unmanaged 化后报 E-NOTE-NOT-IN-BIB


def plan_switch(project: Project, to_managed: bool) -> SwitchPlan:
    if project.bib_cfg_error:
        raise BibModeError(f"[E-BIB-MODE] weft.yaml bib 段非法：{project.bib_cfg_error}")
    if to_managed and len(project.bib_files) != 1:
        raise BibModeError("[E-BIB-MODE] managed 模式要求 bibliography 恰好指向一个文件"
                           f"（先修 _quarto.yml；当前：{'、'.join(project.bib_files) or '无'}）")
    if to_managed and not (project.root / project.bib_files[0]).exists():
        raise BibModeError(f"[E-BIB-MODE] bibliography 文件不存在：{project.bib_files[0]}"
                           "（先创建或修 _quarto.yml）")
    covered = {n.id for n in project.notes.values()
               if n.status == "approved" and n.entry is not None}
    return SwitchPlan(
        to_managed=to_managed, from_managed=project.bib_managed,
        bib_files=list(project.bib_files),
        hand_only_entries=sorted(project.bib_keys - covered),
        notes_not_in_bib=sorted(nid for nid, n in project.notes.items()
                                if n.status != "rejected" and nid not in project.bib_keys))


def apply_switch(project_root: Path, plan: SwitchPlan) -> None:
    """写 weft.yaml 的 bib.managed（bib-mode-fix 设计 §3.3 / M2）：逐行改保注释，原子写，LF。"""
    path = project_root / "weft.yaml"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = text.splitlines()
    flag = "true" if plan.to_managed else "false"
    start = next((i for i, ln in enumerate(lines) if ln.startswith("bib:")), None)
    if start is not None and lines[start].split(":", 1)[1].strip():
        raise BibModeError("[E-BIB-MODE] weft.yaml 的 bib 段为流式写法，请手工修改 bib.managed")
    if start is None:
        new_lines = lines + ["", "bib:", f"  managed: {flag}"]
    else:
        end = next((i for i in range(start + 1, len(lines))
                    if lines[i] and not lines[i][0].isspace()), len(lines))
        managed_idx = next((i for i in range(start + 1, end)
                            if lines[i].strip().startswith("managed:")), None)
        if managed_idx is None:
            if plan.from_managed:
                raise BibModeError("[E-BIB-MODE] weft.yaml 已变化，请刷新后重试")
            new_lines = lines[:start + 1] + [f"  managed: {flag}"] + lines[start + 1:]
        else:
            value = lines[managed_idx].split(":", 1)[1].split("#", 1)[0].strip()
            if value != ("true" if plan.from_managed else "false"):
                raise BibModeError("[E-BIB-MODE] weft.yaml 已变化，请刷新后重试")
            new_lines = list(lines)
            new_lines[managed_idx] = re.sub(r"\b(?:true|false)\b", flag,
                                            lines[managed_idx], count=1)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text("\n".join(new_lines) + "\n", encoding="utf-8", newline="\n")
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def fix_note_in_bib(project: Project, key: str) -> str:
    """把 note 卡 entry 确定性追加进 unmanaged bib（设计 §3.4）；返回 "added"/"present"。"""
    if project.bib_managed:
        raise BibModeError("[E-BIB-MODE] managed 项目由 weft bib sync 管辖，无需修复")
    if project.bib_cfg_error:
        raise BibModeError(f"[E-BIB-MODE] weft.yaml bib 段非法：{project.bib_cfg_error}")
    if len(project.bib_files) != 1:
        raise BibModeError("[E-BIB-MODE] 修复要求 bibliography 恰好指向一个文件"
                           "（先修 _quarto.yml）")
    note = project.notes.get(key)
    if note is None or note.status == "rejected":
        raise BibModeError(f"[E-BIB-MODE] note 卡不存在或已否决：{key}")
    if note.entry is None:
        raise BibModeError(f"[E-BIB-MODE] note 卡缺 entry 字段，无从写 bib：{key}"
                           "（补 entry 或改名复用已有 key）")
    if key in project.bib_keys:
        return "present"
    target = project.root / project.bib_files[0]
    old = target.read_text(encoding="utf-8") if target.exists() else ""
    block = render_entry(note)   # BibValueError 裸穿：调用方标 [E-BIB-VALUE]
    sep = "" if (not old or old.endswith("\n")) else "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    try:
        tmp.write_text(old + sep + block + "\n", encoding="utf-8", newline="\n")
        os.replace(tmp, target)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    project.bib_keys.add(key)   # 内存态同步：同进程连续调用幂等（P-M2）
    return "added"


def fixable_notes(project: Project) -> list[str]:
    """一键修复适用卡（设计 §3.5）：非 rejected + entry 非空 + id 不在 bib + unmanaged + bib 恰一个。"""
    if project.bib_managed or project.bib_cfg_error or len(project.bib_files) != 1:
        return []
    return sorted(nid for nid, n in project.notes.items()
                  if n.status != "rejected" and n.entry is not None
                  and nid not in project.bib_keys)
