# weft new 命令组实施计划（模板化创建空白 part 与卡片）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `weft new part` / `weft new card` 两条 CLI 子命令，按内置模板生成空白叙事 part 与六类元数据卡片，编号自动、碰撞 fail-closed。

**Architecture:** 模板与规划纯函数放 `src/weft/scaffold.py`（不依赖 engine/LLM，与 init 同层）；CLI 层只做项目加载、取 id 集合、调 plan、写文件、打印诊断。卡片落盘目录对齐 `store/writer.card_relpath`（守卫测试防漂移）。

**Tech Stack:** Python 3.11 + Typer + PyYAML + pytest。设计依据：`docs/superpowers/specs/2026-10-10-weft-new-template-design.md`（决策 N1–N10）。

**基线：** 全量 556 passed, 2 deselected。**执行后实绩：全量 602 passed, 2 deselected**（`tests/test_new_cmd.py` 新增 46 例：5 模板 + 22 规划（含参数化展开）+ 18 CLI + 1 守卫）。

---

## Task 0: worktree 隔离

- [ ] `git worktree add .worktrees/weft-new-template -b weft-new-template`，后续所有改动在 `.worktrees/weft-new-template` 内进行（AGENTS 工作流约定）。
- [ ] 在 worktree 内确认基线：`.venv/Scripts/python.exe -m pytest tests -q`（用主仓 venv 跑 worktree 测试需先 `pip install -e` 或直接 `cd` 主仓跑——本仓采用后者：实现完成后回主仓路径跑全量；单测可在 worktree 内用主 venv 指定路径跑）。

实际操作约定：所有文件编辑都发生在 `.worktrees/weft-new-template/` 前缀下；测试命令用主仓 venv：

```bash
.venv/Scripts/python.exe -m pytest .worktrees/weft-new-template/tests/test_new_cmd.py -v
```

---

## Task 1: scaffold 模板层——异常、成分校验、part 模板参数化

**Files:**
- Modify: `src/weft/scaffold.py`
- Test: `tests/test_new_cmd.py`（新建）

- [ ] **Step 1: 写失败测试**（`tests/test_new_cmd.py`）

```python
"""weft new 命令组：模板化创建空白叙事 part 与元数据卡片。"""
import yaml

from weft.scaffold import (
    NewCollisionError,
    NewNameError,
    render_card_template,
    render_part_template,
)

# init 脚手架改造前 _PART_01_MD 的原文（逐字节黄金，防 render_part_template 派生漂移）
_INIT_PART_GOLDEN = """\
---
id: sec-01
section: Introduction
# 节点 = 审阅单位；status 改 approved 后 `weft draft sec-01` 生成草稿。
# nodes 示例（uses 引用元数据卡 id，role 常用 evidence / conclusion）：
# nodes:
# - id: para-01-01
#   purpose: describe
#   uses:
#   - id: fact-01
#     role: evidence
#   logic: 本段叙事策略（给 AI 的行文依据）
#   status: draft
nodes: []
---
part id（sec-01）是 `weft draft` 的寻址单位；正文由生成与拼装流水线产出，不手写在这里。
"""


def test_render_part_template_matches_init_scaffold():
    assert render_part_template("sec-01", "Introduction") == _INIT_PART_GOLDEN


def test_render_part_template_parametrized():
    text = render_part_template("sec-12", "Related Work")
    assert "id: sec-12" in text
    assert "section: Related Work" in text
    assert "# - id: para-12-01" in text
    assert "`weft draft sec-12`" in text
    assert "part id（sec-12）" in text


def test_render_part_template_quotes_yaml_unsafe_section():
    text = render_part_template("sec-02", "Methods: overview")
    assert 'section: "Methods: overview"' in text
    # 整个 frontmatter 必须可被 frontmatter 解析回原值
    import frontmatter

    parsed = frontmatter.loads(text)
    assert parsed["section"] == "Methods: overview"


def test_render_part_template_no_digits_defaults_example_nn():
    text = render_part_template("sec-intro", "引言")
    assert "# - id: para-01-01" in text
    assert "section: 引言" in text


def test_render_card_template_roundtrip():
    import frontmatter

    required = {
        "data": set(),
        "fact": {"data", "statement"},
        "claim": {"claim_type", "statement"},
        "note": set(),
        "method": {"statement", "protocol"},
        "param": {"method"},
    }
    for kind, extra in required.items():
        text = render_card_template(kind, "x-01")
        meta = frontmatter.loads(text)
        assert meta["id"] == "x-01", kind
        assert meta["status"] == "draft", kind
        assert extra <= set(meta.metadata), (kind, sorted(meta.metadata))
```

- [ ] **Step 2: 跑测试确认失败**

```bash
.venv/Scripts/python.exe -m pytest .worktrees/weft-new-template/tests/test_new_cmd.py -v
```
预期：ImportError（`render_part_template` 不存在）。

- [ ] **Step 3: 实现**（`src/weft/scaffold.py`）

头部 import 增加：

```python
import json
import re
```

在 `InitCollisionError` 之后新增：

```python
class NewNameError(Exception):
    """新建参数含非法路径成分（E-NEW-NAME）。"""

    def __init__(self, arg: str, value: str) -> None:
        self.arg = arg
        self.value = value
        super().__init__(f"参数 {arg} 含非法路径成分：{value!r}")


class NewCollisionError(Exception):
    """新建目标已存在或 id 已被占用（E-NEW-COLLISION）；零写入。"""

    def __init__(self, msg: str, rel: str | None = None) -> None:
        self.rel = rel
        super().__init__(msg)
```

模块级常量与纯函数（放在 `SCAFFOLD_FILES` 之前，`_PART_01_MD` 改造见下）：

```python
_UNSAFE_COMPONENT = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_PLAIN_YAML = re.compile(r"[\w][\w \-]*", re.UNICODE)


def _ensure_component(arg: str, value: str) -> None:
    """id/chapter 是落盘路径成分：空、点首尾、空白首尾、分隔符与 Windows 保留字符一律拒绝。"""
    if (not value or value.startswith(".") or value.endswith(".")
            or value != value.strip() or _UNSAFE_COMPONENT.search(value)):
        raise NewNameError(arg, value)


def _yaml_scalar(value: str) -> str:
    """简单词原样（与 init 模板字节一致），含特殊字符时走 JSON 双引号（合法 YAML 流标量）。"""
    if _PLAIN_YAML.fullmatch(value):
        return value
    return json.dumps(value, ensure_ascii=False)


_PART_BODY = """\
# 节点 = 审阅单位；status 改 approved 后 `weft draft {part_id}` 生成草稿。
# nodes 示例（uses 引用元数据卡 id，role 常用 evidence / conclusion）：
# nodes:
# - id: para-{nn}-01
#   purpose: describe
#   uses:
#   - id: fact-01
#     role: evidence
#   logic: 本段叙事策略（给 AI 的行文依据）
#   status: draft
nodes: []
---
part id（{part_id}）是 `weft draft` 的寻址单位；正文由生成与拼装流水线产出，不手写在这里。
"""


def render_part_template(part_id: str, section: str) -> str:
    """参数化生成 part 模板（init 骨架与 weft new part 共用，单一来源）。"""
    digits = re.search(r"\d+", part_id)
    nn = digits.group() if digits else "01"
    front = f"id: {part_id}\nsection: {_yaml_scalar(section)}\n"
    return "---\n" + front + _PART_BODY.format(part_id=part_id, nn=nn)
```

卡片模板常量与渲染函数：

```python
_CARD_TEMPLATES: dict[str, str] = {
    "data": """\
id: {card_id}
status: draft
# refs: []           # 可选：子图级 Quarto label（fig-01a / tbl-01），需先登记进 metadata/figures.yaml
# source: 数据来源（路径/URL/说明）
# description: 数据说明
""",
    "fact": """\
id: {card_id}
status: draft
data: []             # 必填（至少 1 项）：依赖的 data 卡 id；填好前加载报 E-PARSE
statement: ""        # 必填：事实陈述
# supports: []       # 可选：支持的 claim 卡 id
""",
    "claim": """\
id: {card_id}
status: draft
claim_type: uncited  # uncited | cited；cited 时 cites 填 bib key（改类型需连同目录迁移）
statement: ""        # 必填：论点陈述
# cites: []          # claim_type: cited 时填 bib key（须已在 assets/references.bib）
""",
    "note": """\
id: {card_id}        # note 卡 id = bib key
status: draft
# summary: 文献要点（缺省报 W-NOTE-NO-SUMMARY 提醒）
# pdf: 文献 PDF 路径（可选）
# entry: {{}}          # 书目字段；bib managed 模式下 approved + entry 进 references.bib
""",
    "method": """\
id: {card_id}
status: draft
statement: ""        # 必填：方法陈述
protocol: ""         # 必填：操作协议
# derived_from: []   # 可选：方法来源文献 bib key
""",
    "param": """\
id: {card_id}
status: draft
method: ""           # 必填：所属 method 卡 id；悬空报 E-DANGLING-REF
# values: {{}}         # 实验参数键值（每篇不同、逐项核对）
# derived_from: []   # 可选：参数来源文献 bib key
""",
}


def render_card_template(kind: str, card_id: str) -> str:
    return "---\n" + _CARD_TEMPLATES[kind].format(card_id=card_id)
```

注意：note/param 模板里的 `{{}}` 是 format 转义，渲染后为 `{}`。

- [ ] **Step 4: 改造 `_PART_01_MD` 为派生**（同一文件，替换原字面量定义行）：

```python
_PART_01_MD = render_part_template("sec-01", "Introduction")
```

（删除原三引号字面量；`SCAFFOLD_FILES` 引用不变。）

- [ ] **Step 5: 跑测试确认通过**（同 Step 2 命令，5 passed）。

- [ ] **Step 6: 回归 init 测试**：`.venv/Scripts/python.exe -m pytest .worktrees/weft-new-template/tests/test_scaffold.py .worktrees/weft-new-template/tests/test_cli_init.py -v` → 全 passed（字节不变守卫生效）。

- [ ] **Step 7: 提交** `git add -A && git commit -m "feat: scaffold 模板层——part 模板参数化（init 派生字节不变）+ 卡片模板六类 + 路径成分校验"`。

---

## Task 2: scaffold 规划纯函数——plan_new_part / plan_new_card

**Files:**
- Modify: `src/weft/scaffold.py`
- Test: `tests/test_new_cmd.py`（追加）

- [ ] **Step 1: 追加失败测试**

```python
import pytest

from weft.scaffold import CARD_KIND_DIRS, init_project, plan_new_card, plan_new_part


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "p"
    init_project(root)
    return root


def test_plan_new_part_auto_numbering(project):
    target, pid = plan_new_part(project / "narrative", set(), "02-methods", None)
    assert pid == "sec-01"  # 现有集合无 sec-NN 匹配时从 01 起
    assert target == project / "narrative" / "02-methods" / "part-01.md"


def test_plan_new_part_auto_increments_past_existing(project):
    target, pid = plan_new_part(
        project / "narrative", {"sec-01", "sec-02"}, "01-introduction", None)
    assert pid == "sec-03"
    assert target.name == "part-02.md"  # 章节内已有 part-01.md（init 骨架）


def test_plan_new_part_explicit_id(project):
    target, pid = plan_new_part(
        project / "narrative", {"sec-01"}, "01-introduction", "sec-background")
    assert pid == "sec-background"
    assert target.name == "part-02.md"


def test_plan_new_part_id_collision(project):
    with pytest.raises(NewCollisionError):
        plan_new_part(project / "narrative", {"sec-01"}, "01-introduction", "sec-01")


def test_plan_new_part_file_numbering_skips_nonconforming(project):
    (project / "narrative" / "02-x").mkdir()
    (project / "narrative" / "02-x" / "part-05.md").write_text(
        "---\nid: sec-05\nsection: t\nnodes: []\n---\n", encoding="utf-8")
    target, pid = plan_new_part(project / "narrative", {"sec-05"}, "02-x", None)
    assert pid == "sec-06"
    assert target.name == "part-06.md"  # 文件名编号取现有 part-(\d+).md 的 max+1


@pytest.mark.parametrize("bad", ["../evil", "", "a/b", "a\\b", ".", "..", " x", "x ", "x.", ".x", "a:b"])
def test_plan_new_part_bad_chapter(project, bad):
    with pytest.raises(NewNameError):
        plan_new_part(project / "narrative", set(), bad, None)


def test_plan_new_part_blank_explicit_id(project):
    with pytest.raises(NewNameError):
        plan_new_part(project / "narrative", set(), "02-x", "   ")


def test_plan_new_card_targets(project):
    for kind, directory in CARD_KIND_DIRS.items():
        target = plan_new_card(project, set(), kind, "x-01")
        assert target == project / directory / "x-01.md"


def test_plan_new_card_id_collision(project):
    with pytest.raises(NewCollisionError):
        plan_new_card(project, {"fact-01"}, "fact", "fact-01")


@pytest.mark.parametrize("bad", ["", "a/b", "..", ".hid", "x.", "a:b"])
def test_plan_new_card_bad_id(project, bad):
    with pytest.raises(NewNameError):
        plan_new_card(project, set(), "fact", bad)
```

- [ ] **Step 2: 跑测试确认失败**（`plan_new_part` 等不存在 → ImportError）。

- [ ] **Step 3: 实现**（`src/weft/scaffold.py` 追加）：

```python
CARD_KIND_DIRS: dict[str, str] = {
    "data": "metadata/data",
    "fact": "metadata/facts",
    "note": "metadata/notes",
    "method": "metadata/methods",
    "param": "metadata/methods/params",
    "claim": "metadata/claims/uncited",  # 新建 claim 默认 uncited
}

_PART_ID_RE = re.compile(r"^sec-(\d+)$")
_PART_FILE_RE = re.compile(r"^part-(\d+)\.md$")


def plan_new_part(narrative_dir: Path, existing_part_ids, chapter: str,
                  part_id: str | None) -> tuple[Path, str]:
    """计算新 part 落盘路径与最终 id；命名非法/碰撞即抛错，调用方零写入。"""
    _ensure_component("chapter", chapter)
    ids = set(existing_part_ids)
    if part_id is None:
        nums = [int(m.group(1)) for pid in ids if (m := _PART_ID_RE.match(pid))]
        part_id = f"sec-{max(nums, default=0) + 1:02d}"
    elif not part_id.strip():
        raise NewNameError("--id", part_id)
    if part_id in ids:
        raise NewCollisionError(f"part id {part_id} 已存在")
    chapter_dir = narrative_dir / chapter
    nums = [int(m.group(1)) for p in chapter_dir.glob("*.md")
            if (m := _PART_FILE_RE.match(p.name))]
    target = chapter_dir / f"part-{max(nums, default=0) + 1:02d}.md"
    if target.exists():  # 防御分支：自动编号在构造上不可达（见上注）
        rel = target.relative_to(narrative_dir.parent).as_posix()
        raise NewCollisionError(f"目标文件已存在：{rel}", rel)
    return target, part_id


def plan_new_card(root: Path, existing_card_ids, kind: str, card_id: str) -> Path:
    """计算新卡片落盘路径（对齐 writer.card_relpath 规范）；非法/碰撞即抛错。"""
    _ensure_component("id", card_id)
    if card_id in set(existing_card_ids):
        raise NewCollisionError(f"卡片 id {card_id} 已存在")
    target = root / CARD_KIND_DIRS[kind] / f"{card_id}.md"
    if target.exists():
        rel = target.relative_to(root).as_posix()
        raise NewCollisionError(f"目标文件已存在：{rel}", rel)
    return target
```

注意：part 的目标文件名由编号数学推导（现有 `part-(\d+).md` 全部进 max），自动结果与现有文件同名在构造上不可能；`target.exists()` 是防御分支（防同名目录等病态条目），不打专用测试，id/卡片碰撞路径由 Task 2/Task 3 的 E-NEW-COLLISION 用例覆盖。

- [ ] **Step 4: 跑测试确认通过**（Task 1 + Task 2 全绿）。

- [ ] **Step 5: 提交** `git commit -am "feat: scaffold 规划纯函数 plan_new_part/plan_new_card——自动编号、卡片目录映射、fail-closed 碰撞"`。

---

## Task 3: CLI——`weft new part` / `weft new card`

**Files:**
- Modify: `src/weft/cli.py`
- Test: `tests/test_new_cmd.py`（追加）

- [ ] **Step 1: 追加失败测试**

```python
from typer.testing import CliRunner

from weft.cli import app
from weft.store.loader import load_project
from weft.validation import validate_project

runner = CliRunner()


def _load(root):
    project, diags = load_project(root)
    return project, diags


def test_cli_new_part_success(project):
    result = runner.invoke(app, ["new", "part", "02-methods", "Methods", str(project)])
    assert result.exit_code == 0, result.output
    assert "已创建 narrative/02-methods/part-01.md" in result.output
    target = project / "narrative" / "02-methods" / "part-01.md"
    assert target.is_file()
    project2, diags = _load(project)
    part = next(p for p in project2.parts if p.id == "sec-01")
    assert part.section == "Methods"
    assert not [d for d in diags if d.is_error]


def test_cli_new_part_auto_numbering_in_existing_chapter(project):
    result = runner.invoke(app, ["new", "part", "01-introduction", "背景", str(project)])
    assert result.exit_code == 0, result.output
    assert (project / "narrative" / "01-introduction" / "part-02.md").is_file()
    project2, _ = _load(project)
    assert {p.id for p in project2.parts} == {"sec-01", "sec-02"}


def test_cli_new_part_explicit_id(project):
    result = runner.invoke(
        app, ["new", "part", "02-methods", "Methods", "--id", "sec-methods", str(project)])
    assert result.exit_code == 0, result.output
    project2, _ = _load(project)
    assert any(p.id == "sec-methods" for p in project2.parts)


def test_cli_new_part_id_collision_exit_1(project):
    result = runner.invoke(
        app, ["new", "part", "01-introduction", "X", "--id", "sec-01", str(project)])
    assert result.exit_code == 1
    assert "E-NEW-COLLISION" in result.output


@pytest.mark.parametrize("bad", ["../evil", "a/b", ""])
def test_cli_new_part_bad_chapter_exit_1(project, bad):
    result = runner.invoke(app, ["new", "part", bad, "X", str(project)])
    assert result.exit_code == 1
    assert "E-NEW-NAME" in result.output


def test_cli_new_card_all_kinds(project):
    ids = {"data": "data-01", "fact": "fact-01", "claim": "claim-01",
           "note": "smith2020", "method": "method-dft", "param": "param-dft"}
    from weft.scaffold import CARD_KIND_DIRS

    for kind, cid in ids.items():
        result = runner.invoke(app, ["new", "card", kind, cid, str(project)])
        assert result.exit_code == 0, (kind, result.output)
        assert (project / CARD_KIND_DIRS[kind] / f"{cid}.md").is_file()
    project2, _ = _load(project)
    assert project2.data_cards["data-01"].status == "draft"
    assert project2.claims["claim-01"].claim_type == "uncited"
    assert "smith2020" in project2.notes
    # 文件名 = id（loader 的 E-FILENAME-MISMATCH 无诊断即一致）
    names = {p.name for p in (project / "metadata").rglob("*.md")}
    assert "fact-01.md" in names and "smith2020.md" in names


def test_cli_new_card_fact_stub_yields_one_eparse(project):
    runner.invoke(app, ["new", "card", "fact", "fact-09", str(project)])
    _, diags = _load(project)
    errors = [d for d in diags if d.is_error]
    assert len(errors) == 1
    assert errors[0].code == "E-PARSE"
    assert errors[0].field == "data"


def test_cli_new_card_param_stub_yields_dangling(project):
    runner.invoke(app, ["new", "card", "param", "param-01", str(project)])
    project2, diags = _load(project)
    diags = diags + validate_project(project2)
    assert any(d.code == "E-DANGLING-REF" and d.field == "method" for d in diags)


def test_cli_new_card_data_note_stubs_clean(project):
    runner.invoke(app, ["new", "card", "data", "data-01", str(project)])
    runner.invoke(app, ["new", "card", "note", "key2020", str(project)])
    project2, diags = _load(project)
    diags = diags + validate_project(project2)
    assert not [d for d in diags if d.is_error]


def test_cli_new_card_id_collision_exit_1(project):
    runner.invoke(app, ["new", "card", "data", "data-01", str(project)])
    result = runner.invoke(app, ["new", "card", "fact", "data-01", str(project)])
    assert result.exit_code == 1
    assert "E-NEW-COLLISION" in result.output


def test_cli_new_card_bad_id_exit_1(project):
    result = runner.invoke(app, ["new", "card", "fact", "a/b", str(project)])
    assert result.exit_code == 1
    assert "E-NEW-NAME" in result.output


def test_cli_new_card_unknown_kind_rejected(project):
    result = runner.invoke(app, ["new", "card", "story", "s-01", str(project)])
    assert result.exit_code != 0
```

- [ ] **Step 2: 跑测试确认失败**（`new` 命令不存在 → exit code 2）。

- [ ] **Step 3: 实现**（`src/weft/cli.py`）

头部 import 增加 `from enum import Enum`（若无）。在 `bib_app` 定义之后、`init` 命令之前新增：

```python
class _CardKind(str, Enum):
    data = "data"
    fact = "fact"
    claim = "claim"
    note = "note"
    method = "method"
    param = "param"


new_app = typer.Typer(help="按内置模板创建空白叙事 part / 元数据卡片")
app.add_typer(new_app, name="new")


@new_app.command("part")
def new_part(
    chapter: str = typer.Argument(..., help="章节目录名（narrative/<chapter>/），如 02-methods"),
    section: str = typer.Argument(..., help="节标题（part 的 section 字段）"),
    part_id: str | None = typer.Option(None, "--id", help="part id（缺省按 sec-NN 自动编号）"),
    project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录"),
) -> None:
    """按模板新建叙事 part（narrative/<chapter>/part-NN.md）。"""
    from weft.scaffold import (
        NewCollisionError,
        NewNameError,
        plan_new_part,
        render_part_template,
    )

    project, _ = load_project(project_dir)
    try:
        target, pid = plan_new_part(
            project.root / "narrative", project.part_paths.keys(), chapter, part_id)
    except NewNameError as exc:
        _print_diagnostics([Diagnostic(Level.ERROR, "E-NEW-NAME", ".", None, str(exc))])
        raise typer.Exit(code=1) from exc
    except NewCollisionError as exc:
        _print_diagnostics([Diagnostic(
            Level.ERROR, "E-NEW-COLLISION", exc.rel or ".", None, str(exc))])
        raise typer.Exit(code=1) from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_part_template(pid, section), encoding="utf-8", newline="\n")
    typer.echo(f"已创建 {target.relative_to(project.root).as_posix()}")
    typer.echo(f"下一步：填写 nodes，approved 后 weft draft {pid}")


@new_app.command("card")
def new_card(
    kind: _CardKind = typer.Argument(..., help="卡片种类"),
    card_id: str = typer.Argument(..., help="卡片 id（文件名 = id；note 卡 id = bib key）"),
    project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录"),
) -> None:
    """按模板新建空白元数据卡片（status: draft，人填写后人审）。"""
    from weft.scaffold import (
        NewCollisionError,
        NewNameError,
        plan_new_card,
        render_card_template,
    )

    project, _ = load_project(project_dir)
    try:
        target = plan_new_card(project.root, project.card_paths.keys(), kind.value, card_id)
    except NewNameError as exc:
        _print_diagnostics([Diagnostic(Level.ERROR, "E-NEW-NAME", ".", None, str(exc))])
        raise typer.Exit(code=1) from exc
    except NewCollisionError as exc:
        _print_diagnostics([Diagnostic(
            Level.ERROR, "E-NEW-COLLISION", exc.rel or ".", None, str(exc))])
        raise typer.Exit(code=1) from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_card_template(kind.value, card_id), encoding="utf-8", newline="\n")
    typer.echo(f"已创建 {target.relative_to(project.root).as_posix()}")
    typer.echo("下一步：填写字段后 weft validate 检查，approved 进入生成闸门")
```

注意：`project` 的 `part_paths`/`card_paths` 是 dict；`plan_*` 内部 `set()` 化。`weft new` 不做全项目校验闸门（设计 N8），既有 load 诊断忽略。

- [ ] **Step 4: 跑测试确认通过**（全文件绿）。注意 `test_cli_new_card_fact_stub_yields_one_eparse` 依赖 E-PARSE 的 `field == "data"`——loader `_load_card` 的 field 取自 ValidationError 首错 loc，`data` 缺项时 loc 为 `("data",)`，断言成立。

- [ ] **Step 5: 提交** `git commit -am "feat: weft new part/card 命令组——模板化创建空白叙事与卡片（E-NEW-NAME/E-NEW-COLLISION）"`。

---

## Task 4: 防漂移守卫 + 文档回填

**Files:**
- Test: `tests/test_new_cmd.py`（追加 1 个守卫）
- Modify: `AGENTS.md`、`docs/roadmap.md`、`manual.md`（如存在）、本计划（计数回填）

- [ ] **Step 1: 追加守卫测试**（卡片目录映射与 writer 单一来源对齐，防两处漂移）：

```python
def test_card_kind_dirs_match_writer():
    from weft.store.writer import card_relpath

    samples = {
        "data": DataCard(id="x", status="draft"),
        "fact": FactCard(id="x", status="draft", data=["data-01"], statement="s"),
        "claim": ClaimCard(id="x", status="draft", claim_type="uncited", statement="s"),
        "note": NoteCard(id="x", status="draft"),
        "method": MethodCard(id="x", status="draft", statement="s", protocol="p"),
        "param": ParamCard(id="x", status="draft", method="m"),
    }
    for kind, card in samples.items():
        assert card_relpath(card) == f"{CARD_KIND_DIRS[kind]}/x.md"
```

（头部补 `from weft.models.cards import ClaimCard, DataCard, FactCard, MethodCard, NoteCard, ParamCard`。）

- [ ] **Step 2: AGENTS.md 回填**：红线 5 诊断码总表追加 `2026-10-10-weft-new-template-design.md`（E-NEW-NAME / E-NEW-COLLISION）；常用命令行更新 CLI 命令清单加 `new`；测试计数更新。

- [ ] **Step 3: roadmap.md M4 增补一行**（weft new ✅）。

- [ ] **Step 4: manual.md 增补 `weft new` 用法小节**（若文件存在；不存在则跳过并在计划标注）。

- [ ] **Step 5: 全量回归**：`.venv/Scripts/python.exe -m pytest tests -q`，全绿后把精确计数回填本计划"基线"段（预期 556 + 新增）。

- [ ] **Step 6: 提交** `git commit -am "docs: weft new 诊断码进表（AGENTS 红线 5）+ roadmap M4 + manual 用法 + 计划计数回填"`。

---

## Task 5: 合回 main

- [ ] 主仓 `git merge weft-new-template`（--no-ff 或快进视历史偏好，仓库惯例为快进式中文提交，直接 merge 即可）。
- [ ] `git worktree remove .worktrees/weft-new-template && git branch -d weft-new-template`。
- [ ] 主仓全量 `pytest tests -q` 确认 556+N passed。
- [ ] `git push`。

## 执行期决策回填

| # | 偏离/发现 | 处置 |
|---|---|---|
| E1 | Task 1 的 scaffold 整文件重写把 Task 2 规划纯函数一并落地，Task 2 的红灯步骤被合并 | 测试先于验证补齐即绿；提交拆分保留（3aa986c / 5b05851） |
| E2 | note 桩并非"无新增错误"：校验层 `E-NOTE-NOT-IN-BIB` 要求 note id 已在 bib | 并入"待填指路"错误（共三类：fact E-PARSE / param E-DANGLING-REF / note E-NOTE-NOT-IN-BIB），spec N6 与测试策略、模板注释、manual 同步修订 |
| E3 | part 自动 id 是**全局** sec-NN 编号，文件名是**章节内** part-NN 编号；新章节首 part 的 id 通常非 sec-01 | 行为符合设计 N3，测试断言据此修正（CLI 用例改断言 sec-02） |
| E4 | 主仓 venv editable 安装指向主仓 src，worktree 测试需 `PYTHONPATH=<worktree>/src` 前缀执行 | 全程按此约定跑 worktree 测试；Task 0 操作约定已写明 |
| E5 | 手册实际路径为 `docs/manual.md`（commit 43e0176 所述 manual.md 在 docs/ 下） | Task 4 Step 4 按 `docs/manual.md` 执行 |
