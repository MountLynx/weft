# weft bib 模式切换与一键修复 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** bib 模式 unmanaged↔managed 双向切换（预检 + 逐行改 weft.yaml 保注释）与 unmanaged 项目 E-NOTE-NOT-IN-BIB 的一键修复（note entry 确定性追加进 bib），WebUI + CLI 双入口。

**Architecture:** 引擎全部落在 `src/weft/bibgen.py`（bib 域 owner，纯确定性，红线 1 无涉）：`plan_switch` 零写入预检、`apply_switch` 逐行改 `weft.yaml`（M2 保注释）、`fix_note_in_bib` 幂等追加、`fixable_notes` 统一口径。WebUI 新路由模块 `routes/bibmode.py`（`load_reviewable_or_404`，M6），CLI 在 `bib_app` 组加 `mode`/`fix` 两条命令。设计文档：`docs/superpowers/specs/2026-10-13-weft-bib-mode-fix-design.md`（决策 M1–M8）。

**Tech Stack:** pydantic、FastAPI + Jinja2、typer、pytest（现仓依赖，零新增）。

**测试基线：** 773 passed（b2c5a84 口径）。本计划新增 32 个测试（引擎 18 + WebUI 9 + CLI 5；引擎侧比预估多 4：P-M1 口径修正拆出的缺失 bib 文件用例等），实测 **805 passed**（2 deselected 为 smoke，下同）。

## 文件结构

| 文件 | 职责 |
| --- | --- |
| `src/weft/bibgen.py` | Modify：BibModeError / SwitchPlan / plan_switch / apply_switch / fix_note_in_bib / fixable_notes |
| `src/weft/web/routes/bibmode.py` | Create：3 条路由（确认页 GET、切换 POST、修复 POST） |
| `src/weft/web/routes/__init__.py` | Modify：注册 bibmode |
| `src/weft/web/routes/core.py` | Modify：diagnostics_page 传 fix_map |
| `src/weft/web/routes/cards.py` | Modify：_render_detail 传 fixable |
| `src/weft/web/templates/bib_switch_confirm.html` | Create：切换确认页 |
| `src/weft/web/templates/dashboard.html` | Modify：bib 模式块 |
| `src/weft/web/templates/diagnostics.html` | Modify：修复结果横幅 + 行内修复按钮 |
| `src/weft/web/templates/card_detail.html` | Modify：修复结果横幅 + 一键修复按钮 |
| `src/weft/cli.py` | Modify：`weft bib mode` / `weft bib fix` |
| `tests/test_bibgen.py` | Modify：引擎 14 测试 |
| `tests/test_web_bibmode.py` | Create：WebUI 9 测试 |
| `tests/test_cli_bib.py` | Modify：CLI 5 测试 |
| `AGENTS.md`、`docs/roadmap.md` | Modify：红线 4/5 增补、码表、计数、必读文档 |

工作流：git worktree `.worktrees/bib-mode-fix`（分支同名），完成后合回 main 并删除。

---

### Task 1: worktree + 引擎预检 `plan_switch`

**Files:**
- Modify: `src/weft/bibgen.py`（文件尾追加）
- Test: `tests/test_bibgen.py`（文件尾追加）

- [ ] **Step 1: 建 worktree**

```bash
cd "C:/Users/xingy/Desktop/开发/weft"
git worktree add .worktrees/bib-mode-fix -b bib-mode-fix
```

后续所有命令在 `.worktrees/bib-mode-fix` 内执行（`WEFT_SMOKE` 无涉；pytest 用主仓 venv：`C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe -m pytest`，worktree 内相对路径跑）。

- [ ] **Step 2: 写失败测试（tests/test_bibgen.py 尾部追加）**

```python
# ---------- bib 模式切换与一键修复（bib-mode-fix 设计 §3） ----------

from weft.bibgen import BibModeError, plan_switch  # noqa: E402


def _note_with_entry(root, key="li2021", status="draft"):
    write_card(root / "metadata" / "notes", key,
               {"id": key, "summary": "s", "status": status,
                "entry": dict(NOTE_ENTRY)})


def test_plan_switch_to_managed_reports_hand_entries(tmp_path):
    root = make_minimal_project(tmp_path / "demo")   # bib 有 key2020，note 无 entry
    project, _ = load_project(root)
    plan = plan_switch(project, True)
    assert plan.from_managed is False and plan.to_managed is True
    assert plan.bib_files == ["references.bib"]
    assert plan.hand_only_entries == ["key2020"]     # 无 approved+entry 卡覆盖
    assert plan.notes_not_in_bib == []


def test_plan_switch_to_unmanaged_reports_notes_not_in_bib(tmp_path):
    root = make_managed_project(tmp_path / "demo")
    _note_with_entry(root)
    project, _ = load_project(root)
    plan = plan_switch(project, False)
    assert plan.from_managed is True
    assert plan.notes_not_in_bib == ["li2021"]


def test_plan_switch_to_managed_refuses_without_single_bib(tmp_path):
    root = make_minimal_project(tmp_path / "demo")
    (root / "references.bib").unlink()               # bib 文件缺失 → bib_files 空
    project, _ = load_project(root)
    with pytest.raises(BibModeError, match="bibliography"):
        plan_switch(project, True)


def test_plan_switch_refuses_bib_cfg_error(tmp_path):
    root = make_minimal_project(tmp_path / "demo")
    write_yaml(root / "weft.yaml", {"bib": "oops"})  # bib 段非映射 → bib_cfg_error
    project, _ = load_project(root)
    assert project.bib_cfg_error
    with pytest.raises(BibModeError, match="weft.yaml"):
        plan_switch(project, True)
    with pytest.raises(BibModeError):
        plan_switch(project, False)
```

文件头 import 区确认已有：`pytest`、`load_project`、`make_minimal_project`、`make_managed_project`、`NOTE_ENTRY`、`write_card`、`write_yaml`（现测试已在用；缺则补）。

- [ ] **Step 3: 跑测试确认红**

Run: `C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe -m pytest tests/test_bibgen.py -q`（在 worktree 内）
Expected: 4 failed（ImportError: BibModeError）

- [ ] **Step 4: 实现（bibgen.py 尾部追加；`from dataclasses import dataclass` 补到文件头 import 区）**

```python
class BibModeError(Exception):
    """切换/修复动作前置失败（E-BIB-MODE）：操作异常码，非项目状态诊断（bib-mode-fix 设计 §3.1）。"""


@dataclass
class SwitchPlan:
    """模式切换预检报告（零写入；设计 §3.2）。"""

    to_managed: bool
    from_managed: bool
    bib_files: list[str]
    hand_only_entries: list[str]     # bib 中无 approved+entry 卡覆盖的 key：managed 化后下次 sync 消失
    notes_not_in_bib: list[str]      # 非 rejected note 中 id 不在 bib：unmanaged 化后报 E-NOTE-NOT-IN-BIB


def plan_switch(project: Project, to_managed: bool) -> SwitchPlan:
    if project.bib_cfg_error:
        raise BibModeError(f"[E-BIB-MODE] weft.yaml bib 段非法：{project.bib_cfg_error}")
    if to_managed and len(project.bib_files) != 1:
        raise BibModeError("[E-BIB-MODE] managed 模式要求 bibliography 恰好指向一个存在文件"
                           f"（先修 _quarto.yml；当前：{'、'.join(project.bib_files) or '无'}）")
    covered = {n.id for n in project.notes.values()
               if n.status == "approved" and n.entry is not None}
    return SwitchPlan(
        to_managed=to_managed, from_managed=project.bib_managed,
        bib_files=list(project.bib_files),
        hand_only_entries=sorted(project.bib_keys - covered),
        notes_not_in_bib=sorted(nid for nid, n in project.notes.items()
                                if n.status != "rejected" and nid not in project.bib_keys))
```

- [ ] **Step 5: 跑测试确认绿**

Run: `C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe -m pytest tests/test_bibgen.py -q`
Expected: 全绿（原 bibgen 测试 + 新 4）

- [ ] **Step 6: Commit**

```bash
git add src/weft/bibgen.py tests/test_bibgen.py
git commit -m "feat: bib 模式切换预检 plan_switch（SwitchPlan 报告 + E-BIB-MODE 前置拒绝）"
```

---

### Task 2: 引擎执行 `apply_switch`（逐行改 weft.yaml 保注释）

**Files:**
- Modify: `src/weft/bibgen.py`
- Test: `tests/test_bibgen.py`

- [ ] **Step 1: 写失败测试**

```python
def test_apply_switch_flips_line_and_keeps_comments(tmp_path):
    root = make_minimal_project(tmp_path / "demo")
    (root / "weft.yaml").write_text(
        "# weft 项目配置\nbib:\n"
        "  managed: false            # true：由 weft 从已批准文献卡生成（勿手改）\n"
        "figures_dir: figures\n", encoding="utf-8")
    project, _ = load_project(root)
    apply_switch(root, plan_switch(project, True))
    text = (root / "weft.yaml").read_text(encoding="utf-8")
    assert "managed: true" in text
    assert "# weft 项目配置" in text                      # 注释全保留（M2）
    assert "由 weft 从已批准文献卡生成" in text
    project2, diags = load_project(root)
    assert not any(d.is_error for d in diags)
    assert project2.bib_managed is True


def test_apply_switch_appends_block_when_no_weft_yaml(tmp_path):
    root = make_minimal_project(tmp_path / "demo")
    (root / "weft.yaml").unlink()
    project, _ = load_project(root)
    apply_switch(root, plan_switch(project, True))
    project2, _ = load_project(root)
    assert project2.bib_managed is True


def test_apply_switch_inserts_key_when_block_has_no_managed(tmp_path):
    root = make_minimal_project(tmp_path / "demo")
    (root / "weft.yaml").write_text("# 配置\nbib:\nfigures_dir: figures\n",
                                    encoding="utf-8")
    project, _ = load_project(root)
    apply_switch(root, plan_switch(project, True))
    project2, diags = load_project(root)
    assert not any(d.is_error for d in diags)
    assert project2.bib_managed is True
    assert "figures_dir: figures" in (root / "weft.yaml").read_text(encoding="utf-8")


def test_apply_switch_refuses_when_file_drifted(tmp_path):
    root = make_minimal_project(tmp_path / "demo")
    project, _ = load_project(root)                  # from_managed=False
    (root / "weft.yaml").write_text("bib:\n  managed: true\n", encoding="utf-8")
    with pytest.raises(BibModeError, match="已变化"):
        apply_switch(root, plan_switch(project, True))


def test_apply_switch_refuses_flow_style_bib(tmp_path):
    root = make_minimal_project(tmp_path / "demo")
    (root / "weft.yaml").write_text("bib: {managed: false}\n", encoding="utf-8")
    project, _ = load_project(root)
    with pytest.raises(BibModeError, match="流式"):
        apply_switch(root, plan_switch(project, True))
```

文件头补 import：`apply_switch`（并入现有 `from weft.bibgen import ...`）。

- [ ] **Step 2: 跑测试确认红**

Run: `.../python.exe -m pytest tests/test_bibgen.py -q -k apply_switch`
Expected: 5 failed（ImportError）

- [ ] **Step 3: 实现（bibgen.py 追加）**

```python
def apply_switch(project_root: Path, plan: SwitchPlan) -> None:
    """写 weft.yaml 的 bib.managed（设计 §3.3 / M2）：逐行改保注释，原子写，LF。"""
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
```

- [ ] **Step 4: 跑测试确认绿**

Run: `.../python.exe -m pytest tests/test_bibgen.py -q`
Expected: 全绿

- [ ] **Step 5: Commit**

```bash
git add src/weft/bibgen.py tests/test_bibgen.py
git commit -m "feat: apply_switch 逐行改 weft.yaml 保注释（原子写 + 出发值漂移拒绝）"
```

---

### Task 3: 引擎一键修复 `fix_note_in_bib` + `fixable_notes`

**Files:**
- Modify: `src/weft/bibgen.py`
- Test: `tests/test_bibgen.py`

- [ ] **Step 1: 写失败测试**

```python
def test_fix_appends_entry_and_clears_error(tmp_path):
    root = make_minimal_project(tmp_path / "demo")
    _note_with_entry(root)                           # draft + entry，不在 bib
    project, _ = load_project(root)
    assert fix_note_in_bib(project, "li2021") == "added"
    text = (root / "references.bib").read_text(encoding="utf-8")
    assert "@article{li2021," in text and "key2020" in text   # 追加而非覆盖
    project2, diags = load_project(root)
    assert not any(d.code == "E-NOTE-NOT-IN-BIB" for d in diags)


def test_fix_is_idempotent(tmp_path):
    root = make_minimal_project(tmp_path / "demo")
    _note_with_entry(root)
    project, _ = load_project(root)
    fix_note_in_bib(project, "li2021")
    before = (root / "references.bib").read_text(encoding="utf-8")
    assert fix_note_in_bib(project, "li2021") == "present"
    assert (root / "references.bib").read_text(encoding="utf-8") == before


def test_fix_refuses_on_managed(tmp_path):
    root = make_managed_project(tmp_path / "demo")
    project, _ = load_project(root)
    with pytest.raises(BibModeError, match="sync"):
        fix_note_in_bib(project, "key2020")


def test_fix_refuses_without_entry(tmp_path):
    root = make_minimal_project(tmp_path / "demo")
    write_card(root / "metadata" / "notes", "noent",
               {"id": "noent", "summary": "s", "status": "draft"})
    project, _ = load_project(root)
    with pytest.raises(BibModeError, match="entry"):
        fix_note_in_bib(project, "noent")


def test_fix_refuses_rejected_or_missing_note(tmp_path):
    root = make_minimal_project(tmp_path / "demo")
    project, _ = load_project(root)
    with pytest.raises(BibModeError, match="不存在"):
        fix_note_in_bib(project, "ghost2020")


def test_fix_refuses_without_bib_file(tmp_path):
    root = make_minimal_project(tmp_path / "demo")
    _note_with_entry(root)
    (root / "references.bib").unlink()
    project, _ = load_project(root)
    with pytest.raises(BibModeError, match="bibliography"):
        fix_note_in_bib(project, "li2021")


def test_fix_propagates_render_error(tmp_path):
    root = make_minimal_project(tmp_path / "demo")
    write_card(root / "metadata" / "notes", "badent",
               {"id": "badent", "summary": "s", "status": "draft",
                "entry": {"type": "article", "title": "T{", "year": 2020}})
    project, _ = load_project(root)
    with pytest.raises(bibgen.BibValueError):
        fix_note_in_bib(project, "badent")


def test_fixable_notes_scope(tmp_path):
    root = make_minimal_project(tmp_path / "demo")
    _note_with_entry(root, "fixme")                          # ✓ 可修复
    _note_with_entry(root, "gone", status="rejected")        # rejected → 排除
    write_card(root / "metadata" / "notes", "noent",         # 无 entry → 排除
               {"id": "noent", "summary": "s", "status": "draft"})
    project, _ = load_project(root)
    assert fixable_notes(project) == ["fixme"]
    managed_root = make_managed_project(tmp_path / "m")
    assert fixable_notes(load_project(managed_root)[0]) == []
```

注意：`make_minimal_project` 自带 note key2020 在 bib 中且无 entry，不在口径内。

文件头补 import：`apply_switch` 处一并并入 `fix_note_in_bib, fixable_notes` 与 `from weft import bibgen`。

- [ ] **Step 2: 跑测试确认红**

Run: `.../python.exe -m pytest tests/test_bibgen.py -q -k "fix"`
Expected: 8 failed

- [ ] **Step 3: 实现（bibgen.py 追加）**

```python
def fix_note_in_bib(project: Project, key: str) -> str:
    """把 note 卡 entry 确定性追加进 unmanaged bib（设计 §3.4）；返回 "added"/"present"。"""
    if project.bib_managed:
        raise BibModeError("[E-BIB-MODE] managed 项目由 weft bib sync 管辖，无需修复")
    if project.bib_cfg_error:
        raise BibModeError(f"[E-BIB-MODE] weft.yaml bib 段非法：{project.bib_cfg_error}")
    if len(project.bib_files) != 1:
        raise BibModeError("[E-BIB-MODE] 修复要求 bibliography 恰好指向一个存在文件"
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
    tmp = target.with_name(target.name + ".tmp")
    try:
        tmp.write_text(old + sep + block + "\n", encoding="utf-8", newline="\n")
        os.replace(tmp, target)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    return "added"


def fixable_notes(project: Project) -> list[str]:
    """一键修复适用卡（设计 §3.5）：非 rejected + entry 非空 + id 不在 bib + unmanaged + bib 恰一个。"""
    if project.bib_managed or project.bib_cfg_error or len(project.bib_files) != 1:
        return []
    return sorted(nid for nid, n in project.notes.items()
                  if n.status != "rejected" and n.entry is not None
                  and nid not in project.bib_keys)
```

- [ ] **Step 4: 跑测试确认绿**

Run: `.../python.exe -m pytest tests/test_bibgen.py -q`
Expected: 全绿

- [ ] **Step 5: Commit**

```bash
git add src/weft/bibgen.py tests/test_bibgen.py
git commit -m "feat: fix_note_in_bib 幂等追加 + fixable_notes 统一口径（E-NOTE-NOT-IN-BIB 一键修复引擎）"
```

---

### Task 4: WebUI 路由与模板

**Files:**
- Create: `src/weft/web/routes/bibmode.py`、`src/weft/web/templates/bib_switch_confirm.html`
- Modify: `src/weft/web/routes/__init__.py`、`core.py`（diagnostics_page）、`cards.py`（_render_detail）、`dashboard.html`、`diagnostics.html`、`card_detail.html`
- Test: Create `tests/test_web_bibmode.py`

- [ ] **Step 1: 写失败测试（tests/test_web_bibmode.py 新建）**

```python
"""bib 模式切换与一键修复路由（bib-mode-fix 设计 §4）。"""
import pytest

pytest.importorskip("fastapi")

from pathlib import Path

from weft.store.loader import load_project
from tests.helpers import NOTE_ENTRY, make_managed_project, make_minimal_project, write_card, write_yaml
from tests.webutil import make_client


def _poison(root):
    """unmanaged + draft note（带 entry，不在 bib）→ E-NOTE-NOT-IN-BIB 报错项目。"""
    write_card(root / "demo" / "metadata" / "notes", "li2021",
               {"id": "li2021", "summary": "s", "status": "draft",
                "entry": dict(NOTE_ENTRY)})


def test_switch_confirm_renders_report(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.get("/p/demo/bib/switch?to=managed")
    assert resp.status_code == 200
    assert "key2020" in resp.text            # hand_only_entries 警告逐条列出
    assert "确认切换" in resp.text


def test_switch_confirm_unknown_target_404(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/p/demo/bib/switch?to=bogus").status_code == 404


def test_switch_post_flips_mode(tmp_path):
    client, root = make_client(tmp_path)
    make_managed_project(root / "demo")
    resp = client.post("/p/demo/bib/switch", data={"to": "unmanaged"},
                       follow_redirects=False)
    assert resp.status_code == 303
    project, _ = load_project(root / "demo")
    assert project.bib_managed is False
    assert client.get("/p/demo/?bibmode=switched").status_code == 200


def test_switch_post_precondition_failure_rerenders(tmp_path):
    client, root = make_client(tmp_path)
    (root / "demo" / "references.bib").unlink()   # bib_files 空 → to=managed 拒绝
    resp = client.post("/p/demo/bib/switch", data={"to": "managed"})
    assert resp.status_code == 200
    assert "E-BIB-MODE" in resp.text


def test_dashboard_shows_bib_block(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/")
    assert "bib 模式" in resp.text and "unmanaged" in resp.text
    assert '/p/demo/bib/switch?to=managed' in resp.text


def test_fix_post_added_clears_error(tmp_path):
    client, root = make_client(tmp_path)
    _poison(root)
    resp = client.post("/p/demo/bib/fix/li2021", data={"back": "card"},
                       follow_redirects=False)
    assert resp.status_code == 303
    assert "/cards/note/li2021?fix=added" in resp.headers["location"]
    text = (root / "demo" / "references.bib").read_text(encoding="utf-8")
    assert "@article{li2021," in text
    assert 'badge rejected">不可用' not in client.get("/p/demo/").text


def test_fix_post_present(tmp_path):
    client, root = make_client(tmp_path)
    _poison(root)
    bib = root / "demo" / "references.bib"
    bib.write_text(bib.read_text(encoding="utf-8")
                   + "@article{li2021,\n  title = {T},\n  year = {2021},\n}\n",
                   encoding="utf-8")
    resp = client.post("/p/demo/bib/fix/li2021", data={"back": "diagnostics"},
                       follow_redirects=False)
    assert resp.status_code == 303
    assert "diagnostics?fix=present" in resp.headers["location"]


def test_fix_post_error_branch(tmp_path):
    client, root = make_client(tmp_path)
    _poison(root)
    (root / "demo" / "references.bib").unlink()
    resp = client.post("/p/demo/bib/fix/li2021", data={"back": "diagnostics"},
                       follow_redirects=False)
    assert resp.status_code == 303
    assert "diagnostics?fix=error" in resp.headers["location"]


def test_note_detail_fix_button_visibility(tmp_path):
    client, root = make_client(tmp_path)
    _poison(root)
    assert "一键修复" in client.get("/p/demo/cards/note/li2021").text
    assert "一键修复" not in client.get("/p/demo/cards/note/key2020").text
    # 诊断页行内按钮
    diag = client.get("/p/demo/diagnostics").text
    assert "bib/fix/li2021" in diag
```

- [ ] **Step 2: 跑测试确认红**

Run: `.../python.exe -m pytest tests/test_web_bibmode.py -q`
Expected: 全 failed（404 / 断言失败）

- [ ] **Step 3: 实现 `src/weft/web/routes/bibmode.py`（新建）**

```python
"""bib 模式切换与一键修复路由（bib-mode-fix 设计 §4）。"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse

from weft import bibgen
from weft.web.common import load_reviewable_or_404, templates

router = APIRouter()

_TO = {"managed": True, "unmanaged": False}


def _confirm_page(request: Request, entry, to: str, error: str | None):
    plan = None
    try:
        plan = bibgen.plan_switch(entry.project, _TO[to])
    except bibgen.BibModeError as exc:
        error = error or str(exc)
    return templates.TemplateResponse(
        request, "bib_switch_confirm.html",
        {"entry": entry, "to": to, "plan": plan, "error": error})


@router.get("/p/{pid}/bib/switch")
def switch_confirm(request: Request, pid: str, to: str = "managed"):
    if to not in _TO:
        raise HTTPException(status_code=404, detail="未知目标模式")
    return _confirm_page(request, load_reviewable_or_404(request, pid), to, None)


@router.post("/p/{pid}/bib/switch")
async def switch_apply(request: Request, pid: str):
    form = await request.form()
    to = str(form.get("to", ""))
    if to not in _TO:
        raise HTTPException(status_code=404, detail="未知目标模式")
    entry = load_reviewable_or_404(request, pid)
    try:
        plan = bibgen.plan_switch(entry.project, _TO[to])
        bibgen.apply_switch(entry.project.root, plan)
    except bibgen.BibModeError as exc:
        return _confirm_page(request, entry, to, str(exc))
    return RedirectResponse(f"/p/{pid}/?bibmode=switched", status_code=303)


@router.post("/p/{pid}/bib/fix/{key}")
async def fix_note(request: Request, pid: str, key: str):
    entry = load_reviewable_or_404(request, pid)
    form = await request.form()
    back = str(form.get("back", "diagnostics"))
    if back not in ("diagnostics", "card"):
        back = "diagnostics"
    try:
        result = bibgen.fix_note_in_bib(entry.project, key)
    except bibgen.BibModeError:
        result = "error"   # M8：按钮可见⇒前置曾成立，失败只剩竞态，通用横幅
    base = (f"/p/{pid}/diagnostics" if back == "diagnostics"
            else f"/p/{pid}/cards/note/{quote(key)}")
    return RedirectResponse(f"{base}?fix={result}", status_code=303)


def register(app: FastAPI) -> None:
    app.include_router(router)
```

- [ ] **Step 4: 注册路由（routes/__init__.py 的 register_all 尾部）**

```python
    from weft.web.routes import bibmode as bibmode_routes

    bibmode_routes.register(app)
```

- [ ] **Step 5: 模板与既有路由改动**

`core.py` diagnostics_page（替换现函数体）：

```python
@router.get("/p/{pid}/diagnostics")
def diagnostics_page(request: Request, pid: str):
    # 故意用 load_entry_or_404：损坏项目也要能看诊断——诊断页正是看错误的地方（设计 §2/§7）。
    entry = load_entry_or_404(request, pid)
    fix_map = {}
    if entry.project is not None:
        from weft import bibgen
        fix_map = {entry.project.card_paths[k].as_posix(): k
                   for k in bibgen.fixable_notes(entry.project)}
    return templates.TemplateResponse(
        request, "diagnostics.html", {"entry": entry, "fix_map": fix_map})
```

`cards.py` `_render_detail`（context dict 增一项；文件头补 `from weft import bibgen`）：

```python
         "fixable": (bibgen.fixable_notes(entry.project)
                     if kind == "note" else []),
```

`dashboard.html`（stats 与待审队列之间插入）：

```html
<h3>bib 模式</h3>
{% if request.query_params.get("bibmode") == "switched" %}<div class="banner ok">bib 模式已切换。</div>{% endif %}
<p>当前：<span class="badge {{ "approved" if project.bib_managed else "draft" }}">{{ "managed" if project.bib_managed else "unmanaged" }}</span>
{% if project.bib_managed %}
  <a href="/p/{{ entry.pid }}/bib/switch?to=unmanaged">切换为 unmanaged</a>
  ｜ managed：approved+entry 文献卡经 <code>weft bib sync</code> 生成 bib，勿手改
{% else %}
  <a href="/p/{{ entry.pid }}/bib/switch?to=managed">切换为 managed</a>
  ｜ unmanaged：bib 手工维护，note id 须在 bib 中
{% endif %}</p>
```

`diagnostics.html`（`<h2>` 后加横幅；行内操作列）：

```html
{% set fix = request.query_params.get("fix") %}
{% if fix == "added" %}<div class="banner ok">已把条目写入 bib，错误将在下次加载时消除。</div>
{% elif fix == "present" %}<div class="banner ok">bib 中已有该条目，无需修复。</div>
{% elif fix == "error" %}<div class="banner error">修复前置已变化，请刷新后重试。</div>{% endif %}
```

行循环 `<td>{{ d.message }}</td>` 改为：

```html
    <td>{{ d.message }}
      {% if d.code == "E-NOTE-NOT-IN-BIB" and d.path in fix_map %}
      <form method="post" action="/p/{{ entry.pid }}/bib/fix/{{ fix_map[d.path] }}" class="inline">
        <input type="hidden" name="back" value="diagnostics">
        <button type="submit">一键修复</button>
      </form>
      {% endif %}</td>
```

`card_detail.html`（status 表单后加；pdf_warn banner 旁）：

```html
{% set fix = request.query_params.get("fix") %}
{% if fix == "added" %}<div class="banner ok">已把条目写入 bib，错误将在下次加载时消除。</div>
{% elif fix == "present" %}<div class="banner ok">bib 中已有该条目，无需修复。</div>
{% elif fix == "error" %}<div class="banner error">修复前置已变化，请刷新后重试。</div>{% endif %}
{% if kind == "note" and card.id in fixable %}
<form method="post" action="/p/{{ entry.pid }}/bib/fix/{{ card.id }}" class="inline">
  <input type="hidden" name="back" value="card">
  <button type="submit">🔧 一键修复：条目写入 bib</button>
</form>
{% endif %}
```

注意：`card_detail.html` 既有 banner 用 `banner error` 类；`banner ok` 若 webui.css 无此
类则实现时看一眼 `static/webui.css` 的 banner 定义，选已有的肯定类（如 `.ok` 按钮色）
或新增纯样式类（样式令牌架构：主题文件只许令牌声明，样式加在 webui.css）。

- [ ] **Step 6: 跑测试确认绿**

Run: `.../python.exe -m pytest tests/test_web_bibmode.py tests/test_web_pages.py tests/test_web_cards.py -q`
Expected: 全绿（新 9 + 既有不回归）

- [ ] **Step 7: Commit**

```bash
git add src/weft/web tests/test_web_bibmode.py
git commit -m "feat: WebUI bib 模式切换确认页与一键修复路由（dashboard/诊断页/详情页三入口）"
```

---

### Task 5: CLI `weft bib mode` / `weft bib fix`

**Files:**
- Modify: `src/weft/cli.py`（bib_app 组，`bib_sync` 之后）
- Test: `tests/test_cli_bib.py`

- [ ] **Step 1: 写失败测试（tests/test_cli_bib.py 尾部追加）**

```python
# ---------- bib mode / fix（bib-mode-fix 设计 §5） ----------

def test_bib_mode_shows_current(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["bib", "mode", str(tmp_path)])
    assert result.exit_code == 0
    assert "unmanaged" in result.output


def test_bib_mode_switch_with_yes(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["bib", "mode", str(tmp_path), "managed", "--yes"])
    assert result.exit_code == 0, result.output
    assert "managed: true" in (tmp_path / "weft.yaml").read_text(encoding="utf-8")
    assert "weft bib sync" in result.output


def test_bib_mode_refuses_same_mode(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["bib", "mode", str(tmp_path), "unmanaged", "--yes"])
    assert result.exit_code == 0
    assert "无需切换" in result.output


def test_bib_mode_precondition_refusal(tmp_path):
    make_minimal_project(tmp_path)
    (tmp_path / "references.bib").unlink()
    result = runner.invoke(app, ["bib", "mode", str(tmp_path), "managed", "--yes"])
    assert result.exit_code == 1
    assert "E-BIB-MODE" in result.output


def test_bib_fix_all(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "notes", "li2021",
               {"id": "li2021", "summary": "s", "status": "draft",
                "entry": {"type": "article", "title": "T", "author": ["A, B"],
                          "year": 2021, "journal": "J", "volume": "1"}})
    result = runner.invoke(app, ["bib", "fix", str(tmp_path), "--all"])
    assert result.exit_code == 0, result.output
    assert "已写入 bib：li2021" in result.output
    assert "@article{li2021," in (tmp_path / "references.bib").read_text(encoding="utf-8")
```

确认 test_cli_bib.py 头部已有 `runner`/`make_minimal_project`/`write_card` import
（现有测试在用；缺则补）。

- [ ] **Step 2: 跑测试确认红**

Run: `.../python.exe -m pytest tests/test_cli_bib.py -q -k "mode or fix_all"`
Expected: 5 failed（命令不存在）

- [ ] **Step 3: 实现（cli.py，bib_sync 命令后追加）**

```python
@bib_app.command("mode")
def bib_mode(
    project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录"),
    to: str = typer.Argument(None, help="目标模式 managed|unmanaged（缺省只显示当前模式）"),
    yes: bool = typer.Option(False, "--yes", help="跳过确认"),
) -> None:
    """显示或切换 bib 模式（bib-mode-fix 设计 §5）。"""
    from weft import bibgen

    project, load_diags = load_project(project_dir)
    if any(d.is_error for d in load_diags):
        _print_diagnostics(load_diags)
        raise typer.Exit(code=1)
    if to is None:
        typer.echo(f"当前 bib 模式：{'managed' if project.bib_managed else 'unmanaged'}")
        return
    if to not in ("managed", "unmanaged"):
        typer.echo("ERROR 目标模式必须是 managed 或 unmanaged")
        raise typer.Exit(code=1)
    target = to == "managed"
    if target == project.bib_managed:
        typer.echo(f"已是 {to} 模式，无需切换")
        return
    try:
        plan = bibgen.plan_switch(project, target)
    except bibgen.BibModeError as exc:
        typer.echo(f"ERROR {exc}")
        raise typer.Exit(code=1)
    typer.echo(f"切换预检（→ {to}）：")
    if plan.hand_only_entries:
        typer.echo(f"  警告：{len(plan.hand_only_entries)} 条 bib 条目无对应文献卡，"
                   "下次 weft bib sync 后消失：")
        for k in plan.hand_only_entries:
            typer.echo(f"    - {k}")
    if plan.notes_not_in_bib:
        typer.echo(f"  提示：{len(plan.notes_not_in_bib)} 张非否决文献卡不在 bib 中")
    if not yes and not typer.confirm("确认切换？"):
        typer.echo("已取消")
        return
    bibgen.apply_switch(project_dir, plan)
    typer.echo(f"已切换为 {to} 模式（weft.yaml: bib.managed = {'true' if target else 'false'}）")
    typer.echo("下一步：检查无误后运行 weft bib sync 生成 bib" if target
               else "下一步：可用 weft bib fix <key> 把文献卡条目写入 bib")


@bib_app.command("fix")
def bib_fix(
    project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录"),
    key: str = typer.Argument(None, help="文献卡 id（bib key）；--all 时可省略"),
    all_fixable: bool = typer.Option(False, "--all", help="修复全部可修复文献卡"),
) -> None:
    """把文献卡 entry 追加进 unmanaged bib（一键修复；bib-mode-fix 设计 §5）。"""
    from weft import bibgen

    project, load_diags = load_project(project_dir)
    if any(d.is_error for d in load_diags):
        _print_diagnostics(load_diags)
        raise typer.Exit(code=1)
    if all_fixable:
        keys = bibgen.fixable_notes(project)
        if not keys:
            typer.echo("没有可一键修复的文献卡")
            return
    elif key:
        keys = [key]
    else:
        typer.echo("ERROR 需要提供 key 或使用 --all")
        raise typer.Exit(code=1)
    failed = False
    for k in keys:
        try:
            result = bibgen.fix_note_in_bib(project, k)
        except bibgen.BibValueError as exc:
            typer.echo(f"ERROR [E-BIB-VALUE] {k}：{exc}")
            failed = True
        except bibgen.BibModeError as exc:
            typer.echo(f"ERROR {exc}")
            failed = True
        else:
            typer.echo(f"{'已写入 bib' if result == 'added' else 'bib 中已存在，跳过'}：{k}")
    if failed:
        raise typer.Exit(code=1)
```

- [ ] **Step 4: 跑测试确认绿**

Run: `.../python.exe -m pytest tests/test_cli_bib.py -q`
Expected: 全绿

- [ ] **Step 5: Commit**

```bash
git add src/weft/cli.py tests/test_cli_bib.py
git commit -m "feat: CLI weft bib mode/fix（预检报告 + confirm/--yes + --all 批量修复）"
```

---

### Task 6: 文档回填 + 全量 + 合并

**Files:**
- Modify: `AGENTS.md`（必读文档列表 + 红线 4 + 红线 5 码表 + 计数 801）
- Modify: `docs/roadmap.md`（M4 增一行）
- Modify: 本计划文档（设计决策回填 + 计数）

- [ ] **Step 1: AGENTS.md 回填**

- 必读文档列表加：`docs/superpowers/specs/2026-10-13-weft-bib-mode-fix-design.md` — bib 模式切换与一键修复设计定案（`E-BIB-MODE`、plan/apply_switch、fix_note_in_bib；决策 M1–M8）
- 红线 4 白名单句尾追加：`；bib 模式切换/一键修复由 src/weft/bibgen.py 确定性写 weft.yaml 的 bib.managed 与 unmanaged bib 目标文件（追加式，非 AI 落盘）`
- 红线 5 码表 bibgen 设计后加：`、2026-10-13-weft-bib-mode-fix-design.md（E-BIB-MODE）`
- 常用命令注释计数改 `801 passed, 2 deselected`（以实测为准回填）

- [ ] **Step 2: roadmap.md M4 段加一行**

`- bib 模式切换与一键修复 ✅（2026-10-13：weft bib mode/fix + WebUI 三入口，E-BIB-MODE）`

- [ ] **Step 3: 全量测试**

Run: `.../python.exe -m pytest tests -q`
Expected: **801 passed, 2 deselected**（实测回填）

- [ ] **Step 4: 合并回 main 并清理**

```bash
cd "C:/Users/xingy/Desktop/开发/weft"
git add AGENTS.md docs/roadmap.md docs/superpowers/plans/2026-10-13-weft-bib-mode-fix.md
git commit -m "docs: bib 模式切换与一键修复落地——AGENTS 红线 4/5 增补 E-BIB-MODE、roadmap M4、计数回填"
git checkout main && git merge --ff-only bib-mode-fix
git worktree remove .worktrees/bib-mode-fix && git branch -d bib-mode-fix
git push
```

注意：主检出有无关未提交改动（`examples/paper-demo/metadata/data/data-01.md`），不要顺手提交它。

## 设计决策（执行期）

执行中任何偏离设计定案之处，回填至本表（格式：`| P-M# | 偏离 | 理由 |`）。无偏离则写"无"。

| P-M# | 偏离 | 理由 |
| --- | --- | --- |
| P-M2 | fix_note_in_bib 写盘成功后原地更新 `project.bib_keys` | bib_keys 是加载快照，同进程第二次 fix 同 key 会重复追加（测试 test_fix_is_idempotent 抓住）；web 每请求重载不受影响，CLI/长持有对象受影响 |
| P-M1 | bib_files 口径修正：loader 实际保留"声明的缺失文件"（E-BIB-MISSING 为加载级错误）；plan_switch 增加显式存在性检查；涉 bib 缺失的测试改为"未声明 bibliography"可达场景 | 计划误记 loader 行为（实测 `loader.py:270`：`project.bib_files` 取自声明列表，缺失仅报诊断不剔除）；缺文件态项目 project=None，路由 404，预检须自带存在性检查才语义完整 |
