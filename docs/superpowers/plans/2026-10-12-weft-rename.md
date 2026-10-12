# weft 改名对齐实施计划（rename：冲突审查 + 全部位点同步）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `weft rename <old> <new> [--dry-run]` 一条命令完成卡片改名（冲突审查 fail-closed + 文件/frontmatter/全部引用位点同步），WebUI 详情页提供同一能力的表单，共用引擎。

**Architecture:** 新增 `src/weft/rename.py`（plan_rename 纯函数校验+扫描 / apply_rename 按 R7 顺序落盘，复用 `save_card(old_rel=…)` 迁移语义与 `save_part` 正文保留）；托管 bib 同步从 web 路由上移为 `bibgen.sync_managed_bib` 共用；CLI 打印计划、WebUI 详情页内联表单。复用 E-NEW-NAME/E-NEW-COLLISION，无新增诊断码。

**Tech Stack:** Python 3 + pydantic、typer（CLI）、FastAPI + Jinja2（WebUI）、pytest。

**基线：** 625 passed, 2 deselected。**完成预期：651 passed, 2 deselected**（新增 26 个测试项：引擎 18 含参数化 + CLI 6 + WebUI 2）。

**工作目录：** worktree `.worktrees/rename-feature`（分支 `rename-feature`）。测试命令：

```bash
.venv/Scripts/python.exe -m pytest tests -q
.venv/Scripts/python.exe -m pytest tests/test_rename.py -v   # 聚焦
```

---

## File Structure

| 文件 | 动作 | 职责 |
|---|---|---|
| `src/weft/rename.py` | 新建 | RenameError/RenamePlan/RenameResult/plan_rename/apply_rename |
| `src/weft/bibgen.py` | 修改 | 新增 `sync_managed_bib(project_root)`（自 web 上移，R8） |
| `src/weft/web/routes/cards.py` | 修改 | 删 `_sync_managed_bib` 改委托 bibgen；新增 rename 路由；`card_detail` 抽 `_render_detail` |
| `src/weft/web/templates/card_detail.html` | 修改 | 改名表单 + 错误 banner |
| `src/weft/cli.py` | 修改 | 新增 `weft rename` 命令与 `_print_plan` |
| `tests/test_rename.py` | 新建 | 11 个引擎测试 |
| `tests/test_cli_rename.py` | 新建 | 6 个 CLI 测试 |
| `tests/test_web_card_edit.py` | 修改 | +2 个 WebUI 测试 |
| `docs/manual.md`、`AGENTS.md`、`docs/roadmap.md` | 修改 | 命令参考、命名约定段更新、命令清单、M4 |

---

### Task 1: `rename.py` 计划段（校验 + 引用扫描，零写入）

**Files:**
- Create: `src/weft/rename.py`（本任务只实现常量/异常/数据类/`plan_rename`）
- Create: `tests/test_rename.py`

- [ ] **Step 1: 写失败测试** `tests/test_rename.py`

```python
"""rename 引擎：计划段校验与引用扫描、应用段落盘同步（rename 设计定案）。"""
from pathlib import Path

import pytest

from weft.rename import RenameError, plan_rename   # Task 3 起补 apply_rename
from weft.scaffold import NewCollisionError, NewNameError
from weft.models.cards import (
    ClaimCard, DataCard, FactCard, MethodCard, NoteCard, ParamCard,
)
from weft.models.narrative import NarrativePart, Node, Use
from weft.store.writer import card_relpath
from tests.helpers import build_project


def _project(**overrides):
    base = dict(
        data=[DataCard(id="data-01", status="approved", description="测量值")],
        facts=[FactCard(id="fact-01", data=["data-01"], statement="s",
                        supports=["claim-01"], status="approved"),
               FactCard(id="fact-02", data=["data-01", "data-02"], statement="t",
                        status="approved")],
        claims=[ClaimCard(id="claim-01", claim_type="uncited", statement="c",
                          status="approved")],
        parts=[NarrativePart(id="sec-01", section="R", nodes=[
            Node(id="para-01-01", purpose="describe",
                 uses=[Use(id="fact-01", role="evidence")], status="approved")]),
        ],
    )
    base.update(overrides)
    project = build_project(**base)
    # build_project 填的是假想路径（metadata/<id>.md）；本测试断言真实 rel，按规范重填
    for table in (project.data_cards, project.facts, project.claims,
                  project.notes, project.methods, project.params):
        for card in table.values():
            project.card_paths[card.id] = Path(card_relpath(card))
    return project


def test_plan_reports_target_refs_and_rels():
    plan = plan_rename(_project(), "data-01", "arrhenius-60c")
    assert (plan.kind, plan.old_id, plan.new_id) == ("data", "data-01", "arrhenius-60c")
    assert plan.old_rel == "metadata/data/data-01.md"
    assert plan.new_rel == "metadata/data/arrhenius-60c.md"
    assert plan.card_refs == {"fact-01": ["data"], "fact-02": ["data"]}
    assert plan.card_rels == {"fact-01": "metadata/facts/fact-01.md",
                              "fact-02": "metadata/facts/fact-02.md"}
    assert plan.part_refs == {}   # 节点 uses 只直接引用 fact/claim/method/param；data 经 fact 间接可达
    assert plan.part_rels == {}
    assert plan.needs_bib_sync is False


def test_plan_part_refs_for_fact_rename():
    plan = plan_rename(_project(), "fact-01", "temp-rate")
    assert plan.card_refs == {}
    assert plan.part_refs == {"sec-01": 1}
    assert plan.part_rels == {"sec-01": "narrative/01-results/sec-01.md"}


def test_plan_aggregates_fields_per_card():
    plan = plan_rename(_project(
        facts=[FactCard(id="fact-01", data=["data-01"], statement="s",
                        supports=["data-01"], status="approved")]),
        "data-01", "d1")
    assert plan.card_refs == {"fact-01": ["data", "supports"]}


def test_plan_old_missing_raises():
    with pytest.raises(RenameError, match="不存在"):
        plan_rename(_project(), "ghost", "x")


def test_plan_same_id_raises():
    with pytest.raises(RenameError, match="相同"):
        plan_rename(_project(), "data-01", "data-01")


@pytest.mark.parametrize("bad", ["../x", "a/b", "", ".x", "x.", " x", "a:b\\c"])
def test_plan_unsafe_new_id_raises(bad):
    with pytest.raises(NewNameError):
        plan_rename(_project(), "data-01", bad)


def test_plan_collision_raises():
    with pytest.raises(NewCollisionError):
        plan_rename(_project(), "data-01", "fact-01")
```

- [ ] **Step 2: 跑测试确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_rename.py -q
```
预期： collection ERROR（`No module named 'weft.rename'`）。

- [ ] **Step 3: 实现计划段** `src/weft/rename.py`

```python
"""卡片改名引擎（rename 设计定案）：计划-应用两段式，fail-closed。

计划段零写入：N9 命名合法性、全卡种命名空间碰撞、引用位点穷举扫描；
应用段按 R7 顺序落盘：写新文件 → 删旧文件 → 改写引用卡 → 改写 part → managed bib。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from weft.labels import find_card
from weft.scaffold import NewCollisionError, _ensure_component
from weft.store.project import Project
from weft.store.writer import card_relpath


class RenameError(Exception):
    """无码改名错误：旧 id 不存在、新旧 id 相同（R5，CLI 打印 ERROR 行）。"""


@dataclass(frozen=True)
class RenamePlan:
    kind: str
    old_id: str
    new_id: str
    old_rel: str
    new_rel: str
    card_refs: dict[str, list[str]]   # 引用卡 id → 受影响字段（data/supports/cites/method/derived_from）
    card_rels: dict[str, str]         # 引用卡 id → 相对路径（计划打印用）
    part_refs: dict[str, int]         # part id → uses 改写处数
    part_rels: dict[str, str]         # part id → 相对路径（计划打印用）
    needs_bib_sync: bool              # note 改名且 bib_managed（R3）


@dataclass(frozen=True)
class RenameResult:
    written: list[Path]
    bib_status: str | None   # bibgen.sync_managed_bib 返回值（仅 note 改名时有意义）


def plan_rename(project: Project, old_id: str, new_id: str) -> RenamePlan:
    found = find_card(project, old_id)
    if found is None:
        raise RenameError(f"项目里不存在卡片：{old_id}")
    kind, card = found
    if old_id == new_id:
        raise RenameError(f"新 id 与原 id 相同：{old_id}")
    _ensure_component("new_id", new_id)
    if new_id in project.card_paths:
        raise NewCollisionError(
            f"id 已被占用：{new_id}（{project.card_paths[new_id].as_posix()}）",
            project.card_paths[new_id].as_posix())

    card_refs: dict[str, list[str]] = {}
    card_rels: dict[str, str] = {}

    def _mark(cid: str, fname: str) -> None:
        if cid == old_id:   # 改名卡自身不进引用改写列表（内容随文件迁移）
            return
        if fname not in card_refs.setdefault(cid, []):
            card_refs[cid].append(fname)
        card_rels[cid] = project.card_paths[cid].as_posix()

    for cid, f in project.facts.items():
        if old_id in f.data:
            _mark(cid, "data")
        if old_id in f.supports:
            _mark(cid, "supports")
    for cid, c in project.claims.items():
        if old_id in c.cites:
            _mark(cid, "cites")
    for cid, m in project.methods.items():
        if old_id in m.derived_from:
            _mark(cid, "derived_from")
    for cid, p in project.params.items():
        if p.method == old_id:
            _mark(cid, "method")
        if old_id in p.derived_from:
            _mark(cid, "derived_from")

    part_refs: dict[str, int] = {}
    part_rels: dict[str, str] = {}
    for part in project.parts:
        n = sum(1 for node in part.nodes for u in node.uses if u.id == old_id)
        if n:
            part_refs[part.id] = n
            part_rels[part.id] = project.part_paths[part.id].as_posix()

    return RenamePlan(kind=kind, old_id=old_id, new_id=new_id,
                      old_rel=project.card_paths[old_id].as_posix(),
                      new_rel=_new_rel(card, new_id),
                      card_refs=card_refs, card_rels=card_rels,
                      part_refs=part_refs, part_rels=part_rels,
                      needs_bib_sync=(kind == "note" and project.bib_managed))


def _new_rel(card, new_id: str) -> str:
    """新 id 的规范相对路径：借同种卡模型推导（claim 目录随 claim_type）。"""
    return card_relpath(card.model_copy(update={"id": new_id}))
```

- [ ] **Step 4: 跑测试确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_rename.py -q
```
预期： **13 passed**（7 个测试函数；`test_plan_unsafe_new_id_raises` 参数化展开 7 项）。

**计数口径（全计划权威）**：新增测试项 = 引擎计划段 13（Task 1）+ 引擎应用 5（Task 3）
+ CLI 6（Task 4）+ WebUI 2（Task 5）= **26 项**，最终预期 **651 passed, 2 deselected**。

- [ ] **Step 5: 提交**

```bash
git add src/weft/rename.py tests/test_rename.py
git commit -m "feat: rename 引擎计划段——N9 合法性/命名空间碰撞/引用位点穷举扫描（零写入 fail-closed）"
```

---

### Task 2: 托管 bib 同步上移 `bibgen.sync_managed_bib`（R8）

**Files:**
- Modify: `src/weft/bibgen.py`（新增函数）
- Modify: `src/weft/web/routes/cards.py`（删 `_sync_managed_bib`，两处调用点改委托）

- [ ] **Step 1: bibgen.py 末尾新增**（模块内已有 `sync_bib`、`BibValueError`）：

```python
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
```

- [ ] **Step 2: web 委托**——`routes/cards.py`：删除 `_sync_managed_bib` 整个函数，
  在原两处调用点（`card_new_post` 的 note 分支、`card_review` 的 note 分支）把
  `_sync_managed_bib(entry.project.root)` 改为
  `sync_managed_bib(entry.project.root)`，import 区加
  `from weft.bibgen import sync_managed_bib`。

- [ ] **Step 3: 回归确认**

```bash
.venv/Scripts/python.exe -m pytest tests/test_web_card_new.py tests/test_web_card_edit.py tests/test_web_bib_propose.py tests/test_bibgen.py -q
```
预期： 全部 passed（行为不变）。

- [ ] **Step 4: 提交**

```bash
git add src/weft/bibgen.py src/weft/web/routes/cards.py
git commit -m "refactor: 托管 bib 同步上移 bibgen.sync_managed_bib，web 路由委托共用（R8）"
```

---

### Task 3: `apply_rename` 应用段

**Files:**
- Modify: `src/weft/rename.py`（补 `apply_rename`）
- Modify: `tests/test_rename.py`（追加 5 个测试）

- [ ] **Step 1: 追加失败测试**（`tests/test_rename.py` 末尾；文件级用 `tests.helpers.write_card` + tmp_path）

```python
from tests.helpers import make_minimal_project, write_card
from weft.store.loader import load_project


def test_apply_moves_card_file(tmp_path):
    make_minimal_project(tmp_path)
    project, diags = load_project(tmp_path)
    assert not any(d.is_error for d in diags)
    plan = plan_rename(project, "data-01", "run-60c")
    result = apply_rename(project, plan)
    assert not (tmp_path / "metadata" / "data" / "data-01.md").exists()
    new_text = (tmp_path / "metadata" / "data" / "run-60c.md").read_text(encoding="utf-8")
    assert "id: run-60c" in new_text and "description" in new_text
    assert [p.name for p in result.written] == ["run-60c.md"]
    assert result.bib_status is None


def test_apply_updates_card_refs_and_part_uses(tmp_path):
    make_minimal_project(tmp_path)
    project, _ = load_project(tmp_path)
    plan = plan_rename(project, "fact-01", "temp-rate")
    apply_rename(project, plan)
    project2, diags = load_project(tmp_path)
    assert not any(d.is_error for d in diags)
    assert project2.facts["temp-rate"].statement == "温度提高速率。"
    assert "fact-01" not in project2.card_paths
    node = project2.parts[0].nodes[0]
    assert [(u.id, u.role) for u in node.uses] == [("temp-rate", "evidence")]
    raw = (tmp_path / "narrative" / "01-results" / "part-01.md").read_text(encoding="utf-8")
    assert "审阅备注" in raw   # part 正文原样保留


def test_apply_updates_cites_and_derived_from_on_note_rename(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "claims" / "cited", "claim-02",
               {"id": "claim-02", "claim_type": "cited", "statement": "引用陈述",
                "cites": ["key2020"], "status": "approved"})
    write_card(tmp_path / "metadata" / "methods", "qpcr",
               {"id": "qpcr", "statement": "m", "protocol": "p",
                "derived_from": ["key2020"], "status": "approved"})
    project, _ = load_project(tmp_path)
    plan = plan_rename(project, "key2020", "key2021")
    assert plan.card_refs == {"claim-02": ["cites"], "qpcr": ["derived_from"]}
    apply_rename(project, plan)
    project2, _ = load_project(tmp_path)
    assert project2.claims["claim-02"].cites == ["key2021"]
    assert project2.methods["qpcr"].derived_from == ["key2021"]


def test_apply_updates_param_method_ref(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "methods", "qpcr",
               {"id": "qpcr", "statement": "m", "protocol": "p", "status": "approved"})
    write_card(tmp_path / "metadata" / "methods" / "params", "p1",
               {"id": "p1", "method": "qpcr", "status": "approved"})
    project, _ = load_project(tmp_path)
    plan = plan_rename(project, "qpcr", "qpcr-3step")
    assert plan.card_refs == {"p1": ["method"]}
    apply_rename(project, plan)
    project2, _ = load_project(tmp_path)
    assert project2.params["p1"].method == "qpcr-3step"
    assert not (tmp_path / "metadata" / "methods" / "qpcr.md").exists()
    assert (tmp_path / "metadata" / "methods" / "qpcr-3step.md").exists()


def test_apply_managed_note_syncs_bib(tmp_path):
    from tests.helpers import make_managed_project
    make_managed_project(tmp_path)
    write_card(tmp_path / "metadata" / "claims" / "cited", "claim-02",
               {"id": "claim-02", "claim_type": "cited", "statement": "引用陈述",
                "cites": ["key2020"], "status": "approved"})
    project, _ = load_project(tmp_path)
    plan = plan_rename(project, "key2020", "key2021")
    assert plan.needs_bib_sync is True
    result = apply_rename(project, plan)
    assert result.bib_status == "bib_updated"
    bib = (tmp_path / "references.bib").read_text(encoding="utf-8")
    assert "key2021" in bib and "key2020" not in bib
```

- [ ] **Step 2: 跑测试确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_rename.py -q
```
预期： 新增 5 个 FAIL（`ImportError: cannot import name 'apply_rename'`）。

- [ ] **Step 3: 实现 `apply_rename`**（追加到 `rename.py`；import 区补
  `from weft.store.writer import card_relpath, save_card, save_part` 与惰性
  `from weft.bibgen import sync_managed_bib`）：

```python
def apply_rename(project: Project, plan: RenamePlan) -> RenameResult:
    written: list[Path] = []
    kind, card = find_card(project, plan.old_id)
    new_card = card.model_copy(update={"id": plan.new_id})
    written.append(save_card(project.root, new_card, old_rel=plan.old_rel))

    for cid, fields in plan.card_refs.items():
        _ref_kind, ref_card = find_card(project, cid)
        updates: dict = {}
        for fname in fields:
            value = getattr(ref_card, fname)
            if isinstance(value, str):            # param.method 单值
                updates[fname] = plan.new_id
            else:                                 # 列表通道
                updates[fname] = [plan.new_id if v == plan.old_id else v
                                  for v in value]
        written.append(save_card(project.root, ref_card.model_copy(update=updates)))

    for part in project.parts:
        if part.id not in plan.part_refs:
            continue
        new_nodes = [node.model_copy(update={"uses": [
            u.model_copy(update={"id": plan.new_id}) if u.id == plan.old_id else u
            for u in node.uses]})
            if any(u.id == plan.old_id for u in node.uses) else node
            for node in part.nodes]
        save_part(project, part.model_copy(update={"nodes": new_nodes}))
        written.append(project.root / project.part_paths[part.id])

    bib_status = None
    if plan.kind == "note":
        from weft.bibgen import sync_managed_bib
        bib_status = sync_managed_bib(project.root)
    return RenameResult(written=written, bib_status=bib_status)
```

- [ ] **Step 4: 跑测试确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_rename.py -q
```
预期： 全部 passed。

- [ ] **Step 5: 提交**

```bash
git add src/weft/rename.py tests/test_rename.py
git commit -m "feat: rename 引擎应用段——save_card 迁移/引用卡与 part uses 同步/managed bib 自动重渲"
```

---

### Task 4: CLI `weft rename`

**Files:**
- Modify: `src/weft/cli.py`（import + `show` 命令后新增 `rename` + `_print_plan`；docstring 命令清单加 `rename`）
- Create: `tests/test_cli_rename.py`

- [ ] **Step 1: 写失败测试** `tests/test_cli_rename.py`

```python
"""weft rename：一条命令改名 + 冲突审查 + 全部位点同步。"""
from typer.testing import CliRunner

from weft.cli import app
from tests.helpers import make_minimal_project, write_card

runner = CliRunner()


def test_rename_success_syncs_references(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["rename", "fact-01", "temp-rate", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "改写计划：" in result.output
    assert "重命名  metadata/facts/fact-01.md → metadata/facts/temp-rate.md" in result.output
    assert "narrative/01-results/part-01.md（uses 1 处）" in result.output
    assert "✓ 2 个文件已更新" in result.output
    assert (tmp_path / "metadata" / "facts" / "temp-rate.md").exists()
    assert not (tmp_path / "metadata" / "facts" / "fact-01.md").exists()


def test_rename_dry_run_writes_nothing(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["rename", "fact-01", "temp-rate",
                                 str(tmp_path), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "(dry-run，未写入)" in result.output
    assert (tmp_path / "metadata" / "facts" / "fact-01.md").exists()
    assert not (tmp_path / "metadata" / "facts" / "temp-rate.md").exists()


def test_rename_collision_exits_1(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["rename", "fact-01", "claim-01", str(tmp_path)])
    assert result.exit_code == 1
    assert "E-NEW-COLLISION" in result.output
    assert (tmp_path / "metadata" / "facts" / "fact-01.md").exists()


def test_rename_unsafe_name_exits_1(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["rename", "fact-01", "../x", str(tmp_path)])
    assert result.exit_code == 1
    assert "E-NEW-NAME" in result.output
    assert (tmp_path / "metadata" / "facts" / "fact-01.md").exists()


def test_rename_unknown_old_exits_1(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["rename", "ghost", "x", str(tmp_path)])
    assert result.exit_code == 1
    assert "ERROR 项目里不存在卡片：ghost" in result.output


def test_rename_load_error_refuses(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "facts", "broken",
               {"id": "broken", "data": [], "statement": "s", "status": "draft"})
    result = runner.invoke(app, ["rename", "fact-01", "temp-rate", str(tmp_path)])
    assert result.exit_code == 1
    assert "E-PARSE" in result.output
    assert (tmp_path / "metadata" / "facts" / "fact-01.md").exists()
    assert not (tmp_path / "metadata" / "facts" / "temp-rate.md").exists()
```

- [ ] **Step 2: 跑测试确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_cli_rename.py -q
```
预期： 6 个 FAIL（命令不存在）。

- [ ] **Step 3: 实现**——`cli.py`：docstring 清单 `review / show` 后插 `rename`；
  import 区加 `from weft.rename import RenameError, RenamePlan, apply_rename, plan_rename`
  与 `from weft.scaffold import NewCollisionError, NewNameError`；
  `show` 命令之后新增：

```python
def _print_plan(plan: RenamePlan) -> None:
    typer.echo("改写计划：")
    typer.echo(f"  重命名  {plan.old_rel} → {plan.new_rel}")
    for cid, fields in plan.card_refs.items():
        typer.echo(f"  同步    {plan.card_rels[cid]}（{', '.join(fields)}）")
    for pid, n in plan.part_refs.items():
        typer.echo(f"  同步    {plan.part_rels[pid]}（uses {n} 处）")


@app.command()
def rename(
    old_id: str = typer.Argument(..., help="现有卡片 id（六类通用）"),
    new_id: str = typer.Argument(..., help="新 id（全卡种全局唯一，安全路径成分）"),
    project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录"),
    dry_run: bool = typer.Option(False, "--dry-run", help="只打印改写计划，不落盘"),
) -> None:
    """改名并同步全部引用位点（文件/frontmatter/data/supports/cites/method/derived_from/节点 uses）。"""
    project, load_diags = load_project(project_dir)
    if any(d.is_error for d in load_diags):
        _print_diagnostics(load_diags)
        raise typer.Exit(code=1)
    try:
        plan = plan_rename(project, old_id, new_id)
    except RenameError as exc:
        typer.echo(f"ERROR {exc}")
        raise typer.Exit(code=1) from exc
    except NewNameError as exc:
        _print_diagnostics([Diagnostic(Level.ERROR, "E-NEW-NAME", ".", None, str(exc))])
        raise typer.Exit(code=1) from exc
    except NewCollisionError as exc:
        _print_diagnostics([Diagnostic(
            Level.ERROR, "E-NEW-COLLISION", exc.rel or ".", None, str(exc))])
        raise typer.Exit(code=1) from exc
    _print_plan(plan)
    if dry_run:
        typer.echo("(dry-run，未写入)")
        return
    result = apply_rename(project, plan)
    typer.echo(f"✓ {len(result.written)} 个文件已更新")
    if plan.kind == "note":
        if result.bib_status == "bib_updated":
            typer.echo("已同步 managed bib")
        elif result.bib_status is None:
            typer.echo("⚠ references.bib 为自管文件（unmanaged），请手工把条目 key 同步为新 id")
        else:
            typer.echo("⚠ managed bib 重渲失败（bib_error），请检查 references.bib 与 note entry")
```

- [ ] **Step 4: 跑测试确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_cli_rename.py tests/test_cli.py -q
```
预期： 全部 passed。

- [ ] **Step 5: 提交**

```bash
git add src/weft/cli.py tests/test_cli_rename.py
git commit -m "feat: weft rename 命令——dry-run 计划打印、E-NEW-* 诊断、加载错误拒绝（零写入）"
```

---

### Task 5: WebUI 详情页改名表单

**Files:**
- Modify: `src/weft/web/routes/cards.py`（`card_detail` 抽 `_render_detail`；新增 `card_rename` 路由）
- Modify: `src/weft/web/templates/card_detail.html`（改名表单 + 错误 banner）
- Modify: `tests/test_web_card_edit.py`（+2 测试）

- [ ] **Step 1: 追加失败测试**（`tests/test_web_card_edit.py` 末尾，沿用其 importorskip 头部模式）

```python
def test_rename_card_via_ui(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/cards/fact/fact-01/rename",
                       data={"new_id": "temp-rate"}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/p/demo/cards/fact/temp-rate"
    assert (root / "demo" / "metadata" / "facts" / "temp-rate.md").exists()
    assert not (root / "demo" / "metadata" / "facts" / "fact-01.md").exists()


def test_rename_collision_renders_error(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/cards/fact/fact-01/rename",
                       data={"new_id": "claim-01"})
    assert resp.status_code == 200
    assert "E-NEW-COLLISION" in resp.text
    assert (root / "demo" / "metadata" / "facts" / "fact-01.md").exists()
    assert not (root / "demo" / "metadata" / "claims" / "uncited" / "temp-rate.md").exists()
```

- [ ] **Step 2: 跑测试确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_web_card_edit.py -q
```
预期： 新增 2 个 FAIL（404，路由不存在）。

- [ ] **Step 3: 实现**——`routes/cards.py`：

`card_detail` 的响应构造抽成 `_render_detail`（GET 与 rename 错误回显共用）：

```python
def _render_detail(request, entry, kind, card, *, rename_error: str | None = None):
    card_id = card.id
    return templates.TemplateResponse(
        request, "card_detail.html",
        {"entry": entry, "kind": kind, "card": card,
         "rel": entry.project.card_paths[card_id].as_posix(),
         "fields": {k: (yaml.safe_dump(v, allow_unicode=True, sort_keys=False)
                        if k == "entry" and v else ("" if v is None else v))
                    for k, v in card.model_dump().items()
                    if k not in ("id", "status", "comment")},
         "bib_flag": request.query_params.get("bib"),
         "rename_error": rename_error})


@router.get("/p/{pid}/cards/{kind}/{card_id}")
def card_detail(request: Request, pid: str, kind: str, card_id: str):
    entry, table = _table(request, pid, kind)
    card = table.get(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="卡片不存在")
    return _render_detail(request, entry, kind, card)


@router.post("/p/{pid}/cards/{kind}/{card_id}/rename")
async def card_rename(request: Request, pid: str, kind: str, card_id: str):
    """卡片改名（rename 设计 R9）：与 CLI 共用 plan/apply 引擎，错误回显详情页。"""
    entry, table = _table(request, pid, kind)
    card = table.get(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="卡片不存在")
    form = await request.form()
    new_id = str(form.get("new_id") or "").strip()
    try:
        plan = plan_rename(entry.project, card_id, new_id)
    except RenameError as exc:
        return _render_detail(request, entry, kind, card, rename_error=str(exc))
    except NewNameError as exc:
        return _render_detail(request, entry, kind, card,
                              rename_error=f"[E-NEW-NAME] {exc}")
    except NewCollisionError as exc:
        return _render_detail(request, entry, kind, card,
                              rename_error=f"[E-NEW-COLLISION] {exc}")
    apply_rename(entry.project, plan)
    return RedirectResponse(f"/p/{pid}/cards/{kind}/{new_id}", status_code=303)
```

import 区补：`from weft.rename import RenameError, apply_rename, plan_rename`
与 `from weft.scaffold import NewCollisionError, NewNameError`。

`templates/card_detail.html`：审阅表单之后、编辑链接之前插入：

```html
<h3>改名</h3>
{% if rename_error %}<div class="banner error">{{ rename_error }}</div>{% endif %}
<form method="post" action="/p/{{ entry.pid }}/cards/{{ kind }}/{{ card.id }}/rename">
  <label>新 id（全卡种全局唯一，语义命名优先）<input name="new_id" placeholder="如 {{ kind }}-…语义短语"></label>
  <button type="submit">改名并同步引用</button>
</form>
```

- [ ] **Step 4: 跑测试确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_web_card_edit.py tests/test_web_cards.py tests/test_web_card_new.py -q
```
预期： 全部 passed。

- [ ] **Step 5: 提交**

```bash
git add src/weft/web/routes/cards.py src/weft/web/templates/card_detail.html tests/test_web_card_edit.py
git commit -m "feat: WebUI 卡片详情页改名表单——与 CLI 共用 plan/apply 引擎，冲突回显 banner"
```

---

### Task 6: 文档同步 + 全量验证

**Files:**
- Modify: `docs/manual.md`（§7 加 `weft rename`；§5 命名约定段更新）
- Modify: `AGENTS.md`（命令清单加 `rename`）
- Modify: `docs/roadmap.md`（M4 加一行）
- Modify: 本计划（计数回填）

- [ ] **Step 1: manual.md**——`### weft show` 小节后插入：

```markdown
### weft rename

```bash
weft rename <old_id> <new_id> [project_dir] [--dry-run]
```

一条命令完成卡片改名（六类通用）：先审查（新 id 命名合法性 `E-NEW-NAME`、全卡种
命名空间碰撞 `E-NEW-COLLISION`、项目加载有 error 时拒绝），再同步改写全部位点——
卡片文件与 frontmatter id、`fact.data`/`fact.supports`/`claim.cites`/`param.method`/
`derived_from`、全部叙事节点 `uses`（role 保留）。`--dry-run` 只打印改写计划不落盘。
note 卡改名 = bib key 改名：managed 模式自动重渲 references.bib，unmanaged 模式
完成后提醒手工同步。WebUI 卡片详情页提供同一入口。
```

§5 命名约定段中「id 即文件名，全卡种全局唯一；落盘后改名需手工同步所有引用点，
故不做 rename 工具。」改为：

```markdown
id 即文件名，全卡种全局唯一；落盘后用 `weft rename <旧id> <新id>` 改名，命令自动
审查冲突并同步全部引用位点（WebUI 详情页同样提供改名入口）。
```

- [ ] **Step 2: AGENTS.md** 命令清单 `review / show / draft` → `review / show / rename / draft`。

- [ ] **Step 3: roadmap.md** M4 追加：

```markdown
- 改名对齐 `weft rename` ✅（2026-10-12）：一条命令完成卡片改名——冲突审查 fail-closed（复用 E-NEW-NAME/E-NEW-COLLISION）+ 全部引用位点同步（文件/frontmatter/data/supports/cites/param.method/derived_from/节点 uses）+ managed bib 自动重渲；`--dry-run` 计划打印；WebUI 详情页表单共用引擎。设计见 `docs/superpowers/specs/2026-10-12-weft-rename-design.md`。
```

- [ ] **Step 4: 全量测试 + 计数回填**

```bash
.venv/Scripts/python.exe -m pytest tests -q
```
预期： **651 passed, 2 deselected**（625 + 26 项：引擎计划段 13（7 函数，unsafe 参数化展开 7 项）+ 引擎应用 5 + CLI 6 + WebUI 2）。**实际：651 passed, 2 deselected（2026-10-12 全量验证一致，无偏离）。**

- [ ] **Step 5: 提交**

```bash
git add docs/manual.md AGENTS.md docs/roadmap.md docs/superpowers/plans/2026-10-12-weft-rename.md
git commit -m "docs: 改名对齐落地——manual rename 命令参考与命名约定更新、roadmap M4、AGENTS 命令清单、计划计数回填"
```

---

## 合并与收尾（主会话执行）

1. 全量绿 → 回主仓库 `git merge rename-feature`（--no-ff）→ 合并结果全量测试；
2. `git worktree remove .worktrees/rename-feature` + `git worktree prune` + `git branch -d rename-feature`；
3. `git push`。

## 设计偏离回填

执行期如偏离设计定案（R1–R9），回填本节注明决策编号与理由。
