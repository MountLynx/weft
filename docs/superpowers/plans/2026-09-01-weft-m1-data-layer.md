# weft M1 数据层实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付 weft 的纯数据层：pydantic 模型 + 文件加载（store）+ §4 校验规则 + 反向索引（graphgen）+ `weft validate` / `weft graph` / `weft review` 三个 CLI 命令，以"结果与讨论"真实样例项目验收。

**Architecture:** 四个分层模块（models / store / validation / graphgen）+ typer CLI。卡片是 Markdown+YAML frontmatter（python-frontmatter 解析），关系单向存储，反向索引与叙事可达集由 graphgen 纯函数计算后落盘 `generated/`。不碰 LLM（specmodule 依赖留到 M2）。

**Tech Stack:** Python 3.13（venv + pip）、pydantic v2、python-frontmatter、typer、pyyaml、pytest。

**Spec:** `docs/superpowers/specs/2026-09-01-weft-design.md`（§3 数据结构、§4 校验、§5 分层、§8 命令、§9 M1）。

---

## 环境与全局约定（执行前必读）

- 平台 Windows + Git Bash。所有 Python/pytest 命令用 `.venv/Scripts/python`，不要直接 `python`（避免装进全局环境）。
- 仓库根 = `C:\Users\xingy\Desktop\开发\weft`。以下相对路径均相对仓库根。
- 环境已验证：Python 3.13.7、pip 26.2.1 可用。
- 每个任务以一次 git commit 收尾，提交信息风格与仓库一致（`类型: 中文描述`）。
- TDD 节奏：每个任务先写全部失败测试 → 跑一遍确认红 → 写实现 → 跑绿 → 提交。

### 设计决策澄清（spec 未逐字定义处，已定案，实现与测试均按此）

1. **孤儿定义（W-ORPHAN / orphans.md）**：正向可达。种子 = 各叙事节点 `uses` 直接引用的 fact/claim；扩展边 = `fact.data → data`、`fact.supports → claim`。从任何叙事节点出发不可达的 data/fact/claim 即孤儿。依据：§1"未被叙事流引用的元数据不进终稿"——经 supporting fact 可达的 claim 同样会影响行文。
2. **rejected 卡片语义（§3.10）**：所有**提醒（W-\*）**跳过 `status: rejected` 的卡片；所有**错误（E-\*）**照报（结构坏就是坏，修掉或删卡）。测试 `test_rejected_claim_skips_warnings` 钉死此语义。
3. **`uses` 指向 data/note**：§2 规定叙事节点只引用 fact/claim，因此 `uses` 指向不存在的 id **或** 指向 data/note 卡都算 `E-DANGLING-REF`。
4. **表图不查文件（W-FIGURE-FILE-MISSING）**：只检查以 `fig-` 开头的 ref 是否有 `figures/{ref}.png|pdf`；`tbl-*` 是排版产物不是图片文件，不查。
5. **W-NOTE-MISSING（来自 §3.4）**：claim 引用的 key 在 .bib 中但**没有对应 note 卡** → 提醒（"该引文处 AI 只能凭条目本身行文"）。只对被非 rejected claim 引用的 key 报，不对全 bib 报。
6. **`DataCard.description`**：缺省容忍（`""`），§4 无对应规则；`FactCard.statement` / `ClaimCard.statement` 必填（缺失 = E-PARSE）。
7. **ID 格式（§3.9 两位零填充）**：是约定不强制——§4 规则表未列，不做正则校验。
8. **bib 解析**：正则扫 `@type{key,`，跳过 `@string` / `@comment` / `@preamble`；`_quarto.yml` 的 `bibliography` 兼容字符串与列表；bib 文件不存在 → `E-BIB-MISSING` 错误。
9. **`weft graph` 先校验**：存在错误则拒绝生成（只打印诊断并 exit 1）；提醒不阻断。
10. **项目根守卫**：`_quarto.yml` 与 `metadata/` 都缺失 → `E-NOT-A-PROJECT` 单条错误，跳过其余加载。
11. **M1 只读**：不实现保存/回写（M2 引擎与 M4 `weft init` 才需要）；叙事节正文区（frontmatter 之外）M1 忽略不解析。
12. **加载不中断（强化于 Task 7 评审）**：单卡解析失败 / 文件名不符 / id 重复 / 目录不符 → 记诊断后继续加载其余卡片（宁可一次看全所有问题，接受少量级联悬空误报）；所有文件读取（frontmatter、figures.yaml、_quarto.yml、weft.yaml、bib）的语法/编码/IO 失败一律转 E-PARSE 诊断；`bibliography` 空串按 Quarto 语义视为未设置，类型错误（非字符串标量/含非字符串的列表）→ E-PARSE。已知接受的限制：figures.yaml 重复键 last-wins 静默合并（PyYAML 需自定义 Loader 才能检测，M1 不做）。

13. **used-metadata.json 含 rejected-but-reachable**：`used_ids` 只按"是否被叙事可达"判定，不过滤 rejected（orphan 报告才排除 rejected）。graph.json 同理收录全部实体——两者都是全量索引/全集，筛选留给消费方（M2 spec_build 会按 approved 过滤）。

### 诊断码总表（稳定标识，测试与 CLI 输出均用）

| 级别 | 码 | 层 | 规则 |
|---|---|---|---|
| 错误 | E-NOT-A-PROJECT | store | 缺 `_quarto.yml` 且缺 `metadata/` |
| 错误 | E-PARSE | store | frontmatter/YAML 解析失败（pydantic 或语法） |
| 错误 | E-DUPLICATE-ID | store | 实体 id 全局重复 / 叙事节与节点 id 重复 |
| 错误 | E-FILENAME-MISMATCH | store | 文件名 stem ≠ id（四类实体卡） |
| 错误 | E-CLAIM-DIR-MISMATCH | store | claims 子目录名 ≠ claim_type |
| 错误 | E-BIB-MISSING | store | `_quarto.yml` bibliography 指向的文件不存在 |
| 错误 | E-DANGLING-REF | validation | `data`/`supports` 悬空；`uses` 非法（不存在或非 fact/claim） |
| 错误 | E-CITES-NOT-IN-BIB | validation | cites key 不在 bib |
| 错误 | E-NOTE-NOT-IN-BIB | validation | note id 不在 bib |
| 错误 | E-REFS-NOT-IN-FIGURES | validation | data.refs 不在 figures.yaml（含子图展开） |
| 提醒 | W-CLAIM-CITED-NO-CITES | validation | cited 但 cites 空 |
| 提醒 | W-CLAIM-UNSUPPORTED | validation | uncited 且无非 rejected fact 支持 |
| 提醒 | W-FIGURE-FILE-MISSING | validation | `figures/{ref}.png|pdf` 都不存在（仅 fig-\*） |
| 提醒 | W-FIGURE-UNUSED | validation | figures.yaml 条目无任何 data 引用 |
| 提醒 | W-ORPHAN | validation | 孤儿实体（经 graphgen 可达集判定） |
| 提醒 | W-NOTE-NO-SUMMARY | validation | note.summary 为空 |
| 提醒 | W-NOTE-MISSING | validation | 被引用的 bib key 无 note 卡 |
| 提醒 | W-PURPOSE-VOCAB | validation | purpose 不在软词表 |
| 提醒 | W-ROLE-VOCAB | validation | role 不在软词表 |

`fact.data 为空`（§4 错误）由 `FactCard.data = Field(min_length=1)` 在模型层实现，解析失败以 E-PARSE 落地。

### 文件结构总览

```text
pyproject.toml
.gitignore
src/weft/
├── __init__.py
├── diagnostics.py          # Task 2
├── models/
│   ├── __init__.py         # Task 4
│   ├── cards.py            # Task 3
│   ├── narrative.py        # Task 4
│   └── figures.py          # Task 4
├── store/
│   ├── __init__.py         # Task 5
│   ├── project.py          # Task 5
│   └── loader.py           # Task 5/6/7
├── validation/
│   ├── __init__.py         # Task 8
│   └── rules.py            # Task 8/10
├── graphgen/
│   ├── __init__.py         # Task 9
│   ├── index.py            # Task 9
│   └── writer.py           # Task 11
└── cli.py                  # Task 12/13/14
tests/
├── __init__.py             # Task 1
├── helpers.py              # Task 5
├── golden/graph.json       # Task 15
├── golden/used-metadata.json
├── test_package.py         # Task 1
├── test_diagnostics.py     # Task 2
├── test_models_cards.py    # Task 3
├── test_models_narrative.py# Task 4
├── test_store_cards.py     # Task 5
├── test_store_narrative.py # Task 6
├── test_store_config.py    # Task 7
├── test_validation_errors.py   # Task 8
├── test_graphgen.py        # Task 9
├── test_graphgen_writer.py # Task 11
├── test_validation_warnings.py # Task 10
├── test_cli.py             # Task 12/13/14
└── test_example_project.py # Task 15
examples/paper-demo/        # Task 15（样例项目 = M1 验收 + 后续里程碑 fixture）
```

---

### Task 1: 包骨架与工具链

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/weft/__init__.py`
- Create: `tests/__init__.py`（空文件）
- Create: `tests/test_package.py`

- [ ] **Step 1: 写 `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "weft"
version = "0.1.0"
description = "weft —— 元数据×叙事流的 AI 学术写作引擎"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.5",
    "python-frontmatter>=1.1",
    "typer>=0.12",
    "pyyaml>=6",
]

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
weft = "weft.cli:app"

[tool.hatch.build.targets.wheel]
packages = ["src/weft"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

（`specmodule` 依赖 M2 再加；`pythonpath = ["."]` 让测试能 `from tests.helpers import ...`。）

- [ ] **Step 2: 写 `src/weft/__init__.py`**

```python
"""weft：元数据为经线，叙事流为纬线。"""

__version__ = "0.1.0"
```

- [ ] **Step 3: 校对 `.gitignore`（main 上已预置，确认内容一致即可，不要删改）**

```gitignore
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.venv/
.pytest_cache/
generated/
.worktrees/
```

- [ ] **Step 4: 建虚拟环境并安装**

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
```

期望输出末尾：`Successfully installed ... pydantic ... python-frontmatter ... typer ... pyyaml ... pytest ...`。

- [ ] **Step 5: 写冒烟测试 `tests/test_package.py`**

```python
import weft


def test_package_importable():
    assert weft.__version__ == "0.1.0"
```

- [ ] **Step 6: 跑测试**

Run: `.venv/Scripts/python -m pytest tests -v`
Expected: `1 passed`

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore src/weft/__init__.py tests/__init__.py tests/test_package.py
git commit -m "feat: weft 包骨架（pydantic/frontmatter/typer 依赖 + pytest 配置）"
```

---

### Task 2: Diagnostic 类型

**Files:**
- Create: `src/weft/diagnostics.py`
- Test: `tests/test_diagnostics.py`

- [ ] **Step 1: 写失败测试 `tests/test_diagnostics.py`**

```python
from weft.diagnostics import Diagnostic, Level


def test_error_is_error():
    d = Diagnostic(Level.ERROR, "E-X", "metadata/data/data-01.md", "refs", "消息")
    assert d.is_error


def test_warning_is_not_error():
    d = Diagnostic(Level.WARNING, "W-X", "metadata/data/data-01.md", None, "消息")
    assert not d.is_error


def test_field_optional():
    d = Diagnostic(Level.ERROR, "E-X", ".", None, "全局消息")
    assert d.field is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python -m pytest tests/test_diagnostics.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'weft.diagnostics'`

- [ ] **Step 3: 写实现 `src/weft/diagnostics.py`**

```python
"""诊断消息：store / validation / graphgen / cli 共用的唯一消息类型。

定位粒度 = 文件 + 字段（spec §4），path 为相对项目根的 posix 风格路径。
"""
from dataclasses import dataclass
from enum import Enum


class Level(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Diagnostic:
    level: Level
    code: str          # 稳定标识，如 "E-DANGLING-REF"（见计划诊断码总表）
    path: str          # 相对项目根路径；全局性消息用 "."
    field: str | None  # 出错的字段名，可空
    message: str

    @property
    def is_error(self) -> bool:
        return self.level is Level.ERROR
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python -m pytest tests/test_diagnostics.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add src/weft/diagnostics.py tests/test_diagnostics.py
git commit -m "feat: Diagnostic 诊断类型（级别/码/文件+字段定位）"
```

---

### Task 3: 卡片模型（models/cards.py）

**Files:**
- Create: `src/weft/models/__init__.py`（本任务先放最小内容）
- Create: `src/weft/models/cards.py`
- Test: `tests/test_models_cards.py`

- [ ] **Step 1: 写失败测试 `tests/test_models_cards.py`**

```python
import pytest
from pydantic import ValidationError

from weft.models.cards import ClaimCard, DataCard, FactCard, NoteCard


def test_data_card_full():
    card = DataCard.model_validate({
        "id": "data-01",
        "refs": ["fig-01a"],
        "source": "../../data/raw/run3.csv",
        "description": "60°C与25°C下三组重复的反应速率测量",
        "status": "draft",
        "comment": "",
    })
    assert card.refs == ["fig-01a"]
    assert card.source == "../../data/raw/run3.csv"


def test_data_card_defaults():
    card = DataCard(id="data-01", status="approved")
    assert card.refs == []
    assert card.source is None
    assert card.description == ""
    assert card.comment == ""


def test_fact_card_spec_example():
    fact = FactCard.model_validate({
        "id": "fact-01",
        "data": ["data-01", "data-02"],
        "statement": "在60 °C时反应速率比25 °C提高42%（p < 0.01）。",
        "supports": ["claim-01"],
        "status": "approved",
    })
    assert fact.data == ["data-01", "data-02"]


def test_fact_data_empty_is_invalid():
    with pytest.raises(ValidationError):
        FactCard(id="fact-01", data=[], statement="s", status="draft")


def test_claim_type_limited_to_two_values():
    with pytest.raises(ValidationError):
        ClaimCard(id="claim-01", claim_type="hypothesis", statement="s", status="draft")


def test_claim_cites_default_empty():
    claim = ClaimCard(id="claim-01", claim_type="cited", statement="s", status="draft")
    assert claim.cites == []


def test_status_vocabulary_enforced():
    with pytest.raises(ValidationError):
        DataCard(id="data-01", status="pending")


def test_unknown_frontmatter_key_rejected():
    # 拼错字段名（ref 而非 refs）必须在解析期报错
    with pytest.raises(ValidationError):
        DataCard.model_validate({"id": "data-01", "status": "draft", "ref": ["fig-01a"]})


def test_note_card_defaults():
    note = NoteCard(id="smith2020", status="draft")
    assert note.summary == ""
    assert note.pdf is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python -m pytest tests/test_models_cards.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'weft.models'`

- [ ] **Step 3: 写实现 `src/weft/models/cards.py`**

```python
"""元数据卡片模型（数据结构 v1，冻结；spec §3.1–3.4、§3.10）。"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReviewStatus = Literal["draft", "approved", "rejected"]


class _Card(BaseModel):
    """卡片公共字段。未知键一律报错：防 schema 漂移与字段拼写错误。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: ReviewStatus
    comment: str = ""


class DataCard(_Card):
    """data 卡：refs 为子图级 Quarto label（fig-01a / tbl-01），可为空。"""

    refs: list[str] = []
    source: str | None = None
    description: str = ""


class FactCard(_Card):
    """fact 卡。data 为空在模型层即非法（spec §4 错误项）。"""

    data: list[str] = Field(min_length=1)
    statement: str
    supports: list[str] = []


class ClaimCard(_Card):
    """claim 卡：单一类型 + claim_type 属性；cited 时 cites 填 bib key。"""

    claim_type: Literal["uncited", "cited"]
    statement: str
    cites: list[str] = []


class NoteCard(_Card):
    """note 卡：id = bib key。summary 缺省容忍，由校验层提醒。"""

    summary: str = ""
    pdf: str | None = None
```

- [ ] **Step 4: 写 `src/weft/models/__init__.py`（本任务最小内容，Task 4 扩充）**

```python
from weft.models.cards import ClaimCard, DataCard, FactCard, NoteCard, ReviewStatus

__all__ = ["ClaimCard", "DataCard", "FactCard", "NoteCard", "ReviewStatus"]
```

- [ ] **Step 5: 跑测试确认通过**

Run: `.venv/Scripts/python -m pytest tests/test_models_cards.py -v`
Expected: `9 passed`

- [ ] **Step 6: Commit**

```bash
git add src/weft/models/ tests/test_models_cards.py
git commit -m "feat: 四类实体卡 pydantic 模型（extra=forbid，fact.data 非空约束）"
```

---

### Task 4: 叙事与图注模型

**Files:**
- Create: `src/weft/models/narrative.py`
- Create: `src/weft/models/figures.py`
- Modify: `src/weft/models/__init__.py`
- Test: `tests/test_models_narrative.py`

- [ ] **Step 1: 写失败测试 `tests/test_models_narrative.py`**

```python
import pytest
from pydantic import ValidationError

from weft.models.figures import FigureEntry
from weft.models.narrative import NarrativeSection, Node, Use


def test_section_parses_spec_example():
    section = NarrativeSection.model_validate({
        "id": "sec-03",
        "section": "Results",
        "order": 3,
        "nodes": [
            {
                "id": "para-03-01",
                "purpose": "describe",
                "uses": [
                    {"id": "fact-01", "role": "evidence"},
                    {"id": "claim-01", "role": "conclusion"},
                ],
                "logic": "先主结果，再补充次要结果",
                "status": "draft",
                "comment": "",
            }
        ],
    })
    assert section.nodes[0].uses[1].role == "conclusion"
    assert section.nodes[0].logic == "先主结果，再补充次要结果"


def test_node_defaults():
    node = Node(id="para-03-01", purpose="describe", status="approved")
    assert node.uses == []
    assert node.logic == ""


def test_node_requires_status():
    with pytest.raises(ValidationError):
        Node(id="para-03-01", purpose="describe")


def test_use_requires_role():
    with pytest.raises(ValidationError):
        Use(id="fact-01")


def test_use_role_is_free_string():
    # role/purpose 是软词表：模型层放行任意字符串，词表校验在 validation 层
    use = Use(id="fact-01", role="vibe")
    assert use.role == "vibe"


def test_section_order_is_int():
    with pytest.raises(ValidationError):
        NarrativeSection(id="sec-03", section="Results", order="third")


def test_figure_entry_defaults():
    entry = FigureEntry.model_validate({"caption": "总图注"})
    assert entry.subfigs == {}


def test_figure_entry_ignores_unknown_keys():
    # figures.yaml 人工直接维护，解析宽松：未知键忽略
    entry = FigureEntry.model_validate({"caption": "c", "typo": 1})
    assert entry.caption == "c"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python -m pytest tests/test_models_narrative.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'weft.models.narrative'`

- [ ] **Step 3: 写实现 `src/weft/models/narrative.py`**

```python
"""叙事层模型（spec §3.5）：节（section）/ 节点（node）/ 引用（use）。"""
from pydantic import BaseModel, ConfigDict

from weft.models.cards import ReviewStatus


class Use(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    role: str  # 软词表（W-ROLE-VOCAB），模型层放行超集


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    purpose: str  # 软词表（W-PURPOSE-VOCAB）
    uses: list[Use] = []
    logic: str = ""
    status: ReviewStatus
    comment: str = ""


class NarrativeSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    section: str
    order: int
    nodes: list[Node] = []
```

- [ ] **Step 4: 写实现 `src/weft/models/figures.py`**

```python
"""图注层模型（spec §3.6，metadata/figures.yaml）。"""
from pydantic import BaseModel


class FigureEntry(BaseModel):
    """人工直接维护、无 status；解析宽松：未知键忽略，caption/subfigs 可缺省。"""

    caption: str = ""
    subfigs: dict[str, str] = {}
```

- [ ] **Step 5: 更新 `src/weft/models/__init__.py`**

```python
from weft.models.cards import ClaimCard, DataCard, FactCard, NoteCard, ReviewStatus
from weft.models.figures import FigureEntry
from weft.models.narrative import NarrativeSection, Node, Use

__all__ = [
    "ClaimCard",
    "DataCard",
    "FactCard",
    "NoteCard",
    "ReviewStatus",
    "FigureEntry",
    "NarrativeSection",
    "Node",
    "Use",
]
```

- [ ] **Step 6: 跑测试确认通过**

Run: `.venv/Scripts/python -m pytest tests/test_models_narrative.py -v`
Expected: `8 passed`

- [ ] **Step 7: 全量回归**

Run: `.venv/Scripts/python -m pytest tests -v`
Expected: 全部通过（此前任务 13 个 + 本任务 8 个 = 21 个）

- [ ] **Step 8: Commit**

```bash
git add src/weft/models/ tests/test_models_narrative.py
git commit -m "feat: 叙事节/节点/Use 与 FigureEntry 模型"
```

---

### Task 5: store——实体卡加载

**Files:**
- Create: `src/weft/store/__init__.py`
- Create: `src/weft/store/project.py`
- Create: `src/weft/store/loader.py`
- Create: `tests/helpers.py`
- Test: `tests/test_store_cards.py`

- [ ] **Step 1: 写测试工具 `tests/helpers.py`**

```python
"""测试公共工具：文件层写入 helper + 内存 Project 构造 helper。"""
from __future__ import annotations

from pathlib import Path

import frontmatter
import yaml

from weft.models.cards import ClaimCard, DataCard, FactCard, NoteCard
from weft.models.figures import FigureEntry
from weft.models.narrative import NarrativeSection, Node, Use
from weft.store.project import Project


def write_card(directory: Path, name: str, meta: dict, body: str = "") -> Path:
    """写一张 Markdown+frontmatter 卡片，文件名 = name.md。"""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.md"
    path.write_text(frontmatter.dumps(frontmatter.Post(body, **meta)), encoding="utf-8")
    return path


def write_yaml(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def make_minimal_project(root: Path) -> Path:
    """最小合法项目：1 data + 1 fact + 1 uncited claim + 1 note + figures/bib/叙事节。

    校验干净（0 错误 0 提醒）：claim 被支持、实体全部可达、图注被引用、图文件存在。
    """
    write_card(root / "metadata" / "data", "data-01",
               {"id": "data-01", "refs": ["fig-01a"], "status": "approved"})
    write_card(root / "metadata" / "facts", "fact-01",
               {"id": "fact-01", "data": ["data-01"], "statement": "温度提高速率。",
                "supports": ["claim-01"], "status": "approved"})
    write_card(root / "metadata" / "claims" / "uncited", "claim-01",
               {"id": "claim-01", "claim_type": "uncited", "statement": "温度有正效应。",
                "status": "approved"})
    write_card(root / "metadata" / "notes", "key2020",
               {"id": "key2020", "summary": "文献概括。", "status": "approved"})
    write_yaml(root / "metadata" / "figures.yaml",
               {"fig-01": {"caption": "速率曲线", "subfigs": {"a": "60°C"}}})
    write_yaml(root / "_quarto.yml", {"project": {"type": "default"},
                                      "bibliography": "references.bib"})
    (root / "references.bib").write_text(
        "@article{key2020,\n  title = {T},\n  year = {2020},\n}\n", encoding="utf-8")
    write_card(root / "narrative", "01-results",
               {"id": "sec-01", "section": "Results", "order": 1,
                "nodes": [{"id": "para-01-01", "purpose": "describe",
                           "uses": [{"id": "fact-01", "role": "evidence"}],
                           "status": "approved"}]})
    (root / "figures").mkdir(exist_ok=True)
    (root / "figures" / "fig-01a.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return root


def build_project(root: Path | None = None, *, data=None, facts=None, claims=None,
                  notes=None, sections=None, figures=None, bib_keys=None,
                  figures_dir: str = "figures") -> Project:
    """在内存中直接构造 Project（validation/graphgen 单测用，不落盘）。"""
    root = root or Path(".")
    project = Project(root=root, figures_dir=figures_dir)
    project.data_cards = {c.id: c for c in (data or [])}
    project.facts = {c.id: c for c in (facts or [])}
    project.claims = {c.id: c for c in (claims or [])}
    project.notes = {c.id: c for c in (notes or [])}
    project.sections = list(sections or [])
    project.figures = dict(figures or {})
    project.bib_keys = set(bib_keys or set())
    for cards in (project.data_cards, project.facts, project.claims, project.notes):
        for cid in cards:
            project.card_paths.setdefault(cid, Path(f"metadata/{cid}.md"))
    for section in project.sections:
        project.section_paths.setdefault(section.id, Path(f"narrative/{section.id}.md"))
    return project
```

（`tests/helpers.py` 顶部 import 的 `DataCard/FactCard/...` 在本任务未必用到，先保留——后续任务直接用。）

- [ ] **Step 2: 写失败测试 `tests/test_store_cards.py`**

```python
from weft.diagnostics import Level
from weft.store.loader import load_project
from tests.helpers import make_minimal_project, write_card


def test_minimal_project_loads_clean(tmp_path):
    make_minimal_project(tmp_path)
    project, diagnostics = load_project(tmp_path)
    assert diagnostics == []
    assert set(project.data_cards) == {"data-01"}
    assert set(project.facts) == {"fact-01"}
    assert set(project.claims) == {"claim-01"}
    assert set(project.notes) == {"key2020"}
    # figures/bib 断言在 Task 7（加载器到那时才读它们；本任务只装实体卡）
    assert project.card_paths["data-01"].as_posix() == "metadata/data/data-01.md"


def test_filename_mismatch_is_error(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "data", "wrong-name",
               {"id": "data-02", "status": "draft"})
    _, diagnostics = load_project(tmp_path)
    hits = [d for d in diagnostics if d.code == "E-FILENAME-MISMATCH"]
    assert len(hits) == 1
    assert hits[0].path == "metadata/data/wrong-name.md"
    assert hits[0].level is Level.ERROR
    # 卡片仍被装入（不中断加载）
    project, _ = load_project(tmp_path)
    assert "data-02" in project.data_cards


def test_duplicate_id_across_types(tmp_path):
    # note 卡 id 用了实体命名空间的名字 → 全局唯一性检查必须跨类型
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "notes", "data-01",
               {"id": "data-01", "status": "draft"})
    _, diagnostics = load_project(tmp_path)
    dup = [d for d in diagnostics if d.code == "E-DUPLICATE-ID"]
    assert len(dup) == 1
    assert "data-01" in dup[0].message
    project, _ = load_project(tmp_path)
    # 合法 note key2020 保留，后出现的重复 data-01 卡被跳过（first-wins）
    assert set(project.notes) == {"key2020"}
    assert project.card_paths["data-01"].as_posix() == "metadata/data/data-01.md"


def test_yaml_syntax_error_is_parse_error(tmp_path):
    make_minimal_project(tmp_path)
    (tmp_path / "metadata" / "data" / "data-98.md").write_text(
        "---\nid: [unclosed\n---\n", encoding="utf-8")
    _, diagnostics = load_project(tmp_path)
    parse = [d for d in diagnostics if d.code == "E-PARSE"]
    assert len(parse) == 1
    assert parse[0].path == "metadata/data/data-98.md"
    assert parse[0].field is None


def test_non_utf8_card_is_parse_error(tmp_path):
    make_minimal_project(tmp_path)
    (tmp_path / "metadata" / "data" / "data-97.md").write_bytes(
        b"---\nid: data-97\nstatus: approved\ndescription: \xb0\xc2\n---\n")
    _, diagnostics = load_project(tmp_path)
    parse = [d for d in diagnostics if d.code == "E-PARSE"]
    assert len(parse) == 1
    assert parse[0].path == "metadata/data/data-97.md"


def test_claim_directory_mismatch(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "claims" / "cited", "claim-02",
               {"id": "claim-02", "claim_type": "uncited", "statement": "s",
                "status": "draft"})
    _, diagnostics = load_project(tmp_path)
    hits = [d for d in diagnostics if d.code == "E-CLAIM-DIR-MISMATCH"]
    assert len(hits) == 1
    assert hits[0].field == "claim_type"


def test_broken_frontmatter_is_parse_error(tmp_path):
    make_minimal_project(tmp_path)
    (tmp_path / "metadata" / "data" / "data-99.md").write_text(
        "---\nid: data-99\nstatus: bogus\n---\n", encoding="utf-8")
    _, diagnostics = load_project(tmp_path)
    parse = [d for d in diagnostics if d.code == "E-PARSE"]
    assert len(parse) == 1
    assert parse[0].path == "metadata/data/data-99.md"
    assert parse[0].field == "status"


def test_empty_fact_data_is_parse_error(tmp_path):
    # §4「fact.data 为空」由模型层 min_length=1 兜住
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "facts", "fact-02",
               {"id": "fact-02", "data": [], "statement": "s", "status": "draft"})
    _, diagnostics = load_project(tmp_path)
    parse = [d for d in diagnostics if d.code == "E-PARSE"]
    assert len(parse) == 1
    assert parse[0].path == "metadata/facts/fact-02.md"


def test_not_a_project_guard(tmp_path):
    project, diagnostics = load_project(tmp_path)
    assert [d.code for d in diagnostics] == ["E-NOT-A-PROJECT"]
    assert project.data_cards == {}
```

- [ ] **Step 3: 跑测试确认失败**

Run: `.venv/Scripts/python -m pytest tests/test_store_cards.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'weft.store'`

- [ ] **Step 4: 写 `src/weft/store/project.py`**

```python
"""加载后的项目容器：实体卡 + 叙事节 + 图注 + bib/配置 + 路径元数据。"""
from dataclasses import dataclass, field
from pathlib import Path

from weft.models.cards import ClaimCard, DataCard, FactCard, NoteCard
from weft.models.figures import FigureEntry
from weft.models.narrative import NarrativeSection


@dataclass
class Project:
    root: Path
    data_cards: dict[str, DataCard] = field(default_factory=dict)
    facts: dict[str, FactCard] = field(default_factory=dict)
    claims: dict[str, ClaimCard] = field(default_factory=dict)
    notes: dict[str, NoteCard] = field(default_factory=dict)
    sections: list[NarrativeSection] = field(default_factory=list)  # 按 (order, id) 排序
    figures: dict[str, FigureEntry] = field(default_factory=dict)
    bib_keys: set[str] = field(default_factory=set)
    figures_dir: str = "figures"          # weft.yaml figures_dir 可覆盖
    card_paths: dict[str, Path] = field(default_factory=dict)     # 实体 id -> 相对路径
    section_paths: dict[str, Path] = field(default_factory=dict)  # 节 id -> 相对路径
```

- [ ] **Step 5: 写 `src/weft/store/loader.py`（本任务先实现实体卡部分；叙事/图注/配置函数在 Task 6/7 补）**

```python
"""卡片/叙事/图注/bib/配置的加载（spec §3、§5 store 层）。

加载约定：
- 单卡解析失败、文件名≠id、id 重复、claims 目录不符 → 错误诊断，不中断加载。
- 实体 id 全局唯一（data/fact/claim/note 共用一个命名空间，spec §3.9）。
- 路径统一转成相对项目根的 posix 风格（诊断展示用）。
"""
from __future__ import annotations

import re
from pathlib import Path

import frontmatter
import yaml
from pydantic import ValidationError

from weft.diagnostics import Diagnostic, Level
from weft.models.cards import ClaimCard, DataCard, FactCard, NoteCard
from weft.models.figures import FigureEntry
from weft.models.narrative import NarrativeSection
from weft.store.project import Project

_BIB_ENTRY = re.compile(r"@(?P<etype>[A-Za-z]+)\s*\{\s*(?P<key>[^,\s{}]+)\s*,")
_BIB_IGNORED = {"string", "comment", "preamble"}

_CARD_TYPES = [
    ("data_cards", "metadata/data", DataCard),
    ("facts", "metadata/facts", FactCard),
    ("notes", "metadata/notes", NoteCard),
]


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def load_project(root: Path) -> tuple[Project, list[Diagnostic]]:
    root = root.resolve()
    diagnostics: list[Diagnostic] = []

    if not (root / "_quarto.yml").exists() and not (root / "metadata").is_dir():
        diagnostics.append(Diagnostic(
            Level.ERROR, "E-NOT-A-PROJECT", ".", None,
            f"{root} 不是 weft 项目根目录（缺少 _quarto.yml 与 metadata/）"))
        return Project(root=root), diagnostics

    project = Project(root=root)
    seen_ids: dict[str, str] = {}  # id -> 首次出现的文件（实体共用命名空间）

    _load_cards(root, project, seen_ids, diagnostics)
    return project, diagnostics


def _load_frontmatter(path: Path) -> tuple[dict | None, str | None]:
    """返回 (metadata, 错误消息)。错误消息非 None 表示 YAML/编码层失败。

    OSError（文件被占用/是目录等）也在内：加载永不中断是冻结设计决策。
    """
    try:
        post = frontmatter.load(path)
    except (yaml.YAMLError, UnicodeDecodeError, OSError) as exc:
        return None, f"frontmatter 解析失败：{exc}"
    return post.metadata, None


def _load_cards(root: Path, project: Project, seen_ids: dict[str, str],
                diagnostics: list[Diagnostic]) -> None:
    for attr, rel_dir, model in _CARD_TYPES:
        directory = root / rel_dir
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            _load_card(root, project, seen_ids, diagnostics, attr, model, path)

    claims_dir = root / "metadata" / "claims"
    if claims_dir.is_dir():
        for path in sorted(claims_dir.rglob("*.md")):
            _load_card(root, project, seen_ids, diagnostics, "claims", ClaimCard,
                       path, check_claim_dir=True)


def _load_card(root: Path, project: Project, seen_ids: dict[str, str],
               diagnostics: list[Diagnostic], attr: str, model, path: Path,
               *, check_claim_dir: bool = False) -> None:
    rel = _rel(root, path)
    metadata, error = _load_frontmatter(path)
    if error is not None:
        diagnostics.append(Diagnostic(Level.ERROR, "E-PARSE", rel, None, error))
        return
    try:
        card = model.model_validate(metadata)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(p) for p in first["loc"])
        diagnostics.append(Diagnostic(
            Level.ERROR, "E-PARSE", rel, field or None,
            f"frontmatter 解析失败：{first['msg']}"))
        return

    if check_claim_dir and path.parent.name != card.claim_type:
        diagnostics.append(Diagnostic(
            Level.ERROR, "E-CLAIM-DIR-MISMATCH", rel, "claim_type",
            f"卡片位于 {path.parent.name}/ 目录，但 claim_type 为 {card.claim_type}"))

    if path.stem != card.id:
        diagnostics.append(Diagnostic(
            Level.ERROR, "E-FILENAME-MISMATCH", rel, "id",
            f"文件名 {path.stem} 与 id {card.id} 不一致"))

    if card.id in seen_ids:
        diagnostics.append(Diagnostic(
            Level.ERROR, "E-DUPLICATE-ID", rel, "id",
            f"id {card.id} 重复，首次出现于 {seen_ids[card.id]}"))
        return
    seen_ids[card.id] = rel

    getattr(project, attr)[card.id] = card
    project.card_paths[card.id] = path.relative_to(root)
```

- [ ] **Step 6: 写 `src/weft/store/__init__.py`**

```python
from weft.store.loader import load_project
from weft.store.project import Project

__all__ = ["Project", "load_project"]
```

- [ ] **Step 7: 跑测试确认通过**

Run: `.venv/Scripts/python -m pytest tests/test_store_cards.py -v`
Expected: `9 passed`

- [ ] **Step 8: 全量回归**

Run: `.venv/Scripts/python -m pytest tests -v`
Expected: 全部通过（21 + 9 = 30 个）

- [ ] **Step 9: Commit**

```bash
git add src/weft/store/ tests/helpers.py tests/test_store_cards.py
git commit -m "feat: store 实体卡加载（全局 id 唯一、文件名校验、claims 目录校验）"
```

---

### Task 6: store——叙事节加载

**Files:**
- Modify: `src/weft/store/loader.py`（追加 `_load_narrative`，并在 `load_project` 中调用）
- Test: `tests/test_store_narrative.py`

- [ ] **Step 1: 写失败测试 `tests/test_store_narrative.py`**

```python
from weft.store.loader import load_project
from tests.helpers import make_minimal_project, write_card


def test_sections_sorted_by_order(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "narrative", "02-discussion",
               {"id": "sec-02", "section": "Discussion", "order": 2,
                "nodes": [{"id": "para-02-01", "purpose": "interpret", "uses": [],
                           "status": "approved"}]})
    # order 与文件名顺序相反 + 同 order 用 id 决胜：防止用文件名顺序冒充排序
    write_card(tmp_path / "narrative", "00-zzz",
               {"id": "sec-00", "section": "Intro", "order": 0, "nodes": []})
    write_card(tmp_path / "narrative", "05-aaa",
               {"id": "sec-05b", "section": "B", "order": 5, "nodes": []})
    write_card(tmp_path / "narrative", "05-bbb",
               {"id": "sec-05a", "section": "A", "order": 5, "nodes": []})
    project, diagnostics = load_project(tmp_path)
    assert diagnostics == []
    assert [s.id for s in project.sections] == ["sec-00", "sec-01", "sec-02",
                                                "sec-05a", "sec-05b"]
    assert project.section_paths["sec-02"].as_posix() == "narrative/02-discussion.md"


def test_section_body_ignored_in_m1(tmp_path):
    # 正文区只放审阅备注（spec §3.5），M1 加载器不解析、不报错
    make_minimal_project(tmp_path)
    write_card(tmp_path / "narrative", "02-x",
               {"id": "sec-02", "section": "X", "order": 2, "nodes": []},
               body="审阅备注：本节留待补充。")
    project, diagnostics = load_project(tmp_path)
    assert diagnostics == []
    assert len(project.sections) == 2


def test_duplicate_node_id_across_sections(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "narrative", "02-x",
               {"id": "sec-02", "section": "X", "order": 2,
                "nodes": [{"id": "para-01-01", "purpose": "describe", "uses": [],
                           "status": "draft"}]})
    _, diagnostics = load_project(tmp_path)
    hits = [d for d in diagnostics if d.code == "E-DUPLICATE-ID" and "para-01-01" in d.message]
    assert len(hits) == 1


def test_broken_section_frontmatter(tmp_path):
    make_minimal_project(tmp_path)
    # 其余必填字段齐全，只让 order 非法——确保第一个报错就是 order 的 int_parsing
    (tmp_path / "narrative" / "09-bad.md").write_text(
        "---\nid: sec-09\nsection: Bad\norder: not-a-number\n---\n", encoding="utf-8")
    _, diagnostics = load_project(tmp_path)
    parse = [d for d in diagnostics if d.code == "E-PARSE"]
    assert len(parse) == 1
    assert parse[0].path == "narrative/09-bad.md"
    assert parse[0].field == "order"


def test_duplicate_section_id_first_wins(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "narrative", "09-dup",
               {"id": "sec-01", "section": "Dup", "order": 9, "nodes": []})
    _, diagnostics = load_project(tmp_path)
    dup = [d for d in diagnostics if d.code == "E-DUPLICATE-ID"]
    assert len(dup) == 1
    project, _ = load_project(tmp_path)
    # first-wins：保留首个 sec-01，后出现的整文件跳过
    assert len([s for s in project.sections if s.id == "sec-01"]) == 1
    assert project.section_paths["sec-01"].as_posix() == "narrative/01-results.md"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python -m pytest tests/test_store_narrative.py -v`
Expected: FAIL，`AttributeError: ... load_project` 返回的 sections 恒为空 / `test_sections_sorted_by_order` 断言失败

- [ ] **Step 3: 实现 `_load_narrative`**

在 `loader.py` 的 `_load_cards` 函数之后追加：

```python
def _load_narrative(root: Path, project: Project, diagnostics: list[Diagnostic]) -> None:
    directory = root / "narrative"
    if not directory.is_dir():
        return
    seen_sections: dict[str, str] = {}
    seen_nodes: dict[str, str] = {}
    sections: list[NarrativeSection] = []

    for path in sorted(directory.glob("*.md")):
        rel = _rel(root, path)
        metadata, error = _load_frontmatter(path)
        if error is not None:
            diagnostics.append(Diagnostic(Level.ERROR, "E-PARSE", rel, None, error))
            continue
        try:
            section = NarrativeSection.model_validate(metadata)
        except ValidationError as exc:
            first = exc.errors()[0]
            field = ".".join(str(p) for p in first["loc"])
            diagnostics.append(Diagnostic(
                Level.ERROR, "E-PARSE", rel, field or None,
                f"frontmatter 解析失败：{first['msg']}"))
            continue

        if section.id in seen_sections:
            diagnostics.append(Diagnostic(
                Level.ERROR, "E-DUPLICATE-ID", rel, "id",
                f"叙事节 id {section.id} 重复，首次出现于 {seen_sections[section.id]}"))
            continue
        seen_sections[section.id] = rel
        project.section_paths[section.id] = path.relative_to(root)
        sections.append(section)

        for node in section.nodes:
            if node.id in seen_nodes:
                diagnostics.append(Diagnostic(
                    Level.ERROR, "E-DUPLICATE-ID", rel, f"nodes[{node.id}]",
                    f"叙事节点 id {node.id} 重复，首次出现于 {seen_nodes[node.id]}"))
                continue
            seen_nodes[node.id] = rel

    project.sections = sorted(sections, key=lambda s: (s.order, s.id))
```

并在 `load_project` 中，把

```python
    _load_cards(root, project, seen_ids, diagnostics)
    return project, diagnostics
```

改为：

```python
    _load_cards(root, project, seen_ids, diagnostics)
    _load_narrative(root, project, diagnostics)
    return project, diagnostics
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python -m pytest tests/test_store_narrative.py -v`
Expected: `5 passed`

- [ ] **Step 5: 全量回归 + Commit**

Run: `.venv/Scripts/python -m pytest tests -v`
Expected: 全部通过（30 + 5 = 35 个）

```bash
git add src/weft/store/loader.py tests/test_store_narrative.py
git commit -m "feat: store 叙事节加载（order 排序、跨节节点 id 唯一性）"
```

---

### Task 7: store——图注、bib、项目配置

**Files:**
- Modify: `src/weft/store/loader.py`（追加 `_load_figures`、`_load_config`，并在 `load_project` 中调用）
- Test: `tests/test_store_config.py`

- [ ] **Step 1: 写失败测试 `tests/test_store_config.py`**

```python
from weft.store.loader import load_project
from tests.helpers import make_minimal_project, write_yaml


def test_figures_dir_override(tmp_path):
    make_minimal_project(tmp_path)
    write_yaml(tmp_path / "weft.yaml", {"figures_dir": "assets/figs"})
    project, diagnostics = load_project(tmp_path)
    assert diagnostics == []
    assert project.figures_dir == "assets/figs"


def test_figures_yaml_entries_loaded(tmp_path):
    make_minimal_project(tmp_path)
    write_yaml(tmp_path / "metadata" / "figures.yaml",
               {"fig-01": {"caption": "总图注", "subfigs": {"a": "子图a", "b": "子图b"}},
                "tbl-01": {"caption": "表格注"}})
    project, diagnostics = load_project(tmp_path)
    assert diagnostics == []
    assert project.figures["fig-01"].subfigs == {"a": "子图a", "b": "子图b"}
    assert project.figures["tbl-01"].subfigs == {}


def test_bibliography_as_list_with_missing_file(tmp_path):
    make_minimal_project(tmp_path)
    write_yaml(tmp_path / "_quarto.yml",
               {"bibliography": ["references.bib", "missing.bib"]})
    project, diagnostics = load_project(tmp_path)
    miss = [d for d in diagnostics if d.code == "E-BIB-MISSING"]
    assert len(miss) == 1
    assert "missing.bib" in miss[0].message
    assert project.bib_keys == {"key2020"}  # 存在的 bib 正常解析


def test_bib_keys_ignore_string_entries(tmp_path):
    make_minimal_project(tmp_path)
    (tmp_path / "references.bib").write_text(
        "@string{jan = \"January\",}\n"
        "@article{key2020,\n  title = {T},\n  year = {2020},\n}\n"
        "@inproceedings{doe2021,\n  title = {D},\n  year = {2021},\n}\n",
        encoding="utf-8")
    project, diagnostics = load_project(tmp_path)
    assert diagnostics == []
    assert project.bib_keys == {"key2020", "doe2021"}


def test_no_bibliography_field_is_fine(tmp_path):
    make_minimal_project(tmp_path)
    write_yaml(tmp_path / "_quarto.yml", {"project": {"type": "default"}})
    project, diagnostics = load_project(tmp_path)
    assert diagnostics == []
    assert project.bib_keys == set()


def test_empty_bibliography_string_is_unset(tmp_path):
    make_minimal_project(tmp_path)
    write_yaml(tmp_path / "_quarto.yml", {"bibliography": ""})
    project, diagnostics = load_project(tmp_path)
    assert diagnostics == []
    assert project.bib_keys == set()


def test_bibliography_list_with_non_string_is_parse_error(tmp_path):
    make_minimal_project(tmp_path)
    write_yaml(tmp_path / "_quarto.yml", {"bibliography": [123]})
    project, diagnostics = load_project(tmp_path)
    assert [d.code for d in diagnostics] == ["E-PARSE"]
    assert diagnostics[0].field == "bibliography"


def test_bibliography_scalar_int_is_parse_error(tmp_path):
    make_minimal_project(tmp_path)
    write_yaml(tmp_path / "_quarto.yml", {"bibliography": 123})
    project, diagnostics = load_project(tmp_path)
    assert [d.code for d in diagnostics] == ["E-PARSE"]
    assert diagnostics[0].field == "bibliography"


def test_bib_path_is_directory_is_parse_error(tmp_path):
    make_minimal_project(tmp_path)
    (tmp_path / "bibdir").mkdir()
    write_yaml(tmp_path / "_quarto.yml", {"bibliography": "bibdir"})
    project, diagnostics = load_project(tmp_path)
    assert [d.code for d in diagnostics] == ["E-PARSE"]
    assert project.bib_keys == set()


def test_quarto_yml_as_directory_no_crash(tmp_path):
    # _quarto.yml 是目录：读取失败必须转诊断，不得抛异常
    make_minimal_project(tmp_path)
    (tmp_path / "_quarto.yml").unlink()
    (tmp_path / "_quarto.yml").mkdir()
    project, diagnostics = load_project(tmp_path)
    assert "E-PARSE" in [d.code for d in diagnostics]


def test_figures_yaml_non_utf8_is_parse_error(tmp_path):
    make_minimal_project(tmp_path)
    (tmp_path / "metadata" / "figures.yaml").write_bytes(b"fig-01: \xb0\xc2\n")
    project, diagnostics = load_project(tmp_path)
    assert [d.code for d in diagnostics] == ["E-PARSE"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python -m pytest tests/test_store_config.py -v`
Expected: FAIL（`figures_dir` 恒为默认值、bib 缺失无诊断等断言失败）

- [ ] **Step 3: 实现 `_load_figures` 与 `_load_config`**

在 `loader.py` 的 `_load_narrative` 之后追加（`_read_yaml` 是共享的容错读取 helper，放在 `_load_frontmatter` 旁）：

```python
def _read_yaml(path: Path, rel: str, diagnostics: list[Diagnostic]):
    """读 YAML 文件；语法/编码/IO 失败一律转 E-PARSE 诊断，返回 None。"""
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError, OSError) as exc:
        diagnostics.append(Diagnostic(Level.ERROR, "E-PARSE", rel, None,
                                      f"YAML 语法错误：{exc}"))
        return None


def _load_figures(root: Path, project: Project, diagnostics: list[Diagnostic]) -> None:
    path = root / "metadata" / "figures.yaml"
    if not path.exists():
        return
    rel = _rel(root, path)
    raw = _read_yaml(path, rel, diagnostics)
    if raw is None:
        return
    if not isinstance(raw, dict):
        diagnostics.append(Diagnostic(Level.ERROR, "E-PARSE", rel, None,
                                      "figures.yaml 顶层必须是映射"))
        return
    for key, value in raw.items():
        try:
            project.figures[str(key)] = FigureEntry.model_validate(value or {})
        except ValidationError as exc:
            diagnostics.append(Diagnostic(Level.ERROR, "E-PARSE", rel, str(key),
                                          f"图注条目解析失败：{exc.errors()[0]['msg']}"))


def _load_config(root: Path, project: Project, diagnostics: list[Diagnostic]) -> None:
    quarto: dict = {}
    quarto_path = root / "_quarto.yml"
    if quarto_path.exists():
        loaded = _read_yaml(quarto_path, "_quarto.yml", diagnostics)
        quarto = loaded if isinstance(loaded, dict) else {}

    weft_cfg: dict = {}
    weft_path = root / "weft.yaml"
    if weft_path.exists():
        loaded = _read_yaml(weft_path, "weft.yaml", diagnostics)
        weft_cfg = loaded if isinstance(loaded, dict) else {}

    project.figures_dir = str(weft_cfg.get("figures_dir", "figures"))

    bib_field = quarto.get("bibliography")
    if isinstance(bib_field, str):
        bib_files = [bib_field]
    elif isinstance(bib_field, list) and all(isinstance(x, str) for x in bib_field):
        bib_files = bib_field
    else:
        if bib_field is not None:  # 字段缺失(None)不算错
            diagnostics.append(Diagnostic(Level.ERROR, "E-PARSE", "_quarto.yml",
                                          "bibliography",
                                          "bibliography 必须是字符串或字符串列表"))
        bib_files = []
    for rel_bib in bib_files:
        if not rel_bib.strip():
            continue  # 空串按 Quarto 语义视为未设置
        bib_path = root / rel_bib
        if not bib_path.exists():
            diagnostics.append(Diagnostic(
                Level.ERROR, "E-BIB-MISSING", str(rel_bib), "bibliography",
                f"bibliography 文件不存在：{rel_bib}"))
            continue
        try:
            text = bib_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            diagnostics.append(Diagnostic(Level.ERROR, "E-PARSE", str(rel_bib),
                                          "bibliography", f"bib 文件读取失败：{exc}"))
            continue
        for match in _BIB_ENTRY.finditer(text):
            if match.group("etype").lower() not in _BIB_IGNORED:
                project.bib_keys.add(match.group("key"))
```

并把 `load_project` 尾部改为：

```python
    _load_cards(root, project, seen_ids, diagnostics)
    _load_narrative(root, project, diagnostics)
    _load_figures(root, project, diagnostics)
    _load_config(root, project, diagnostics)
    return project, diagnostics
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python -m pytest tests/test_store_config.py -v`
Expected: `11 passed`

- [ ] **Step 5: 全量回归 + Commit**

Run: `.venv/Scripts/python -m pytest tests -v`
Expected: 全部通过（35 + 11 = 46 个）

```bash
git add src/weft/store/loader.py tests/test_store_config.py
git commit -m "feat: store 加载 figures.yaml/_quarto.yml bib/weft.yaml 配置"
```

---

### Task 8: validation——错误规则

**Files:**
- Create: `src/weft/validation/__init__.py`
- Create: `src/weft/validation/rules.py`
- Test: `tests/test_validation_errors.py`

- [ ] **Step 1: 写失败测试 `tests/test_validation_errors.py`**

```python
from weft.models.cards import ClaimCard, DataCard, FactCard, NoteCard
from weft.models.figures import FigureEntry
from weft.models.narrative import NarrativeSection, Node, Use
from weft.validation import validate_project
from tests.helpers import build_project


def _errors(diagnostics):
    return [d for d in diagnostics if d.is_error]


def _one_error_code(diagnostics):
    codes = [d.code for d in _errors(diagnostics)]
    assert len(codes) == 1
    return codes[0]


def test_clean_project_has_no_diagnostics(tmp_path):
    (tmp_path / "figures").mkdir()
    (tmp_path / "figures" / "fig-01a.png").write_bytes(b"x")
    project = build_project(
        root=tmp_path,
        data=[DataCard(id="data-01", status="approved", refs=["fig-01a"])],
        facts=[FactCard(id="fact-01", data=["data-01"], statement="s",
                        supports=["claim-01"], status="approved")],
        claims=[ClaimCard(id="claim-01", claim_type="uncited", statement="s",
                          status="approved")],
        figures={"fig-01": FigureEntry(caption="c", subfigs={"a": "s"})},
        bib_keys={"key2020"},
        sections=[NarrativeSection(id="sec-01", section="Results", order=1, nodes=[
            Node(id="para-01-01", purpose="describe",
                 uses=[Use(id="fact-01", role="evidence")], status="approved")]),
        ],
    )
    assert validate_project(project) == []


def test_dangling_data_ref():
    facts = [FactCard(id="fact-01", data=["data-99"], statement="s", status="approved")]
    project = build_project(facts=facts)
    diagnostics = validate_project(project)
    assert _one_error_code(diagnostics) == "E-DANGLING-REF"
    err = _errors(diagnostics)[0]
    assert err.field == "data"
    assert "data-99" in err.message
    assert err.path == "metadata/fact-01.md"


def test_dangling_supports_ref():
    facts = [FactCard(id="fact-01", data=["data-01"], statement="s",
                      supports=["claim-99"], status="approved")]
    data = [DataCard(id="data-01", status="approved")]
    project = build_project(data=data, facts=facts)
    diagnostics = validate_project(project)
    assert _one_error_code(diagnostics) == "E-DANGLING-REF"
    assert _errors(diagnostics)[0].field == "supports"


def test_uses_must_point_at_fact_or_claim():
    # data 卡存在，但 uses 不允许指向 data（spec §2：叙事节点只引用 fact/claim）
    sections = [NarrativeSection(id="sec-01", section="R", order=1, nodes=[
        Node(id="para-01-01", purpose="describe",
             uses=[Use(id="data-01", role="evidence")], status="approved")])]
    data = [DataCard(id="data-01", status="approved")]
    project = build_project(data=data, sections=sections)
    diagnostics = validate_project(project)
    assert _one_error_code(diagnostics) == "E-DANGLING-REF"
    assert "uses" in _errors(diagnostics)[0].field


def test_cites_not_in_bib():
    claims = [ClaimCard(id="claim-01", claim_type="cited", statement="s",
                        cites=["ghostkey"], status="approved")]
    project = build_project(claims=claims, bib_keys={"real2020"})
    diagnostics = validate_project(project)
    assert _one_error_code(diagnostics) == "E-CITES-NOT-IN-BIB"
    assert _errors(diagnostics)[0].field == "cites"


def test_note_key_not_in_bib():
    project = build_project(notes=[NoteCard(id="ghost2020", summary="s", status="approved")],
                            bib_keys=set())
    diagnostics = validate_project(project)
    assert _one_error_code(diagnostics) == "E-NOTE-NOT-IN-BIB"
    assert _errors(diagnostics)[0].field == "id"


def test_refs_not_in_figures():
    data = [DataCard(id="data-01", status="approved", refs=["fig-99z"])]
    project = build_project(data=data)
    diagnostics = validate_project(project)
    assert _one_error_code(diagnostics) == "E-REFS-NOT-IN-FIGURES"
    assert _errors(diagnostics)[0].field == "refs"


def test_subfig_ref_valid_only_when_listed():
    # fig-01b 未在 subfigs 中列出 → 无效
    data = [DataCard(id="data-01", status="approved", refs=["fig-01b"])]
    figures = {"fig-01": FigureEntry(caption="c", subfigs={"a": "s"})}
    project = build_project(data=data, figures=figures)
    diagnostics = validate_project(project)
    assert _one_error_code(diagnostics) == "E-REFS-NOT-IN-FIGURES"


def test_parent_ref_and_subfig_ref_both_valid():
    data = [DataCard(id="data-01", status="approved", refs=["fig-01a", "fig-01"]),
            DataCard(id="data-02", status="approved", refs=["tbl-01"])]
    figures = {"fig-01": FigureEntry(caption="c", subfigs={"a": "s"}),
               "tbl-01": FigureEntry(caption="t")}
    project = build_project(data=data, figures=figures)
    errors = _errors(validate_project(project))
    assert [d.code for d in errors if d.code == "E-REFS-NOT-IN-FIGURES"] == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python -m pytest tests/test_validation_errors.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'weft.validation'`

- [ ] **Step 3: 写实现 `src/weft/validation/rules.py`**

```python
"""§4 校验规则。store 层结构诊断（解析/重复/目录）不在本模块。

软词表（spec §3.5）：purpose/role 允许超集，超词表只提醒。
rejected 卡片跳过全部提醒；错误不受豁免（见计划设计决策 2）。
"""
from __future__ import annotations

from weft.diagnostics import Diagnostic, Level
from weft.store.project import Project

PURPOSE_VOCAB = {"describe", "interpret", "compare", "transition"}
ROLE_VOCAB = {"evidence", "conclusion", "comparison", "background", "counterpoint"}


def _card_rel(project: Project, entity_id: str) -> str:
    return project.card_paths[entity_id].as_posix()


def _section_rel(project: Project, section_id: str) -> str:
    return project.section_paths[section_id].as_posix()


def _check_dangling_refs(project: Project) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for fid, fact in project.facts.items():
        rel = _card_rel(project, fid)
        for did in fact.data:
            if did not in project.data_cards:
                out.append(Diagnostic(Level.ERROR, "E-DANGLING-REF", rel, "data",
                                      f"fact 引用了不存在的 data id：{did}"))
        for cid in fact.supports:
            if cid not in project.claims:
                out.append(Diagnostic(Level.ERROR, "E-DANGLING-REF", rel, "supports",
                                      f"fact 引用了不存在的 claim id：{cid}"))
    for section in project.sections:
        rel = _section_rel(project, section.id)
        for node in section.nodes:
            for use in node.uses:
                if use.id not in project.facts and use.id not in project.claims:
                    out.append(Diagnostic(
                        Level.ERROR, "E-DANGLING-REF", rel,
                        f"nodes[{node.id}].uses",
                        f"uses 必须指向 fact/claim，但 {use.id} 不是已存在的 fact/claim"))
    return out


def _check_cites_in_bib(project: Project) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for clid, claim in project.claims.items():
        for key in claim.cites:
            if key not in project.bib_keys:
                out.append(Diagnostic(Level.ERROR, "E-CITES-NOT-IN-BIB",
                                      _card_rel(project, clid), "cites",
                                      f"cites key 不在 bib 中：{key}"))
    return out


def _check_notes_in_bib(project: Project) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for nid in project.notes:
        if nid not in project.bib_keys:
            out.append(Diagnostic(Level.ERROR, "E-NOTE-NOT-IN-BIB",
                                  _card_rel(project, nid), "id",
                                  f"note 的 id（bib key）不在 bib 中：{nid}"))
    return out


def _valid_refs(project: Project) -> set[str]:
    """合法 ref = figures.yaml 顶层键 ∪ 键+子图后缀（fig-01 + a → fig-01a）。"""
    refs = set(project.figures)
    for key, entry in project.figures.items():
        refs |= {f"{key}{sub}" for sub in entry.subfigs}
    return refs


def _check_refs_in_figures(project: Project) -> list[Diagnostic]:
    valid = _valid_refs(project)
    out: list[Diagnostic] = []
    for did, card in project.data_cards.items():
        for ref in card.refs:
            if ref not in valid:
                out.append(Diagnostic(Level.ERROR, "E-REFS-NOT-IN-FIGURES",
                                      _card_rel(project, did), "refs",
                                      f"refs 编号不在 figures.yaml 中：{ref}"))
    return out


def validate_project(project: Project) -> list[Diagnostic]:
    """交叉校验，返回错误在前（按路径/码排序）的全部诊断。"""
    diagnostics: list[Diagnostic] = []
    diagnostics += _check_dangling_refs(project)
    diagnostics += _check_cites_in_bib(project)
    diagnostics += _check_notes_in_bib(project)
    diagnostics += _check_refs_in_figures(project)

    order = {Level.ERROR: 0, Level.WARNING: 1}
    diagnostics.sort(key=lambda d: (order[d.level], d.path, d.code, d.field or ""))
    return diagnostics
```

- [ ] **Step 4: 写 `src/weft/validation/__init__.py`**

```python
from weft.validation.rules import validate_project

__all__ = ["validate_project"]
```

- [ ] **Step 5: 跑测试确认通过**

Run: `.venv/Scripts/python -m pytest tests/test_validation_errors.py -v`
Expected: `9 passed`

- [ ] **Step 6: 全量回归 + Commit**

Run: `.venv/Scripts/python -m pytest tests -v`
Expected: 全部通过

```bash
git add src/weft/validation/ tests/test_validation_errors.py
git commit -m "feat: validation 错误规则（悬空引用/bib/figures.yaml）"
```

---

### Task 9: graphgen——反向索引与可达集

**Files:**
- Create: `src/weft/graphgen/__init__.py`
- Create: `src/weft/graphgen/index.py`
- Test: `tests/test_graphgen.py`

- [ ] **Step 1: 写失败测试 `tests/test_graphgen.py`**

（writer 的 2 个用例在 Task 11 单独放 `tests/test_graphgen_writer.py`——避免本任务 import 尚不存在的 `weft.graphgen.writer` 导致整个测试模块收集失败。）

```python
from weft.graphgen.index import build_index, orphan_ids, used_ids
from weft.models.cards import ClaimCard, DataCard, FactCard, NoteCard
from weft.models.narrative import NarrativeSection, Node, Use
from tests.helpers import build_project


def _project(**overrides):
    """一个全连通的小项目：fact-01 被叙事使用，claim-01/data-01 经它可达。"""
    base = dict(
        data=[DataCard(id="data-01", status="approved")],
        facts=[FactCard(id="fact-01", data=["data-01"], statement="s",
                        supports=["claim-01"], status="approved")],
        claims=[ClaimCard(id="claim-01", claim_type="uncited", statement="s",
                          status="approved")],
        sections=[NarrativeSection(id="sec-01", section="Results", order=1, nodes=[
            Node(id="para-01-01", purpose="describe",
                 uses=[Use(id="fact-01", role="evidence")], status="approved")]),
        ],
    )
    base.update(overrides)
    return build_project(**base)


def test_index_reverse_edges():
    index = build_index(_project())
    assert index["version"] == 1
    entities = index["entities"]
    assert entities["data-01"]["kind"] == "data"
    assert entities["data-01"]["status"] == "approved"
    assert entities["data-01"]["referenced_by"]["facts"] == ["fact-01"]
    # data 经 fact 间接可达叙事节点
    assert entities["data-01"]["referenced_by"]["nodes"] == ["para-01-01"]
    assert entities["claim-01"]["referenced_by"]["facts"] == ["fact-01"]
    # claim 经 fact.supports 间接可达叙事节点
    assert entities["claim-01"]["referenced_by"]["nodes"] == ["para-01-01"]
    assert entities["fact-01"]["referenced_by"]["nodes"] == ["para-01-01"]


def test_used_ids_and_orphans():
    project = _project()
    assert used_ids(project) == {"data": ["data-01"], "facts": ["fact-01"],
                                 "claims": ["claim-01"]}
    assert orphan_ids(project) == {"data": [], "facts": [], "claims": []}


def test_orphan_excludes_rejected():
    project = _project(data=[DataCard(id="data-02", status="rejected")])
    assert orphan_ids(project)["data"] == []


def test_orphan_detected():
    project = _project(data=[DataCard(id="data-02", status="draft")])
    assert orphan_ids(project)["data"] == ["data-02"]


def test_index_includes_rejected_entities():
    # 反向索引是全量索引，rejected 也收录；筛选取决于消费方
    project = _project(data=[DataCard(id="data-02", status="rejected")])
    assert build_index(project)["entities"]["data-02"]["status"] == "rejected"


def test_index_tolerates_dangling_refs():
    # 悬空引用是 validation 的职责；build_index 必须静默跳过（Task 10 会在带错项目上调用它）
    project = _project(
        facts=[FactCard(id="fact-01", data=["data-01", "ghost-data"], statement="s",
                        supports=["claim-01", "claim-ghost"], status="approved")],
        sections=[NarrativeSection(id="sec-01", section="R", order=1, nodes=[
            Node(id="para-01-01", purpose="describe",
                 uses=[Use(id="fact-01", role="evidence"),
                       Use(id="ghost-use", role="evidence")], status="approved")]),
        ],
        claims=[ClaimCard(id="claim-01", claim_type="cited", statement="s",
                          cites=["ghost-note"], status="approved")],
    )
    index = build_index(project)  # 不得抛异常
    assert "ghost-data" not in index["entities"]
    assert "claim-ghost" not in index["entities"]
    for entry in index["entities"].values():
        for ids in entry["referenced_by"].values():
            assert not any(str(i).startswith("ghost") for i in ids)


def test_direct_claim_seed_reachable():
    # 种子规则：node.uses 直接引用的 claim 也算可达（无需 fact 支撑）
    project = _project(
        facts=[],
        sections=[NarrativeSection(id="sec-01", section="R", order=1, nodes=[
            Node(id="para-01-01", purpose="interpret",
                 uses=[Use(id="claim-01", role="conclusion")], status="approved")]),
        ],
    )
    entities = build_index(project)["entities"]
    assert entities["claim-01"]["referenced_by"]["nodes"] == ["para-01-01"]
    assert used_ids(project)["claims"] == ["claim-01"]
    assert orphan_ids(project)["claims"] == []


def test_multi_fact_partial_inheritance():
    # fact-A 被用、fact-B 未被用，都 support claim-C → claim-C 只继承 fact-A 的节点
    project = _project(
        facts=[FactCard(id="fact-01", data=["data-01"], statement="s",
                        supports=["claim-01"], status="approved"),
               FactCard(id="fact-02", data=["ghost-d"], statement="t",
                        supports=["claim-01"], status="approved")],
        sections=[NarrativeSection(id="sec-01", section="R", order=1, nodes=[
            Node(id="para-01-01", purpose="describe",
                 uses=[Use(id="fact-01", role="evidence")], status="approved")]),
        ],
    )
    entities = build_index(project)["entities"]
    assert entities["claim-01"]["referenced_by"]["nodes"] == ["para-01-01"]
    assert entities["data-01"]["referenced_by"]["nodes"] == ["para-01-01"]
    assert used_ids(project)["facts"] == ["fact-01"]  # fact-02 未被叙事使用


def test_note_reverse_edge_and_exclusion():
    project = _project(
        claims=[ClaimCard(id="claim-01", claim_type="cited", statement="s",
                          cites=["smith2020"], status="approved")],
        notes=[NoteCard(id="smith2020", summary="s", status="approved")],
    )
    entities = build_index(project)["entities"]
    assert entities["smith2020"]["referenced_by"]["claims"] == ["claim-01"]
    assert used_ids(project)["claims"] == ["claim-01"]  # note 不进 used/orphan
    # claim-01 经 fact-01.supports 继承叙事节点：可达，故不是孤儿（used/orphan 互为反集）
    assert orphan_ids(project)["claims"] == []
    # note 既不在 used 也不在 orphan：输出无 notes 类别，任何列表都不含 note id
    assert set(used_ids(project)) == {"data", "facts", "claims"}
    assert set(orphan_ids(project)) == {"data", "facts", "claims"}
    assert all("smith2020" not in ids for ids in used_ids(project).values())
    assert all("smith2020" not in ids for ids in orphan_ids(project).values())
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python -m pytest tests/test_graphgen.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'weft.graphgen'`

- [ ] **Step 3: 写实现 `src/weft/graphgen/index.py`**

```python
"""反向索引与 narrative 正向可达性（纯函数，不写文件；spec §5 graphgen 层）。

可达语义（计划设计决策 1）：种子 = 叙事节点 uses 直接引用的 fact/claim；
扩展边 = fact.data → data、fact.supports → claim。
"""
from __future__ import annotations

from weft.store.project import Project

_PLURAL = {"data": "data", "fact": "facts", "claim": "claims"}


def _kind(entities: dict, eid: str) -> str | None:
    entry = entities.get(eid)
    return entry["kind"] if entry else None


def _edge(entities: dict, target_id: str, field: str, source_id: str,
          expected_kind: str) -> None:
    if _kind(entities, target_id) == expected_kind:
        entities[target_id]["referenced_by"][field].append(source_id)


def build_index(project: Project) -> dict:
    """全量反向索引（含 rejected；消费方自行过滤）。

    referenced_by.facts : data ← fact.data / claim ← fact.supports
    referenced_by.claims: note ← claim.cites
    referenced_by.nodes : 正向可达的叙事节点（fact/claim 为直接 uses；
                          data 与被 supports 的 claim 经引用它们的 fact 间接可达）
    """
    entities: dict[str, dict] = {}
    for kind, cards in (("data", project.data_cards), ("fact", project.facts),
                        ("claim", project.claims), ("note", project.notes)):
        for cid, card in cards.items():
            entities[cid] = {"kind": kind, "status": card.status,
                             "referenced_by": {"facts": [], "claims": [], "nodes": []}}

    for fid, fact in project.facts.items():
        for did in fact.data:
            _edge(entities, did, "facts", fid, "data")
        for clid in fact.supports:
            _edge(entities, clid, "facts", fid, "claim")
    for clid, claim in project.claims.items():
        for key in claim.cites:
            _edge(entities, key, "claims", clid, "note")

    for section in project.sections:
        for node in section.nodes:
            for use in node.uses:
                if _kind(entities, use.id) in ("fact", "claim"):
                    entities[use.id]["referenced_by"]["nodes"].append(node.id)

    # data / 被 supports 的 claim：继承引用它们的 fact 的节点（间接可达）
    for fid, fact in project.facts.items():
        fact_nodes = entities[fid]["referenced_by"]["nodes"]
        if not fact_nodes:
            continue
        for did in fact.data:
            if _kind(entities, did) == "data":
                entities[did]["referenced_by"]["nodes"].extend(fact_nodes)
        for clid in fact.supports:
            if _kind(entities, clid) == "claim":
                entities[clid]["referenced_by"]["nodes"].extend(fact_nodes)

    for entry in entities.values():
        entry["referenced_by"] = {k: sorted(set(v))
                                  for k, v in entry["referenced_by"].items()}

    return {"version": 1, "entities": entities}


def used_ids(project: Project) -> dict[str, list[str]]:
    """narrative 正向可达的实体（按类别；note 不参与，叙事不直接引用 note）。"""
    index = build_index(project)
    used: dict[str, list[str]] = {"data": [], "facts": [], "claims": []}
    for eid, entry in index["entities"].items():
        if entry["kind"] != "note" and entry["referenced_by"]["nodes"]:
            used[_PLURAL[entry["kind"]]].append(eid)
    for ids in used.values():
        ids.sort()
    return used


def orphan_ids(project: Project) -> dict[str, list[str]]:
    """used 的反集（排除 rejected 与 note）。"""
    index = build_index(project)
    orphans: dict[str, list[str]] = {"data": [], "facts": [], "claims": []}
    for eid, entry in index["entities"].items():
        if entry["kind"] == "note" or entry["status"] == "rejected":
            continue
        if not entry["referenced_by"]["nodes"]:
            orphans[_PLURAL[entry["kind"]]].append(eid)
    for ids in orphans.values():
        ids.sort()
    return orphans
```

- [ ] **Step 4: 写 `src/weft/graphgen/__init__.py`**

```python
from weft.graphgen.index import build_index, orphan_ids, used_ids

__all__ = ["build_index", "orphan_ids", "used_ids"]
```

- [ ] **Step 5: 跑测试确认通过**

Run: `.venv/Scripts/python -m pytest tests/test_graphgen.py -v`
Expected: `9 passed`

- [ ] **Step 6: Commit**

```bash
git add src/weft/graphgen/ tests/test_graphgen.py
git commit -m "feat: graphgen 反向索引与 narrative 正向可达集"
```

---

### Task 10: validation——提醒规则

**Files:**
- Modify: `src/weft/validation/rules.py`（追加 6 个提醒检查函数并注册进 `validate_project`；引入 graphgen 可达集）
- Test: `tests/test_validation_warnings.py`

- [ ] **Step 1: 写失败测试 `tests/test_validation_warnings.py`**

```python
from weft.models.cards import ClaimCard, DataCard, FactCard, NoteCard
from weft.models.figures import FigureEntry
from weft.models.narrative import NarrativeSection, Node, Use
from weft.validation import validate_project
from tests.helpers import build_project


def _codes(diagnostics):
    return [d.code for d in diagnostics]


def _fact_used_by_narrative():
    return (
        [FactCard(id="fact-01", data=["data-01"], statement="s", status="approved")],
        [NarrativeSection(id="sec-01", section="R", order=1, nodes=[
            Node(id="para-01-01", purpose="describe",
                 uses=[Use(id="fact-01", role="evidence")], status="approved")]),
        ],
    )


def test_cited_without_cites_warns():
    claims = [ClaimCard(id="claim-01", claim_type="cited", statement="s",
                        status="approved")]
    project = build_project(claims=claims)
    assert "W-CLAIM-CITED-NO-CITES" in _codes(validate_project(project))


def test_rejected_claim_skips_warnings_but_not_errors():
    claims = [ClaimCard(id="claim-01", claim_type="cited", statement="s",
                        cites=["ghostkey"], status="rejected")]
    project = build_project(claims=claims, bib_keys=set())
    diagnostics = validate_project(project)
    assert "W-CLAIM-CITED-NO-CITES" not in _codes(diagnostics)
    # 错误不受 rejected 豁免（设计决策 2）
    assert "E-CITES-NOT-IN-BIB" in _codes(diagnostics)


def test_uncited_claim_without_fact_support_warns():
    claims = [ClaimCard(id="claim-01", claim_type="uncited", statement="s",
                        status="approved")]
    project = build_project(claims=claims)
    assert "W-CLAIM-UNSUPPORTED" in _codes(validate_project(project))


def test_supported_claim_no_warning():
    claims = [ClaimCard(id="claim-01", claim_type="uncited", statement="s",
                        status="approved")]
    facts = [FactCard(id="fact-01", data=["data-01"], statement="s",
                      supports=["claim-01"], status="approved")]
    project = build_project(data=[DataCard(id="data-01", status="approved")],
                            facts=facts, claims=claims)
    assert "W-CLAIM-UNSUPPORTED" not in _codes(validate_project(project))


def test_unsupported_ignores_rejected_facts():
    claims = [ClaimCard(id="claim-01", claim_type="uncited", statement="s",
                        status="draft")]
    facts = [FactCard(id="fact-01", data=["data-01"], statement="s",
                      supports=["claim-01"], status="rejected")]
    project = build_project(data=[DataCard(id="data-01", status="approved")],
                            facts=facts, claims=claims)
    assert "W-CLAIM-UNSUPPORTED" in _codes(validate_project(project))


def test_orphan_data_warns():
    data = [DataCard(id="data-01", status="approved")]
    project = build_project(data=data)
    assert "W-ORPHAN" in _codes(validate_project(project))


def test_data_reachable_via_fact_not_orphan():
    facts, sections = _fact_used_by_narrative()
    project = build_project(data=[DataCard(id="data-01", status="approved")],
                            facts=facts, sections=sections)
    assert "W-ORPHAN" not in _codes(validate_project(project))


def test_claim_reached_only_via_supports_is_used():
    # fact-01 被叙事使用，其 supports 的 claim-01 算可达 → 非孤儿（设计决策 1）
    claims = [ClaimCard(id="claim-01", claim_type="uncited", statement="s",
                        status="approved")]
    facts = [FactCard(id="fact-01", data=["data-01"], statement="s",
                      supports=["claim-01"], status="approved")]
    sections = [NarrativeSection(id="sec-01", section="R", order=1, nodes=[
        Node(id="para-01-01", purpose="describe",
             uses=[Use(id="fact-01", role="evidence")], status="approved")]),
    ]
    project = build_project(data=[DataCard(id="data-01", status="approved")],
                            facts=facts, claims=claims, sections=sections)
    assert "W-ORPHAN" not in _codes(validate_project(project))


def test_figure_file_missing_only_for_fig_refs(tmp_path):
    (tmp_path / "figures").mkdir()
    data = [DataCard(id="data-01", status="approved", refs=["fig-01a", "tbl-01"])]
    figures = {"fig-01": FigureEntry(caption="c", subfigs={"a": "s"}),
               "tbl-01": FigureEntry(caption="t")}
    project = build_project(root=tmp_path, data=data, figures=figures)
    codes = _codes(validate_project(project))
    assert codes.count("W-FIGURE-FILE-MISSING") == 1  # 只查 fig-01a；tbl-01 不查文件


def test_figure_file_present_no_warning(tmp_path):
    fig_dir = tmp_path / "figures"
    fig_dir.mkdir()
    (fig_dir / "fig-01a.png").write_bytes(b"x")
    facts, sections = _fact_used_by_narrative()
    project = build_project(
        root=tmp_path,
        data=[DataCard(id="data-01", status="approved", refs=["fig-01a"])],
        facts=facts, figures={"fig-01": FigureEntry(caption="c", subfigs={"a": "s"})},
        sections=sections)
    assert "W-FIGURE-FILE-MISSING" not in _codes(validate_project(project))


def test_unused_figure_entry_warns():
    data = [DataCard(id="data-01", status="approved", refs=["fig-01a"])]
    figures = {"fig-01": FigureEntry(caption="c", subfigs={"a": "s"}),
               "fig-02": FigureEntry(caption="没人用")}
    project = build_project(data=data, figures=figures)
    diagnostics = validate_project(project)
    unused = [d for d in diagnostics if d.code == "W-FIGURE-UNUSED"]
    assert len(unused) == 1
    assert unused[0].field == "fig-02"
    assert unused[0].path == "metadata/figures.yaml"


def test_note_without_summary_warns():
    project = build_project(notes=[NoteCard(id="k2020", status="approved")],
                            bib_keys={"k2020"})
    diagnostics = validate_project(project)
    warn = [d for d in diagnostics if d.code == "W-NOTE-NO-SUMMARY"]
    assert len(warn) == 1 and warn[0].field == "summary"


def test_note_missing_for_cited_key_warns():
    # §3.4：key 在 bib 但无 note 卡 → 提醒
    claims = [ClaimCard(id="claim-01", claim_type="cited", statement="s",
                        cites=["real2020"], status="approved")]
    project = build_project(claims=claims, bib_keys={"real2020"})
    diagnostics = validate_project(project)
    warn = [d for d in diagnostics if d.code == "W-NOTE-MISSING"]
    assert len(warn) == 1
    assert "real2020" in warn[0].message


def test_purpose_and_role_vocab_warnings():
    facts, sections = _fact_used_by_narrative()
    sections = [NarrativeSection(id="sec-01", section="R", order=1, nodes=[
        Node(id="para-01-01", purpose="speculate",
             uses=[Use(id="fact-01", role="vibe")], status="approved")]),
    ]
    project = build_project(data=[DataCard(id="data-01", status="approved")],
                            facts=facts, sections=sections)
    codes = _codes(validate_project(project))
    assert "W-PURPOSE-VOCAB" in codes
    assert "W-ROLE-VOCAB" in codes


def test_rejected_suppression_scoped_to_card_across_rules(tmp_path):
    # 设计决策 2 的另一半：rejected 卡对图注/词表/summary 规则同样豁免，
    # 但 W-FIGURE-UNUSED（figures.yaml 视角）与 approved 侧提醒不受影响。
    data = [DataCard(id="data-01", status="rejected", refs=["fig-01a"])]
    facts = [FactCard(id="fact-01", data=["data-01"], statement="s", status="approved")]
    claims = [ClaimCard(id="claim-01", claim_type="uncited", statement="s",
                        status="approved")]
    notes = [NoteCard(id="k2020", status="rejected")]  # rejected 且无 summary
    figures = {"fig-01": FigureEntry(caption="c", subfigs={"a": "s"})}
    sections = [NarrativeSection(id="sec-01", section="R", order=1, nodes=[
        # uses 让 approved 的 fact/claim 可达（否则 W-ORPHAN 会照报它们）；
        # claim-01 经直接 use 可达但仍无 fact 支持 → W-CLAIM-UNSUPPORTED 保留
        Node(id="para-01-01", purpose="speculate", status="approved",
             uses=[Use(id="fact-01", role="evidence"),
                   Use(id="claim-01", role="evidence")]),  # approved 故意用错词，应报
    ])]
    project = build_project(root=tmp_path, data=data, facts=facts, claims=claims,
                            notes=notes, figures=figures, bib_keys={"k2020"},
                            sections=sections)
    codes = _codes(validate_project(project))
    assert "W-FIGURE-FILE-MISSING" not in codes      # rejected data 卡豁免
    assert "W-NOTE-NO-SUMMARY" not in codes          # rejected note 豁免
    assert "W-ORPHAN" not in codes                   # rejected data 不进孤儿报告
    assert "W-FIGURE-UNUSED" in codes                # figures.yaml 视角：fig-01 无有效引用
    assert "W-PURPOSE-VOCAB" in codes                # approved 节点错词照报
    assert "W-CLAIM-UNSUPPORTED" in codes            # approved 侧提醒不受影响


def test_diagnostics_sorted_errors_first_by_path():
    # 排序契约：错误在前（Task 12 CLI 输出依赖），错误内按 path 排序
    from weft.diagnostics import Level
    data = [DataCard(id="data-02", status="approved", refs=["fig-99z"])]
    facts = [FactCard(id="fact-01", data=["data-99"], statement="s", status="approved")]
    project = build_project(data=data, facts=facts)
    diagnostics = validate_project(project)
    assert any(not d.is_error for d in diagnostics)  # 确有提醒参与排序
    levels = [d.level for d in diagnostics]
    assert levels == sorted(levels, key=lambda lv: 0 if lv is Level.ERROR else 1)
    error_paths = [d.path for d in diagnostics if d.is_error]
    assert error_paths == sorted(error_paths)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python -m pytest tests/test_validation_warnings.py -v`
Expected: FAIL（各 W-\* 码尚未产生）

- [ ] **Step 3: 扩展 `src/weft/validation/rules.py`**

在文件顶部 import 区加入：

```python
from weft.graphgen.index import build_index
```

在 `_check_refs_in_figures` 之后追加六个检查函数：

```python
def _check_claims(project: Project) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    supported = {cid
                 for fact in project.facts.values()
                 if fact.status != "rejected"
                 for cid in fact.supports}
    for clid, claim in project.claims.items():
        if claim.status == "rejected":
            continue
        rel = _card_rel(project, clid)
        if claim.claim_type == "cited" and not claim.cites:
            out.append(Diagnostic(Level.WARNING, "W-CLAIM-CITED-NO-CITES", rel,
                                  "cites", "claim_type 为 cited 但 cites 为空（缺引文提醒）"))
        if claim.claim_type == "uncited" and clid not in supported:
            out.append(Diagnostic(Level.WARNING, "W-CLAIM-UNSUPPORTED", rel, None,
                                  "uncited claim 没有任何非 rejected 的 fact 支持它"))
    return out


def _check_figures_files(project: Project) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    fig_dir = project.root / project.figures_dir
    referenced: set[str] = set()
    for card in project.data_cards.values():
        if card.status == "rejected":
            continue
        for ref in card.refs:
            referenced.add(ref)
            # 表格（tbl-*）是排版产物不是图片文件，不检查 figures/ 目录
            if ref.startswith("fig-") \
                    and not (fig_dir / f"{ref}.png").exists() \
                    and not (fig_dir / f"{ref}.pdf").exists():
                out.append(Diagnostic(
                    Level.WARNING, "W-FIGURE-FILE-MISSING", _card_rel(project, card.id),
                    "refs", f"图文件缺失：{project.figures_dir}/{ref}.png|pdf"))
    for key, entry in project.figures.items():
        used = key in referenced or any(f"{key}{sub}" in referenced for sub in entry.subfigs)
        if not used:
            out.append(Diagnostic(Level.WARNING, "W-FIGURE-UNUSED",
                                  "metadata/figures.yaml", key,
                                  f"figures.yaml 中的图没有被任何 data 卡引用：{key}"))
    return out


def _check_orphans(project: Project) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for eid, entry in build_index(project)["entities"].items():
        if entry["kind"] == "note" or entry["status"] == "rejected":
            continue
        if not entry["referenced_by"]["nodes"]:
            out.append(Diagnostic(Level.WARNING, "W-ORPHAN", _card_rel(project, eid),
                                  None, "孤儿实体：未被任何叙事节点引用（含间接可达）"))
    return out


def _check_notes_summary(project: Project) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for nid, note in project.notes.items():
        if note.status != "rejected" and not note.summary.strip():
            out.append(Diagnostic(Level.WARNING, "W-NOTE-NO-SUMMARY",
                                  _card_rel(project, nid), "summary",
                                  "note 缺少 summary（该引文处 AI 只能凭 bib 条目行文）"))
    return out


def _check_note_cards_exist(project: Project) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for clid, claim in project.claims.items():
        if claim.status == "rejected":
            continue
        for key in claim.cites:
            if key in project.bib_keys and key not in project.notes:
                out.append(Diagnostic(Level.WARNING, "W-NOTE-MISSING",
                                      _card_rel(project, clid), "cites",
                                      f"引文 {key} 在 bib 中但没有 note 卡"
                                      "（该引文处 AI 只能凭 bib 条目行文）"))
    return out


def _check_vocab(project: Project) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for section in project.sections:
        rel = _section_rel(project, section.id)
        for node in section.nodes:
            if node.status == "rejected":
                continue
            if node.purpose not in PURPOSE_VOCAB:
                out.append(Diagnostic(
                    Level.WARNING, "W-PURPOSE-VOCAB", rel,
                    f"nodes[{node.id}].purpose",
                    f"purpose 不在词表 {sorted(PURPOSE_VOCAB)}：{node.purpose}"))
            for i, use in enumerate(node.uses):
                if use.role not in ROLE_VOCAB:
                    out.append(Diagnostic(
                        Level.WARNING, "W-ROLE-VOCAB", rel,
                        f"nodes[{node.id}].uses[{i}].role",
                        f"role 不在词表 {sorted(ROLE_VOCAB)}：{use.role}"))
    return out
```

并把 `validate_project` 的诊断聚合段改为：

```python
    diagnostics: list[Diagnostic] = []
    diagnostics += _check_dangling_refs(project)
    diagnostics += _check_cites_in_bib(project)
    diagnostics += _check_notes_in_bib(project)
    diagnostics += _check_refs_in_figures(project)
    diagnostics += _check_claims(project)
    diagnostics += _check_figures_files(project)
    diagnostics += _check_orphans(project)
    diagnostics += _check_notes_summary(project)
    diagnostics += _check_note_cards_exist(project)
    diagnostics += _check_vocab(project)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python -m pytest tests/test_validation_warnings.py -v`
Expected: `16 passed`

- [ ] **Step 5: 全量回归 + Commit**

Run: `.venv/Scripts/python -m pytest tests -v`
Expected: 全部通过（Task 8 的 `test_clean_project_has_no_diagnostics` 必须仍然全绿——它同时覆盖"无提醒"）

```bash
git add src/weft/validation/ tests/test_validation_warnings.py
git commit -m "feat: validation 提醒规则（缺引文/孤儿/图注/软词表/note 缺卡）"
```

---

### Task 11: graphgen——输出文件

**Files:**
- Create: `src/weft/graphgen/writer.py`
- Modify: `src/weft/graphgen/__init__.py`
- Test: `tests/test_graphgen_writer.py`

- [ ] **Step 1: 写失败测试 `tests/test_graphgen_writer.py`**

```python
import json
from pathlib import Path

from weft.graphgen.index import build_index
from weft.graphgen.writer import write_outputs
from weft.models.cards import DataCard, FactCard
from weft.models.narrative import NarrativeSection, Node, Use
from tests.helpers import build_project


def _project(root=None, data=None):
    """全连通小项目：fact-01 被叙事使用，data-01 经它可达。"""
    return build_project(
        root=root or Path("."),
        data=data or [DataCard(id="data-01", status="approved")],
        facts=[FactCard(id="fact-01", data=["data-01"], statement="s", status="approved")],
        sections=[NarrativeSection(id="sec-01", section="Results", order=1, nodes=[
            Node(id="para-01-01", purpose="describe",
                 uses=[Use(id="fact-01", role="evidence")], status="approved")]),
        ],
    )


def test_writer_outputs(tmp_path):
    project = _project(root=tmp_path)
    paths = write_outputs(project, tmp_path / "generated")
    assert [p.name for p in paths] == ["graph.json", "used-metadata.json", "orphans.md"]
    graph = json.loads((tmp_path / "generated" / "graph.json").read_text(encoding="utf-8"))
    assert graph == build_index(project)
    used = json.loads(
        (tmp_path / "generated" / "used-metadata.json").read_text(encoding="utf-8"))
    assert used == {"data": ["data-01"], "facts": ["fact-01"], "claims": []}
    orphans = (tmp_path / "generated" / "orphans.md").read_text(encoding="utf-8")
    assert "无孤儿实体" in orphans


def test_orphans_md_lists_paths(tmp_path):
    project = _project(root=tmp_path, data=[
        DataCard(id="data-01", status="approved"),
        DataCard(id="data-02", status="draft"),
    ])
    write_outputs(project, tmp_path / "generated")
    text = (tmp_path / "generated" / "orphans.md").read_text(encoding="utf-8")
    assert "data-02（data）— metadata/data-02.md" in text
    assert "data-01（data）" not in text
    raw = (tmp_path / "generated" / "orphans.md").read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python -m pytest tests/test_graphgen_writer.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'weft.graphgen.writer'`

- [ ] **Step 3: 写实现 `src/weft/graphgen/writer.py`**

```python
"""把索引与可达集写入 generated/：graph.json、used-metadata.json、orphans.md。

JSON 统一 ensure_ascii=False + sort_keys=True + 尾部换行 + LF（newline="\n"，
平台无关），保证输出字节级确定（可黄金比对）。
"""
from __future__ import annotations

import json
from pathlib import Path

from weft.graphgen.index import build_index, orphan_ids, used_ids
from weft.store.project import Project


def write_outputs(project: Project, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    graph = build_index(project)
    used = used_ids(project)
    orphans = orphan_ids(project)

    graph_path = out_dir / "graph.json"
    used_path = out_dir / "used-metadata.json"
    orphans_path = out_dir / "orphans.md"

    graph_path.write_text(_to_json(graph), encoding="utf-8", newline="\n")
    used_path.write_text(_to_json(used), encoding="utf-8", newline="\n")
    orphans_path.write_text(_orphans_md(project, orphans), encoding="utf-8", newline="\n")
    return [graph_path, used_path, orphans_path]


def _to_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _orphans_md(project: Project, orphans: dict[str, list[str]]) -> str:
    lines = ["# 孤儿实体报告", ""]
    total = sum(len(ids) for ids in orphans.values())
    if total == 0:
        lines.append("无孤儿实体。")
        return "\n".join(lines) + "\n"
    lines += ["未被任何叙事节点引用（含间接可达）的实体：", ""]
    titles = {"data": "data", "facts": "fact", "claims": "claim"}
    for group, ids in orphans.items():
        for eid in ids:
            path = project.card_paths.get(eid, Path("?")).as_posix()
            lines.append(f"- {eid}（{titles[group]}）— {path}")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: 更新 `src/weft/graphgen/__init__.py`**

```python
from weft.graphgen.index import build_index, orphan_ids, used_ids
from weft.graphgen.writer import write_outputs

__all__ = ["build_index", "orphan_ids", "used_ids", "write_outputs"]
```

- [ ] **Step 5: 跑测试确认通过**

Run: `.venv/Scripts/python -m pytest tests/test_graphgen_writer.py tests/test_graphgen.py -v`
Expected: `7 passed`（writer 2 + index 5）

- [ ] **Step 6: 全量回归 + Commit**

Run: `.venv/Scripts/python -m pytest tests -v`
Expected: 全部通过

```bash
git add src/weft/graphgen/ tests/test_graphgen_writer.py
git commit -m "feat: graphgen 落盘 graph.json/used-metadata.json/orphans.md"
```

---

### Task 12: CLI——`weft validate`

**Files:**
- Create: `src/weft/cli.py`
- Test: `tests/test_cli.py`

**注意**：typer 在只有一个 `@app.command()` 时会把应用当单命令处理（子命令名会被吃掉）。因此本任务一次性注册全部三个命令，`graph`/`review` 先放占位实现，Task 13/14 各自替换。

- [ ] **Step 1: 写失败测试 `tests/test_cli.py`**

```python
from typer.testing import CliRunner

from weft.cli import app
from tests.helpers import make_minimal_project, write_card

runner = CliRunner()


def test_validate_clean_project(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["validate", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "0 个错误，0 个提醒" in result.output


def test_validate_error_exits_1(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "facts", "fact-02",
               {"id": "fact-02", "data": ["data-99"], "statement": "s",
                "status": "draft"})
    result = runner.invoke(app, ["validate", str(tmp_path)])
    assert result.exit_code == 1
    assert "E-DANGLING-REF" in result.output
    assert "1 个错误" in result.output


def test_validate_warning_only_exits_0(tmp_path):
    make_minimal_project(tmp_path)
    # claim-02：cited 且 cites 空 → 纯提醒
    write_card(tmp_path / "metadata" / "claims" / "cited", "claim-02",
               {"id": "claim-02", "claim_type": "cited", "statement": "s",
                "status": "draft"})
    result = runner.invoke(app, ["validate", str(tmp_path)])
    assert result.exit_code == 0
    assert "W-CLAIM-CITED-NO-CITES" in result.output
    assert "0 个错误" in result.output


def test_validate_not_a_project(tmp_path):
    result = runner.invoke(app, ["validate", str(tmp_path)])
    assert result.exit_code == 1
    assert "E-NOT-A-PROJECT" in result.output
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python -m pytest tests/test_cli.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'weft.cli'`

- [ ] **Step 3: 写实现 `src/weft/cli.py`**

```python
"""typer 入口：weft validate / graph / review（spec §8，M1 交付前三个）。"""
from __future__ import annotations

import sys
from pathlib import Path

import typer

from weft.diagnostics import Diagnostic
from weft.store.loader import load_project
from weft.validation import validate_project

app = typer.Typer(add_completion=False,
                  help="weft —— 元数据为经线、叙事流为纬线的 AI 学术写作引擎")


def _ensure_utf8_stdout() -> None:
    """Windows 重定向输出默认 GBK，中文诊断会 UnicodeEncodeError；统一切 UTF-8。

    在模块导入时执行一次：除命令输出外，--help 与 typer 的用法错误提示也一并覆盖。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.encoding and stream.encoding.lower() not in ("utf-8", "utf8"):
                stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass


_ensure_utf8_stdout()


def _print_diagnostics(diagnostics: list[Diagnostic]) -> None:
    for d in diagnostics:
        prefix = "ERROR" if d.is_error else "WARN "
        field = f" 字段 {d.field}:" if d.field else ""
        typer.echo(f"{prefix} {d.path} [{d.code}]{field} {d.message}")


@app.command()
def validate(project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录")) -> None:
    """运行 §4 全部校验，报告错误与提醒；有错误时退出码 1。"""
    project, load_diags = load_project(project_dir)
    diagnostics = load_diags + validate_project(project)
    _print_diagnostics(diagnostics)
    n_errors = sum(1 for d in diagnostics if d.is_error)
    typer.echo(f"—— {n_errors} 个错误，{len(diagnostics) - n_errors} 个提醒")
    if n_errors:
        raise typer.Exit(code=1)


@app.command()
def graph(project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录")) -> None:
    """生成 generated/graph.json、used-metadata.json、orphans.md。"""
    typer.echo("尚未实现（M1 Task 13）")
    raise typer.Exit(code=2)


@app.command()
def review(project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录")) -> None:
    """按类型列出未审阅（status: draft）的实体与叙事节点。"""
    typer.echo("尚未实现（M1 Task 14）")
    raise typer.Exit(code=2)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python -m pytest tests/test_cli.py -v`
Expected: `4 passed`

- [ ] **Step 5: 真实环境冒烟（验证 console script 与 UTF-8 输出）**

```bash
"C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/weft" --help
```

Expected: 打印 `Usage: weft [OPTIONS] COMMAND [ARGS]...` 与 `validate / graph / review` 三个子命令。

- [ ] **Step 6: 全量回归 + Commit**

Run: `.venv/Scripts/python -m pytest tests -v`
Expected: 全部通过

```bash
git add src/weft/cli.py tests/test_cli.py
git commit -m "feat: CLI 骨架与 weft validate（typer，UTF-8 输出，退出码语义）"
```

---

### Task 13: CLI——`weft graph`

**Files:**
- Modify: `src/weft/cli.py`（替换 `graph` 命令体；新增 import）
- Test: `tests/test_cli.py`（追加）

- [ ] **Step 1: 追加失败测试到 `tests/test_cli.py`**

在文件末尾追加：

```python
def test_graph_blocked_by_errors(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "notes", "ghostkey",
               {"id": "ghostkey", "summary": "s", "status": "draft"})
    result = runner.invoke(app, ["graph", str(tmp_path)])
    assert result.exit_code == 1
    assert "E-NOTE-NOT-IN-BIB" in result.output
    assert "拒绝生成" in result.output
    assert not (tmp_path / "generated").exists()  # 错误路径连目录都不该建


def test_graph_writes_outputs(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["graph", str(tmp_path)])
    assert result.exit_code == 0, result.output
    for name in ("graph.json", "used-metadata.json", "orphans.md"):
        assert (tmp_path / "generated" / name).exists()
    assert "generated/graph.json" in result.output
    assert "generated/used-metadata.json" in result.output
    assert "generated/orphans.md" in result.output


def test_graph_prints_warnings_after_writes(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "claims" / "cited", "claim-02",
               {"id": "claim-02", "claim_type": "cited", "statement": "s",
                "status": "draft"})
    result = runner.invoke(app, ["graph", str(tmp_path)])
    assert result.exit_code == 0, result.output
    warn_pos = result.output.index("W-CLAIM-CITED-NO-CITES")
    write_pos = result.output.index("已写入 generated/orphans.md")
    assert write_pos < warn_pos


def test_graph_generated_occupied_by_file(tmp_path):
    make_minimal_project(tmp_path)
    (tmp_path / "generated").write_text("占位", encoding="utf-8")
    result = runner.invoke(app, ["graph", str(tmp_path)])
    assert result.exit_code == 1
    assert "无法写入" in result.output
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python -m pytest tests/test_cli.py -v`
Expected: 新增用例 FAIL（当前 graph 是占位实现）

- [ ] **Step 3: 实现 `graph` 命令**

`src/weft/cli.py` 顶部 import 区加入：

```python
from weft.graphgen.writer import write_outputs
```

把 `graph` 命令体替换为：

```python
@app.command()
def graph(project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录")) -> None:
    """生成 generated/graph.json、used-metadata.json、orphans.md；校验有错误时拒绝。"""
    project, load_diags = load_project(project_dir)
    diagnostics = load_diags + validate_project(project)
    if any(d.is_error for d in diagnostics):
        _print_diagnostics(diagnostics)
        typer.echo("—— 校验存在错误，拒绝生成反向索引")
        raise typer.Exit(code=1)
    written = None
    try:
        written = write_outputs(project, project.root / "generated")
    except OSError as exc:
        typer.echo(f"ERROR 无法写入 generated/：{exc}")
        raise typer.Exit(code=1) from exc
    for path in written:
        typer.echo(f"已写入 {path.relative_to(project.root).as_posix()}")
    warnings = [d for d in diagnostics if not d.is_error]
    if warnings:
        _print_diagnostics(warnings)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python -m pytest tests/test_cli.py -v`
Expected: `8 passed`

- [ ] **Step 5: 全量回归 + Commit**

Run: `.venv/Scripts/python -m pytest tests -v`
Expected: 全部通过（86 + 4 = 90 个）

```bash
git add src/weft/cli.py tests/test_cli.py
git commit -m "feat: weft graph 命令（错误阻断，写 generated/ 三产物）"
```

---

### Task 14: CLI——`weft review`

**Files:**
- Modify: `src/weft/cli.py`（替换 `review` 命令体；新增 `_print_review` 与 import）
- Test: `tests/test_cli.py`（追加）

- [ ] **Step 1: 追加失败测试到 `tests/test_cli.py`**

在文件末尾追加：

```python
def test_review_lists_draft_items(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "data", "data-02",
               {"id": "data-02", "refs": [], "status": "draft"})
    result = runner.invoke(app, ["review", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "data-02" in result.output
    assert "metadata/data/data-02.md" in result.output
    # approved 的叙事节点不出现
    assert "para-01-01" not in result.output


def test_review_empty_when_all_approved(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["review", str(tmp_path)])
    assert result.exit_code == 0
    assert "（无）" in result.output


def test_review_reports_load_errors(tmp_path):
    # 非项目目录：加载失败直接报错退出
    result = runner.invoke(app, ["review", str(tmp_path)])
    assert result.exit_code == 1
    assert "E-NOT-A-PROJECT" in result.output


def test_review_lists_draft_nodes(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "narrative", "02-discussion",
               {"id": "sec-02", "section": "Discussion", "order": 2,
                "nodes": [{"id": "para-02-01", "purpose": "interpret", "uses": [],
                           "status": "draft"},
                          {"id": "para-02-02", "purpose": "compare", "uses": [],
                           "status": "approved"}]})
    result = runner.invoke(app, ["review", str(tmp_path)])
    assert result.exit_code == 0, result.output
    # draft 节点以 节id/段id 复合形式列出，路径为叙事文件
    assert "sec-02/para-02-01" in result.output
    assert "narrative/02-discussion.md" in result.output
    # 同节的 approved 兄弟节点不出现
    assert "para-02-02" not in result.output
    # approved 的 sec-01/para-01-01 也不出现
    assert "para-01-01" not in result.output
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python -m pytest tests/test_cli.py -v`
Expected: 新增 3 个用例 FAIL

- [ ] **Step 3: 实现 `review` 命令**

`src/weft/cli.py` 顶部 import 区加入：

```python
from weft.store.project import Project
```

在 `_print_diagnostics` 之后追加：

```python
def _print_review(project: Project) -> None:
    typer.echo("待审阅实体（status: draft）：")
    groups = (("data", project.data_cards), ("fact", project.facts),
              ("claim", project.claims), ("note", project.notes))
    entity_found = False
    for label, cards in groups:
        for cid, card in cards.items():
            if card.status == "draft":
                entity_found = True
                rel = project.card_paths[cid].as_posix()
                typer.echo(f"  {label}  {cid}  {rel}")
    if not entity_found:
        typer.echo("  （无）")
    typer.echo("待审阅叙事节点：")
    node_found = False
    for section in project.sections:
        for node in section.nodes:
            if node.status == "draft":
                node_found = True
                rel = project.section_paths[section.id].as_posix()
                typer.echo(f"  {section.id}/{node.id}  {rel}")
    if not node_found:
        typer.echo("  （无）")
```

把 `review` 命令体替换为：

```python
@app.command()
def review(project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录")) -> None:
    """按类型列出未审阅（status: draft）的实体与叙事节点。"""
    project, load_diags = load_project(project_dir)
    if any(d.is_error for d in load_diags):
        _print_diagnostics(load_diags)
        raise typer.Exit(code=1)
    _print_review(project)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python -m pytest tests/test_cli.py -v`
Expected: `11 passed`

- [ ] **Step 5: 全量回归 + Commit**

Run: `.venv/Scripts/python -m pytest tests -v`
Expected: 全部通过（94 个）

```bash
git add src/weft/cli.py tests/test_cli.py
git commit -m "feat: weft review 命令（draft 实体与叙事节点审阅清单）"
```

---

### Task 15: 样例项目与 M1 验收

**Files:**
- Create: `examples/paper-demo/` 全套文件（目录结构见 spec §3.8）
- Create: `tests/golden/graph.json`、`tests/golden/used-metadata.json`
- Test: `tests/test_example_project.py`

样例内容 = spec 各节示例扩展成的自洽"结果与讨论"小论文：3 张 data 卡、2 张 fact 卡、3 张 claim 卡（uncited×1 + cited×2，其中 claim-03 为 draft 以演示审阅清单）、2 张 note 卡、2 个叙事节（4 个节点，2 个 draft）、1 图 1 表。**验收标准：`weft validate` = 0 错误 0 提醒。**

- [ ] **Step 1: 写 `examples/paper-demo/_quarto.yml`**

```yaml
project:
  type: default

bibliography: references.bib

crossref:
  fig-prefix: "Fig."
  tbl-prefix: "Table"
  subref-prefix: "Fig."
```

- [ ] **Step 2: 写 `examples/paper-demo/index.qmd`**

```markdown
---
title: "温度对反应速率的影响"
format:
  html:
    toc: true
---

## 摘要（占位）

M1 阶段仅提供项目骨架；正文由 M2/M3 的生成与组装流水线产出。
```

- [ ] **Step 3: 写 `examples/paper-demo/references.bib`**

```bibtex
@article{smith2020,
  author  = {Smith, Jane and Lee, Kyung},
  title   = {Thermally activated catalysis in batch reactors},
  journal = {Journal of Thermal Chemistry},
  year    = {2020},
  volume  = {12},
  pages   = {45--58}
}

@article{doe2021,
  author  = {Doe, John and Wang, Lei},
  title   = {Platinum-based catalysis across temperature gradients},
  journal = {Catalysis Today},
  year    = {2021},
  volume  = {8},
  pages   = {101--115}
}
```

- [ ] **Step 4: 写 `examples/paper-demo/metadata/figures.yaml`**

```yaml
fig-01:
  caption: "不同温度下的反应速率随时间变化。误差线表示三次重复的标准差。"
  subfigs:
    a: "60 °C 下的速率曲线"
    b: "25 °C 下的速率曲线"
tbl-01:
  caption: "各温度条件下的反应条件与初始速率汇总。"
```

- [ ] **Step 5: 写三张 data 卡**

`examples/paper-demo/metadata/data/data-01.md`：

```markdown
---
id: data-01
refs: [fig-01a]
source: "../../data/raw/run-60c.csv"
description: "60 °C 下三次重复反应的速率-时间测量值（每 5 分钟取样）"
status: approved
comment: ""
---
```

`examples/paper-demo/metadata/data/data-02.md`：

```markdown
---
id: data-02
refs: [fig-01b]
source: "../../data/raw/run-25c.csv"
description: "25 °C 下三次重复反应的速率-时间测量值（每 5 分钟取样）"
status: approved
comment: ""
---
```

`examples/paper-demo/metadata/data/data-03.md`：

```markdown
---
id: data-03
refs: [tbl-01]
source: "../../data/raw/summary.csv"
description: "各温度条件的初始速率均值、标准差与最终产率汇总"
status: approved
comment: ""
---
```

- [ ] **Step 6: 写两张 fact 卡**

`examples/paper-demo/metadata/facts/fact-01.md`：

```markdown
---
id: fact-01
data: [data-01, data-02]
statement: "60 °C 时的初始反应速率比 25 °C 高 42%（p < 0.01，n = 3）。"
supports: [claim-01]
status: approved
comment: ""
---
```

`examples/paper-demo/metadata/facts/fact-02.md`：

```markdown
---
id: fact-02
data: [data-03]
statement: "60 °C 与 25 °C 的最终产率均超过 90%，温度对产率无显著影响。"
supports: [claim-01, claim-02]
status: approved
comment: ""
---
```

- [ ] **Step 7: 写三张 claim 卡（注意目录 = claim_type）**

`examples/paper-demo/metadata/claims/uncited/claim-01.md`：

```markdown
---
id: claim-01
claim_type: uncited
statement: "温度升高显著提高反应速率，但不影响最终产率。"
cites: []
status: approved
comment: ""
---
```

`examples/paper-demo/metadata/claims/cited/claim-02.md`：

```markdown
---
id: claim-02
claim_type: cited
statement: "该温度效应与 Smith 等提出的热激活催化机制一致。"
cites: [smith2020]
status: approved
comment: ""
---
```

`examples/paper-demo/metadata/claims/cited/claim-03.md`：

```markdown
---
id: claim-03
claim_type: cited
statement: "与 Doe 等报道的 Pt 基催化体系相比，本体系的表观活化能更低。"
cites: [doe2021]
status: draft
comment: "待补活化能计算后再审。"
---
```

- [ ] **Step 8: 写两张 note 卡**

`examples/paper-demo/metadata/notes/smith2020.md`：

```markdown
---
id: smith2020
summary: "Smith 等提出热激活催化机制，核心证据是 Arrhenius 图在 45 °C 以上出现拐点，对应催化活性位点的结构转变。"
pdf: "../pdfs/smith2020.pdf"
status: approved
comment: ""
---
```

`examples/paper-demo/metadata/notes/doe2021.md`：

```markdown
---
id: doe2021
summary: "Doe 等报道了 Pt 基催化体系在 25–80 °C 区间的速率数据，表观活化能 52 kJ/mol，可作为本工作的对照体系。"
status: approved
comment: ""
---
```

- [ ] **Step 9: 写两个叙事节**

`examples/paper-demo/narrative/03-results.md`：

```markdown
---
id: sec-03
section: "Results"
order: 3
nodes:
  - id: para-03-01
    purpose: describe
    uses:
      - {id: fact-01, role: evidence}
      - {id: claim-01, role: conclusion}
    logic: "先报告主结果（温度对速率的影响，引用 fig-01a/b），再给出结论句"
    status: approved
    comment: ""
  - id: para-03-02
    purpose: describe
    uses:
      - {id: fact-02, role: evidence}
    logic: "报告产率汇总（tbl-01），说明温度不影响产率"
    status: draft
    comment: ""
---

审阅备注：图表落点由 fact→data→refs 推导，正文区不放终稿。
```

`examples/paper-demo/narrative/04-discussion.md`：

```markdown
---
id: sec-04
section: "Discussion"
order: 4
nodes:
  - id: para-04-01
    purpose: interpret
    uses:
      - {id: claim-02, role: conclusion}
      - {id: fact-01, role: evidence}
    logic: "把主结果与热激活催化机制联系起来解释"
    status: approved
    comment: ""
  - id: para-04-02
    purpose: compare
    uses:
      - {id: claim-03, role: comparison}
    logic: "与 Doe 体系的活化能比较，并指出本工作局限"
    status: draft
    comment: ""
---

审阅备注：claim-03 待活化能计算完成后审阅。
```

- [ ] **Step 10: 放置样例图文件（1×1 PNG 占位，base64 已验证）**

```bash
.venv/Scripts/python -c "import base64,pathlib; d=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='); pathlib.Path('examples/paper-demo/figures').mkdir(parents=True,exist_ok=True); pathlib.Path('examples/paper-demo/figures/fig-01a.png').write_bytes(d); pathlib.Path('examples/paper-demo/figures/fig-01b.png').write_bytes(d)"
```

（tbl-01 是表，不需要文件；`data/raw/*.csv` 不创建——`source` 字段 M1 不校验存在性，M2 引擎溯源时再处理。）

- [ ] **Step 11: 人工验收运行（M1 验收标准）**

```bash
.venv/Scripts/weft validate examples/paper-demo
```

Expected: 无诊断行，末行 `—— 0 个错误，0 个提醒`，退出码 0。

```bash
.venv/Scripts/weft graph examples/paper-demo
```

Expected: 打印三个"已写入 generated/..."行（写入 `examples/paper-demo/generated/`，已被 .gitignore 覆盖，不入库）。

```bash
.venv/Scripts/weft review examples/paper-demo
```

Expected: 列出 `claim  claim-03  metadata/claims/cited/claim-03.md` 与节点 `sec-03/para-03-02`、`sec-04/para-04-02`。

- [ ] **Step 12: 落黄金文件 `tests/golden/graph.json`**

内容（由上一步产物核对后写入；JSON 语义与 `weft graph` 输出一致）：

```json
{
  "entities": {
    "claim-01": {
      "kind": "claim",
      "referenced_by": {
        "claims": [],
        "facts": ["fact-01", "fact-02"],
        "nodes": ["para-03-01", "para-03-02", "para-04-01"]
      },
      "status": "approved"
    },
    "claim-02": {
      "kind": "claim",
      "referenced_by": {
        "claims": [],
        "facts": ["fact-02"],
        "nodes": ["para-03-02", "para-04-01"]
      },
      "status": "approved"
    },
    "claim-03": {
      "kind": "claim",
      "referenced_by": {
        "claims": [],
        "facts": [],
        "nodes": ["para-04-02"]
      },
      "status": "draft"
    },
    "data-01": {
      "kind": "data",
      "referenced_by": {
        "claims": [],
        "facts": ["fact-01"],
        "nodes": ["para-03-01", "para-04-01"]
      },
      "status": "approved"
    },
    "data-02": {
      "kind": "data",
      "referenced_by": {
        "claims": [],
        "facts": ["fact-01"],
        "nodes": ["para-03-01", "para-04-01"]
      },
      "status": "approved"
    },
    "data-03": {
      "kind": "data",
      "referenced_by": {
        "claims": [],
        "facts": ["fact-02"],
        "nodes": ["para-03-02"]
      },
      "status": "approved"
    },
    "doe2021": {
      "kind": "note",
      "referenced_by": {
        "claims": ["claim-03"],
        "facts": [],
        "nodes": []
      },
      "status": "approved"
    },
    "fact-01": {
      "kind": "fact",
      "referenced_by": {
        "claims": [],
        "facts": [],
        "nodes": ["para-03-01", "para-04-01"]
      },
      "status": "approved"
    },
    "fact-02": {
      "kind": "fact",
      "referenced_by": {
        "claims": [],
        "facts": [],
        "nodes": ["para-03-02"]
      },
      "status": "approved"
    },
    "smith2020": {
      "kind": "note",
      "referenced_by": {
        "claims": ["claim-02"],
        "facts": [],
        "nodes": []
      },
      "status": "approved"
    }
  },
  "version": 1
}
```

- [ ] **Step 13: 落黄金文件 `tests/golden/used-metadata.json`**

```json
{
  "claims": ["claim-01", "claim-02", "claim-03"],
  "data": ["data-01", "data-02", "data-03"],
  "facts": ["fact-01", "fact-02"]
}
```

- [ ] **Step 14: 写测试 `tests/test_example_project.py`**

```python
"""M1 验收：样例项目跑通三条命令，graph 产物与黄金文件一致。"""
import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from weft.cli import app

runner = CliRunner()
SAMPLE = Path(__file__).parent.parent / "examples" / "paper-demo"
GOLDEN = Path(__file__).parent / "golden"


def _copy_sample(tmp_path: Path) -> Path:
    work = tmp_path / "proj"
    shutil.copytree(SAMPLE, work)
    return work


def test_sample_validates_clean(tmp_path):
    work = _copy_sample(tmp_path)
    result = runner.invoke(app, ["validate", str(work)])
    assert result.exit_code == 0, result.output
    assert "0 个错误，0 个提醒" in result.output


def test_sample_graph_matches_golden(tmp_path):
    work = _copy_sample(tmp_path)
    result = runner.invoke(app, ["graph", str(work)])
    assert result.exit_code == 0, result.output
    for name in ("graph.json", "used-metadata.json"):
        actual = json.loads((work / "generated" / name).read_text(encoding="utf-8"))
        golden = json.loads((GOLDEN / name).read_text(encoding="utf-8"))
        assert actual == golden, name


def test_sample_review_lists_drafts(tmp_path):
    work = _copy_sample(tmp_path)
    result = runner.invoke(app, ["review", str(work)])
    assert result.exit_code == 0, result.output
    assert "claim-03" in result.output
    assert "sec-03/para-03-02" in result.output
    assert "sec-04/para-04-02" in result.output
```

- [ ] **Step 15: 跑测试确认通过**

Run: `.venv/Scripts/python -m pytest tests/test_example_project.py -v`
Expected: `3 passed`

- [ ] **Step 16: 全量回归（M1 完整验收）**

Run: `.venv/Scripts/python -m pytest tests -v`
Expected: 全部通过（97 个用例）。再跑一次 Task 15 Step 11 的三条命令确认人工视角无异常。

- [ ] **Step 17: Commit**

```bash
git add examples/paper-demo tests/golden tests/test_example_project.py
git commit -m "feat: 结果与讨论样例项目 + graph 黄金文件（M1 数据层验收）"
```

---

## 验收清单（M1 Definition of Done）

- [ ] `.venv/Scripts/python -m pytest tests -v` 全绿
- [ ] `weft validate examples/paper-demo` → `0 个错误，0 个提醒`，退出码 0
- [ ] `weft graph examples/paper-demo` → `generated/` 三个产物，内容与黄金文件一致
- [ ] `weft review examples/paper-demo` → 列出 claim-03 与两个 draft 节点
- [ ] 错误路径演练：随便弄坏一张卡（改 id、删 refs 目标），`validate` 报错定位到文件+字段且退出码 1
- [ ] spec §9 M1 范围全覆盖：models / store / validation / graphgen / validate / graph / review；未实现项（engine、assemble、render）留给 M2/M3
