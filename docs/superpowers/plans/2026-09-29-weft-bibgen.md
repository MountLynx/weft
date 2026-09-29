# weft bibgen 实施计划——可选的 bib 自动生成与维护路径

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** managed 模式下 `assets/references.bib` 成为派生快照：真源 = `metadata/notes/` 中 `status: approved` 且带 `entry` 书目字段的 note 卡；`weft bib sync` 确定性渲染 + WebUI 批准即同步 + AI 提案草稿卡，演示全链路无需 Zotero。

**Architecture:** 纯确定性渲染器 `src/weft/bibgen.py`（同输入→字节级同输出，全量原子重写、key 排序、静态头注释）；schema 走红线 2 加法演进（NoteCard 可选 `entry`，新文件 `models/bib.py`）；读取接口零变化（loader 仍从 `_quarto.yml` 正则提 key）。设计定案见 `docs/superpowers/specs/2026-09-29-weft-bibgen-design.md`（决策 B1–B8）。

**Tech Stack:** Python 3.11+ / pydantic v2（`extra="forbid"`）/ typer / FastAPI+Jinja2 / pytest。无新依赖。

**基线计数：391 passed, 2 deselected**（worktree 实测；主检出 392 含 1 个未提交测试，见 P-D6）。本计划完成后预期（worktree）：**464 passed, 2 deselected**。

**执行约定：**
- 在 git worktree `.worktrees/bibgen` 中开发（superpowers:using-git-worktrees），合回 main 后删除。
- 测试命令：`.venv/Scripts/python.exe -m pytest tests -q`；聚焦：`... -v tests/test_xxx.py::test_yyy`。
- 每任务：先写失败测试 → 跑红 → 最小实现 → 跑绿 → 全量回归 → 中文 conventional commit（只 add 本任务文件；主检出的进行中改动 workflow.py / tests/test_workflow.py / examples/paper-demo/metadata/data/data-01.md / docs/manual.md 不在 worktree 内，无卷入风险）。
- 生成文件固定 LF。

## 任务与计数总览（worktree 实际数字，P-D6/P-D7 勘误后）

| 任务 | 内容 | 新增测试 | 累计 passed |
|---|---|---|---|
| T1 | `models/bib.py` + NoteCard.entry | 5 | 396 |
| T2 | loader/Project：bib_files / bib_managed / bib_cfg_error | 7（4 计划 + 3 审查补） | 403 |
| T3 | `bibgen.py` 渲染器 + key minting | 13（8 计划 + 5 审查补） | 416 |
| T4 | validate：E-BIB-SHAPE / W-BIB-ETYPE / W-BIB-STALE / E-NOTE-NOT-IN-BIB managed 语义 | 10（9 计划 + 1 审查补） | 426 |
| T5 | scaffold init 模板 `bib: managed: false` | 1 | 427 |
| T6 | CLI `weft bib sync [--check]` | 9（5 计划 + 4 审查补） | 436 |
| T7 | WebUI：note 表单 entry 字段 + 批准/编辑后自动同步 | 11（5 计划 + 6 审查补；1 旧测试契约改写不增减） | 447 |
| T8 | engine `bib_propose.py` + ScriptedLLMClient 分支 | 5 | 452 |
| T9 | WebUI AI 提案路由 + 模板 | 5 | 457 |
| T10 | parse 文献模式 entry 提取联动 | 5 | 462 |
| T11 | paper-demo 转 managed | 2 | 464 |
| T12 | AGENTS.md / roadmap 登记（诊断码总表、红线 4、必读清单） | 0 | 464 |

## 设计决策（计划期定案，执行期偏离继续回填此处）

| # | 决策 |
|---|---|
| P-D1 | spec §9 设想"CLI review 与 WebUI 共用批准函数"；实际 `weft review` 只列出不批准，唯一 weft 经手的写路径是 WebUI `card_review`/`card_edit_post`（共用 `store.writer.save_card`）。同步钩子挂这两个路由的 `kind == "note"` 分支；手改文件靠 `W-BIB-STALE` + `weft bib sync`。 |
| P-D2 | note 表单 entry 用单个 `yaml_map` 控件（完全沿用 `param.values` 模式），不铺 12 个字段控件；`form_to_meta` 特例：空映射 → `entry=None`。 |
| P-D3 | bibgen 复用 loader 的 key 提取正则：`from weft.store.loader import _BIB_ENTRY, _BIB_IGNORED`（weft→store 单向，无环；不复制正则）。 |
| P-D4 | YAML 1.1 陷阱：`yes/on/true` 裸写都会解析成布尔，`bib.managed` 非布尔测试用 `1` 构造。 |
| P-D5 | spec §4 示例 `author: [Smith, Jane, Lee, Kyung]` 未加引号会被 YAML 拆成 4 项——实现与测试一律用 `["Smith, Jane", "Lee, Kyung"]` 引号形式（spec 笔误，实现不随；spec 后续修订时更正示例）。 |
| P-D6 | 计数基线勘误（T1 质量审查）：计划写基线 392，含主检出**未提交**的 `test_prompt_core_manuscript_language_is_english`；worktree（干净 HEAD）实测基线 **391 passed, 2 deselected**。worktree 内各任务累计验收 = 总览表数字 **−1**（T1=396 … T11=445）；合回主检出后即计划数字（446）。另：T1 审查补齐 spec §11 承诺的 year str/int 双收与缺 title 断言（加强既有测试，不增计数）。 |
| P-D7 | T2 质量审查三项登记：① 计划 Step 3 代码自带 bug——未知键 `sorted(set(...))` 撞混合类型 YAML 键（如 `{1: x, wat: y}`）抛 TypeError 违反红线 3，改为 `sorted(str(k) for k in ...)` 并补回归测试（计划文本的偏离，正当）；② `bib_cfg_error` 无条件转 E-BIB-SHAPE——unmanaged 项目 bib 段有未知键也报（spec §7 表述只提 managed，此处更宽是有意的：拼写错误无论如何都该看见）；③ `bib_files` 过滤空白项但**不**去首尾空格——保持 Quarto 对 bibliography 的字面语义，与既有 key 提取循环一致。补 3 个分支测试（非 dict bib / 空白项过滤 / 混合类型键），总览表计数已同步更新。 |
| P-D8 | T3 计划文本与审查加固登记：① 计划 Step 3 `render_bib` 连接公式与自家 golden 矛盾（BIB_HEADER 自带结尾换行），以 golden 为准改为 `BIB_HEADER + "\n" + "\n\n".join(blocks) + "\n"`；② 质量审查补 4 道加固：零字段条目（title/year 为空串，schema 合法）渲染畸形 bib → `BibValueError`；fields 逃生舱与标准字段重名 → `BibValueError`（拒绝而非静默）；空白题名 `key_base_from_entry` IndexError → `(split() or [""])[0]`；写盘失败清理 `.tmp` 残留。③ `bib_is_stale` docstring 引用的 E-BIB-MISSING 真实存在（loader v1 代码），审查者误报，不改；`managed_target` 空 `bib_files` 不设防（所有调用方先查形状，T4/T6/T7 一致）。补 5 个测试，总览表计数同步。 |
| P-D9 | T4 质量审查 Critical 登记：计划 Step 3 自带缺陷——`_check_bib_managed` 直调 `bib_is_stale` 会把 `BibValueError`（approved 卡花括号不平衡，schema 合法、loader 正常）裸抛给所有 validate 消费方（validate/graph/draft/assemble/serve 全崩），使 spec §8"W-BIB-STALE 可见"承诺不可达。修复：try/except 转 `E-BIB-VALUE` ERROR 诊断（path=bib 文件、field=entry）——E-BIB-VALUE 由此获得第二个发射点（validate 侧，与渲染器侧同码）。补 1 回归测试；形状错时仍跳过 stale 检查（if/else 语义不变）；unmanaged hint 缺席与两文件无 STALE 各加锁断言。 |
| P-D10 | T6 质量审查登记（计划级缺口）：① **bootstrap 缺口**——managed 项目 bib 文件不存在时，loader 的 E-BIB-MISSING（v1 语义）把 `weft bib sync` 挡在 load 闸，"生成文件的命令不能创建文件"；修复：load 后对 managed 项目豁免指向声明 bib 文件的 E-BIB-MISSING（sync 负责创建；T7 WebUI 直调 sync_bib 本就无此闸，CLI 对齐后分叉消除）；② CLI 形状闸补 `bib_cfg_error` 分支（与 validate 的 E-BIB-SHAPE 覆盖对齐，未知键在 sync 时也拦）；③ 补 3 测试（缺文件引导/两文件形状/cfg 拼写错误）。诊断构造 rules.py 与 cli.py 各一份维持现状（YAGNI，第三个发射点出现再提取）。④ 实现者补充（已裁定保留）：①使 `--check` 遇缺失文件裸抛 FileNotFoundError——check 分支加守卫：目标缺失 → E-BIB-MISSING 干净退 1（check 不负责创建，与 `bib_is_stale` 缺失≠stale 语义闭环）+ 1 回归测试。 |
| P-D11 | T7 执行与审查登记：① 计划测试代码两处笔误修正（获批）：URL kind 段是单数 `note`（计划写 `notes` 必 404）；bib_error 触发改为 draft 落盘→批准动作（approved 直落坏值会被 T4 的 E-BIB-VALUE 判项目不可用 404，原写法到不了路由）。② 质量审查 Critical 处置——bib_error 横幅是 UI 死胡同（approved 坏值落盘后全站 404），**E-BIB-VALUE 前置为落盘前拒绝**：`_entry_value_error` 预检（dataclasses.replace 假设态渲染）在 review 400 拒绝 / edit/new 转表单字段错误；spec §8"批准失败不回滚"语义保持成立（无需回滚——什么都没落盘）；bib_error 旗标降级为纯防御路径（实测正常流不可达）。③ 审查缺口修补：`card_new_post` 新建即批准（note+approved）补同步钩子（draft/rejected 新建不挂——本就不在 bib）；`_sync_managed_bib` 捕获扩至 OSError/UnicodeDecodeError；banner 文案泛化+`&lt;id&gt;` 转义+`banner success` 绿色变体（webui.css 组件层）+entry 单元格 pre-wrap。④ 补 6 测试；1 旧测试（bib_error 旗标）契约改写为 400 预检契约。 |

---

### Task 1: schema 演进——`models/bib.py` + NoteCard.entry

**Files:**
- Create: `src/weft/models/bib.py`
- Modify: `src/weft/models/cards.py`（NoteCard，L43-48）
- Test: `tests/test_models_cards.py`

- [ ] **Step 1: 写失败测试**（追加到 `tests/test_models_cards.py` 末尾；该文件现有 import 若无 `ValidationError`/`pytest` 则补 `import pytest` 与 `from pydantic import ValidationError`）

```python
from weft.models.bib import BIB_TYPES, BibEntryFields


def test_note_card_without_entry_loads():
    """向后兼容：旧 note 卡不含 entry 照常加载（红线 2 加法演进）。"""
    card = NoteCard.model_validate({"id": "k1", "status": "approved"})
    assert card.entry is None


def test_note_card_entry_roundtrip():
    card = NoteCard.model_validate({
        "id": "k1", "status": "approved",
        "entry": {"type": "article", "title": "T",
                  "author": ["Smith, Jane", "Lee, Kyung"],
                  "year": 2020, "journal": "J", "volume": "12"},
    })
    assert card.entry.title == "T"
    assert card.entry.year == 2020
    assert card.entry.author == ["Smith, Jane", "Lee, Kyung"]


def test_note_card_entry_forbids_unknown_field():
    with pytest.raises(ValidationError):
        NoteCard.model_validate({
            "id": "k1", "status": "approved",
            "entry": {"title": "T", "year": 2020, "wat": 1}})


def test_note_card_entry_requires_title_and_year():
    with pytest.raises(ValidationError):
        NoteCard.model_validate({
            "id": "k1", "status": "approved", "entry": {"title": "T"}})


def test_bib_types_vocab():
    assert {"article", "book", "inproceedings", "misc"} <= BIB_TYPES
```

- [ ] **Step 2: 跑红** — `.venv/Scripts/python.exe -m pytest tests/test_models_cards.py -q`，预期 5 个新测试 FAIL（`ModuleNotFoundError: weft.models.bib`）

- [ ] **Step 3: 实现** — 新建 `src/weft/models/bib.py`：

```python
"""书目字段模型（bibgen 设计 §4，红线 2 加法演进登记处）。

NoteCard.entry 可选嵌套：managed 模式下已批准 note 卡是 bib 的真源
（spec 2026-09-29-weft-bibgen §2）。加法演进：旧卡不含 entry 照常加载，无需数据迁移。
"""
from pydantic import BaseModel, ConfigDict

BIB_TYPES = frozenset({
    "article", "book", "inproceedings", "incollection", "phdthesis",
    "mastersthesis", "techreport", "manual", "misc", "online", "unpublished",
})


class BibEntryFields(BaseModel):
    """BibTeX 条目书目字段；必填仅 title/year，缺省字段渲染时跳过。"""

    model_config = ConfigDict(extra="forbid")

    type: str = "article"
    title: str
    author: list[str] = []
    year: str | int
    journal: str | None = None
    booktitle: str | None = None
    publisher: str | None = None
    volume: str | None = None
    number: str | None = None
    pages: str | None = None
    doi: str | None = None
    url: str | None = None
    fields: dict[str, str] = {}   # 逃生舱：其余 BibTeX 字段原样透传
```

`src/weft/models/cards.py`：顶部加 `from weft.models.bib import BibEntryFields`，NoteCard 改为：

```python
class NoteCard(_Card):
    """note 卡：id = bib key。summary 缺省容忍，由校验层提醒。

    entry（bibgen）：可选书目字段；managed 模式下 approved + entry 进 bib。
    """

    summary: str = ""
    pdf: str | None = None
    entry: BibEntryFields | None = None
```

- [ ] **Step 4: 跑绿 + 全量回归** — `pytest tests/test_models_cards.py -q` 全 PASS；`pytest tests -q` 预期 **397 passed, 2 deselected**

- [ ] **Step 5: Commit**

```bash
git add src/weft/models/bib.py src/weft/models/cards.py tests/test_models_cards.py
git commit -m "feat: note 卡可选 entry 书目字段（bibgen 红线 2 加法演进，设计 §4）"
```

---

### Task 2: loader/Project——bib_files / bib_managed / bib_cfg_error

**Files:**
- Modify: `src/weft/store/project.py`（Project dataclass，L28 附近）
- Modify: `src/weft/store/loader.py`（`_load_config`，L244-272 之后追加）
- Test: `tests/test_store_config.py`

- [ ] **Step 1: 写失败测试**（追加到 `tests/test_store_config.py`）

```python
def test_bib_managed_flag_and_files_loaded(tmp_path):
    make_minimal_project(tmp_path)
    write_yaml(tmp_path / "weft.yaml", {"bib": {"managed": True}})
    project, diagnostics = load_project(tmp_path)
    assert not any(d.is_error for d in diagnostics)
    assert project.bib_managed is True
    assert project.bib_cfg_error is None
    assert project.bib_files == ["references.bib"]


def test_bib_files_loaded_without_weft_yaml(tmp_path):
    make_minimal_project(tmp_path)
    project, _ = load_project(tmp_path)
    assert project.bib_managed is False
    assert project.bib_cfg_error is None
    assert project.bib_files == ["references.bib"]


def test_bib_unknown_key_reports_cfg_error(tmp_path):
    make_minimal_project(tmp_path)
    write_yaml(tmp_path / "weft.yaml", {"bib": {"managed": True, "wat": 1}})
    project, _ = load_project(tmp_path)
    assert project.bib_managed is True          # 已知键仍生效
    assert project.bib_cfg_error is not None and "wat" in project.bib_cfg_error


def test_bib_managed_non_bool_reports_cfg_error(tmp_path):
    make_minimal_project(tmp_path)
    write_yaml(tmp_path / "weft.yaml", {"bib": {"managed": 1}})   # P-D4：避开 yes/on 布尔陷阱
    project, _ = load_project(tmp_path)
    assert project.bib_managed is False
    assert project.bib_cfg_error is not None
```

- [ ] **Step 2: 跑红** — `pytest tests/test_store_config.py -q`，4 个新测试 FAIL（`Project` 无该属性）

- [ ] **Step 3: 实现** — `src/weft/store/project.py` 在 `bib_keys` 行后加：

```python
    bib_files: list[str] = field(default_factory=list)  # _quarto.yml bibliography 声明（bibgen）
    bib_managed: bool = False         # weft.yaml bib.managed（bibgen 设计 §3）
    bib_cfg_error: str | None = None  # bib 段形状错误（validate 转 E-BIB-SHAPE）
```

`src/weft/store/loader.py` 的 `_load_config` 末尾（`for match in _BIB_ENTRY...` 循环之后）追加：

```python
    project.bib_files = [b for b in bib_files if b.strip()]

    bib_cfg = weft_cfg.get("bib")
    if bib_cfg is None:
        bib_cfg = {}
    if not isinstance(bib_cfg, dict):
        project.bib_cfg_error = "bib 段必须是映射"
    else:
        managed = bib_cfg.get("managed", False)
        if not isinstance(managed, bool):
            project.bib_cfg_error = "bib.managed 必须是布尔值"
        else:
            project.bib_managed = managed
            unknown = sorted(set(bib_cfg) - {"managed"})
            if unknown:
                project.bib_cfg_error = f"bib 段未知键：{unknown}"
```

- [ ] **Step 4: 跑绿 + 回归** — 预期 **401 passed, 2 deselected**

- [ ] **Step 5: Commit**

```bash
git add src/weft/store/project.py src/weft/store/loader.py tests/test_store_config.py
git commit -m "feat: loader 读取 bib.managed 配置与 bibliography 文件列表（bibgen 设计 §3）"
```

---

### Task 3: 渲染器 `src/weft/bibgen.py`（确定性 + 原子写 + key minting）

**Files:**
- Create: `src/weft/bibgen.py`
- Test: `tests/test_bibgen.py`（新建）

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_bibgen.py`：

```python
"""bibgen 单测：确定性渲染（bibgen 设计 §5）+ key minting（§6）。"""
import pytest

from tests.helpers import build_project
from weft import bibgen
from weft.models.cards import NoteCard

EXPECTED = """\
% ----------------------------------------------------------
% 此文件由 weft 自动生成（weft.yaml: bib.managed = true）。
% 真源：metadata/notes/ 中 status: approved 且带 entry 的文献卡。
% 请勿手改——手改内容会在下次同步时丢失。新增文献请建文献卡。
% ----------------------------------------------------------

@article{smith2020,
  title = {Thermally activated catalysis},
  author = {Smith, Jane and Lee, Kyung},
  year = {2020},
  journal = {Journal of Thermal Chemistry},
  volume = {12},
  pages = {45--58}
}

@misc{x2021,
  title = {X},
  year = {2021},
  note = {预印本}
}
"""


def _note(nid, status="approved", entry=None):
    meta = {"id": nid, "status": status}
    if entry is not None:
        meta["entry"] = entry
    return NoteCard.model_validate(meta)


def test_render_bib_golden_sorted_deterministic():
    project = build_project(notes=[
        _note("x2021", entry={"type": "misc", "title": "X", "year": 2021,
                              "fields": {"note": "预印本"}}),
        _note("smith2020", entry={
            "type": "article", "title": "Thermally activated catalysis",
            "author": ["Smith, Jane", "Lee, Kyung"], "year": 2020,
            "journal": "Journal of Thermal Chemistry", "volume": "12",
            "pages": "45--58"}),
    ])
    assert bibgen.render_bib(project) == EXPECTED
    assert bibgen.render_bib(project) == bibgen.render_bib(project)


def test_render_bib_excludes_draft_rejected_entryless():
    project = build_project(notes=[
        _note("a2020", entry={"title": "A", "year": 2020}),
        _note("b2020", status="draft", entry={"title": "B", "year": 2020}),
        _note("c2020", status="rejected", entry={"title": "C", "year": 2020}),
        _note("d2020"),
    ])
    text = bibgen.render_bib(project)
    assert "a2020" in text
    for key in ("b2020", "c2020", "d2020"):
        assert key not in text


def test_render_entry_skips_empty_fields():
    project = build_project(notes=[
        _note("a2020", entry={"title": "A", "year": 2020, "doi": "", "author": []}),
    ])
    text = bibgen.render_bib(project)
    assert "doi" not in text and "author" not in text


def _project_with_bib_file(tmp_path, notes, bib_text=""):
    project = build_project(root=tmp_path, notes=notes)
    project.bib_files = ["references.bib"]
    (tmp_path / "references.bib").write_text(bib_text, encoding="utf-8")
    return project


def test_sync_bib_stats_and_write(tmp_path):
    project = _project_with_bib_file(
        tmp_path, [_note("a2020", entry={"title": "A", "year": 2020})],
        bib_text="@article{old1999,\n  title = {O},\n  year = {1999},\n}\n")
    target, stats = bibgen.sync_bib(project)
    assert target.name == "references.bib"
    assert stats == {"added": 1, "removed": 1, "total": 1}
    content = target.read_text(encoding="utf-8")
    assert content == bibgen.render_bib(project)
    assert "\r\n" not in content and content.startswith("%")


def test_sync_bib_idempotent(tmp_path):
    project = _project_with_bib_file(
        tmp_path, [_note("a2020", entry={"title": "A", "year": 2020})])
    _, first = bibgen.sync_bib(project)
    before = (tmp_path / "references.bib").read_text(encoding="utf-8")
    _, second = bibgen.sync_bib(project)
    assert second == {"added": 0, "removed": 0, "total": 1}
    assert (tmp_path / "references.bib").read_text(encoding="utf-8") == before


def test_sync_bib_brace_error_writes_nothing(tmp_path):
    project = _project_with_bib_file(
        tmp_path, [_note("a2020", entry={"title": "{T", "year": 2020})],
        bib_text="@article{old1999,\n  title = {O},\n  year = {1999},\n}\n")
    with pytest.raises(bibgen.BibValueError):
        bibgen.sync_bib(project)
    assert "old1999" in (tmp_path / "references.bib").read_text(encoding="utf-8")


def test_draft_key_suffixes():
    used = {"smith2020"}
    assert bibgen.draft_key("smith2020", used) == "smith2020a"
    assert bibgen.draft_key("smith2020", used) == "smith2020b"
    assert bibgen.draft_key("fresh2020", used) == "fresh2020"


def test_key_base_from_entry():
    from weft.models.bib import BibEntryFields
    assert bibgen.key_base_from_entry(BibEntryFields.model_validate(
        {"title": "Ignored", "author": ["Smith, Jane"], "year": 2020})) == "smith2020"
    assert bibgen.key_base_from_entry(BibEntryFields.model_validate(
        {"title": "Thermally activated", "year": 2020})) == "thermally2020"
```

- [ ] **Step 2: 跑红** — `pytest tests/test_bibgen.py -q`，8 个 FAIL（`No module named weft.bibgen`）

- [ ] **Step 3: 实现** — 新建 `src/weft/bibgen.py`：

```python
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
    return BIB_HEADER + "\n\n".join(blocks) + "\n"


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
```

- [ ] **Step 4: 跑绿 + 回归** — 预期 **409 passed, 2 deselected**

- [ ] **Step 5: Commit**

```bash
git add src/weft/bibgen.py tests/test_bibgen.py
git commit -m "feat: bibgen 确定性渲染器——approved 文献卡→bib 全量原子重写（设计 §5-§6）"
```

---

### Task 4: validate 规则与 managed 语义

**Files:**
- Modify: `src/weft/validation/rules.py`
- Modify: `tests/helpers.py`（加 `make_managed_project`）
- Test: `tests/test_validation_bib.py`（新建）

- [ ] **Step 1: 写失败测试** — `tests/helpers.py` 末尾追加：

```python
NOTE_ENTRY = {"type": "article", "title": "T", "author": ["A, B"], "year": 2020,
              "journal": "J", "volume": "1"}


def make_managed_project(root: Path) -> Path:
    """make_minimal_project + bib.managed: true + note key2020 带 entry（bibgen 测试用）。"""
    make_minimal_project(root)
    write_yaml(root / "weft.yaml", {"bib": {"managed": True}})
    write_card(root / "metadata" / "notes", "key2020",
               {"id": "key2020", "summary": "文献概括。", "status": "approved",
                "entry": NOTE_ENTRY})
    return root
```

新建 `tests/test_validation_bib.py`：

```python
"""managed 模式校验：E-BIB-SHAPE / W-BIB-ETYPE / W-BIB-STALE / E-NOTE-NOT-IN-BIB 语义。"""
from weft import bibgen
from weft.store.loader import load_project
from tests.helpers import make_managed_project, make_minimal_project, write_card, write_yaml
from weft.validation import validate_project


def _managed_fresh(root):
    make_managed_project(root)
    project, _ = load_project(root)
    (root / "references.bib").write_text(bibgen.render_bib(project), encoding="utf-8")
    project, _ = load_project(root)
    return project


def test_managed_fresh_no_bib_diagnostics(tmp_path):
    project = _managed_fresh(tmp_path)
    codes = {d.code for d in validate_project(project)}
    assert not codes & {"E-BIB-SHAPE", "W-BIB-STALE", "W-BIB-ETYPE"}


def test_managed_two_bib_files_shape_error(tmp_path):
    project = _managed_fresh(tmp_path)
    (tmp_path / "manual.bib").write_text("@article{x1,\n title = {X},\n year = {1},\n}\n",
                                         encoding="utf-8")
    write_yaml(tmp_path / "_quarto.yml",
               {"project": {"type": "default"},
                "bibliography": ["references.bib", "manual.bib"]})
    project, _ = load_project(tmp_path)
    assert any(d.code == "E-BIB-SHAPE" for d in validate_project(project))


def test_bib_cfg_error_shape(tmp_path):
    make_managed_project(tmp_path)
    write_yaml(tmp_path / "weft.yaml", {"bib": {"wat": 1}})
    project, _ = load_project(tmp_path)
    assert any(d.code == "E-BIB-SHAPE" and d.path == "weft.yaml"
               for d in validate_project(project))


def test_etype_warning(tmp_path):
    project = _managed_fresh(tmp_path)
    write_card(tmp_path / "metadata" / "notes", "key2020",
               {"id": "key2020", "summary": "s", "status": "approved",
                "entry": {"type": "blog", "title": "T", "year": 2020}})
    project, _ = load_project(tmp_path)
    assert any(d.code == "W-BIB-ETYPE" for d in validate_project(project))


def test_etype_rejected_skipped(tmp_path):
    project = _managed_fresh(tmp_path)
    write_card(tmp_path / "metadata" / "notes", "key2020",
               {"id": "key2020", "summary": "s", "status": "rejected",
                "entry": {"type": "blog", "title": "T", "year": 2020}})
    project, _ = load_project(tmp_path)
    assert not any(d.code == "W-BIB-ETYPE" for d in validate_project(project))


def test_stale_warning(tmp_path):
    project = _managed_fresh(tmp_path)
    with open(tmp_path / "references.bib", "a", encoding="utf-8") as f:
        f.write("% 手改痕迹\n")
    assert any(d.code == "W-BIB-STALE" for d in validate_project(project))


def test_approved_note_without_entry_error(tmp_path):
    make_managed_project(tmp_path)
    write_card(tmp_path / "metadata" / "notes", "key2020",
               {"id": "key2020", "summary": "s", "status": "approved"})
    project, _ = load_project(tmp_path)
    # 先按当前卡渲染（无 entry → bib 里没有 key2020），再校验
    (tmp_path / "references.bib").write_text(bibgen.render_bib(project), encoding="utf-8")
    project, _ = load_project(tmp_path)
    diags = [d for d in validate_project(project) if d.code == "E-NOTE-NOT-IN-BIB"]
    assert len(diags) == 1 and "entry" in diags[0].message


def test_draft_note_exempt_in_managed(tmp_path):
    project = _managed_fresh(tmp_path)
    write_card(tmp_path / "metadata" / "notes", "new2021",
               {"id": "new2021", "summary": "s", "status": "draft"})
    project, _ = load_project(tmp_path)
    assert not any(d.code == "E-NOTE-NOT-IN-BIB" for d in validate_project(project))


def test_unmanaged_draft_note_still_checked(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "notes", "new2021",
               {"id": "new2021", "summary": "s", "status": "draft"})
    project, _ = load_project(tmp_path)
    assert any(d.code == "E-NOTE-NOT-IN-BIB" and d.path.endswith("new2021.md")
               for d in validate_project(project))
```

- [ ] **Step 2: 跑红** — `pytest tests/test_validation_bib.py -q`，9 个 FAIL（无 bib 诊断 / helper 缺失）

- [ ] **Step 3: 实现** — `src/weft/validation/rules.py`：

顶部 import 加：

```python
from weft import bibgen
from weft.models.bib import BIB_TYPES
```

`_check_notes_in_bib`（L85-92）整体替换为：

```python
def _check_notes_in_bib(project: Project) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for nid, note in project.notes.items():
        if project.bib_managed and note.status != "approved":
            continue  # managed：draft/rejected 豁免（未批准提案本就不在 bib，设计 §7）
        if nid not in project.bib_keys:
            hint = ("（approved 文献卡应有 entry 并已同步进 bib：缺 entry 或未跑 "
                    "weft bib sync）" if project.bib_managed else "")
            out.append(Diagnostic(Level.ERROR, "E-NOTE-NOT-IN-BIB",
                                  _card_rel(project, nid), "id",
                                  f"note 的 id（bib key）不在 bib 中：{nid}{hint}"))
    return out
```

新增（放在 `_check_notes_in_bib` 之后）：

```python
def _check_bib_managed(project: Project) -> list[Diagnostic]:
    """bibgen 设计 §7：managed 形状 / 过期 / 词表提醒。unmanaged 项目零变化。"""
    out: list[Diagnostic] = []
    if project.bib_cfg_error:
        out.append(Diagnostic(Level.ERROR, "E-BIB-SHAPE", "weft.yaml", "bib",
                              project.bib_cfg_error))
    if project.bib_managed:
        if len(project.bib_files) != 1:
            out.append(Diagnostic(
                Level.ERROR, "E-BIB-SHAPE", "_quarto.yml", "bibliography",
                "managed 项目 bibliography 必须恰好指向一个文件（生成目标）"))
        elif bibgen.bib_is_stale(project):
            out.append(Diagnostic(
                Level.WARNING, "W-BIB-STALE", project.bib_files[0], None,
                "bib 文件与已批准文献卡不一致（运行 weft bib sync）"))
    for nid, note in project.notes.items():
        if note.status == "rejected" or note.entry is None:
            continue
        if note.entry.type not in BIB_TYPES:
            out.append(Diagnostic(
                Level.WARNING, "W-BIB-ETYPE", _card_rel(project, nid), "entry.type",
                f"entry.type 不在受控词表 {sorted(BIB_TYPES)}：{note.entry.type}"))
    return out
```

`validate_project` 中 `diagnostics += _check_notes_in_bib(project)` 之后插入一行：

```python
    diagnostics += _check_bib_managed(project)
```

- [ ] **Step 4: 跑绿 + 回归** — 预期 **418 passed, 2 deselected**（若 `test_validation_warnings/errors` 有既有 E-NOTE-NOT-IN-BIB 断言受 hint 文案影响，按新文案更新断言字符串）

- [ ] **Step 5: Commit**

```bash
git add src/weft/validation/rules.py tests/helpers.py tests/test_validation_bib.py
git commit -m "feat: managed bib 校验——E-BIB-SHAPE/W-BIB-STALE/W-BIB-ETYPE 与 note 语义微调（设计 §7）"
```

---

### Task 5: scaffold init 模板

**Files:**
- Modify: `src/weft/scaffold.py`（`_WEFT_YAML`，L33-38）
- Test: `tests/test_scaffold.py`

- [ ] **Step 1: 写失败测试**（追加到 `tests/test_scaffold.py`）

```python
def test_init_weft_yaml_declares_bib_managed_false(tmp_path):
    from weft.scaffold import init_project
    init_project(tmp_path / "p")
    text = (tmp_path / "p" / "weft.yaml").read_text(encoding="utf-8")
    assert "managed: false" in text
```

- [ ] **Step 2: 跑红** — `pytest tests/test_scaffold.py -q`，新测试 FAIL

- [ ] **Step 3: 实现** — `_WEFT_YAML` 替换为：

```python
_WEFT_YAML = """\
# weft 项目配置：全部键可省略，以下注释即默认值。
# figures_dir: figures      # 图表目录（data 卡 refs 指向其中的 Quarto label）
# assemble_mode: strict     # strict | lenient：part 拼装失败是否阻断 assemble
# paper_file: paper.qmd     # assemble 拼装产物（weft render 的渲染对象）
bib:
  managed: false            # true：assets/references.bib 由 weft 从已批准文献卡生成（勿手改）
"""
```

- [ ] **Step 4: 跑绿 + 回归** — 预期 **419 passed, 2 deselected**（init 零诊断验收测试必须仍绿：`managed: false` 合法加载）

- [ ] **Step 5: Commit**

```bash
git add src/weft/scaffold.py tests/test_scaffold.py
git commit -m "feat: init 模板显式声明 bib.managed: false（bibgen 设计 §3）"
```

---

### Task 6: CLI `weft bib sync [--check]`

**Files:**
- Modify: `src/weft/cli.py`（模块 docstring L1、`app` 定义后注册子 app、文件末尾附近新增命令）
- Test: `tests/test_cli_bib.py`（新建）

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_cli_bib.py`：

```python
"""weft bib sync（bibgen 设计 §5 CLI）。"""
from typer.testing import CliRunner

from weft import bibgen
from weft.cli import app
from weft.store.loader import load_project
from tests.helpers import make_managed_project, make_minimal_project, write_card

runner = CliRunner()


def _fresh_bib(root):
    project, _ = load_project(root)
    (root / "references.bib").write_text(bibgen.render_bib(project), encoding="utf-8")


def test_sync_rejects_unmanaged(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["bib", "sync", str(tmp_path)])
    assert result.exit_code == 1 and "bib.managed" in result.output


def test_sync_writes_managed_bib(tmp_path):
    make_managed_project(tmp_path)
    result = runner.invoke(app, ["bib", "sync", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "已写入 references.bib（1 条" in result.output
    content = (tmp_path / "references.bib").read_text(encoding="utf-8")
    assert content.startswith("%") and "@article{key2020" in content


def test_check_stale_exits_1(tmp_path):
    make_managed_project(tmp_path)
    _fresh_bib(tmp_path)
    with open(tmp_path / "references.bib", "a", encoding="utf-8") as f:
        f.write("% 手改\n")
    result = runner.invoke(app, ["bib", "sync", str(tmp_path), "--check"])
    assert result.exit_code == 1 and "W-BIB-STALE" in result.output


def test_check_fresh_exits_0(tmp_path):
    make_managed_project(tmp_path)
    _fresh_bib(tmp_path)
    result = runner.invoke(app, ["bib", "sync", str(tmp_path), "--check"])
    assert result.exit_code == 0 and "一致（1 条）" in result.output


def test_sync_value_error_exits_1_without_write(tmp_path):
    make_managed_project(tmp_path)
    write_card(tmp_path / "metadata" / "notes", "key2020",
               {"id": "key2020", "summary": "s", "status": "approved",
                "entry": {"type": "article", "title": "{T", "year": 2020}})
    before = (tmp_path / "references.bib").read_text(encoding="utf-8")
    result = runner.invoke(app, ["bib", "sync", str(tmp_path)])
    assert result.exit_code == 1 and "E-BIB-VALUE" in result.output
    assert (tmp_path / "references.bib").read_text(encoding="utf-8") == before
```

- [ ] **Step 2: 跑红** — `pytest tests/test_cli_bib.py -q`，5 个 FAIL（无 `bib` 命令）

- [ ] **Step 3: 实现** — `src/weft/cli.py`：

docstring（L1）改为：

```python
"""typer 入口：weft init / validate / graph / review / draft / assemble / render / inspire / parse / replace / missing-cites / bib / serve。"""
```

`app = typer.Typer(...)` 之后加：

```python
bib_app = typer.Typer(add_completion=False, help="bib 生成与维护（managed 模式，bibgen 设计）")
app.add_typer(bib_app, name="bib")
```

文件末尾（`missing_cites` 命令之后）加：

```python
@bib_app.command("sync")
def bib_sync(
    project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录"),
    check: bool = typer.Option(False, "--check", help="不写文件：不一致时 W-BIB-STALE 且退出 1"),
) -> None:
    """把已批准文献卡（approved + entry）渲染为 bibliography 目标文件。"""
    from weft import bibgen

    project, load_diags = load_project(project_dir)
    if any(d.is_error for d in load_diags):
        _print_diagnostics(load_diags)
        raise typer.Exit(code=1)
    if not project.bib_managed:
        typer.echo("ERROR 未启用 bib.managed（weft.yaml），本命令仅用于 managed 项目")
        raise typer.Exit(code=1)
    if len(project.bib_files) != 1:
        _print_diagnostics([Diagnostic(
            Level.ERROR, "E-BIB-SHAPE", "_quarto.yml", "bibliography",
            "managed 项目 bibliography 必须恰好指向一个文件（生成目标）")])
        raise typer.Exit(code=1)
    try:
        if check:
            if bibgen.bib_is_stale(project):
                _print_diagnostics([Diagnostic(
                    Level.WARNING, "W-BIB-STALE", project.bib_files[0], None,
                    "bib 文件与已批准文献卡不一致")])
                raise typer.Exit(code=1)
            target = bibgen.managed_target(project)
            n = len(bibgen.bib_keys_in(target.read_text(encoding="utf-8")))
            typer.echo(f"bib 与已批准文献卡一致（{n} 条）：{project.bib_files[0]}")
            return
        _, stats = bibgen.sync_bib(project)
    except bibgen.BibValueError as exc:
        _print_diagnostics([Diagnostic(
            Level.ERROR, "E-BIB-VALUE", project.bib_files[0], "entry", str(exc))])
        raise typer.Exit(code=1) from exc
    typer.echo(f"已写入 {project.bib_files[0]}"
               f"（{stats['total']} 条，+{stats['added']} / -{stats['removed']}）")
```

- [ ] **Step 4: 跑绿 + 回归** — 预期 **424 passed, 2 deselected**

- [ ] **Step 5: Commit**

```bash
git add src/weft/cli.py tests/test_cli_bib.py
git commit -m "feat: CLI weft bib sync——确定性渲染/过期自检/E-BIB-VALUE 拦截（设计 §5）"
```

---

### Task 7: WebUI——note 表单 entry 字段 + 批准/编辑后自动同步

**Files:**
- Modify: `src/weft/web/card_forms.py`（FIELD_SPECS note 行、form_to_meta、values_for_template）
- Modify: `src/weft/web/routes/cards.py`（card_detail、card_review、card_edit_post + 同步 helper）
- Modify: `src/weft/web/templates/card_detail.html`（同步结果 banner）
- Test: `tests/test_web_cards.py`

- [ ] **Step 1: 写失败测试**（追加到 `tests/test_web_cards.py`）

```python
from tests.helpers import make_managed_project

ENTRY_YAML = "type: article\ntitle: T\nauthor:\n- A, B\nyear: 2020\njournal: J\nvolume: '1'\n"


def _managed_web_client(tmp_path):
    client, root = make_client(tmp_path)
    make_managed_project(root / "demo")
    return client, root


def test_note_edit_form_shows_entry_yaml(tmp_path):
    client, _ = _managed_web_client(tmp_path)
    resp = client.get("/p/demo/cards/notes/key2020/edit")
    assert resp.status_code == 200 and 'name="entry"' in resp.text
    assert "type: article" in resp.text          # 既有 entry 以 YAML 文本回显


def test_note_edit_saves_entry(tmp_path):
    client, root = _managed_web_client(tmp_path)
    resp = client.post("/p/demo/cards/notes/key2020/edit", data={
        "summary": "s", "pdf": "", "entry": ENTRY_YAML,
        "status": "approved", "comment": ""}, follow_redirects=False)
    assert resp.status_code == 303
    project, _ = load_project(root / "demo")
    assert project.notes["key2020"].entry.title == "T"


def test_approve_note_managed_syncs_bib(tmp_path):
    client, root = _managed_web_client(tmp_path)
    resp = client.post("/p/demo/cards/notes/key2020/status",
                       data={"status": "approved", "comment": ""},
                       follow_redirects=False)
    assert resp.status_code == 303 and "bib=bib_updated" in resp.headers["location"]
    content = (root / "demo" / "references.bib").read_text(encoding="utf-8")
    assert content.startswith("%") and "@article{key2020" in content


def test_approve_note_unmanaged_no_bib_flag(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/cards/notes/key2020/status",
                       data={"status": "approved", "comment": ""},
                       follow_redirects=False)
    assert resp.status_code == 303 and "bib=" not in resp.headers["location"]


def test_approve_note_managed_bib_error_flag(tmp_path):
    client, root = _managed_web_client(tmp_path)
    write_card(root / "demo" / "metadata" / "notes", "key2020",
               {"id": "key2020", "summary": "s", "status": "approved",
                "entry": {"type": "article", "title": "{T", "year": 2020}})
    resp = client.post("/p/demo/cards/notes/key2020/status",
                       data={"status": "approved", "comment": ""},
                       follow_redirects=False)
    assert "bib=bib_error" in resp.headers["location"]
    content = (root / "demo" / "references.bib").read_text(encoding="utf-8")
    assert not content.startswith("%")       # 旧内容未被破坏
```

（文件顶部若缺 `from tests.helpers import make_managed_project, write_card` 与 `load_project` 则补；`make_client` 来自 `tests.webutil` 已在文件顶部。）

- [ ] **Step 2: 跑红** — `pytest tests/test_web_cards.py -q`，5 个新测试 FAIL

- [ ] **Step 3: 实现** —

`src/weft/web/card_forms.py`：FIELD_SPECS `"note"` 行改为：

```python
    "note": [FieldSpec("summary", "summary", "textarea"),
             FieldSpec("pdf", "pdf（文件路径，可选）", "text"),
             FieldSpec("entry", "entry（书目字段，YAML 映射；managed 批准后进 bib）", "yaml_map")],
```

`form_to_meta` 末尾（`meta["id"] = ...` 行之前）插入：

```python
    if kind == "note" and not meta.get("entry"):
        meta["entry"] = None   # 空映射 = 无书目字段（避免 BibEntryFields 必填校验误伤，P-D2）
```

`values_for_template` 中 `if kind == "param":` 块之后加：

```python
    if kind == "note" and values.get("entry"):
        values["entry"] = yaml.safe_dump(values["entry"], allow_unicode=True,
                                         sort_keys=False)
```

`src/weft/web/routes/cards.py`：顶部 import 加 `import yaml`；新增模块级 helper（`_table` 之前）：

```python
def _sync_managed_bib(project_root) -> str | None:
    """note 卡写盘后重渲 managed bib；返回重定向标记（None = unmanaged/形状不齐，P-D1）。"""
    from weft import bibgen
    from weft.store.loader import load_project

    project, _ = load_project(project_root)
    if not project.bib_managed or len(project.bib_files) != 1:
        return None
    try:
        bibgen.sync_bib(project)
    except bibgen.BibValueError:
        return "bib_error"
    return "bib_updated"
```

`card_detail` 的 context 中 `"fields": {...}` 改为（entry 以 YAML 展示）：

```python
         "fields": {k: (yaml.safe_dump(v, allow_unicode=True, sort_keys=False)
                        if k == "entry" and v else ("" if v is None else v))
                    for k, v in card.model_dump().items()
                    if k not in ("id", "status", "comment")},
         "bib_flag": request.query_params.get("bib"),
```

`card_review` 末尾 `return RedirectResponse(...)` 替换为：

```python
    url = f"/p/{pid}/cards/{kind}/{card_id}"
    if kind == "note":
        flag = _sync_managed_bib(entry.project.root)
        if flag:
            url += f"?bib={flag}"
    return RedirectResponse(url, status_code=303)
```

`card_edit_post` 末尾 `save_card(...)` 之后、`return RedirectResponse(...)` 同样替换为：

```python
    save_card(entry.project.root, card,
              old_rel=entry.project.card_paths[card_id].as_posix())
    url = f"/p/{pid}/cards/{kind}/{card_id}"
    if kind == "note":
        flag = _sync_managed_bib(entry.project.root)
        if flag:
            url += f"?bib={flag}"
    return RedirectResponse(url, status_code=303)
```

`src/weft/web/templates/card_detail.html`：`<p><code>{{ rel }}</code></p>` 之后加：

```html
{% if bib_flag == "bib_updated" %}<div class="banner">references.bib 已同步（bibgen）。</div>{% endif %}
{% if bib_flag == "bib_error" %}<div class="banner error">bib 同步失败：entry 字段值花括号不平衡（E-BIB-VALUE）；修正后再次保存/批准即重试。</div>{% endif %}
```

- [ ] **Step 4: 跑绿 + 回归** — 预期 **429 passed, 2 deselected**（`test_web_card_edit/new/pages` 若有 note 表单字段数断言，随 entry 字段更新）

- [ ] **Step 5: Commit**

```bash
git add src/weft/web/card_forms.py src/weft/web/routes/cards.py src/weft/web/templates/card_detail.html tests/test_web_cards.py
git commit -m "feat: WebUI note 表单 entry 字段与批准/编辑后 bib 自动同步（设计 §7/§9，P-D1/P-D2）"
```

---

### Task 8: engine `bib_propose.py` + ScriptedLLMClient 分支

**Files:**
- Create: `src/weft/engine/bib_propose.py`
- Modify: `src/weft/engine/clients.py`（ScriptedLLMClient 加分支）
- Test: `tests/test_bib_propose.py`（新建）

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_bib_propose.py`：

```python
"""engine bib_propose（bibgen 设计 §8 路径 1）：线索→entry 草稿卡字段，不落盘。"""
import asyncio

import pytest
from llm.client import LLMResponse

from tests.helpers import build_project
from weft.engine.bib_propose import BibProposeError, propose_note
from weft.engine.clients import ScriptedLLMClient
from weft.models.cards import NoteCard


def _project_with(*ids):
    return build_project(notes=[NoteCard.model_validate({"id": i, "status": "approved"})
                                for i in ids])


def test_propose_note_happy_path():
    project = _project_with("key2020")
    key, fields = asyncio.run(
        propose_note(project, "DOI 10.1/x；Smith 2020 热激活催化", ScriptedLLMClient()))
    assert key == "smith2020"
    assert fields["status"] == "draft"
    assert fields["entry"]["title"] == "Thermally activated catalysis"
    assert fields["entry"]["author"] == ["Smith, Jane"]
    assert "Smith 2020" in fields["comment"]


def test_propose_note_conflict_suffix():
    project = _project_with("key2020", "smith2020")
    key, _ = asyncio.run(propose_note(project, "Smith 2020", ScriptedLLMClient()))
    assert key == "smith2020a"


def test_propose_note_key_fallback_title():
    class _NoAuthorClient:
        async def complete(self, **kwargs):
            return LLMResponse(
                content='{"title": "Thermally activated catalysis", "year": 2020}',
                usage={}, finish_reason="end_turn")

    key, _ = asyncio.run(propose_note(_project_with("key2020"), "无作者的线索",
                                      _NoAuthorClient()))
    assert key == "thermally2020"


def test_propose_note_invalid_json():
    class _BadClient:
        async def complete(self, **kwargs):
            return LLMResponse(content="不是 JSON", usage={}, finish_reason="end_turn")

    with pytest.raises(BibProposeError):
        asyncio.run(propose_note(_project_with("key2020"), "x", _BadClient()))


def test_propose_note_invalid_schema():
    class _NoYearClient:
        async def complete(self, **kwargs):
            return LLMResponse(content='{"title": "T"}', usage={},
                               finish_reason="end_turn")

    with pytest.raises(BibProposeError):
        asyncio.run(propose_note(_project_with("key2020"), "x", _NoYearClient()))
```

- [ ] **Step 2: 跑红** — `pytest tests/test_bib_propose.py -q`，5 个 FAIL（`No module named weft.engine.bib_propose`）

- [ ] **Step 3: 实现** — `src/weft/engine/clients.py` 的 `ScriptedLLMClient`：类属性区（`_PARSE_MATCH` 之后）加：

```python
    _BIB_PROPOSE = json.dumps(
        {"type": "article", "title": "Thermally activated catalysis",
         "author": ["Smith, Jane"], "year": 2020,
         "journal": "Journal of Thermal Chemistry"}, ensure_ascii=False)
```

`_respond` 的 `if "【文章·成卡覆盖】" ...` 分支之后、兜底 return 之前加：

```python
        if "【文献·条目提案】" in prompt:
            return self._BIB_PROPOSE
```

新建 `src/weft/engine/bib_propose.py`：

```python
"""WebUI 文献提案（bibgen 设计 §8 路径 1）：线索 → entry 草稿卡字段。

单次 LLM 调用（引擎层，红线 1 合规）；落盘由调用方经 card_writer 白名单
写 status: draft 的 note 卡。元数据幻觉风险由人批准闸门兜底（B2）。
"""
from __future__ import annotations

import json

from weft import bibgen
from weft.engine.card_writer import all_card_ids
from weft.models.bib import BibEntryFields

_PROMPT_TEMPLATE = (
    "【文献·条目提案】\n"
    "任务：根据线索提取/拟出这条文献的 BibTeX 书目字段。\n"
    "线索（可能含 DOI、标题、作者、年份、摘要等，也可能不全）：\n{clues}\n\n"
    '输出 JSON：{{"type": "article|book|inproceedings|…", "title": "…",'
    ' "author": ["姓, 名"], "year": 2020, "journal": "…", "volume": "12",'
    ' "number": "…", "pages": "45--58", "doi": "…", "url": "…"}}。\n'
    "规则：只填有依据的字段，没有依据的省略；title 与 year 必给"
    "（实在缺失就按线索最合理拟出，人审把关）；author 每项格式“姓, 名”。"
)


class BibProposeError(Exception):
    """提案失败：LLM 输出非 JSON 或不满足 entry schema。"""


async def propose_note(project, clues: str, client) -> tuple[str, dict]:
    """返回（拟分配 key, note 卡 frontmatter 字段 dict）；不落盘。"""
    prompt = _PROMPT_TEMPLATE.format(clues=clues.strip() or "（无）")
    response = await client.complete(prompt=prompt)
    try:
        entry = BibEntryFields.model_validate(json.loads(response.content))
    except (json.JSONDecodeError, ValueError) as exc:   # ValueError 涵盖 ValidationError
        raise BibProposeError(f"条目提案输出非法（须为 entry JSON）：{exc}") from exc
    key = bibgen.draft_key(bibgen.key_base_from_entry(entry), all_card_ids(project))
    fields = {
        "id": key,
        "status": "draft",
        "summary": "",
        "entry": entry.model_dump(),
        "comment": "来源：AI 条目提案（线索：" + (clues.strip()[:40] or "无") + "…）",
    }
    return key, fields
```

- [ ] **Step 4: 跑绿 + 回归** — 预期 **434 passed, 2 deselected**（parse mock 未动，parse 测试不受影响）

- [ ] **Step 5: Commit**

```bash
git add src/weft/engine/bib_propose.py src/weft/engine/clients.py tests/test_bib_propose.py
git commit -m "feat: engine 文献条目提案——线索→entry 草稿卡字段 + key minting（设计 §8 路径 1）"
```

---

### Task 9: WebUI AI 提案路由 + 模板

**Files:**
- Modify: `src/weft/web/routes/cards.py`（import、两个路由、注册顺序注意）
- Create: `src/weft/web/templates/bib_propose.html`
- Modify: `src/weft/web/templates/cards.html`（note 列表页加入口链接）
- Test: `tests/test_web_bib_propose.py`（新建）

- [ ] **Step 1: 写失败测试** — 新建 `tests/test_web_bib_propose.py`：

```python
"""WebUI 文献提案路由（bibgen 设计 §8 路径 1）。"""
import pytest

pytest.importorskip("fastapi")

from weft.engine.clients import ScriptedLLMClient
from weft.store.loader import load_project
from tests.webutil import make_client


def _patch(monkeypatch, client_obj):
    monkeypatch.setattr("weft.web.routes.cards.make_client",
                        lambda mock, project_root=None: client_obj)


def test_propose_page_renders(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/notes/propose")
    assert resp.status_code == 200
    assert 'name="clues"' in resp.text and "draft" in resp.text


def test_propose_creates_draft_note(tmp_path, monkeypatch):
    client, root = make_client(tmp_path)
    scripted = ScriptedLLMClient()
    _patch(monkeypatch, scripted)
    resp = client.post("/p/demo/notes/propose", data={"clues": "Smith 2020 催化"},
                       follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/cards/notes/smith2020")
    assert "Smith 2020 催化" in scripted.prompts[0]     # 线索进了 prompt
    project, _ = load_project(root / "demo")
    card = project.notes["smith2020"]
    assert card.status == "draft" and card.entry.title == "Thermally activated catalysis"


def test_propose_conflict_suffix(tmp_path, monkeypatch):
    client, root = make_client(tmp_path)
    (root / "demo" / "metadata" / "notes" / "smith2020.md").write_text(
        "---\nid: smith2020\nsummary: 占位\nstatus: approved\n---\n", encoding="utf-8")
    _patch(monkeypatch, ScriptedLLMClient())
    resp = client.post("/p/demo/notes/propose", data={"clues": "Smith 2020"},
                       follow_redirects=False)
    assert resp.headers["location"].endswith("/cards/notes/smith2020a")


def test_propose_invalid_json_rerenders(tmp_path, monkeypatch):
    class _Bad:
        async def complete(self, **kwargs):
            from llm.client import LLMResponse
            return LLMResponse(content="不是 JSON", usage={}, finish_reason="end_turn")

    client, root = make_client(tmp_path)
    _patch(monkeypatch, _Bad())
    resp = client.post("/p/demo/notes/propose", data={"clues": "x"})
    assert resp.status_code == 200 and "条目提案输出非法" in resp.text
    assert not (root / "demo" / "metadata" / "notes" / "smith2020.md").exists()


def test_propose_invalid_schema_rerenders(tmp_path, monkeypatch):
    class _NoYear:
        async def complete(self, **kwargs):
            from llm.client import LLMResponse
            return LLMResponse(content='{"title": "T"}', usage={},
                               finish_reason="end_turn")

    client, root = make_client(tmp_path)
    _patch(monkeypatch, _NoYear())
    resp = client.post("/p/demo/notes/propose", data={"clues": "x"})
    assert resp.status_code == 200 and "条目提案输出非法" in resp.text
```

- [ ] **Step 2: 跑红** — `pytest tests/test_web_bib_propose.py -q`，5 个 FAIL（404）

- [ ] **Step 3: 实现** —

`src/weft/web/routes/cards.py` 顶部 import 区加：

```python
from weft.engine.bib_propose import BibProposeError, propose_note
from weft.engine.clients import make_client
```

（两个新路由插在 `card_new_post` 之后、`card_detail` 之前——`/notes/propose` 与 `/cards/{kind}/{card_id}` 前缀不同无冲突，但保持"具体路径先注册"惯例：）

```python
@router.get("/p/{pid}/notes/propose")
def bib_propose_get(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    return templates.TemplateResponse(
        request, "bib_propose.html",
        {"pid": pid, "action": f"/p/{pid}/notes/propose",
         "cancel_url": f"/p/{pid}/cards/notes", "clues": "", "error": ""})


@router.post("/p/{pid}/notes/propose")
async def bib_propose_post(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    form = await request.form()
    clues = str(form.get("clues") or "")
    client = make_client(mock=False, project_root=entry.project.root)

    def rerender(error: str):
        return templates.TemplateResponse(
            request, "bib_propose.html",
            {"pid": pid, "action": f"/p/{pid}/notes/propose",
             "cancel_url": f"/p/{pid}/cards/notes", "clues": clues, "error": error})

    try:
        key, fields = await propose_note(entry.project, clues, client)
    except BibProposeError as exc:
        return rerender(str(exc))
    from weft.engine.card_writer import write_proposed_cards
    write_proposed_cards(entry.project, [("note", fields)])
    return RedirectResponse(f"/p/{pid}/cards/notes/{key}", status_code=303)
```

新建 `src/weft/web/templates/bib_propose.html`：

```html
{% extends "base.html" %}
{% block title %}AI 提案文献{% endblock %}
{% block content %}
<h2>AI 提案文献（note 卡草稿）</h2>
{% if error %}<div class="banner error">{{ error }}</div>{% endif %}
<form method="post" action="{{ action }}">
  <label>线索（DOI / 标题 / 作者 / 年份 / 摘要，任意组合）
    <textarea name="clues" rows="6">{{ clues }}</textarea>
  </label>
  <button type="submit" class="btn-primary">生成提案草稿卡</button>
  <a href="{{ cancel_url }}">取消</a>
</form>
<p>生成结果为 status: draft 的 note 卡（含 entry 书目字段）；批准后才会进 bib（managed 项目自动同步）。</p>
{% endblock %}
```

`src/weft/web/templates/cards.html`：`<p><a href="/p/{{ entry.pid }}/cards/{{ kind }}/new">…` 行之后加：

```html
{% if kind == "notes" %}<p><a href="/p/{{ entry.pid }}/notes/propose">✨ AI 提案文献</a></p>{% endif %}
```

- [ ] **Step 4: 跑绿 + 回归** — 预期 **439 passed, 2 deselected**（`test_engine_layering` 必须仍绿：web→engine 属既有方向，engine 才是 llm 唯一入口）

- [ ] **Step 5: Commit**

```bash
git add src/weft/web/routes/cards.py src/weft/web/templates/bib_propose.html src/weft/web/templates/cards.html tests/test_web_bib_propose.py
git commit -m "feat: WebUI 文献提案路由——线索→note 草稿卡（bibgen 设计 §8 路径 1）"
```

---

### Task 10: parse 文献模式 entry 提取联动

**Files:**
- Modify: `src/weft/engine/parse/schemas.py`（ArticleExtractOutput）
- Modify: `src/weft/engine/parse/spec_build.py`（`_EXTRACT_LITERATURE_SCHEMA`）
- Modify: `src/weft/engine/parse/apply.py`（note new 分支）
- Test: `tests/test_parse_schemas.py`、`tests/test_parse_apply.py`、`tests/test_parse_spec_build.py`

- [ ] **Step 1: 写失败测试**

`tests/test_parse_schemas.py` 追加（复用该文件顶部既有 import）：

```python
from weft.engine.parse.schemas import ArticleExtractOutput


def test_extract_entry_optional_and_roundtrip():
    out = ArticleExtractOutput.model_validate({"summary": "s", "entry": {
        "type": "article", "title": "T", "year": 2020, "author": ["A, B"]}})
    assert out.entry.title == "T"
    assert ArticleExtractOutput.model_validate({"summary": "s"}).entry is None
```

`tests/test_parse_apply.py` 追加（`_source/_project/_extract/_apply/NoteReview` 均为该文件既有夹具；文件顶部需补 `import frontmatter`）：

```python
def test_apply_note_new_with_entry(tmp_path):
    from weft.models.bib import BibEntryFields
    source = _source(tmp_path)
    project = _project(tmp_path, with_note=False)
    base = _extract()
    extract = ArticleExtractOutput(
        summary=base.summary, cards=base.cards, links=base.links,
        entry=BibEntryFields(type="article", title="T", author=["A, B"], year=2020))
    _apply(project, source, note=NoteReview(verdict="new"), extract=extract)
    meta = frontmatter.load(tmp_path / "metadata" / "notes" / "key2020.md").metadata
    assert meta["entry"]["title"] == "T"
    assert meta["entry"]["author"] == ["A, B"]


def test_apply_note_new_without_entry(tmp_path):
    source = _source(tmp_path)
    project = _project(tmp_path, with_note=False)
    _apply(project, source, note=NoteReview(verdict="new"))
    meta = frontmatter.load(tmp_path / "metadata" / "notes" / "key2020.md").metadata
    assert "entry" not in meta
```

`tests/test_parse_spec_build.py` 追加：

```python
def test_literature_extract_schema_mentions_entry():
    from weft.engine.parse.spec_build import _EXTRACT_LITERATURE_SCHEMA
    assert '"entry"' in _EXTRACT_LITERATURE_SCHEMA
```

- [ ] **Step 2: 跑红** — 三个文件各自跑，新测试 FAIL（`entry` 字段不存在 / prompt 无 entry / note 无 entry）

- [ ] **Step 3: 实现** —

`src/weft/engine/parse/schemas.py`：顶部加 `from weft.models.bib import BibEntryFields`；`ArticleExtractOutput` 改为：

```python
class ArticleExtractOutput(BaseModel):
    """P2 拆解：拟建卡 + 内部连接；summary/entry 仅文献模式有值（书目字段，原文锚定）。"""

    cards: list[ArticleProposedCard] = []
    links: list[_Link] = []
    summary: str = ""
    entry: BibEntryFields | None = None
```

`src/weft/engine/parse/spec_build.py` 的 `_EXTRACT_LITERATURE_SCHEMA` 替换为：

```python
_EXTRACT_LITERATURE_SCHEMA = (
    '输出 JSON：{"summary": "结构化文献摘要（研究问题、方法、核心发现、局限；'
    '200-400 字）", "cards": [{"key": "f1/c1/…临时编号", "kind": "fact|claim",'
    ' "statement": "原子陈述", "placeholder": false, "needs_citation": true}],'
    ' "links": [{"from": "f1", "to": "c1"}],'
    ' "entry": {"type": "article|book|inproceedings|…", "title": "本文题名",'
    ' "author": ["姓, 名"], "year": 2020, "journal": "期刊名", "volume": "卷",'
    ' "number": "期", "pages": "45--58", "doi": "…"}}。'
    "规则：summary 以第三人称概括本篇文献（将作为 note 卡的摘要）；"
    "本文的数据表述→fact，本文的发现/结论/论断→claim（needs_citation 通常为 true）；"
    "\"xxx/某值\"类占位数据置 placeholder=true；links 只表达新 fact 支持新 claim；"
    "entry 从原文提取本文书目字段（题名/作者/年份/期刊卷期页/DOI），"
    "只填有依据的，title 与 year 必给，提取不到 entry 就整体省略。"
)
```

`src/weft/engine/parse/apply.py` 的 `note_review.verdict == "new"` 分支替换为：

```python
        if note_review.verdict == "new":
            note_fields = {
                "id": bib_key, "status": "draft",
                "summary": extract.summary,
                "comment": f"来源：文章 {source.name}（解析摘要）",
            }
            if extract.entry is not None:
                note_fields["entry"] = extract.entry.model_dump()
            entries.append(("note", note_fields))
```

（`note_lines`/报告逻辑不动；apply 顶部 import 需要时补 `BibEntryFields` 仅测试用，apply 本身无需。）

- [ ] **Step 4: 跑绿 + 回归** — 预期 **444 passed, 2 deselected**（ScriptedLLMClient 的 `_PARSE_EXTRACT` 未加 entry → 既有 parse e2e 走"无 entry"路径，保持绿色；若 `test_parse_schemas` 断言了 `ArticleExtractOutput` 的完整字段集，随新字段更新）

- [ ] **Step 5: Commit**

```bash
git add src/weft/engine/parse/schemas.py src/weft/engine/parse/spec_build.py src/weft/engine/parse/apply.py tests/test_parse_schemas.py tests/test_parse_apply.py tests/test_parse_spec_build.py
git commit -m "feat: parse 文献模式提取 entry 书目字段进 note 草稿卡（bibgen 设计 §8 路径 2）"
```

---

### Task 11: paper-demo 转 managed（线上展示基准）

**Files:**
- Create: `examples/paper-demo/weft.yaml`
- Modify: `examples/paper-demo/metadata/notes/smith2020.md`、`examples/paper-demo/metadata/notes/doe2021.md`（补 entry）
- Regenerate: `examples/paper-demo/assets/references.bib`
- Test: `tests/test_example_project.py`

- [ ] **Step 1: 写失败测试**（追加到 `tests/test_example_project.py`，沿用其 `SAMPLE` 常量）

```python
def test_paper_demo_is_managed_with_generated_bib():
    from weft import bibgen
    from weft.store.loader import load_project
    project, diags = load_project(SAMPLE)
    assert project.bib_managed is True
    bib_text = (SAMPLE / "assets" / "references.bib").read_text(encoding="utf-8")
    assert bib_text.startswith("%")            # 生成物头注释
    assert bib_text == bibgen.render_bib(project)   # 与真源字节一致（不 stale）


def test_paper_demo_bib_keys_unchanged():
    from weft.store.loader import load_project
    project, diags = load_project(SAMPLE)
    assert project.bib_keys == {"smith2020", "doe2021"}
    assert not any(d.is_error for d in diags)
```

- [ ] **Step 2: 跑红** — 2 个 FAIL（无 weft.yaml / bib 非生成物）

- [ ] **Step 3: 转换** —

新建 `examples/paper-demo/weft.yaml`：

```yaml
bib:
  managed: true
```

两张 note 卡的 frontmatter 各补 `entry`（YAML 注意：author 列表项含逗号必须加引号，P-D5）：

`smith2020.md`：

```yaml
---
id: smith2020
summary: "Smith 等提出热激活催化机制，核心证据是 Arrhenius 图在 45 °C 以上出现拐点，对应催化活性位点的结构转变。"
pdf: "../pdfs/smith2020.pdf"
status: approved
comment: ""
entry:
  type: article
  title: Thermally activated catalysis in batch reactors
  author:
  - "Smith, Jane"
  - "Lee, Kyung"
  year: 2020
  journal: Journal of Thermal Chemistry
  volume: '12'
  pages: 45--58
---
```

`doe2021.md`（原卡无 pdf 字段，summary 原样保留，只追加 entry）：

```yaml
---
id: doe2021
summary: "Doe 等报道了 Pt 基催化体系在 25–80 °C 区间的速率数据，表观活化能 52 kJ/mol，可作为本工作的对照体系。"
status: approved
comment: ""
entry:
  type: article
  title: Platinum-based catalysis across temperature gradients
  author:
  - "Doe, John"
  - "Wang, Lei"
  year: 2021
  journal: Catalysis Today
  volume: '8'
  pages: 101--115
---
```

重新生成 bib（命令行验证 + 落盘）：

```bash
.venv/Scripts/weft.exe bib sync examples/paper-demo
.venv/Scripts/weft.exe validate examples/paper-demo
```

预期 `references.bib` 内容（doe2021 < smith2020 ASCII 序）：

```bibtex
% ----------------------------------------------------------
% 此文件由 weft 自动生成（weft.yaml: bib.managed = true）。
% 真源：metadata/notes/ 中 status: approved 且带 entry 的文献卡。
% 请勿手改——手改内容会在下次同步时丢失。新增文献请建文献卡。
% ----------------------------------------------------------

@article{doe2021,
  title = {Platinum-based catalysis across temperature gradients},
  author = {Doe, John and Wang, Lei},
  year = {2021},
  journal = {Catalysis Today},
  volume = {8},
  pages = {101--115}
}

@article{smith2020,
  title = {Thermally activated catalysis in batch reactors},
  author = {Smith, Jane and Lee, Kyung},
  year = {2020},
  journal = {Journal of Thermal Chemistry},
  volume = {12},
  pages = {45--58}
}
```

- [ ] **Step 4: 跑绿 + 回归** — `pytest tests/test_example_project.py tests/test_graphgen.py -q` 全绿（黄金文件不变：key 集合未变）；全量预期 **446 passed, 2 deselected**

- [ ] **Step 5: Commit**

```bash
git add examples/paper-demo/weft.yaml examples/paper-demo/metadata/notes/smith2020.md examples/paper-demo/metadata/notes/doe2021.md examples/paper-demo/assets/references.bib tests/test_example_project.py
git commit -m "feat: paper-demo 转 bib managed——展示样例以已批准文献卡为真源（设计 §10）"
```

---

### Task 12: AGENTS.md / roadmap 登记

**Files:**
- Modify: `AGENTS.md`、`docs/roadmap.md`

- [ ] **Step 1: AGENTS.md 四处编辑**

1. 常用命令行（`weft.exe --help` 注释）改为含 `bib`：
   `init / validate / graph / review / draft / assemble / render / inspire / parse / replace / missing-cites / bib / serve`
2. 必读文档清单追加一行：

```markdown
- `docs/superpowers/specs/2026-09-29-weft-bibgen-design.md` — bibgen 设计定案（note 卡 entry 书目字段、managed 模式 bib=派生快照、`weft bib sync`、决策 B1–B8）；其计划文档 `2026-09-29-weft-bibgen.md` 含决策 P-D1–P-D5
```

3. 红线 4 末尾（"`inspirations/proposals/` 提案（均固定 LF，写入前归一化 CRLF）。"之后、"。draft 管线…"之前）插入：

```markdown
bib 渲染器 `src/weft/bibgen.py` 写 managed 项目的 bibliography 目标文件（默认 `assets/references.bib`；确定性产物，非 AI 直接落盘）；
```

4. 红线 5 的总表清单中 `2026-09-28-weft-parse.md（E-ARTICLE-SHAPE / E-ARTICLE-FAILED / E-ARTICLE-KEY / W-ARTICLE-LONG）` 之后追加：

```markdown
、`2026-09-29-weft-bibgen-design.md`（E-BIB-SHAPE / E-BIB-VALUE / W-BIB-STALE / W-BIB-ETYPE）
```

- [ ] **Step 2: roadmap.md** — 在 `## M4 打磨 🔨` 小节的最后一条清单项"- 溯源注释完善与用户文档。"之后追加：

```markdown
- bib 自动生成（bibgen）✅（2026-09-29）：`weft bib sync`；managed 模式以已批准文献卡为真源（note 卡 entry 书目字段，spec 2026-09-29-weft-bibgen），WebUI 批准/编辑即同步，AI 提案与 parse 文献模式两条草案入口。
```

- [ ] **Step 3: 全量回归** — `pytest tests -q` 仍 **446 passed, 2 deselected**（文档任务不动代码；测试计数钉死）

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md docs/roadmap.md
git commit -m "docs: AGENTS/roadmap 登记 bibgen——红线 4/5 增补、必读清单、M4 里程碑回填"
```

---

## 收尾（合并）

- [ ] worktree 内 `git log --oneline` 核对 12 个提交齐全，`pytest tests -q` 446 passed
- [ ] 合回 main：`git checkout main && git merge --no-ff <worktree分支>`，删除 worktree 与分支
- [ ] `git push`（origin/main 已配置）
- [ ] 手动冒烟（可选，演示彩排）：`weft init /tmp/demo && weft serve`，走"AI 提案文献 → 批准 → references.bib 出现 → claim 引用 → draft 放行"全链路
