# weft M2 生成层实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付 `engine/` 适配层（SpecModule 0.1.4）与 `weft draft <section>` 命令——单章节（样例项目 sec-03/sec-04）端到端生成到 `drafts/`，先免 key 假客户端跑通管线，再接真实 LLM（冒烟默认排除）。

**Architecture:** `engine/` 是全项目唯一 import `module_harness` / `llm` 的层（设计文档 §5）。一次章节生成 = 一个 SpecModule run，走通道②（spec + tasklist 由代码确定性构造，不经 LLM 翻译）；每个 approved 叙事节点 → 一个 `draft_para` harness task，末尾 `align_check` 节点（可关）+ `weft_validate_draft` script task 做生成时三规则校验；run 成功后 weft 把各段归一化写入 `drafts/<section>.md` 并加 HTML 溯源注释。零残留嵌入（`persist=False`）使路径白名单天然成立。

**Tech Stack:** Python 3.11+，pydantic 2，typer，`specmodule==0.1.4`（PyPI，提供 `module_harness` + `llm` 两个顶层包），pytest。

**基线：** main @ M1 合并后，97 个测试全绿。测试命令统一用 `.venv/Scripts/python -m pytest`（Windows）。

---

## 设计决策（执行期不再重新讨论）

1. **版本锁定**：`pyproject.toml` 加 `"specmodule==0.1.4"`。SpecModule 0.1.4 已于 2026-09-02 发布 PyPI（weft/.venv 已装，import 即可用——所以 Task 1 是配置任务，无"先红后绿"）。
2. **通道②直构 tasklist**：`Module(spec=..., tasklist=Tasklist(...))`，不走 template 翻译通道——tasklist 是 weft 代码构造的确定性产物，不是 LLM 产物；`review_harness=None` 关闭 tasklist 一致性审核（对代码构造的 tasklist 审核冗余且费 LLM 调用）。
3. **零残留嵌入**：`persist=False, status_file=False, keep_records=False, stream_log=False`——SpecModule 磁盘零写入，路径白名单（AI 产物只落 `drafts/`、`generated/`）因此天然成立：唯一落盘点是 `engine/drafts.py::write_draft` 的 `drafts/<section>.md`。run id 由 weft 生成 `uuid4().hex[:8]`（fast mode 无持久 run id）。断点续跑/回滚是 M4 范围（届时切 `persist=True` + 检查点 API）。
4. **ScriptedLLMClient 替代 MockLLMClient**：设计文档 §6.6 写"MockLLMClient 用于无 API key 的管线测试"，但 0.1.4 的 `llm.mock.MockLLMClient` 对 `json_object` 固定返回 `{"result","summary","issues"}`，不匹配 `draft_para` 的 `{"paragraph","uses","cites"}` 输出形状，走它必然校验失败。weft 在 `engine/clients.py` 自实现同协议假客户端 `ScriptedLLMClient`（免 key），`--mock` 与管线测试共用。此偏离已在此记录，不改设计文档（其 §6 语义不变：无 key 可跑管线）。
5. **task 命名与 flow**：段落任务 `p01..pNN`（tick 名须为合法标识符），对齐任务 `AL`，校验任务 `V`；flow 顺序链 `p01 --> p02 --> ... --> AL --> V`。`spec["task_nodes"]` 保存 tick 名 → node id 映射，供 V 脚本与结果收集反查。
6. **align 单节点可关**：默认开（设计文档三重防护之一），`--no-align` 跳过省 LLM 调用。整节查一次（全部段落 JSON 经 inputs 别名机制注入一个 align_check 节点），不逐段对齐。对齐未过（`aligned: false`）视为生成失败。
7. **段间不传前文**：各段落任务独立生成——首段"无前文"特殊分支、mock 确定性、组装后人调序三个问题都因此消失；连贯性靠节点 logic + 共享实体上下文。M4 打磨再议前文传递。
8. **prompt 注入方式**（SpecModule 三层 prompt，已核实 `module_harness/prompt.py`）：Layer 1 `prompt_core` 全段任务共享（硬约束 + 输出 JSON schema）；Layer 3 `prompt_extra`（即 Task.prompt）逐节点注入 purpose/logic/entities JSON，是**追加**语义；`{key}` 占位符替换只认 view 里的节点别名，实体 JSON 的大括号键不会被误替换（未匹配保留原样）——Task 6 有测试钉住。
9. **溯源注释内容**：`<!-- weft:node=<id> uses=<实体id> -->` 的 uses 取**节点声明的 uses**（weft 侧已审事实源），不是草稿自报的 uses（后者只用于三规则校验）。设计文档 §6.5"node id + 实体 id + run id"中 run id 放文件头一行。
10. **失败语义**：harness 节点输出不合法 → SpecModule 记 `Failure` 继续流动 → V 脚本读该节点输出时形状校验失败 → 抛 `DraftRuleError` → `module.run()` 原样上抛 → CLI 打印诊断并 exit 1，**不写 drafts 文件**（拒绝生成语义）。硬规则（规则 1/3）在 V 脚本内抛 `DraftRuleError`；软提醒（规则 2）经 V 输出 `{"reminders": [...]}` 带回。
11. **生成前强校验**：`weft draft` 先跑 `validate_project`，任何 error 即拒绝（spec §4"校验不过 → 拒绝生成"）。

## 新增诊断码（稳定标识，接 M1 总表）

| 码 | 级别 | 位置 | 含义 |
|---|---|---|---|
| `E-SECTION-NOT-FOUND` | 错误 | CLI | section id 不存在 |
| `E-NOTHING-TO-DRAFT` | 错误 | CLI | 节内无 approved 节点 |
| `E-DRAFT-SHAPE` | 错误 | draft_rules | harness 输出缺键/类型不符/不可读 |
| `E-CITE-NOT-IN-BIB` | 错误 | draft_rules | `[@key]` 不在项目 bib（§4 生成时规则 1） |
| `W-CITE-NOT-IN-CLAIM` | 提醒 | draft_rules | citekey 不属于本节点所用 claim 的 cites（规则 2） |
| `E-USES-BEYOND-NODE` | 错误 | draft_rules | 草稿标注实体 ⊄ 节点 uses（规则 3） |
| `E-DRAFT-FAILED` | 错误 | run/clients | run 失败 / LLM 配置缺失 / 对齐未过（`DraftError` 消息内携带） |

生成时诊断的 `path` 定位到 `drafts/<section_id>.md`，`field` 为 `<节点id>.<字段>`（沿用"文件+字段"粒度约定）。

## 文件结构

```text
src/weft/engine/
├── __init__.py        # 导出 run_draft / DraftResult / make_client / 异常类型
├── spec_build.py      # entity_bundle / build_spec / build_tasklist（叙事节 → spec + Tasklist）
├── draft_rules.py     # DraftError / DraftRuleError / parse_node_draft / check_node_draft
├── drafts.py          # render_draft_markdown / write_draft（归一化写入 + 白名单）
├── clients.py         # ScriptedLLMClient / make_client（客户端选择）
└── run.py             # run_draft（registry、Module run、失败包装、结果收集）
```

与设计文档 §5 的 `engine/spec_build.py + run.py` 相比拆出 `draft_rules.py / drafts.py / clients.py` 三个聚焦文件：三规则要脱离 SpecModule 纯函数单测；drafts 写入要独立测白名单；clients 被 CLI 与测试共用；两个错误类型集中在 draft_rules.py（clients/run 都从它 import，无循环依赖）。职责边界不变。

新增测试文件：`tests/test_engine_layering.py`、`tests/test_draft_rules.py`、`tests/test_spec_build.py`、`tests/test_drafts.py`、`tests/test_clients.py`、`tests/test_engine_run.py`、`tests/test_cli_draft.py`、`tests/test_smoke_real_llm.py`。

---

### Task 1: specmodule 依赖与分层守卫

**Files:**
- Modify: `pyproject.toml`（dependencies）
- Create: `tests/test_engine_layering.py`
- Modify: `tests/test_package.py`（追加一条导入冒烟）

- [ ] **Step 1: 写两个守卫测试**

创建 `tests/test_engine_layering.py`：

```python
"""分层守卫（spec §5）：engine/ 是 src 内唯一 import specmodule（llm/module_harness）的层。

防分层腐化：engine/ 之外的 src 模块出现对 specmodule 包的 import 即失败。
tests/ 不在扫描范围（测试基建可 import llm.client 构造假响应）。
"""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "weft"

_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+(llm|module_harness)\b", re.MULTILINE)


def test_only_engine_imports_specmodule():
    offenders = [
        py.relative_to(SRC).as_posix()
        for py in SRC.rglob("*.py")
        if not py.relative_to(SRC).as_posix().startswith("engine/")
        and _IMPORT_RE.search(py.read_text(encoding="utf-8"))
    ]
    assert offenders == []
```

在 `tests/test_package.py` 末尾追加：

```python
def test_specmodule_dependency_importable():
    import module_harness

    from llm.client import LLMResponse

    assert hasattr(module_harness, "call_harness")
    assert hasattr(module_harness, "Module")
    assert LLMResponse is not None
```

- [ ] **Step 2: pyproject 加依赖并安装**

`pyproject.toml` 的 `dependencies` 列表改为：

```toml
dependencies = [
    "pydantic>=2.5",
    "python-frontmatter>=1.1",
    "typer>=0.12",
    "pyyaml>=6",
    "specmodule==0.1.4",
]
```

Run: `.venv/Scripts/python.exe -m pip install -e ".[dev]" -q`
Expected: 安装成功（specmodule 0.1.4 已在 PyPI；本机 .venv 已装过则显示 satisfied）。

- [ ] **Step 3: 跑新测试**

Run: `.venv/Scripts/python -m pytest tests/test_engine_layering.py tests/test_package.py -v`
Expected: 2 个新测试 PASS（分层守卫此时 src 内无违规者——engine/ 还没建）。

- [ ] **Step 4: 全量回归**

Run: `.venv/Scripts/python -m pytest tests -q`
Expected: `99 passed`（97 + 2）。

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/test_engine_layering.py tests/test_package.py
git commit -m "feat: specmodule==0.1.4 依赖锁定 + engine 分层守卫测试（M2 Task 1）"
```

---

### Task 2: 错误类型与生成时三规则 draft_rules.py

**Files:**
- Create: `src/weft/engine/draft_rules.py`
- Create: `src/weft/engine/__init__.py`
- Test: `tests/test_draft_rules.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_draft_rules.py`：

```python
"""生成时校验三规则（spec §4 生成时行）+ harness 输出形状解析。"""
import pytest

from tests.helpers import build_project
from weft.diagnostics import Level
from weft.engine.draft_rules import (
    DraftError,
    DraftRuleError,
    check_node_draft,
    parse_node_draft,
)
from weft.models.cards import ClaimCard
from weft.models.narrative import Node, Use

SEC = "sec-01"
NODE_ID = "para-01-01"


def _node(uses=("fact-01", "claim-01")):
    # 默认同时 use fact 与 claim：规则 2 的允许集来自“节点所用 claim 的 cites”，
    # 只 use fact 时 claim_cites 恒为空集，通过用例无法构造
    return Node(id=NODE_ID, purpose="describe",
                uses=[Use(id=u, role="evidence") for u in uses], status="approved")


def _project(bib=("key2020",), claim_cites=("key2020",)):
    return build_project(
        bib_keys=set(bib),
        claims=[ClaimCard(id="claim-01", claim_type="cited", statement="s",
                          cites=list(claim_cites), status="approved")],
    )


def test_parse_ok():
    draft, diag = parse_node_draft(
        {"paragraph": "正文。", "uses": ["fact-01"], "cites": []}, NODE_ID, SEC)
    assert diag is None
    assert draft["paragraph"] == "正文。"


def test_parse_non_dict():
    draft, diag = parse_node_draft("not json", NODE_ID, SEC)
    assert draft is None
    assert diag.code == "E-DRAFT-SHAPE"
    assert diag.path == f"drafts/{SEC}.md"
    assert diag.field == f"{NODE_ID}.output"


def test_parse_empty_paragraph():
    _, diag = parse_node_draft({"paragraph": "  ", "uses": [], "cites": []}, NODE_ID, SEC)
    assert diag.code == "E-DRAFT-SHAPE"


def test_parse_bad_uses_type():
    _, diag = parse_node_draft({"paragraph": "p", "uses": "fact-01", "cites": []}, NODE_ID, SEC)
    assert diag.code == "E-DRAFT-SHAPE"


def test_rule3_uses_beyond_node():
    diags = check_node_draft({"paragraph": "p", "uses": ["claim-99"], "cites": []},
                             _node(), _project(), SEC)
    assert [d.code for d in diags] == ["E-USES-BEYOND-NODE"]
    assert diags[0].level is Level.ERROR


def test_rule1_cite_not_in_bib():
    diags = check_node_draft({"paragraph": "p", "uses": [], "cites": ["nokey"]},
                             _node(), _project(), SEC)
    assert [d.code for d in diags] == ["E-CITE-NOT-IN-BIB"]


def test_rule2_cite_not_in_claim_cites_is_warning():
    # keyother 在 bib 内但不属于 claim-01 的 cites → 纯提醒不阻断
    diags = check_node_draft({"paragraph": "p", "uses": [], "cites": ["keyother"]},
                             _node(), _project(bib=("key2020", "keyother")), SEC)
    assert [d.code for d in diags] == ["W-CITE-NOT-IN-CLAIM"]
    assert diags[0].level is Level.WARNING


def test_rule2_pass_when_cite_belongs_to_claim():
    diags = check_node_draft({"paragraph": "p", "uses": [], "cites": ["key2020"]},
                             _node(), _project(), SEC)
    assert diags == []


def test_error_types():
    _, diag = parse_node_draft(42, NODE_ID, SEC)
    assert isinstance(DraftRuleError(diag), RuntimeError)
    assert isinstance(DraftError("x"), RuntimeError)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python -m pytest tests/test_draft_rules.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'weft.engine'`。

- [ ] **Step 3: 实现 draft_rules.py**

创建 `src/weft/engine/__init__.py`：

```python
"""engine 生成层（spec §5/§6）：全项目唯一 import module_harness / llm 的层。"""
```

创建 `src/weft/engine/draft_rules.py`：

```python
"""生成时校验三规则（spec §4 生成时行）+ harness 输出形状解析 + 生成层错误类型。

纯函数、不 import specmodule：从 harness JSON dict 到诊断的映射可独立单测。
硬规则违规由 V 脚本转成 DraftRuleError 上抛（拒绝生成）；软提醒收集带回。
DraftError 与 DraftRuleError 集中在此定义，clients/run 复用（避免循环依赖）。
"""
from weft.diagnostics import Diagnostic, Level
from weft.models.narrative import Node
from weft.store.project import Project


class DraftError(RuntimeError):
    """生成层失败（配置缺失 / run 失败 / 对齐未过）；消息面向 CLI 直接输出。"""


class DraftRuleError(RuntimeError):
    """硬规则违规：携带诊断，run 层不捕获、CLI 直接打印并退出码 1。"""

    def __init__(self, diagnostic: Diagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(
            f"[{diagnostic.code}] {diagnostic.path} 字段 {diagnostic.field}: "
            f"{diagnostic.message}")


def _diag(code: str, node_id: str, section_id: str, field: str, message: str,
          level: Level = Level.ERROR) -> Diagnostic:
    return Diagnostic(level, code, f"drafts/{section_id}.md",
                      f"{node_id}.{field}", message)


def parse_node_draft(value: object, node_id: str,
                     section_id: str) -> tuple[dict | None, Diagnostic | None]:
    """harness JSON 输出形状校验：paragraph 非空 str，uses/cites 是 list[str]。"""
    if not isinstance(value, dict):
        return None, _diag("E-DRAFT-SHAPE", node_id, section_id, "output",
                           "输出不是 JSON 对象")
    paragraph = value.get("paragraph")
    if not isinstance(paragraph, str) or not paragraph.strip():
        return None, _diag("E-DRAFT-SHAPE", node_id, section_id, "output",
                           "paragraph 缺失或为空白")
    for key in ("uses", "cites"):
        v = value.get(key, [])
        if not isinstance(v, list) or any(not isinstance(x, str) for x in v):
            return None, _diag("E-DRAFT-SHAPE", node_id, section_id, "output",
                               f"{key} 不是字符串列表")
    return value, None


def check_node_draft(draft: dict, node: Node, project: Project,
                     section_id: str) -> list[Diagnostic]:
    """规则 1/2/3。返回诊断列表；硬规则（ERROR）由调用方 raise DraftRuleError。"""
    diags: list[Diagnostic] = []
    uses = [u.id for u in node.uses]
    # 规则 3（硬）：草稿标注引用的实体 id ⊆ 节点 uses
    for eid in draft["uses"]:
        if eid not in uses:
            diags.append(_diag("E-USES-BEYOND-NODE", node.id, section_id, "uses",
                               f"草稿标注实体 {eid} 不在本节点 uses"
                               f"（{', '.join(uses) or '空'}）"))
    # 本节点所用 claim 的 cites 并集（规则 2 的允许集）
    claim_cites: set[str] = set()
    for uid in uses:
        claim = project.claims.get(uid)
        if claim is not None:
            claim_cites.update(claim.cites)
    for key in draft["cites"]:
        # 规则 1（硬）：[@key] 必须在 bib 内
        if key not in project.bib_keys:
            diags.append(_diag("E-CITE-NOT-IN-BIB", node.id, section_id, "cites",
                               f"citekey {key} 不在项目 bib"))
        # 规则 2（软）：[@key] 应属于本段所用 claim 的 cites
        elif key not in claim_cites:
            diags.append(_diag("W-CITE-NOT-IN-CLAIM", node.id, section_id, "cites",
                               f"citekey {key} 不属于本节点所用 claim 的 cites",
                               level=Level.WARNING))
    return diags
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python -m pytest tests/test_draft_rules.py -v`
Expected: `9 passed`。

- [ ] **Step 5: 全量回归**

Run: `.venv/Scripts/python -m pytest tests -q`
Expected: `108 passed`（99 + 9）。

- [ ] **Step 6: Commit**

```bash
git add src/weft/engine/__init__.py src/weft/engine/draft_rules.py tests/test_draft_rules.py
git commit -m "feat: 生成时三规则与输出形状解析（E-DRAFT-SHAPE/E-CITE-NOT-IN-BIB/W-CITE-NOT-IN-CLAIM/E-USES-BEYOND-NODE）"
```

---

### Task 3: spec 与 tasklist 构建 spec_build.py

**Files:**
- Create: `src/weft/engine/spec_build.py`
- Test: `tests/test_spec_build.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_spec_build.py`：

```python
"""叙事节 → spec + tasklist（通道②）的确定性构造。"""
import pytest

from tests.helpers import build_project
from weft.engine.spec_build import build_spec, build_tasklist, entity_bundle
from weft.models.cards import ClaimCard, DataCard, FactCard, NoteCard
from weft.models.narrative import NarrativeSection, Node, Use


def _project():
    return build_project(
        data=[DataCard(id="data-01", status="approved", refs=[],
                       source="../../data/run3.csv", description="速率测量")],
        facts=[FactCard(id="fact-01", status="approved", data=["data-01"],
                        statement="温度提高速率。")],
        claims=[ClaimCard(id="claim-01", claim_type="cited", status="approved",
                          statement="温度有正效应。", cites=["key2020"])],
        notes=[NoteCard(id="key2020", status="approved", summary="文献概括。")],
        bib_keys={"key2020"},
    )


def _section():
    approved = Node(id="para-01-01", purpose="describe",
                    uses=[Use(id="fact-01", role="evidence"),
                          Use(id="claim-01", role="conclusion")],
                    logic="先主结果", status="approved")
    draft = Node(id="para-01-02", purpose="interpret", uses=[], status="draft")
    return NarrativeSection(id="sec-01", section="Results", order=1,
                            nodes=[approved, draft])


def test_build_spec_filters_non_approved():
    spec = build_spec(_project(), _section())
    assert set(spec["nodes"]) == {"para-01-01"}
    assert spec["task_nodes"] == {"p01": "para-01-01"}
    assert spec["section"] == {"id": "sec-01", "title": "Results", "order": 1}


def test_entity_bundle_fact_carries_data_description():
    bundle = entity_bundle(_project(), "fact-01")
    assert bundle["kind"] == "fact"
    assert bundle["statement"] == "温度提高速率。"
    assert bundle["data"] == [{"id": "data-01", "description": "速率测量",
                               "source": "../../data/run3.csv"}]


def test_entity_bundle_claim_carries_cites_and_note_summaries():
    bundle = entity_bundle(_project(), "claim-01")
    assert bundle["claim_type"] == "cited"
    assert bundle["cites"] == ["key2020"]
    assert bundle["note_summaries"] == [{"key": "key2020", "summary": "文献概括。"}]


def test_entity_bundle_rejects_note_and_unknown():
    project = _project()
    with pytest.raises(ValueError):
        entity_bundle(project, "key2020")   # uses 只准 fact/claim（spec §2）
    with pytest.raises(ValueError):
        entity_bundle(project, "ghost")


def test_build_tasklist_flow_with_align():
    tasklist = build_tasklist(build_spec(_project(), _section()), align=True)
    assert tasklist.flow == "p01 --> AL --> V"
    assert tasklist.tasks["p01"].harness == "draft_para"
    assert tasklist.tasks["p01"].outputformat == {"type": "json_object"}
    assert tasklist.tasks["AL"].harness == "align_check"
    assert tasklist.tasks["AL"].inputs == {"d1": "p01"}
    assert tasklist.tasks["V"].script == "weft_validate_draft"


def test_build_tasklist_flow_without_align():
    tasklist = build_tasklist(build_spec(_project(), _section()), align=False)
    assert tasklist.flow == "p01 --> V"
    assert "AL" not in tasklist.tasks


def test_para_prompt_embeds_entity_json():
    tasklist = build_tasklist(build_spec(_project(), _section()), align=False)
    prompt = tasklist.tasks["p01"].prompt
    assert "describe" in prompt
    assert "先主结果" in prompt
    assert "温度提高速率。" in prompt       # 实体全文进 prompt
    assert "文献概括。" in prompt           # claim 所引 note 的 summary 进 prompt
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python -m pytest tests/test_spec_build.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'weft.engine.spec_build'`。

- [ ] **Step 3: 实现 spec_build.py**

创建 `src/weft/engine/spec_build.py`：

```python
"""叙事节 → SpecModule spec + tasklist（通道②，代码确定性构造，spec §6.1/6.2）。

spec 形状：
{
  "section": {"id", "title", "order"},
  "task_nodes": {"p01": "para-01-01", ...},   # tick 名 → node id
  "nodes": {"para-01-01": {"purpose", "logic", "uses", "entities": [bundle, ...]}},
}
只收 status: approved 的节点与实体（spec §3.10：生成器只读 approved）。
"""
import json

from module_harness import TaskDefinition, Tasklist

from weft.models.narrative import NarrativeSection
from weft.store.project import Project


def tick_name(index: int) -> str:
    return f"p{index + 1:02d}"


def entity_bundle(project: Project, entity_id: str) -> dict:
    """已审阅实体全文 bundle（spec §6.1）；claim 额外带所引 note 的 summary。

    uses 只准引 fact/claim（spec §2）；note 经 claim.cites 间接进入。
    """
    if entity_id in project.facts:
        fact = project.facts[entity_id]
        return {
            "id": entity_id, "kind": "fact",
            "statement": fact.statement,
            "data": [{"id": d, "description": project.data_cards[d].description,
                      "source": project.data_cards[d].source}
                     for d in fact.data if d in project.data_cards],
        }
    if entity_id in project.claims:
        claim = project.claims[entity_id]
        return {
            "id": entity_id, "kind": "claim",
            "statement": claim.statement,
            "claim_type": claim.claim_type,
            "cites": list(claim.cites),
            "note_summaries": [{"key": k, "summary": project.notes[k].summary}
                               for k in claim.cites if k in project.notes],
        }
    raise ValueError(f"uses 指向非 fact/claim 实体或不存在：{entity_id}")


def build_spec(project: Project, section: NarrativeSection) -> dict:
    approved = [n for n in section.nodes if n.status == "approved"]
    nodes = {}
    for n in approved:
        nodes[n.id] = {
            "purpose": n.purpose,
            "logic": n.logic,
            "uses": [{"id": u.id, "role": u.role} for u in n.uses],
            "entities": [entity_bundle(project, u.id) for u in n.uses],
        }
    return {
        "section": {"id": section.id, "title": section.section, "order": section.order},
        "task_nodes": {tick_name(i): n.id for i, n in enumerate(approved)},
        "nodes": nodes,
    }


def _para_prompt(node_spec: dict) -> str:
    """Layer 3（prompt_extra，追加语义）：本节点的要求与实体全文。"""
    return (
        f"节点 purpose：{node_spec['purpose']}\n"
        f"节点 logic：{node_spec['logic'] or '（无）'}\n"
        "可引用的已审阅实体（JSON，只准使用这些）：\n"
        + json.dumps(node_spec["entities"], ensure_ascii=False, indent=1)
    )


def build_tasklist(spec: dict, *, align: bool) -> Tasklist:
    """p01..pNN 顺序链 --> [AL -->] V。

    harness 层配置（prompt_core 等）在 run.py 注册；这里只给任务级覆盖。
    """
    ticks = list(spec["task_nodes"])
    tasks: dict[str, TaskDefinition] = {}
    for tick in ticks:
        node_spec = spec["nodes"][spec["task_nodes"][tick]]
        tasks[tick] = TaskDefinition(
            type="harness", harness="draft_para",
            prompt=_para_prompt(node_spec),
            outputformat={"type": "json_object"},
            temperature=0.3,
        )
    if align:
        aliases = {f"d{i + 1}": tick for i, tick in enumerate(ticks)}
        tasks["AL"] = TaskDefinition(
            type="harness", harness="align_check",
            prompt="已生成的全部段落（逐段 JSON）：\n"
                   + "\n".join(f"{{{k}}}" for k in aliases),
            inputs=aliases,
        )
    tasks["V"] = TaskDefinition(type="script", script="weft_validate_draft")
    flow_ticks = ticks + (["AL"] if align else []) + ["V"]
    return Tasklist(tasks=tasks, flow=" --> ".join(flow_ticks))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python -m pytest tests/test_spec_build.py -v`
Expected: `7 passed`。

- [ ] **Step 5: 全量回归**

Run: `.venv/Scripts/python -m pytest tests -q`
Expected: `115 passed`（108 + 7）。

- [ ] **Step 6: Commit**

```bash
git add src/weft/engine/spec_build.py tests/test_spec_build.py
git commit -m "feat: engine spec_build——叙事节到 spec/tasklist 的确定性构造（approved 过滤 + 实体全文 bundle）"
```

---

### Task 4: 草稿渲染与白名单写入 drafts.py

**Files:**
- Create: `src/weft/engine/drafts.py`
- Test: `tests/test_drafts.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_drafts.py`：

```python
"""草稿归一化渲染 + 白名单写入（drafts/<section>.md 唯一落盘点）。"""
import pytest

from tests.helpers import build_project
from weft.engine.drafts import render_draft_markdown, write_draft
from weft.models.narrative import NarrativeSection, Node, Use


def _section():
    return NarrativeSection(
        id="sec-01", section="Results", order=1,
        nodes=[Node(id="para-01-01", purpose="describe",
                    uses=[Use(id="fact-01", role="evidence")], status="approved"),
               Node(id="para-01-02", purpose="interpret",
                    uses=[], status="approved")])


def test_render_traceability_comments():
    section = _section()
    paragraphs = {"para-01-01": "第一段。", "para-01-02": "第二段。"}
    out = render_draft_markdown(section, paragraphs, "ab12cd34")
    assert out == (
        "<!-- weft:run=ab12cd34 section=sec-01 -->\n"
        "\n"
        "<!-- weft:node=para-01-01 uses=fact-01 -->\n"
        "第一段。\n"
        "\n"
        "<!-- weft:node=para-01-02 -->\n"
        "第二段。\n"
    )


def test_render_uses_come_from_node_not_draft():
    # 溯源记录节点声明的 uses（weft 侧事实源），与草稿自报无关（决策 9）
    section = _section()
    out = render_draft_markdown(section, {"para-01-01": "第一段。"}, "ab12cd34")
    assert "<!-- weft:node=para-01-01 uses=fact-01 -->" in out


def test_render_skips_undrafted_nodes():
    section = _section()
    out = render_draft_markdown(section, {"para-01-02": "第二段。"}, "ab12cd34")
    assert "para-01-01" not in out
    assert "第二段。" in out


def test_write_draft_path_and_lf(tmp_path):
    project = build_project(root=tmp_path)
    path = write_draft(project, "sec-01", "正文\n")
    assert path == tmp_path / "drafts" / "sec-01.md"
    raw = path.read_bytes()
    assert b"\r" not in raw                     # 固定 LF（同 graphgen 约定）
    assert raw.endswith(b"\n")


def test_write_draft_overwrites(tmp_path):
    project = build_project(root=tmp_path)
    write_draft(project, "sec-01", "旧")
    path = write_draft(project, "sec-01", "新")
    assert path.read_text(encoding="utf-8") == "新"


def test_write_draft_rejects_path_escape(tmp_path):
    project = build_project(root=tmp_path)
    with pytest.raises(ValueError):
        write_draft(project, "../evil", "x")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python -m pytest tests/test_drafts.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'weft.engine.drafts'`。

- [ ] **Step 3: 实现 drafts.py**

创建 `src/weft/engine/drafts.py`：

```python
"""草稿归一化写入：drafts/<section>.md + HTML 溯源注释（spec §6.5）。

路径白名单：本模块是 M2 唯一把 AI 产物落盘的地方，路径硬编码为
root/drafts/<section_id>.md，不接受调用方传入路径；section_id 再过一次
逃逸检查（纵深防御，id 正常来自 loader 校验过的叙事节）。
溯源注释的 uses 取节点声明的 uses（决策 9），不取草稿自报值。
"""
from pathlib import Path

from weft.models.narrative import NarrativeSection
from weft.store.project import Project


def render_draft_markdown(section: NarrativeSection, paragraphs_by_node: dict[str, str],
                          run_id: str) -> str:
    """段落顺序 = 节内 nodes 顺序；未生成节点（draft/rejected）跳过。"""
    lines = [f"<!-- weft:run={run_id} section={section.id} -->", ""]
    for node in section.nodes:
        paragraph = paragraphs_by_node.get(node.id)
        if paragraph is None:
            continue
        uses = ",".join(u.id for u in node.uses)
        comment = f"<!-- weft:node={node.id} uses={uses} -->" if uses \
            else f"<!-- weft:node={node.id} -->"
        lines += [comment, paragraph, ""]
    return "\n".join(lines) + "\n"


def write_draft(project: Project, section_id: str, content: str) -> Path:
    drafts_dir = project.root / "drafts"
    path = drafts_dir / f"{section_id}.md"
    if path.resolve().parent != drafts_dir.resolve():
        raise ValueError(f"非法 section id（路径逃逸）：{section_id}")
    drafts_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return path
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python -m pytest tests/test_drafts.py -v`
Expected: `6 passed`。

- [ ] **Step 5: 全量回归**

Run: `.venv/Scripts/python -m pytest tests -q`
Expected: `121 passed`（115 + 6）。

- [ ] **Step 6: Commit**

```bash
git add src/weft/engine/drafts.py tests/test_drafts.py
git commit -m "feat: engine drafts——溯源注释渲染（uses 取节点声明）与 drafts/ 白名单写入（固定 LF）"
```

---

### Task 5: 客户端选择 clients.py

**Files:**
- Create: `src/weft/engine/clients.py`
- Test: `tests/test_clients.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_clients.py`：

```python
"""LLM 客户端选择：ScriptedLLMClient 免 key 管线；真实客户端走 .env/环境变量。"""
import asyncio
import json

import pytest

from weft.engine.clients import ScriptedLLMClient, make_client
from weft.engine.draft_rules import DraftError


def _complete(client, **kwargs):
    return asyncio.run(client.complete(**kwargs))


def test_scripted_returns_draft_shape_and_records_prompt():
    client = ScriptedLLMClient(paragraph="_mock_段。")
    resp = _complete(client, prompt="你是学术写作引擎 weft 的行文器。任务提示",
                     output_format={"type": "json_object"})
    assert json.loads(resp.content) == {"paragraph": "_mock_段。", "uses": [], "cites": []}
    assert client.prompts == ["你是学术写作引擎 weft 的行文器。任务提示"]


def test_scripted_aligned_for_align_prompt():
    client = ScriptedLLMClient()
    resp = _complete(client, prompt="你是对齐检查器。判断当前节点产出是否偏离 spec 目标。")
    assert json.loads(resp.content)["aligned"] is True


def test_scripted_custom_uses_and_cites():
    client = ScriptedLLMClient(uses=["claim-99"], cites=["keyother"])
    resp = _complete(client, prompt="行文器")
    assert json.loads(resp.content)["uses"] == ["claim-99"]


def test_scripted_broken_flag_returns_non_json():
    client = ScriptedLLMClient(broken=True)
    with pytest.raises(json.JSONDecodeError):
        json.loads(_complete(client, prompt="行文器").content)


def test_make_client_mock_returns_scripted():
    assert isinstance(make_client(mock=True), ScriptedLLMClient)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python -m pytest tests/test_clients.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'weft.engine.clients'`。

- [ ] **Step 3: 实现 clients.py**

创建 `src/weft/engine/clients.py`：

```python
"""LLM 客户端选择：mock（免 key 管线冒烟）与真实（.env / 环境变量）。

设计文档 §6.6 的 MockLLMClient（llm.mock）对 json_object 固定返回
{"result","summary","issues"}，不匹配 draft_para 输出形状（计划决策 4），
故自实现同协议假客户端：complete(**kwargs) → llm.client.LLMResponse。
"""
import json

from llm.client import LLMResponse

from weft.engine.draft_rules import DraftError


class ScriptedLLMClient:
    """按 prompt 关键词分流的假客户端（与 embed_minimal 的 mock 同一模式）：

    - prompt 含"对齐检查器"（align_check 内置 prompt_core 标识）→ aligned=true
    - 否则视为 draft_para → {"paragraph", "uses", "cites"}
    broken=True 时 draft 通道返回非 JSON（测 E-DRAFT-SHAPE 路径）。
    """

    def __init__(self, paragraph: str = "（mock 段落）正文。",
                 uses: list[str] | None = None, cites: list[str] | None = None,
                 broken: bool = False) -> None:
        self.paragraph = paragraph
        self.uses = list(uses or [])
        self.cites = list(cites or [])
        self.broken = broken
        self.prompts: list[str] = []   # 测试断言 prompt 注入用

    async def complete(self, **kwargs) -> LLMResponse:
        prompt = kwargs.get("prompt") or ""
        self.prompts.append(prompt)
        if "对齐检查器" in prompt:
            content = json.dumps({"aligned": True, "suggestions": ""})
        elif self.broken:
            content = "这不是 JSON"
        else:
            content = json.dumps(
                {"paragraph": self.paragraph, "uses": self.uses, "cites": self.cites},
                ensure_ascii=False)
        return LLMResponse(content=content, usage={}, finish_reason="end_turn")


def make_client(mock: bool):
    """mock=True → ScriptedLLMClient；否则真实客户端（失败转 DraftError/E-DRAFT-FAILED）。"""
    if mock:
        return ScriptedLLMClient()
    try:
        from llm import LLMConfig, create_llm_client

        return create_llm_client(LLMConfig.from_env())
    except Exception as exc:
        raise DraftError(f"真实 LLM 客户端构造失败（检查 .env / 环境变量）：{exc}") from exc
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python -m pytest tests/test_clients.py -v`
Expected: `5 passed`。

- [ ] **Step 5: 全量回归**

Run: `.venv/Scripts/python -m pytest tests -q`
Expected: `126 passed`（121 + 5）。

- [ ] **Step 6: Commit**

```bash
git add src/weft/engine/clients.py tests/test_clients.py
git commit -m "feat: engine clients——ScriptedLLMClient 免 key 假客户端与 make_client 选择器"
```

---

### Task 6: 运行层 run.py

**Files:**
- Create: `src/weft/engine/run.py`
- Modify: `src/weft/engine/__init__.py`（最终导出）
- Test: `tests/test_engine_run.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_engine_run.py`：

```python
"""run_draft 端到端（ScriptedLLMClient，免 key、零落盘）。"""
import pytest

from tests.helpers import build_project
from weft.engine.clients import ScriptedLLMClient
from weft.engine.draft_rules import DraftRuleError
from weft.engine.run import run_draft
from weft.models.cards import ClaimCard, FactCard
from weft.models.narrative import NarrativeSection, Node, Use

SEC = "sec-01"


def _project(bib=("key2020",), claim_cites=("key2020",)):
    return build_project(
        facts=[FactCard(id="fact-01", status="approved", data=["data-01"],
                        statement="温度提高速率。")],
        claims=[ClaimCard(id="claim-01", claim_type="cited", status="approved",
                          statement="s", cites=list(claim_cites))],
        bib_keys=set(bib),
    )


def _section(n_approved=2):
    nodes = [
        Node(id=f"para-01-{i:02d}", purpose="describe",
             uses=[Use(id="fact-01", role="evidence"),
                   Use(id="claim-01", role="conclusion")],
             logic="", status="approved")
        for i in range(1, n_approved + 1)
    ]
    return NarrativeSection(id=SEC, section="Results", order=1, nodes=nodes)


def test_run_draft_end_to_end_two_paragraphs():
    result = run_draft(_project(), _section(), client=ScriptedLLMClient())
    assert set(result.drafts_by_node) == {"para-01-01", "para-01-02"}
    assert result.drafts_by_node["para-01-01"]["paragraph"] == "（mock 段落）正文。"
    assert len(result.run_id) == 8
    assert result.reminders == []


def test_run_draft_prompt_carries_entities():
    client = ScriptedLLMClient()
    run_draft(_project(), _section(n_approved=1), client=client)
    para_prompts = [p for p in client.prompts if "对齐检查器" not in p]
    assert len(para_prompts) == 1
    assert "温度提高速率。" in para_prompts[0]      # 实体全文注入（决策 8）


def test_run_draft_collects_soft_reminders():
    client = ScriptedLLMClient(cites=["keyother"])
    result = run_draft(_project(bib=("key2020", "keyother")),
                       _section(n_approved=1), client=client)
    assert any("W-CITE-NOT-IN-CLAIM" in r for r in result.reminders)


def test_run_draft_hard_rule_aborts():
    client = ScriptedLLMClient(uses=["claim-99"])
    with pytest.raises(DraftRuleError) as excinfo:
        run_draft(_project(), _section(n_approved=1), client=client)
    assert excinfo.value.diagnostic.code == "E-USES-BEYOND-NODE"


def test_run_draft_broken_output_shape():
    with pytest.raises(DraftRuleError) as excinfo:
        run_draft(_project(), _section(n_approved=1),
                  client=ScriptedLLMClient(broken=True))
    assert excinfo.value.diagnostic.code == "E-DRAFT-SHAPE"


def test_run_draft_without_align_skips_align_node():
    client = ScriptedLLMClient()
    run_draft(_project(), _section(n_approved=1), client=client, align=False)
    assert not any("对齐检查器" in p for p in client.prompts)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python -m pytest tests/test_engine_run.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'weft.engine.run'`。

- [ ] **Step 3: 实现 run.py**

创建 `src/weft/engine/run.py`：

```python
"""engine 运行层：一次章节生成 = 一个 SpecModule run（spec §6）。

零残留嵌入（决策 3）：persist/status_file/keep_records/stream_log 全关，
SpecModule 不落盘；产物由 weft.engine.drafts 白名单写入 drafts/。
失败语义（决策 10）：V 脚本抛 DraftRuleError → run() 上抛 → CLI exit 1。
"""
import asyncio
import uuid
from dataclasses import dataclass, field

from module_harness import (
    EventBus,
    HarnessConfig,
    HarnessRegistry,
    Module,
    OutputFormat,
    register_align_check_harness,
)

from weft.diagnostics import Level
from weft.engine.draft_rules import (
    DraftError,
    DraftRuleError,
    _diag,
    check_node_draft,
    parse_node_draft,
)
from weft.engine.spec_build import build_spec, build_tasklist
from weft.models.narrative import NarrativeSection
from weft.store.project import Project

DRAFT_PARA_CORE = (
    "你是学术写作引擎 weft 的行文器。依据任务提示给出的已审阅实体与节点要求，"
    "写出一节论文中的一段正文（中文，学术论文语体）。\n"
    "硬性约束：\n"
    "1. 只准使用任务提示中列出的实体及其内容；不得引入任何未给出的数据、观点或结论。\n"
    "2. 不得改写、编造实体卡的任何字段值。\n"
    "3. 引文标注只准使用实体 bundle 给出的 bib key，以 [@key] 形式写在句尾。\n"
    '输出 JSON（且仅输出 JSON，无其它文本）：'
    '{"paragraph": "段落正文", "uses": ["引用的实体 id"], "cites": ["key"]}'
)


@dataclass
class DraftResult:
    section_id: str
    run_id: str
    drafts_by_node: dict[str, dict] = field(default_factory=dict)
    reminders: list[str] = field(default_factory=list)


def _make_validate_script(section: NarrativeSection, tick_by_node: dict[str, str],
                          project: Project):
    """V 脚本：逐段形状校验 + 三规则；硬规则抛 DraftRuleError（拒绝生成）。"""

    def validate_draft(view):
        reminders: list[str] = []
        for tick, node_id in tick_by_node.items():
            try:
                raw = view[tick].value
            except (KeyError, AttributeError, TypeError) as exc:
                raise DraftRuleError(
                    _diag("E-DRAFT-SHAPE", node_id, section.id, "output",
                          f"节点输出不可读：{exc}")) from exc
            draft, shape = parse_node_draft(raw, node_id, section.id)
            if shape is not None:
                raise DraftRuleError(shape)
            node = next(n for n in section.nodes if n.id == node_id)
            for diag in check_node_draft(draft, node, project, section.id):
                if diag.is_error:
                    raise DraftRuleError(diag)
                reminders.append(
                    f"{diag.code} {diag.path} 字段 {diag.field}: {diag.message}")
        return {"reminders": reminders}

    return validate_draft


def run_draft(project: Project, section: NarrativeSection, *, client,
              align: bool = True) -> DraftResult:
    """同步入口；内部自持事件循环（weft CLI 无既有 loop）。"""
    spec = build_spec(project, section)
    if not spec["nodes"]:
        raise DraftError(f"[E-NOTHING-TO-DRAFT] 节 {section.id} 无 approved 节点")
    run_id = uuid.uuid4().hex[:8]
    tick_by_node = spec["task_nodes"]

    bus = EventBus()
    reg = HarnessRegistry(llm_client=client, event_bus=bus)
    reg.harness("draft_para", HarnessConfig(
        prompt_core=DRAFT_PARA_CORE,
        output_format=OutputFormat(type="json_object"),
        notdo=["不要输出 JSON 以外的任何文本", "不得使用 Markdown 标题或列表"],
        temperature=0.3,
    ))
    if align:
        register_align_check_harness(reg)
    reg.script("weft_validate_draft",
               _make_validate_script(section, tick_by_node, project))

    module = Module(
        spec=spec,
        tasklist=build_tasklist(spec, align=align),
        llm_client=client,
        event_bus=bus,
        registry=reg,
        module_id=f"weft-draft-{section.id}-{run_id}",
        review_harness=None,      # 决策 2：tasklist 是代码构造的，跳过一致性审核
        keep_records=False,       # 决策 3：零残留
        persist=False,
        status_file=False,
        stream_log=False,
    )
    try:
        firings = asyncio.run(module.run())
    except DraftRuleError:
        raise
    except Exception as exc:
        raise DraftError(f"[E-DRAFT-FAILED] SpecModule run 失败：{exc}") from exc

    result = DraftResult(section_id=section.id, run_id=run_id)
    for firing in firings:
        if firing.node in tick_by_node and isinstance(firing.output, dict):
            result.drafts_by_node[tick_by_node[firing.node]] = firing.output
        elif firing.node == "AL" and isinstance(firing.output, dict):
            if firing.output.get("aligned") is False:
                raise DraftError(
                    f"[E-DRAFT-FAILED] 对齐检查未通过：{firing.output.get('suggestions', '')}")
        elif firing.node == "V" and isinstance(firing.output, dict):
            result.reminders = list(firing.output.get("reminders", []))
    return result
```

然后把 `src/weft/engine/__init__.py` 更新为最终导出：

```python
"""engine 生成层（spec §5/§6）：全项目唯一 import module_harness / llm 的层。"""
from weft.engine.clients import ScriptedLLMClient, make_client
from weft.engine.draft_rules import DraftError, DraftRuleError
from weft.engine.run import DraftResult, run_draft

__all__ = [
    "DraftError", "DraftResult", "DraftRuleError",
    "ScriptedLLMClient", "make_client", "run_draft",
]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python -m pytest tests/test_engine_run.py -v`
Expected: `6 passed`。

- [ ] **Step 5: 全量回归**

Run: `.venv/Scripts/python -m pytest tests -q`
Expected: `132 passed`（126 + 6）。

- [ ] **Step 6: 零落盘验证（白名单证据）**

Run: `.venv/Scripts/python -m pytest tests/test_engine_run.py -q && git status --short`
Expected: 测试全过；`git status` 无未跟踪的 `.specmodule/`、`stream.log` 等残留（fast mode 零写入）。

- [ ] **Step 7: Commit**

```bash
git add src/weft/engine/run.py src/weft/engine/__init__.py tests/test_engine_run.py
git commit -m "feat: engine run_draft——零残留 SpecModule run、V 脚本三规则闸门、对齐检查接入"
```

---

### Task 7: CLI `weft draft` 命令

**Files:**
- Modify: `src/weft/cli.py`（import 区 + 新命令）
- Create: `tests/test_cli_draft.py`
- Modify: `tests/test_example_project.py`（追加样例验收）

- [ ] **Step 1: 写失败测试**

创建 `tests/test_cli_draft.py`：

```python
"""weft draft 命令：校验闸门、节查找、mock 端到端。"""
from typer.testing import CliRunner

from weft.cli import app
from tests.helpers import make_minimal_project, write_card

runner = CliRunner()


def test_draft_section_not_found(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["draft", "sec-99", str(tmp_path)])
    assert result.exit_code == 1
    assert "E-SECTION-NOT-FOUND" in result.output


def test_draft_nothing_approved(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "narrative", "02-intro",
               {"id": "sec-02", "section": "Intro", "order": 2,
                "nodes": [{"id": "para-02-01", "purpose": "describe",
                           "uses": [], "status": "draft"}]})
    result = runner.invoke(app, ["draft", "sec-02", str(tmp_path)])
    assert result.exit_code == 1
    assert "E-NOTHING-TO-DRAFT" in result.output


def test_draft_validation_errors_block(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "facts", "fact-02",
               {"id": "fact-02", "data": ["data-99"], "statement": "s",
                "status": "draft"})
    result = runner.invoke(app, ["draft", "sec-01", str(tmp_path)])
    assert result.exit_code == 1
    assert "拒绝生成" in result.output
    assert not (tmp_path / "drafts" / "sec-01.md").exists()


def test_draft_mock_writes_traceable_file(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["draft", "sec-01", "--mock", str(tmp_path)])
    assert result.exit_code == 0, result.output
    out = (tmp_path / "drafts" / "sec-01.md").read_text(encoding="utf-8")
    assert "<!-- weft:run=" in out
    assert "<!-- weft:node=para-01-01 uses=fact-01 -->" in out
    assert "（mock 段落）正文。" in out
    assert "已写入 drafts/sec-01.md" in result.output


def test_draft_mock_no_align_flag(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["draft", "sec-01", "--mock", "--no-align",
                                 str(tmp_path)])
    assert result.exit_code == 0, result.output


def test_draft_skips_non_approved_nodes(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "narrative", "01-results",
               {"id": "sec-01", "section": "Results", "order": 1,
                "nodes": [
                    {"id": "para-01-01", "purpose": "describe",
                     "uses": [{"id": "fact-01", "role": "evidence"}],
                     "status": "approved"},
                    {"id": "para-01-02", "purpose": "interpret",
                     "uses": [{"id": "claim-01", "role": "conclusion"}],
                     "status": "draft"},
                ]})
    result = runner.invoke(app, ["draft", "sec-01", "--mock", str(tmp_path)])
    assert result.exit_code == 0, result.output
    out = (tmp_path / "drafts" / "sec-01.md").read_text(encoding="utf-8")
    assert "para-01-01" in out
    assert "para-01-02" not in out
```

在 `tests/test_example_project.py` 末尾追加 M2 验收：

```python
def test_sample_draft_mock_end_to_end(tmp_path):
    work = _copy_sample(tmp_path)
    result = runner.invoke(app, ["draft", "sec-03", "--mock", str(work)])
    assert result.exit_code == 0, result.output
    out = (work / "drafts" / "sec-03.md").read_text(encoding="utf-8")
    assert "<!-- weft:node=para-03-01 uses=fact-01,claim-01 -->" in out
    assert "para-03-02" not in out        # draft 节点不生成
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python -m pytest tests/test_cli_draft.py tests/test_example_project.py -v`
Expected: 新增 7 个测试 FAIL（`draft` 命令不存在，typer 报 no such command，exit code 2）；原 3 条样例测试 PASS。

- [ ] **Step 3: 实现 CLI 命令**

`src/weft/cli.py` 顶部 import 区，把：

```python
from weft.diagnostics import Diagnostic
```

改为：

```python
from weft.diagnostics import Diagnostic, Level
```

在 `review` 命令之后追加（engine 的 import 放命令函数体内：依赖重且仅 draft 需要，不拖慢 validate/graph/review 启动）：

```python
@app.command()
def draft(
    section_id: str = typer.Argument(..., help="叙事节 id，如 sec-03"),
    project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录"),
    mock: bool = typer.Option(False, "--mock", help="免 key 假客户端（管线冒烟）"),
    no_align: bool = typer.Option(False, "--no-align", help="跳过对齐检查节点"),
) -> None:
    """对指定叙事节执行生成（SpecModule run），产物写入 drafts/<section>.md。"""
    from weft.engine import DraftError, DraftRuleError, make_client, run_draft
    from weft.engine.drafts import render_draft_markdown, write_draft

    project, load_diags = load_project(project_dir)
    diagnostics = load_diags + validate_project(project)
    if any(d.is_error for d in diagnostics):
        _print_diagnostics(diagnostics)
        typer.echo("—— 校验存在错误，拒绝生成")
        raise typer.Exit(code=1)

    section = next((s for s in project.sections if s.id == section_id), None)
    if section is None:
        _print_diagnostics([Diagnostic(
            Level.ERROR, "E-SECTION-NOT-FOUND", ".", None,
            f"叙事节 {section_id} 不存在")])
        raise typer.Exit(code=1)
    if not any(n.status == "approved" for n in section.nodes):
        _print_diagnostics([Diagnostic(
            Level.ERROR, "E-NOTHING-TO-DRAFT",
            project.section_paths[section.id].as_posix(), None,
            f"节 {section_id} 内没有 status: approved 的叙事节点")])
        raise typer.Exit(code=1)

    try:
        client = make_client(mock)
        result = run_draft(project, section, client=client, align=not no_align)
    except (DraftRuleError, DraftError) as exc:
        typer.echo(f"ERROR {exc}")
        raise typer.Exit(code=1) from exc

    paragraphs = {nid: d["paragraph"] for nid, d in result.drafts_by_node.items()}
    content = render_draft_markdown(section, paragraphs, result.run_id)
    path = write_draft(project, section.id, content)
    for reminder in result.reminders:
        typer.echo(f"WARN {reminder}")
    typer.echo(
        f"已写入 {path.relative_to(project.root).as_posix()}"
        f"（{len(paragraphs)} 段，run={result.run_id}）")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python -m pytest tests/test_cli_draft.py tests/test_example_project.py -v`
Expected: `10 passed`（test_cli_draft 6 条 + test_example_project 4 条 = 原 3 + 新 1）。

- [ ] **Step 5: 全量回归**

Run: `.venv/Scripts/python -m pytest tests -q`
Expected: `139 passed`（132 + 7）。

- [ ] **Step 6: 真机冒烟（人工，可选）**

Run: `cd examples/paper-demo && C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/weft.exe draft sec-03 . --mock && cat drafts/sec-03.md`
Expected: exit 0，drafts/sec-03.md 含溯源注释与 mock 段落（只 para-03-01，para-03-02 是 draft 节点被跳过）。
执行后清理：`rm -rf examples/paper-demo/drafts`（drafts/ 是产物目录，不入库）。

- [ ] **Step 7: Commit**

```bash
git add src/weft/cli.py tests/test_cli_draft.py tests/test_example_project.py
git commit -m "feat: weft draft 命令——校验闸门、approved 节点过滤、溯源草稿落盘（M2 CLI）"
```

---

### Task 8: 真实 LLM 冒烟 + 文档收尾

**Files:**
- Modify: `pyproject.toml`（pytest markers + addopts）
- Create: `tests/test_smoke_real_llm.py`
- Modify: `docs/roadmap.md`（M2 状态）

- [ ] **Step 1: 注册 smoke marker 并默认排除**

`pyproject.toml` 的 `[tool.pytest.ini_options]` 改为：

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
markers = [
    "smoke: 真实 LLM 冒烟（活 API 调用；默认排除，pytest -m smoke 显式运行）",
]
addopts = "-m 'not smoke'"
```

Run: `.venv/Scripts/python -m pytest tests -q`
Expected: `139 passed`（尚无 smoke 标记测试，行为不变）。

- [ ] **Step 2: 写冒烟测试（默认跳过）**

创建 `tests/test_smoke_real_llm.py`：

```python
"""真实 LLM 冒烟（spec §11）：默认排除。

运行：配置好 LLM 环境变量/.env 后
    set WEFT_SMOKE_LLM=1 && .venv/Scripts/python -m pytest tests -m smoke -v
"""
import os
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from weft.cli import app

pytestmark = pytest.mark.smoke
runner = CliRunner()
SAMPLE = Path(__file__).parent.parent / "examples" / "paper-demo"


@pytest.mark.skipif(not os.environ.get("WEFT_SMOKE_LLM"),
                    reason="设 WEFT_SMOKE_LLM=1 并配置 LLM 环境变量后才真正调用")
def test_real_llm_drafts_sec04(tmp_path):
    work = tmp_path / "proj"
    shutil.copytree(SAMPLE, work)
    result = runner.invoke(app, ["draft", "sec-04", str(work)])
    assert result.exit_code == 0, result.output
    draft = (work / "drafts" / "sec-04.md").read_text(encoding="utf-8")
    assert "<!-- weft:node=para-04-01" in draft
    assert len(draft.strip()) > 100        # 真实行文而非 mock 占位
```

- [ ] **Step 3: 全量回归（含 deselected 计数）**

Run: `.venv/Scripts/python -m pytest tests -q`
Expected: `139 passed, 1 deselected`。

- [ ] **Step 4: 更新 roadmap**

`docs/roadmap.md`：

1. 「当前状态」段整段替换为：

```markdown
## 当前状态

**M2 生成层已完成并合入 main（2026-09-02）**：`engine/` 适配层（specmodule==0.1.4，通道②直构 tasklist，零残留嵌入）+ `weft draft <section>` 单章节端到端生成到 `drafts/`，含生成时三规则闸门、对齐检查（`--no-align` 可关）、溯源注释；免 key `ScriptedLLMClient` 管线测试全绿，真实 LLM 冒烟以 `pytest -m smoke` 显式运行。M1 数据层（97 测试）已于同日合入。下一步进入 M3 渲染层。
```

2. M2 标题 `## M2 生成层 ⬜（下一步）` 改为 `## M2 生成层 ✅（2026-09-02）`，并在该节末尾追加一行：

```markdown
- CLI：`weft draft <section>`，`--mock` 免 key 管线冒烟、`--no-align` 跳过对齐；生成前强校验闸门（有错误即拒绝）。
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/test_smoke_real_llm.py docs/roadmap.md
git commit -m "test: 真实 LLM 冒烟（smoke marker 默认排除）+ roadmap M2 勾选（M2 Task 8）"
```

---

## 验收清单（对照设计文档 §6/§11 与 roadmap M2）

- [ ] 通道② spec+tasklist：每个 approved 叙事节点一个 harness task（Task 3 测试钉住）
- [ ] spec 携带已审阅实体全文（statement/description/source/cites/note.summary）（Task 3）
- [ ] 生成时三规则：硬规则拒绝、软提醒带回（Task 2/6）
- [ ] drafts/ 溯源注释（node id + 实体 id + run id）（Task 4/7）
- [ ] 路径白名单：零残留嵌入 + drafts 唯一落盘点（Task 6 Step 6 / Task 4）
- [ ] 免 key 管线（决策 4：ScriptedLLMClient 替代 MockLLMClient，全绿）（Task 5/6/7）
- [ ] 真实 LLM 冒烟默认排除（Task 8）
- [ ] 样例项目 sec-03 端到端（Task 7 样例验收）；sec-04 在真实 LLM 冒烟里（Task 8）
