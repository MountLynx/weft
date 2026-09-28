# weft parse 文章解析管线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 roadmap 扩展场景 #1"文章解析"——`weft parse` 把 `articles/` 收件箱中的完整文章（md/txt）经 SpecModule 五节点管线解析为 note/fact/claim 草稿卡，统一管线按 `--key` 分文献模式/拆解模式（设计定案：`docs/superpowers/specs/2026-09-28-weft-parse-design.md`）。

**Architecture:** 新建 `engine/parse/`（schemas / spec_build / run / apply）；把 run 层机械件从 `engine/inspire/run.py` 提炼为 `engine/pipeline.py`（inspire 同步切换复用，既有测试守护等价）；受控写入器从 `engine/inspire/cards.py` 迁移扩展为 `engine/card_writer.py`（支持 note）。note 同 key 冲突走三档判定（new 直落 / supplement 提案 / unchanged 零写入）。

**Tech Stack:** Python 3.10+ / pydantic / SpecModule（`module_harness[openai]`，版本锁定）/ typer / pytest。

**执行环境约定：**
- 工作区约定用 git worktree：在 `.worktrees/weft-parse` 建分支 `weft-parse` 开发，全部任务完成后合回 main 并删除 worktree（superpowers:finishing-a-development-branch）。
- Windows + Git Bash；测试命令一律 `.venv/Scripts/python.exe -m pytest …`（worktree 内需先 `.venv/Scripts/python.exe -m pip install -e ".[dev]"` 或直接用主仓 venv 跑 worktree 路径——推荐后者：`cd .worktrees/weft-parse && C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe -m pytest tests -q`）。
- 生成文件固定 LF（card_writer/scaffold 已处理，勿引入 `\r\n`）。

**基线与精确计数：** 基线 342 passed, 1 deselected（2026-09-28 实测）。本计划新增测试（Task 1:+2、Task 3:+2、Task 5:+6、Task 6:+5、Task 7:+11、Task 8:+12、Task 9:+1、Task 10:+9、Task 11:+1 deselected）→ **预期最终 390 passed, 2 deselected**。若执行期出现合理偏差，把实际数回填本表与 AGENTS.md。

## 诊断码总表（登记处，红线 5）

| 码 | 级别 | 语义 | path |
|---|---|---|---|
| `E-ARTICLE-SHAPE` | 错误 | parse 节点输出不合 schema / A1 一致性校验失败（fail-closed，整链不落盘） | `articles/<文件名>` |
| `E-ARTICLE-FAILED` | 错误 | parse 节点 aborted / 基础设施失败 / 并发重跑拒绝 | `articles/<文件名>` |
| `E-ARTICLE-KEY` | 错误 | `--key` 不在 bib 中（CLI 与 A1 双重闸门） | `articles` |
| `W-ARTICLE-LONG` | 提醒 | 文章超长（> 60,000 字符），解析质量可能下降；不阻断不分块 | `articles/<文件名>` |

命名说明：`E-PARSE` 已被 store 层占用（卡片 YAML 解析失败），故本管线用 `E-ARTICLE-*` 前缀。

## 设计决策（执行期）

| # | 决策 | 依据 |
|---|---|---|
| P1 | `all_card_ids` / `next_card_id`（原 inspire/apply.py 的 `_all_ids`/`_next_id`）随写入器迁入 `card_writer.py` 并公开——两管线 A1 的真重复，与 D8"真重复提炼"同判 | spec §8 延伸 |
| P2 | `ParseResult` 用 `run_id` 单字段（不保留 InspireResult 的 run_id+module_id 双字段历史包袱） | 简化 |
| P3 | 文献模式 claim 的 `cites` 过滤仍走"∩ project.bib_keys"（A1 机械闸），mock 客户端返回 `key2020`（make_minimal_project 的 key）作确定性测试值 | 闭包纪律 |
| P4 | note 提案写盘安排在草稿卡写盘之后、归档之前（与卡片补充提案同一批次），前置一致性校验全部在首个写盘前完成 | 零残留纪律 |
| P5 | pipeline `_slug` 空值回退 `'run'`（旧 inspire 为 `'inspire'`）：纯 CJK 文件名的 module_id 尾缀变化（weft-inspire-inspire → weft-inspire-run），fails-safe（旧快照孤立、重跑全新），无碰撞语义变化 | Task 2 质量审查发现，计划原代码即 `'run'` |
| P6 | `run_pipeline` 的 `project` 参数补 `Project` 类型标注（顺 Task 3 提交） | Task 2 质量审查建议 |
| P7 | 文献模式 P3 注入 bib key（_REVIEW_LITERATURE_SCHEMA_TEMPLATE.replace），note 三档判定可对照正确 note 卡；decompose match 回补 [@key] 归属条款（原计划 P3 prompt 缺 key，Task 6 质量审查发现） | D6"由管线判断新内容"依赖 key 可见 |
| P8 | Task 7 追加 2 个测试镜像覆盖 pipeline 两个未测分支：并发重跑拒绝（monkeypatch `query_run_status` phase=running）与首节点失败清场（leading==0 → 全新重跑），Task 7 计数 +9 → +11 | Task 2 质量审查建议（该两分支此前任何套件均未覆盖） |
| P9 | Task 8 测试 `_project` helper 在 `root` 给定且 `with_note` 时用 `write_card` 把既有 note 卡落盘：supplement/unchanged 档断言"原卡不动"读的是盘上 `metadata/notes/key2020.md`，而 `build_project` 纯内存不落盘，计划原文的测试会 FileNotFoundError（实现无需改动，A1 语义正确） | 执行期实测发现计划测试 bug |
| P10 | A1 前置 _safe_id(bib_key)（病态 bib key 含 / 或 .. 会在写卡中途炸 _safe_id，破坏零残留）；文献模式 new + 空 summary 出 WARN；补归档重名测试（Task 8 计数 +11 → +12） | Task 8 质量审查 Minor 项 |
| P11 | decompose e2e 断言改为 claims/cited/claim-02.md：mock `_PARSE_MATCH` 恒返回 cited+cites=[key2020]（服务文献模式 e2e），decompose 模式下该 claim 带合法 key 落 cited 目录同样自洽；不做 mode-aware mock（测试替身保持无状态） | Task 9 质量审查发现计划内部矛盾 |

---

### Task 1: 提炼受控写入器 `engine/card_writer.py`（+ note 支持）

**Files:**
- Create: `src/weft/engine/card_writer.py`
- Delete: `src/weft/engine/inspire/cards.py`
- Modify: `src/weft/engine/inspire/apply.py:16`（import）、`src/weft/engine/inspire/apply.py:36-50`（_next_id/_all_ids 迁出）、`src/weft/engine/inspire/apply.py:241`（_normalize import）
- Delete: `tests/test_inspire_cards.py` → Create: `tests/test_card_writer.py`

- [ ] **Step 1: 写失败测试（新文件，import 新模块必失败）**

创建 `tests/test_card_writer.py`：

```python
"""受控写入器（红线 4）：草稿卡 → metadata/（fact|claim|note），提案 → inspirations/proposals/。"""
import pytest

from weft.engine.card_writer import write_proposal, write_proposed_cards
from weft.store.project import Project
from pathlib import Path

FACT_FIELDS = {"id": "fact-09", "status": "draft", "data": ["data-01"],
               "statement": "温度提高速率。", "supports": [], "comment": ""}
CLAIM_FIELDS = {"id": "claim-09", "status": "draft", "claim_type": "cited",
                "statement": "温度有正效应。", "cites": [], "comment": ""}
NOTE_FIELDS = {"id": "key2020", "status": "draft", "summary": "文献概括。",
               "comment": ""}


def _project(tmp_path: Path) -> Project:
    return Project(root=tmp_path)


def test_write_fact_card_to_metadata(tmp_path):
    paths = write_proposed_cards(_project(tmp_path),
                                 [("fact", dict(FACT_FIELDS))])
    path = tmp_path / "metadata" / "facts" / "fact-09.md"
    assert paths == [path] and path.is_file()
    assert "id: fact-09" in path.read_text(encoding="utf-8")


def test_write_claim_card_follows_claim_type_subdir(tmp_path):
    write_proposed_cards(_project(tmp_path), [("claim", dict(CLAIM_FIELDS))])
    assert (tmp_path / "metadata" / "claims" / "cited" / "claim-09.md").is_file()
    uncited = dict(CLAIM_FIELDS, id="claim-10", claim_type="uncited")
    write_proposed_cards(_project(tmp_path), [("claim", uncited)])
    assert (tmp_path / "metadata" / "claims" / "uncited" / "claim-10.md").is_file()


def test_write_note_card_to_metadata(tmp_path):
    paths = write_proposed_cards(_project(tmp_path), [("note", dict(NOTE_FIELDS))])
    path = tmp_path / "metadata" / "notes" / "key2020.md"
    assert paths == [path] and path.is_file()
    assert "summary: 文献概括。" in path.read_text(encoding="utf-8")


def test_write_rejects_unknown_kind(tmp_path):
    with pytest.raises(ValueError):
        write_proposed_cards(_project(tmp_path),
                             [("data", dict(NOTE_FIELDS, id="data-09"))])


def test_write_normalizes_crlf(tmp_path):
    fields = dict(FACT_FIELDS, statement="第一行\r\n第二行")
    write_proposed_cards(_project(tmp_path), [("fact", fields)])
    text = (tmp_path / "metadata" / "facts" / "fact-09.md").read_bytes()
    assert b"\r" not in text


def test_write_proposal_path_and_rejects_escape(tmp_path):
    proposal_fields = dict(FACT_FIELDS, id="fact-01")
    path = write_proposal(_project(tmp_path), "fact-01", proposal_fields)
    assert path == tmp_path / "inspirations" / "proposals" / "fact-01.md"
    assert path.is_file()
    with pytest.raises(ValueError):
        write_proposal(_project(tmp_path), "../evil", dict(proposal_fields))
    with pytest.raises(ValueError):
        write_proposal(_project(tmp_path), "fact-01", dict(FACT_FIELDS))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_card_writer.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'weft.engine.card_writer'`）

- [ ] **Step 3: 创建 `src/weft/engine/card_writer.py`**

```python
"""受控写入器（红线 4）：AI 产物唯二落盘点（inspire / parse 两管线共用）。

- 草稿卡：metadata/facts|claims/<claim_type>|notes/<id>.md（status: draft，进现有审阅流）
- 替换提案：inspirations/proposals/<目标卡id>.md（metadata 扫描路径外，不撞 id）

与 engine/drafts.py 同纪律：路径不接受调用方传入，id 过逃逸检查，固定 LF。
id 分配（next_card_id / all_card_ids）是两管线 A1 聚合的真重复公用件（计划 P1）。
"""
from __future__ import annotations

from pathlib import Path

import frontmatter

from weft.store.project import Project

PROPOSALS_DIR = ("inspirations", "proposals")


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _safe_id(card_id: str) -> None:
    if not card_id or Path(card_id).name != card_id or card_id in (".", ".."):
        raise ValueError(f"非法卡 id（路径逃逸）：{card_id}")


def _card_path(project: Project, kind: str, fields: dict) -> Path:
    _safe_id(fields["id"])
    if kind == "fact":
        return project.root / "metadata" / "facts" / f"{fields['id']}.md"
    if kind == "claim":
        claim_type = fields["claim_type"]
        if claim_type not in ("cited", "uncited"):
            raise ValueError(f"非法 claim_type：{claim_type}")
        return (project.root / "metadata" / "claims" / claim_type
                / f"{fields['id']}.md")
    if kind == "note":
        return project.root / "metadata" / "notes" / f"{fields['id']}.md"
    raise ValueError(f"不支持的卡类型：{kind}")


def _write_card(path: Path, fields: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post("", **fields)
    path.write_text(_normalize(frontmatter.dumps(post)),
                    encoding="utf-8", newline="\n")
    return path


def write_proposed_cards(project: Project,
                         entries: list[tuple[str, dict]]) -> list[Path]:
    """批量写草稿卡；entries = [(kind, frontmatter 字段)]，kind ∈ fact|claim|note。"""
    return [_write_card(_card_path(project, kind, fields), fields)
            for kind, fields in entries]


def write_proposal(project: Project, target_id: str, fields: dict) -> Path:
    """写替换提案（完整新卡，id = 目标卡 id）。"""
    _safe_id(target_id)
    if fields.get("id") != target_id:
        raise ValueError(f"提案卡 id {fields.get('id')} 与目标卡 {target_id} 不一致")
    path = project.root.joinpath(*PROPOSALS_DIR) / f"{target_id}.md"
    return _write_card(path, fields)


def all_card_ids(project: Project) -> set[str]:
    """全部既有卡 id（六类卡全局唯一命名空间）。"""
    used: set[str] = set()
    for table in (project.data_cards, project.facts, project.claims,
                  project.notes, project.methods, project.params):
        used.update(table)
    return used


def next_card_id(used: set[str], prefix: str) -> str:
    """前缀-序号分配（fact-01 / claim-01…）；used 原地更新防重。"""
    n = 1
    while f"{prefix}-{n:02d}" in used:
        n += 1
    card_id = f"{prefix}-{n:02d}"
    used.add(card_id)
    return card_id
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_card_writer.py -q`
Expected: 6 passed

- [ ] **Step 5: 切换 inspire/apply.py 的 import 并删除旧写入器**

`src/weft/engine/inspire/apply.py` 三处修改：

1. 第 16 行 `from weft.engine.inspire.cards import write_proposal, write_proposed_cards` 改为：

```python
from weft.engine.card_writer import (
    all_card_ids,
    next_card_id,
    write_proposal,
    write_proposed_cards,
)
```

2. 删除 `_next_id` 与 `_all_ids` 两个函数定义（第 36–50 行），并把函数体内两处调用改名：`_next_id(used, "fact")` → `next_card_id(used, "fact")`、`_next_id(used, "claim")` → `next_card_id(used, "claim")`、`used = _all_ids(project)` → `used = all_card_ids(project)`。

3. `apply_proposal` 内 `from weft.engine.inspire.cards import _normalize` 改为 `from weft.engine.card_writer import _normalize`。

然后 `git rm src/weft/engine/inspire/cards.py`，并删除 `tests/test_inspire_cards.py`（已被 test_card_writer.py 取代）。

- [ ] **Step 6: 全量测试守护**

Run: `.venv/Scripts/python.exe -m pytest tests -q`
Expected: 344 passed, 1 deselected（342 − 4 删 + 6 新 + 2 净增）；若有 import 残漏此处会暴露

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: 受控写入器提炼 engine/card_writer.py——write_proposed_cards 扩 note 类型、id 分配公用件随迁（parse 设计 D8）"
```

---

### Task 2: 提炼管线运行层 `engine/pipeline.py`（inspire 切换复用）

**Files:**
- Create: `src/weft/engine/pipeline.py`
- Modify: `src/weft/engine/inspire/run.py`（整体重写为薄编排层）
- Modify: `tests/test_inspire_run.py:66-80`（_register_harnesses 测试改走 pipeline）

- [ ] **Step 1: 创建 `src/weft/engine/pipeline.py`（提炼自 inspire/run.py，机械件参数化）**

```python
"""多节点 SpecModule 管线公用运行层（parse 设计 §8，D8 提炼件）。

从 engine/inspire/run.py 提炼：module 构建、断点续跑/回退、firings 扫描、
节点输出 schema 校验、错误映射全部经 PipelineSpec 参数化；harness cores /
输出 schema / tasklist 构造属于各管线（engine/inspire | engine/parse），
本模块不认识任何具体管线。

与 M2 决策 14c 同语义：harness 失败不流向后继，事后扫描 fail-closed
（failed → code_shape，aborted / 缺输出 → code_failed）。persist 断点续跑：
每 tick 快照落 runs_base 下，失败后重跑经 Module.resume() 从断点续跑。
"""
import asyncio
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Type

from module_harness import (
    EventBus,
    HarnessConfig,
    HarnessRegistry,
    Module,
    OutputFormat,
    Tasklist,
)
from module_harness.infra.query import load_snapshot_summary, run_db_path
from module_harness.infra.status import query_run_status
from pydantic import BaseModel, ValidationError

_TEMPERATURE = 0.2
_MAX_TOKENS = {"max_tokens": 32768}   # SpecModule 默认 4096 会被推理模型思考耗尽（e2e 实测）
_MAX_TICKS = 14                        # 5 节点链 + 余量（M2 决策 14d）


@dataclass
class PipelineSpec:
    """一条管线的全部可变件；其余运行机械件在本模块内固化。"""

    harness_cores: dict[str, str]             # harness 名 → core prompt（顺序即注册序）
    tick_models: dict[str, Type[BaseModel]]   # tick → 输出模型（顺序 = 链序）
    module_prefix: str                        # module_id 前缀，如 weft-inspire
    runs_base: Callable[[Path], Path]         # project.root → 快照 base_dir
    code_shape: str                           # 节点输出不合 schema 的诊断码
    code_failed: str                          # 节点 aborted / 缺输出的诊断码
    error_cls: Type[Exception]                # 管线异常类型（CLI/WebUI 按此捕获）


@dataclass
class PipelineRun:
    run_id: str
    outputs: dict[str, BaseModel]
    resumed: bool = False


def _slug(source: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", Path(source).stem).strip("-")


def register_harnesses(reg, cores: dict[str, str]) -> None:
    """注册管线各 harness：json_object 输出 + 收敛温度 + 抬高输出上限。"""
    for name, core in cores.items():
        reg.harness(name, HarnessConfig(
            prompt_core=core,
            output_format=OutputFormat(type="json_object"),
            notdo=["不要输出 JSON 以外的任何文本"],
            temperature=_TEMPERATURE,
            api_params=dict(_MAX_TOKENS),
        ))


def run_pipeline(spec: PipelineSpec, project, tasklist_builder: Callable[[], Tasklist],
                 client, source: str) -> PipelineRun:
    """跑一条多节点管线；tasklist_builder() 闭包携带全文/digest/mode。"""
    module_id = f"{spec.module_prefix}-{_slug(source) or 'run'}"[:120]
    base_dir = spec.runs_base(Path(project.root))
    prior = load_snapshot_summary(module_id, base_dir=base_dir)

    resumed = False
    resume_tick = 0
    if prior is not None:
        outs = prior.get("outputs") or {}
        # 失败节点的快照 output 是 Failure 描述字符串（非 dict）——不算完成
        complete = all(isinstance(outs.get(t), dict) for t in spec.tick_models)
        status = query_run_status(module_id, base_dir=base_dir)
        if complete:
            # 上一次已全程完成：同源重跑 = 全新运行，清场防陈旧输出混入
            shutil.rmtree(run_db_path(module_id, base_dir=base_dir).parent,
                          ignore_errors=True)
            prior = None
        elif status is not None and status.phase == "running":
            raise spec.error_cls(
                f"[{spec.code_failed}] run {module_id} 正在运行（phase=running），"
                "不接受并发重跑")
        else:
            # 断点续跑：失败节点在 tickflow 里已被消费（出边写 False），
            # resume 不会重试——须回退到最后一个成功节点的 tick 快照。
            leading = 0
            for tick in spec.tick_models:
                if isinstance(outs.get(tick), dict):
                    leading += 1
                else:
                    break
            if leading == 0:
                shutil.rmtree(run_db_path(module_id, base_dir=base_dir).parent,
                              ignore_errors=True)
            else:
                resumed = True
                resume_tick = leading - 1

    bus = EventBus()
    reg = HarnessRegistry(llm_client=client, event_bus=bus)
    register_harnesses(reg, spec.harness_cores)
    module = Module(
        spec={"task_nodes": {tick: tick for tick in spec.tick_models}},
        tasklist=tasklist_builder(),
        llm_client=client,
        event_bus=bus,
        registry=reg,
        module_id=module_id,
        base_dir=base_dir,
        review_harness=None,      # tasklist 代码构造，跳过一致性审核（M2 决策 2）
        keep_records=True,        # firings 落库：断点取回节点输出 + 审计
        persist=True,             # 每 tick 快照（续跑依赖）
        status_file=True,         # 阶段状态（跨进程查询）
        control=False,
        stream_log=False,
    )
    try:
        if resumed:
            firings = asyncio.run(module.resume(rollback_to=resume_tick,
                                                max_ticks=_MAX_TICKS))
        else:
            firings = asyncio.run(module.run(max_ticks=_MAX_TICKS))
    except Exception as exc:
        raise spec.error_cls(
            f"[{spec.code_failed}] SpecModule run 失败：{exc}") from exc

    # 节点输出：以持久化 firings 的最新值为底（续跑时覆盖已完成节点），
    # 本次 firings 里的输出优先（更新）。
    summary = load_snapshot_summary(module_id, base_dir=base_dir)
    outputs: dict[str, dict] = dict((summary or {}).get("outputs") or {})
    for firing in firings:
        if firing.status == "failed":
            raise spec.error_cls(
                f"[{spec.code_shape}] 节点 {firing.node} 输出不可读："
                f"{firing.error or 'harness 失败'}")
        if firing.status == "aborted":
            raise spec.error_cls(
                f"[{spec.code_failed}] 节点 {firing.node} 基础设施失败：{firing.error}")
        if isinstance(firing.output, dict):
            outputs[firing.node] = firing.output
    missing = {t for t in spec.tick_models
               if not isinstance(outputs.get(t), dict)}
    if missing:
        raise spec.error_cls(
            f"[{spec.code_failed}] 节点未完成：{sorted(missing)}")

    parsed: dict[str, BaseModel] = {}
    for tick, model in spec.tick_models.items():
        try:
            parsed[tick] = model.model_validate(outputs[tick])
        except ValidationError as exc:
            raise spec.error_cls(
                f"[{spec.code_shape}] 节点 {tick} 输出不合 schema："
                f"{exc.errors()[0]['msg']}") from exc
    return PipelineRun(run_id=module_id, outputs=parsed, resumed=resumed)
```

（注意：原 run.py 的 `except InspireError: raise` 分支在提炼后不再需要——error_cls 就是本管线异常类型，统一走 `except Exception` 重抛路径即可，语义不变。）

- [ ] **Step 2: 重写 `src/weft/engine/inspire/run.py` 为薄编排层**

```python
"""inspire 管线：节点 schema/harness 内容 + 运行编排（inspire 设计 §4）。

运行机械件已提炼为 engine/pipeline.py（parse 设计 D8）；本模块只提供
inspire 的 cores / tick 模型 / tasklist 构造，并组装 InspireResult。
快照落 generated/inspirations/.runs/（weft 受管目录）。
"""
from dataclasses import dataclass

from weft.digest import build_digest
from weft.engine.inspire.schemas import (
    CoverageOutput,
    ExtractOutput,
    LogicOutput,
    MatchOutput,
    ReviewOutput,
)
from weft.engine.inspire.spec_build import build_inspire_tasklist
from weft.engine.pipeline import PipelineSpec, run_pipeline
from weft.store.project import Project

_HARNESS_CORES = {
    "inspire_logic": "你是灵感笔记的逻辑核查器，只输出 JSON。",
    "inspire_extract": "你是学术写作引擎的卡片拆解器，只输出 JSON。",
    "inspire_review": "你是元数据卡审查器，必须对照现有卡索引穷举比对，只输出 JSON。",
    "inspire_match": "你是文献与数据匹配器，只准使用索引中出现的 key，只输出 JSON。",
    "inspire_cover": "你是成卡覆盖审查器，逐要点对账原文与草案卡，宁可多报不可漏报，只输出 JSON。",
}
_TICK_MODELS = {"t01": LogicOutput, "t02": ExtractOutput,
                "t03": ReviewOutput, "t04": MatchOutput, "t05": CoverageOutput}


class InspireError(Exception):
    """message 首段含 [E-INSPIRE-SHAPE] / [E-INSPIRE-FAILED]（风格同 draft）。"""


@dataclass
class InspireResult:
    run_id: str
    logic: LogicOutput
    extract: ExtractOutput
    review: ReviewOutput
    match: MatchOutput
    coverage: CoverageOutput
    module_id: str = ""
    resumed: bool = False


def _spec(project: Project) -> PipelineSpec:
    return PipelineSpec(
        harness_cores=_HARNESS_CORES,
        tick_models=_TICK_MODELS,
        module_prefix="weft-inspire",
        runs_base=lambda root: root / "generated" / "inspirations" / ".runs",
        code_shape="E-INSPIRE-SHAPE",
        code_failed="E-INSPIRE-FAILED",
        error_cls=InspireError,
    )


def run_inspire(project: Project, text: str, *, client,
                source: str = "inspire") -> InspireResult:
    def _tasklist():
        return build_inspire_tasklist(text, build_digest(project))

    run = run_pipeline(_spec(project), project, _tasklist, client, source)
    return InspireResult(run_id=run.run_id, logic=run.outputs["t01"],
                         extract=run.outputs["t02"], review=run.outputs["t03"],
                         match=run.outputs["t04"], coverage=run.outputs["t05"],
                         module_id=run.run_id, resumed=run.resumed)
```

- [ ] **Step 3: 更新 `tests/test_inspire_run.py` 的 harness 注册测试**

`test_harnesses_register_with_raised_max_tokens` 整体替换为：

```python
def test_harnesses_register_with_raised_max_tokens():
    """真实推理模型思考 token 会耗尽默认 4096 输出上限（e2e 实测 finish=length
    且 content 空）；管线 harness 必须经 api_params 抬高 max_tokens。"""
    from weft.engine import pipeline
    from weft.engine.inspire import run as inspire_run

    recorded = []

    class StubReg:
        def harness(self, name, cfg):
            recorded.append((name, cfg))

    pipeline.register_harnesses(StubReg(), inspire_run._HARNESS_CORES)
    assert [name for name, _ in recorded] == list(inspire_run._HARNESS_CORES)
    for _, cfg in recorded:
        assert cfg.api_params == {"max_tokens": 32768}
```

- [ ] **Step 4: 跑 inspire 全套 + 全量测试守护等价性**

Run: `.venv/Scripts/python.exe -m pytest tests/test_inspire_run.py tests/test_cli_inspire.py tests/test_web_inspire.py -q`
Expected: 全部 passed（断点续跑/清场重跑/快照路径行为不变）

Run: `.venv/Scripts/python.exe -m pytest tests -q`
Expected: 344 passed, 1 deselected

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: 管线运行层提炼 engine/pipeline.py——PipelineSpec 参数化（cores/模型/快照/错误码/异常类），inspire 切换复用，既有测试守护等价（parse 设计 D8）"
```

---

### Task 3: `apply_proposal` 扩展 note 目标

**Files:**
- Modify: `src/weft/engine/inspire/apply.py`（apply_proposal 内 model/table 选择）
- Test: `tests/test_inspire_apply.py`（追加 2 例）

- [ ] **Step 1: 写失败测试（追加到 tests/test_inspire_apply.py 末尾）**

```python
def test_apply_proposal_supports_note_target(tmp_path):
    """parse 管线的 note 补充提案：weft replace 同一入口，归档 archive/cards/notes/。"""
    from weft.store.loader import load_project

    make_minimal_project(tmp_path)
    proposal = tmp_path / "inspirations" / "proposals" / "key2020.md"
    proposal.parent.mkdir(parents=True, exist_ok=True)
    proposal.write_text(
        "---\nid: key2020\nstatus: draft\nsummary: 旧摘要，补充了实验细节。\n"
        'comment: "取代 key2020（文章补充）"\n---\n', encoding="utf-8")
    project, _ = load_project(tmp_path)
    old_path, archive_path = apply_proposal(project, "key2020")
    assert "实验细节" in old_path.read_text(encoding="utf-8")
    assert archive_path == tmp_path / "archive" / "cards" / "notes" / "key2020.md"
    assert archive_path.is_file()
    assert not proposal.exists()


def test_apply_proposal_note_id_mismatch_rejected(tmp_path):
    from weft.store.loader import load_project

    make_minimal_project(tmp_path)
    proposal = tmp_path / "inspirations" / "proposals" / "key2020.md"
    proposal.parent.mkdir(parents=True, exist_ok=True)
    proposal.write_text("---\nid: otherkey\nstatus: draft\nsummary: x\n---\n",
                        encoding="utf-8")
    project, _ = load_project(tmp_path)
    with pytest.raises(ValueError, match="不一致"):
        apply_proposal(project, "key2020")
    assert proposal.exists()   # 磁盘零改动
```

（若测试文件顶部尚未 import `apply_proposal` / `make_minimal_project` / `pytest`，补上：
`from weft.engine.inspire.apply import apply_proposal`、`from tests.helpers import make_minimal_project`。）

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_inspire_apply.py -q -k note`
Expected: FAIL（note 目标被当成 ClaimCard 校验，报缺 claim_type 之类）

- [ ] **Step 3: 修改 `apply_proposal` 的 model/table 选择**

在 `src/weft/engine/inspire/apply.py` 的 `apply_proposal` 中，把：

```python
    is_fact = "facts" in old_rel.parts
    model = FactCard if is_fact else ClaimCard
```

改为：

```python
    from weft.models.cards import NoteCard

    is_fact = "facts" in old_rel.parts
    is_note = "notes" in old_rel.parts
    model = NoteCard if is_note else (FactCard if is_fact else ClaimCard)
```

并把闸门处：

```python
    table = project.facts if is_fact else project.claims
```

改为：

```python
    table = (project.notes if is_note
             else project.facts if is_fact else project.claims)
```

（归档路径 `archive/cards/<old_rel.parent.name>` 本就通用，notes 目标自动归档到 `archive/cards/notes/`，无需改动。顶部 `from weft.models.cards import ClaimCard, FactCard` 可顺手合并 NoteCard。）

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_inspire_apply.py -q`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: weft replace 支持 note 目标——apply_proposal 三类卡分派（parse 设计 §5）"
```

---

### Task 4: init 骨架加 `articles/` 收件箱目录

**Files:**
- Modify: `src/weft/scaffold.py:98-109`（SCAFFOLD_DIRS）
- Modify: `tests/test_scaffold.py:14-27`（SCAFFOLD_DIRS 期望元组）

- [ ] **Step 1: 更新测试期望（先红）**

`tests/test_scaffold.py` 的 `SCAFFOLD_DIRS` 元组首位插入 `"articles"`：

```python
SCAFFOLD_DIRS = (
    "articles",
    "assets",
    "figures",
    "inspirations",
    "metadata",
    "metadata/data",
    "metadata/facts",
    "metadata/notes",
    "metadata/methods",
    "metadata/params",
    "metadata/claims/cited",
    "metadata/claims/uncited",
    "narrative/01-introduction",
)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_scaffold.py -q`
Expected: FAIL（`test_init_new_dir_creates_directories`：articles 目录不存在）

- [ ] **Step 3: 修改 `src/weft/scaffold.py`**

```python
# 不随文件派生的空目录：六类卡片目录 + figures（默认 figures_dir）+ 灵感/文章收件箱。
SCAFFOLD_DIRS: tuple[str, ...] = (
    "articles",
    "figures",
    "inspirations",
    "metadata/data",
    "metadata/facts",
    "metadata/notes",
    "metadata/methods",
    "metadata/params",
    "metadata/claims/cited",
    "metadata/claims/uncited",
)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_scaffold.py tests/test_cli_init.py tests/test_web_new_project.py -q`
Expected: 全部 passed（骨架文件数仍 7，`test_cli_init.py` 的 `count("已创建 ") == 7` 不受影响；init 后 validate 仍零诊断——空目录不参与加载）

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: weft init 骨架新增 articles/ 文章收件箱（parse 设计 §2）"
```

---

### Task 5: `engine/parse/schemas.py`（P1–P5 输出契约）

**Files:**
- Create: `src/weft/engine/parse/__init__.py`
- Create: `src/weft/engine/parse/schemas.py`
- Create: `tests/test_parse_schemas.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_parse_schemas.py`：

```python
"""parse 节点输出 schema：summary 可选性、note 三档判定、supplement 校验器。"""
import pytest
from pydantic import ValidationError

from weft.engine.parse.schemas import (
    ArticleClassification,
    ArticleExtractOutput,
    ArticleMatchOutput,
    ArticleReviewOutput,
    NoteReview,
)


def test_extract_summary_defaults_empty():
    out = ArticleExtractOutput(cards=[], links=[])
    assert out.summary == ""


def test_review_note_defaults_to_none():
    out = ArticleReviewOutput(classifications=[])
    assert out.note is None


def test_note_review_supplement_requires_merged_summary():
    with pytest.raises(ValidationError):
        NoteReview(verdict="supplement", merged_summary="   ")
    note = NoteReview(verdict="supplement", merged_summary="原要点 + 新增")
    assert note.verdict == "supplement"


def test_note_review_rejects_bad_verdict():
    with pytest.raises(ValidationError):
        NoteReview(verdict="rebuild")


def test_classification_supplement_requires_merged_statement():
    with pytest.raises(ValidationError):
        ArticleClassification(key="f1", verdict="supplement", against=["fact-01"])
    assert ArticleClassification(
        key="f1", verdict="supplement", against=["fact-01"],
        merged_statement="合并陈述").merged_statement == "合并陈述"


def test_match_output_claim_type_literal():
    with pytest.raises(ValidationError):
        ArticleMatchOutput(claim_cites=[{"key": "c1", "claim_type": "quoted"}])
    out = ArticleMatchOutput.model_validate(
        {"fact_data": [], "claim_cites": [{"key": "c1", "claim_type": "cited",
                                           "cites": ["k1"]}],
         "placeholders": [{"text": "xx", "matched_fact": None}]})
    assert out.placeholders[0].matched_fact is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_parse_schemas.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'weft.engine.parse'`）

- [ ] **Step 3: 实现**

创建 `src/weft/engine/parse/__init__.py`：

```python
"""文章解析管线（parse 设计定案 2026-09-28）：schemas / spec_build / run / apply。"""
```

创建 `src/weft/engine/parse/schemas.py`：

```python
"""parse 管线节点输出 schema：P1–P5 结构化 JSON 的 pydantic 契约（parse 设计 §4）。

与 inspire schemas 平行（两管线独立演进：summary、note 三档判定为 parse 专属）。
AI 输出一律经这些模型校验，非法即 E-ARTICLE-SHAPE 整链不落盘。
拟建卡不带真实 id（临时 key f1/c1，A1 统一分配）。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ArticleLogicOutput(BaseModel):
    """P1 逻辑核查（建议性，不阻断；输出格式仍须合法）。"""

    issues: list[str] = []


class _Link(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str


class ArticleProposedCard(BaseModel):
    key: str
    kind: Literal["fact", "claim"]
    statement: str
    placeholder: bool = False
    needs_citation: bool = False


class ArticleExtractOutput(BaseModel):
    """P2 拆解：拟建卡 + 内部连接；summary 仅文献模式有值（结构化文献摘要）。"""

    cards: list[ArticleProposedCard] = []
    links: list[_Link] = []
    summary: str = ""


class ArticleClassification(BaseModel):
    key: str
    verdict: Literal["new", "conflict", "supplement"]
    against: list[str] = []   # 相关/冲突/被补充的现有卡 id
    reason: str = ""
    merged_statement: str = ""  # supplement 必填：完整新卡陈述

    @model_validator(mode="after")
    def _supplement_needs_merge(self) -> "ArticleClassification":
        if self.verdict == "supplement" and not self.merged_statement.strip():
            raise ValueError("supplement 必须给出 merged_statement（完整新卡陈述）")
        return self


class NoteReview(BaseModel):
    """note 三档判定（parse 设计 §5）：new=直落 / supplement=提案 / unchanged=不动。"""

    verdict: Literal["new", "supplement", "unchanged"]
    reason: str = ""
    merged_summary: str = ""  # supplement 必填：原摘要全部要点 + 新增整合

    @model_validator(mode="after")
    def _supplement_needs_merge(self) -> "NoteReview":
        if self.verdict == "supplement" and not self.merged_summary.strip():
            raise ValueError("supplement 必须给出 merged_summary（整合后的完整摘要）")
        return self


class ArticleReviewOutput(BaseModel):
    """P3 对照审查：卡片分类 + note 三档（拆解模式 note=None）。"""

    classifications: list[ArticleClassification] = []
    note: NoteReview | None = None


class ArticleFactMatch(BaseModel):
    key: str
    data_ids: list[str] = []


class ArticleClaimMatch(BaseModel):
    key: str
    claim_type: Literal["cited", "uncited"]
    cites: list[str] = []
    reason: str = ""


class ArticlePlaceholderMatch(BaseModel):
    text: str
    matched_fact: str | None = None


class ArticleMatchOutput(BaseModel):
    """P4 匹配：fact→data 关联；claim 分类与 cites；占位→现有 fact。"""

    fact_data: list[ArticleFactMatch] = []
    claim_cites: list[ArticleClaimMatch] = []
    placeholders: list[ArticlePlaceholderMatch] = []


class ArticleCoverageEntry(BaseModel):
    sentence: str              # 原文要点（摘录）
    card_keys: list[str] = []  # 覆盖该要点的草案卡 key
    covered: bool = True
    suggestion: str = ""       # covered=False 时：处理建议


class ArticleCoverageOutput(BaseModel):
    """P5 覆盖审查：逐要点对账文章原文与草案卡，漏卡可见。"""

    coverage: list[ArticleCoverageEntry] = []
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_parse_schemas.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: parse 管线节点输出 schema——summary 可选、note 三档判定校验器（parse 设计 §4-5）"
```

---

### Task 6: `engine/parse/spec_build.py`（双模式 Tasklist）

**Files:**
- Create: `src/weft/engine/parse/spec_build.py`
- Create: `tests/test_parse_spec_build.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_parse_spec_build.py`：

```python
"""parse spec_build：双模式 prompt 分叉、flow 单边、view 注入、key 前置。"""
import pytest

from weft.engine.parse.spec_build import build_parse_tasklist

DIGEST = "== fact ==\nfact-01 | approved | 温度提高速率。"


def _tasklist(**kwargs):
    kwargs.setdefault("text", "一篇测试文章。")
    kwargs.setdefault("digest", DIGEST)
    return build_parse_tasklist(**kwargs)


def test_flow_single_edge_per_line_and_chain_order():
    tl = _tasklist(mode="decompose")
    assert set(tl.tasks) == {"p01", "p02", "p03", "p04", "p05"}
    assert tl.flow.splitlines() == ["[p01] --> p02", "p02 --> p03",
                                    "p03 --> p04", "p04 --> p05"]


def test_view_inputs_wiring():
    tl = _tasklist(mode="decompose")
    assert tl.tasks["p03"].inputs == {"p02": "p02"}
    assert tl.tasks["p04"].inputs == {"p02": "p02", "p03": "p03"}
    assert tl.tasks["p05"].inputs == {"p02": "p02"}


def test_literature_mode_prompts():
    tl = _tasklist(mode="literature", bib_key="smith2024")
    assert "summary" in tl.tasks["p02"].prompt          # 摘要折进 P2
    assert '"note"' in tl.tasks["p03"].prompt           # note 三档判定指令
    assert "unchanged" in tl.tasks["p03"].prompt
    assert '"smith2024"' in tl.tasks["p04"].prompt      # 次级引用默认值注入


def test_decompose_mode_prompts():
    tl = _tasklist(mode="decompose")
    assert "summary" not in tl.tasks["p02"].prompt
    assert '"note"' not in tl.tasks["p03"].prompt
    assert "note/bib key" in tl.tasks["p04"].prompt     # 同 inspire 的匹配规则


def test_literature_requires_bib_key():
    with pytest.raises(ValueError):
        _tasklist(mode="literature")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_parse_spec_build.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 `src/weft/engine/parse/spec_build.py`**

```python
"""文章 → SpecModule 任务表（p01–p05 链式；parse 设计 §3-§4）。

prompt 起始标记【文章·…】兼作 mock 客户端分流键。mode 分叉：
- literature（文献模式，bib_key 必填）：P2 产 note 摘要；P3 三档判定 note；
  P4 所有 claim 默认 cites=[bib_key]（次级引用语义）。
- decompose（拆解模式）：与 inspire 同规则，不产 note。

p03/p04/p05 的 view 注入沿用 M2 决策 10：flow 只定触发边，{tick} 占位 + inputs 别名。
"""
from typing import Literal

from module_harness import TaskDefinition, Tasklist

Mode = Literal["literature", "decompose"]

_TICK_HARNESS = {
    "p01": "parse_logic",
    "p02": "parse_extract",
    "p03": "parse_review",
    "p04": "parse_match",
    "p05": "parse_cover",
}

_TEMPERATURE = 0.2   # 拆解/审查/匹配都要收敛，不用创作温度

_EXTRACT_DECOMPOSE_SCHEMA = (
    '输出 JSON：{"cards": [{"key": "f1/c1/…临时编号", "kind": "fact|claim",'
    ' "statement": "原子陈述", "placeholder": false, "needs_citation": false}],'
    ' "links": [{"from": "f1", "to": "c1"}]}。'
    "规则：数据表述→fact，观点/论断→claim；"
    "本研究数据与文献值的对比→claim（needs_citation=true），"
    "其中本研究自己的数据表述另拆一张 fact 卡并用 link 支持该对比 claim；"
    "\"xxx/某值\"类占位数据置 placeholder=true；"
    "needs_citation=该论断语义上是否需要文献支撑；links 只表达新 fact 支持新 claim。"
)

_EXTRACT_LITERATURE_SCHEMA = (
    '输出 JSON：{"summary": "结构化文献摘要（研究问题、方法、核心发现、局限；'
    '200-400 字）", "cards": [{"key": "f1/c1/…临时编号", "kind": "fact|claim",'
    ' "statement": "原子陈述", "placeholder": false, "needs_citation": true}],'
    ' "links": [{"from": "f1", "to": "c1"}]}。'
    "规则：summary 以第三人称概括本篇文献（将作为 note 卡的摘要）；"
    "本文的数据表述→fact，本文的发现/结论/论断→claim（needs_citation 通常为 true）；"
    "\"xxx/某值\"类占位数据置 placeholder=true；links 只表达新 fact 支持新 claim。"
)

_REVIEW_DECOMPOSE_SCHEMA = (
    '输出 JSON：{"classifications": [{"key": "…", "verdict": "new|conflict|supplement",'
    ' "against": ["现有卡id"], "reason": "理由", "merged_statement": ""}]}。'
    "规则：new=全新；conflict=与现有卡事实矛盾（against 填冲突卡 id，reason 必填）；"
    "supplement=与现有 fact/claim 卡高度相关且略有补充（目标只能是现存 fact/claim 卡，"
    "data/note 是人工维护的输入卡，禁止作为补充目标；against 填目标卡 id，"
    "merged_statement 必填：包含原卡全部信息与补充内容的完整新卡陈述，不得丢失原卡信息）。"
)

_REVIEW_LITERATURE_SCHEMA = (
    '输出 JSON：{"classifications": [{"key": "…", "verdict": "new|conflict|supplement",'
    ' "against": ["现有卡id"], "reason": "理由", "merged_statement": ""}],'
    ' "note": {"verdict": "new|supplement|unchanged", "reason": "理由",'
    ' "merged_summary": ""}}。'
    "规则（卡片）：new=全新；conflict=与现有卡事实矛盾（against 填冲突卡 id，reason 必填）；"
    "supplement=目标只能是现存 fact/claim 卡（data/note 是人工维护的输入卡，禁止），"
    "merged_statement 必填且不得丢失原卡信息。"
    "规则（note）：本篇文献的 bib key 见匹配节点规则；若现有卡片摘要索引中已有该 key 的"
    " note 卡，对照其摘要与本次解析的新摘要逐要点比对——有实质新内容→supplement 且"
    " merged_summary 必填（原摘要全部要点 + 新增内容整合，不得丢失原摘要信息）；"
    "无实质新内容→unchanged；索引中没有该 key 的 note 卡→new。"
)

_MATCH_DECOMPOSE_SCHEMA = (
    '输出 JSON：{"fact_data": [{"key": "…", "data_ids": ["现有data卡id"]}],'
    ' "claim_cites": [{"key": "…", "claim_type": "cited|uncited", "cites": ["bib key"],'
    ' "reason": "…"}], "placeholders": [{"text": "占位原文",'
    ' "matched_fact": "现有fact卡id或null"}]}。'
    "规则：fact 至少关联到一张现有 data 卡才可给 data_ids，关联不到就留空数组；"
    "cites 只能取索引中出现的 note/bib key；索引中的 bib key 通常编码了作者与年份"
    "（如 gikonyo2023 = Gikonyo 2023），文章中明确署名引用（如“Gikonyo et al., 2023”）"
    "或以 [@key] 引用的文献，必须在索引中查找对应 key 填入 cites，找不到才留空；"
    "语义上需要文献但索引没有→cited 且 cites 留空，不需要文献→uncited；"
    "占位优先在现有 fact 卡中匹配，没有则 matched_fact=null。"
)

_MATCH_LITERATURE_SCHEMA_TEMPLATE = (
    '输出 JSON：{"fact_data": [{"key": "…", "data_ids": ["现有data卡id"]}],'
    ' "claim_cites": [{"key": "…", "claim_type": "cited|uncited",'
    ' "cites": ["{bibkey}"], "reason": "…"}], "placeholders": [{"text": "占位原文",'
    ' "matched_fact": "现有fact卡id或null"}]}。'
    "规则：本篇文献的 bib key 是 {bibkey}——所有 claim 一律 claim_type=cited 且"
    ' cites=["{bibkey}"]（次级引用语义：引你实际读到的这篇；文中提及的他人工作也先引'
    "本篇，原始出处由人工审阅时调整；确不需引文的个别论断才 uncited）；"
    "fact 至少关联到一张现有 data 卡才可给 data_ids，关联不到就留空数组；"
    "占位优先在现有 fact 卡中匹配，没有则 matched_fact=null。"
)

_COVER_SCHEMA = (
    '输出 JSON：{"coverage": [{"sentence": "原文要点摘录",'
    ' "card_keys": ["覆盖它的草案卡 key"], "covered": true|false, "suggestion": ""}]}。'
    "规则：把文章全文逐要点对账（每个数据点、论断、对比、引用都要核对）；"
    "被至少一张草案卡覆盖→covered=true 并填 card_keys；"
    "没有任何卡覆盖→covered=false 且 suggestion 必填（该补什么卡 / 需补 data / 为何弃置）。"
)


def _logic_prompt(text: str) -> str:
    return (
        "【文章·逻辑核查】\n"
        "任务：审查以下文章的写作逻辑问题（断裂推理、未定义概念、自相矛盾、"
        "跳跃结论）；没有问题就返回空列表。这是建议性检查，不修改文本。\n"
        '输出 JSON：{"issues": ["问题描述", …]}\n'
        f"文章全文：\n{text}"
    )


def _extract_prompt(text: str, mode: Mode) -> str:
    schema = (_EXTRACT_LITERATURE_SCHEMA if mode == "literature"
              else _EXTRACT_DECOMPOSE_SCHEMA)
    return (
        "【文章·卡片拆解】\n"
        "任务：把文章拆解为原子卡片草案（一卡一意，宁可多拆不可混装）。\n"
        + schema + f"\n文章全文：\n{text}"
    )


def _review_prompt(digest: str, mode: Mode) -> str:
    schema = (_REVIEW_LITERATURE_SCHEMA if mode == "literature"
              else _REVIEW_DECOMPOSE_SCHEMA)
    return (
        "【文章·现有卡审查】\n"
        "任务：对照现有卡片逐张审查草案，穷举比对（不要只看相似的）。\n"
        f"现有卡片摘要索引：\n{digest}\n"
        "待审卡片草案（JSON）：\n{p02}\n"
        + schema
    )


def _match_prompt(text: str, digest: str, mode: Mode, bib_key: str | None) -> str:
    head = (
        "【文章·匹配】\n"
        "任务：为草案做三类匹配：fact→现有 data 卡关联；claim 的 cited/uncited "
        "分类与文献匹配；占位表述→现有 fact 卡匹配。\n"
        f"文章全文（文中 [@key] 形式的显式引用是最强信号）：\n{text}\n"
        f"现有卡片摘要索引：\n{digest}\n"
        "卡片草案（JSON）：\n{p02}\n"
        "审查结论（JSON）：\n{p03}\n"
    )
    if mode == "literature":
        return head + _MATCH_LITERATURE_SCHEMA_TEMPLATE.replace(
            "{bibkey}", bib_key or "")
    return head + _MATCH_DECOMPOSE_SCHEMA


def _cover_prompt(text: str) -> str:
    return (
        "【文章·成卡覆盖】\n"
        "任务：审查拆卡覆盖情况——逐要点核对文章原文是否都被草案卡覆盖，"
        "宁可多报不可漏报。\n"
        f"文章全文：\n{text}\n"
        "卡片草案（JSON）：\n{p02}\n"
        + _COVER_SCHEMA
    )


def build_parse_tasklist(text: str, digest: str, *, mode: Mode,
                         bib_key: str | None = None) -> Tasklist:
    if mode == "literature" and not bib_key:
        raise ValueError("文献模式（literature）需要 bib_key")
    prompts = {
        "p01": _logic_prompt(text),
        "p02": _extract_prompt(text, mode),
        "p03": _review_prompt(digest, mode),
        "p04": _match_prompt(text, digest, mode, bib_key),
        "p05": _cover_prompt(text),
    }
    tasks: dict[str, TaskDefinition] = {}
    for tick, prompt in prompts.items():
        kwargs: dict = dict(
            type="harness", harness=_TICK_HARNESS[tick],
            prompt=prompt,
            outputformat={"type": "json_object"},
            temperature=_TEMPERATURE,
        )
        if tick == "p03":
            kwargs["inputs"] = {"p02": "p02"}
        elif tick == "p04":
            kwargs["inputs"] = {"p02": "p02", "p03": "p03"}
        elif tick == "p05":
            kwargs["inputs"] = {"p02": "p02"}
        tasks[tick] = TaskDefinition(**kwargs)
    flow = "[p01] --> p02\np02 --> p03\np03 --> p04\np04 --> p05"
    return Tasklist(tasks=tasks, flow=flow)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_parse_spec_build.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: parse spec_build 双模式 Tasklist——文献/拆解 prompt 分叉、key 次级引用注入（parse 设计 §3-4）"
```

---

### Task 7: `engine/parse/run.py`（运行层，复用 pipeline）

**Files:**
- Create: `src/weft/engine/parse/run.py`
- Create: `tests/test_parse_run.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_parse_run.py`：

```python
"""parse 管线运行（复用 pipeline 提炼件）：fail-closed、快照位置、双模式注入、超长提醒。"""
import pytest

from weft.engine.parse.run import LONG_TEXT_CHARS, ParseError, run_parse
from tests.helpers import build_project
from weft.models.cards import ClaimCard, DataCard, FactCard, NoteCard

LOGIC_JSON = '{"issues": []}'
EXTRACT_JSON = ('{"summary": "本文研究了搅拌对溶解的影响。",'
                ' "cards": [{"key": "f1", "kind": "fact", "statement": "升温加速"},'
                ' {"key": "c1", "kind": "claim", "statement": "催化是主因",'
                ' "needs_citation": true}], "links": [{"from": "f1", "to": "c1"}]}')
REVIEW_JSON = ('{"classifications": [{"key": "f1", "verdict": "new"},'
               ' {"key": "c1", "verdict": "new"}],'
               ' "note": {"verdict": "new", "reason": "", "merged_summary": ""}}')
MATCH_JSON = ('{"fact_data": [{"key": "f1", "data_ids": ["data-01"]}],'
              ' "claim_cites": [{"key": "c1", "claim_type": "cited",'
              ' "cites": ["key2020"]}], "placeholders": []}')
COVER_JSON = '{"coverage": []}'


class FakeParseClient:
    """按 prompt 标记分流的假客户端（tests 层豁免分层）。"""

    def __init__(self, responses: dict[str, str], boom: bool = False):
        self.responses = responses
        self.boom = boom
        self.prompts: list[str] = []

    async def complete(self, **kwargs):
        prompt = kwargs.get("prompt") or ""
        self.prompts.append(prompt)
        if self.boom:
            raise RuntimeError("网络炸了")
        for marker, content in self.responses.items():
            if marker in prompt:
                from llm.client import LLMResponse
                return LLMResponse(content=content, usage={}, finish_reason="end_turn")
        raise AssertionError(f"未预期的 prompt：{prompt[:60]}")


def _client(**overrides) -> FakeParseClient:
    responses = {"【文章·逻辑核查】": LOGIC_JSON,
                 "【文章·卡片拆解】": EXTRACT_JSON,
                 "【文章·现有卡审查】": REVIEW_JSON,
                 "【文章·匹配】": MATCH_JSON,
                 "【文章·成卡覆盖】": COVER_JSON}
    responses.update(overrides)
    return FakeParseClient(responses)


def _project(root=None):
    return build_project(root=root,
        data=[DataCard(id="data-01", refs=["fig-01a"], description="速率测量",
                       status="approved")],
        facts=[FactCard(id="fact-01", data=["data-01"], statement="温度提高速率。",
                        status="approved")],
        claims=[ClaimCard(id="claim-01", claim_type="uncited",
                          statement="温度有正效应。", status="approved")],
        notes=[NoteCard(id="key2020", summary="热激活机制。", status="approved")],
        bib_keys={"key2020"})


def test_run_parse_parses_all_node_outputs():
    client = _client()
    result = run_parse(_project(), "一篇关于升温的文章。", client=client)
    assert result.logic.issues == []
    assert result.extract.summary == "本文研究了搅拌对溶解的影响。"
    assert [c.key for c in result.extract.cards] == ["f1", "c1"]
    match_prompt = next(p for p in client.prompts if "【文章·匹配】" in p)
    assert "fact-01" in match_prompt   # digest 注入


def test_literature_mode_injects_bib_key_and_note_review():
    client = _client()
    run_parse(_project(), "文章", client=client, bib_key="key2020")
    match_prompt = next(p for p in client.prompts if "【文章·匹配】" in p)
    assert '"key2020"' in match_prompt          # 次级引用默认值注入
    review_prompt = next(p for p in client.prompts if "【文章·现有卡审查】" in p)
    assert "unchanged" in review_prompt         # note 三档判定指令


def test_run_parse_shape_failure_is_fail_closed():
    client = _client(**{"【文章·匹配】": "这不是 JSON"})
    with pytest.raises(ParseError, match="E-ARTICLE-SHAPE"):
        run_parse(_project(), "文章", client=client)


def test_run_parse_infra_failure_maps_to_failed():
    client = FakeParseClient({}, boom=True)
    with pytest.raises(ParseError, match="E-ARTICLE-FAILED"):
        run_parse(_project(), "文章", client=client)


def test_run_parse_missing_node_output_is_failed():
    full = {"【文章·逻辑核查】": LOGIC_JSON, "【文章·卡片拆解】": EXTRACT_JSON,
            "【文章·现有卡审查】": REVIEW_JSON, "【文章·匹配】": MATCH_JSON,
            "【文章·成卡覆盖】": COVER_JSON}
    client = FakeParseClient({k: v for k, v in full.items() if k != "【文章·匹配】"})
    with pytest.raises(ParseError, match="E-ARTICLE-FAILED"):
        run_parse(_project(), "文章", client=client)


def test_run_persists_checkpoints_and_no_root_residue(tmp_path):
    from module_harness.infra.query import load_snapshot_summary

    project = _project(tmp_path)
    result = run_parse(project, "文章", client=_client(), source="paper.md")
    assert result.run_id == "weft-parse-paper"
    summary = load_snapshot_summary(
        result.run_id, base_dir=project.root / "generated" / "articles" / ".runs")
    assert summary is not None
    assert set(summary["outputs"]) >= {"p01", "p02", "p03", "p04"}
    assert not (project.root / ".specmodule").exists()


def test_run_resumes_from_checkpoint_after_failure(tmp_path):
    project = _project(tmp_path)
    flaky = _client(**{"【文章·匹配】": "这不是 JSON",
                       "【文章·成卡覆盖】": "这不是 JSON"})
    with pytest.raises(ParseError):
        run_parse(project, "文章", client=flaky, source="paper.md")

    second = _client()
    result = run_parse(project, "文章", client=second, source="paper.md")
    assert result.resumed is True
    assert result.match.fact_data[0].data_ids == ["data-01"]
    # 断点续跑：P1–P3 不再调用 LLM
    assert not any("逻辑核查" in p for p in second.prompts)
    assert any("匹配" in p for p in second.prompts)


def test_run_fresh_after_completed_run(tmp_path):
    project = _project(tmp_path)
    run_parse(project, "文章", client=_client(), source="paper.md")
    second = _client()
    result = run_parse(project, "文章", client=second, source="paper.md")
    assert result.resumed is False
    assert len(second.prompts) == 5


def test_long_text_warns_but_runs():
    client = _client()
    result = run_parse(_project(), "x" * (LONG_TEXT_CHARS + 1), client=client)
    assert len(result.warnings) == 1
    assert "W-ARTICLE-LONG" in result.warnings[0]
    assert result.run_id   # 管线照常完成（不阻断不分块）
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_parse_run.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 `src/weft/engine/parse/run.py`**

```python
"""parse 管线运行层：P1–P5 一次 SpecModule run（parse 设计 §4、§7）。

运行机械件复用 engine/pipeline.py（D8 提炼件）；本模块只提供 parse 的
cores / tick 模型 / tasklist 构造与 ParseResult 组装。快照落
generated/articles/.runs/（weft 受管目录）。W-ARTICLE-LONG 为超长提醒：
不阻断不分块（长文提醒见设计 §7）。
"""
from dataclasses import dataclass, field

from weft.digest import build_digest
from weft.engine.parse.schemas import (
    ArticleCoverageOutput,
    ArticleExtractOutput,
    ArticleLogicOutput,
    ArticleMatchOutput,
    ArticleReviewOutput,
)
from weft.engine.parse.spec_build import build_parse_tasklist
from weft.engine.pipeline import PipelineSpec, run_pipeline
from weft.store.project import Project

_HARNESS_CORES = {
    "parse_logic": "你是文章的逻辑核查器，只输出 JSON。",
    "parse_extract": "你是学术写作引擎的文章拆解器，只输出 JSON。",
    "parse_review": "你是元数据卡审查器，必须对照现有卡索引穷举比对，只输出 JSON。",
    "parse_match": "你是文献与数据匹配器，只准使用索引中出现的 key，只输出 JSON。",
    "parse_cover": "你是成卡覆盖审查器，逐要点对账原文与草案卡，宁可多报不可漏报，只输出 JSON。",
}
_TICK_MODELS = {"p01": ArticleLogicOutput, "p02": ArticleExtractOutput,
                "p03": ArticleReviewOutput, "p04": ArticleMatchOutput,
                "p05": ArticleCoverageOutput}
LONG_TEXT_CHARS = 60_000   # 超长提醒阈值（常量不配置化，YAGNI）


class ParseError(Exception):
    """message 首段含 [E-ARTICLE-SHAPE] / [E-ARTICLE-FAILED]（风格同 draft/inspire）。"""


@dataclass
class ParseResult:
    run_id: str
    logic: ArticleLogicOutput
    extract: ArticleExtractOutput
    review: ArticleReviewOutput
    match: ArticleMatchOutput
    coverage: ArticleCoverageOutput
    warnings: list[str] = field(default_factory=list)
    resumed: bool = False


def run_parse(project: Project, text: str, *, client, source: str = "article",
              bib_key: str | None = None) -> ParseResult:
    mode = "literature" if bib_key else "decompose"
    warnings: list[str] = []
    if len(text) > LONG_TEXT_CHARS:
        warnings.append(
            f"W-ARTICLE-LONG 文章超长（{len(text)} 字符 > {LONG_TEXT_CHARS}），"
            "解析质量可能下降")

    def _tasklist():
        return build_parse_tasklist(text, build_digest(project), mode=mode,
                                    bib_key=bib_key)

    spec = PipelineSpec(
        harness_cores=_HARNESS_CORES,
        tick_models=_TICK_MODELS,
        module_prefix="weft-parse",
        runs_base=lambda root: root / "generated" / "articles" / ".runs",
        code_shape="E-ARTICLE-SHAPE",
        code_failed="E-ARTICLE-FAILED",
        error_cls=ParseError,
    )
    run = run_pipeline(spec, project, _tasklist, client, source)
    return ParseResult(run_id=run.run_id, logic=run.outputs["p01"],
                       extract=run.outputs["p02"], review=run.outputs["p03"],
                       match=run.outputs["p04"], coverage=run.outputs["p05"],
                       warnings=warnings, resumed=run.resumed)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_parse_run.py -q`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: parse 管线运行层——复用 pipeline 提炼件，E-ARTICLE-* 映射、W-ARTICLE-LONG 超长提醒（parse 设计 §4、§7）"
```

---

### Task 8: `engine/parse/apply.py`（A1 聚合：note 三档 + 闭包 + 报告）

**Files:**
- Create: `src/weft/engine/parse/apply.py`
- Create: `tests/test_parse_apply.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_parse_apply.py`：

```python
"""parse A1 聚合：note 三档、落盘闭包、归档、报告、一致性 fail-closed。"""
import pytest

from weft.engine.parse.apply import apply_article
from weft.engine.parse.schemas import (
    ArticleClaimMatch,
    ArticleClassification,
    ArticleCoverageOutput,
    ArticleExtractOutput,
    ArticleFactMatch,
    ArticleLogicOutput,
    ArticleMatchOutput,
    ArticleProposedCard,
    ArticleReviewOutput,
    NoteReview,
)
from tests.helpers import build_project
from weft.models.cards import ClaimCard, DataCard, FactCard, NoteCard


def _project(root=None, *, with_note=True):
    return build_project(root=root,
        data=[DataCard(id="data-01", refs=["fig-01a"], description="速率测量",
                       status="approved")],
        facts=[FactCard(id="fact-01", data=["data-01"], statement="温度提高速率。",
                        status="approved")],
        claims=[ClaimCard(id="claim-01", claim_type="uncited",
                          statement="温度有正效应。", status="approved")],
        notes=[NoteCard(id="key2020", summary="旧摘要。", status="approved")]
              if with_note else [],
        bib_keys={"key2020"})


def _extract(summary="新解析的摘要。"):
    return ArticleExtractOutput(
        summary=summary,
        cards=[ArticleProposedCard(key="f1", kind="fact", statement="搅拌加速溶解"),
               ArticleProposedCard(key="c1", kind="claim", statement="搅拌是主因",
                                   needs_citation=True)],
        links=[])


def _review(note=None, classifications=None):
    return ArticleReviewOutput(
        classifications=classifications
        or [ArticleClassification(key="f1", verdict="new"),
            ArticleClassification(key="c1", verdict="new")],
        note=note)


def _match():
    return ArticleMatchOutput(
        fact_data=[ArticleFactMatch(key="f1", data_ids=["data-01"])],
        claim_cites=[ArticleClaimMatch(key="c1", claim_type="cited",
                                       cites=["key2020"])],
        placeholders=[])


def _source(tmp_path, name="paper.md", text="一篇关于搅拌的文章。"):
    path = tmp_path / "articles" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _apply(project, source, *, note=None, bib_key="key2020", extract=None,
           review=None, match=None):
    return apply_article(project, source=source,
                         logic=ArticleLogicOutput(),
                         extract=extract or _extract(),
                         review=review or _review(note=note),
                         match=match or _match(),
                         coverage=ArticleCoverageOutput(),
                         bib_key=bib_key)


def test_literature_new_note_lands_draft_card(tmp_path):
    source = _source(tmp_path)
    project = _project(tmp_path, with_note=False)
    outcome = _apply(project, source, note=NoteReview(verdict="new"))
    note_path = tmp_path / "metadata" / "notes" / "key2020.md"
    assert note_path in outcome.written_cards and note_path.is_file()
    text = note_path.read_text(encoding="utf-8")
    assert "status: draft" in text and "新解析的摘要。" in text


def test_literature_supplement_writes_proposal_only(tmp_path):
    source = _source(tmp_path)
    project = _project(tmp_path)   # key2020 已存在
    note = NoteReview(verdict="supplement", reason="新版补了实验",
                      merged_summary="旧摘要。新版补充：实验细节。")
    outcome = _apply(project, source, note=note)
    old_text = (tmp_path / "metadata" / "notes" / "key2020.md").read_text(encoding="utf-8")
    assert "旧摘要。" in old_text and "实验细节" not in old_text   # 既有卡不动
    proposal = tmp_path / "inspirations" / "proposals" / "key2020.md"
    assert proposal in outcome.proposals and proposal.is_file()
    proposal_text = proposal.read_text(encoding="utf-8")
    assert "实验细节" in proposal_text and "取代 key2020" in proposal_text


def test_literature_unchanged_zero_note_writes(tmp_path):
    source = _source(tmp_path)
    project = _project(tmp_path)
    outcome = _apply(project, source, note=NoteReview(verdict="unchanged"))
    note_text = (tmp_path / "metadata" / "notes" / "key2020.md").read_text(encoding="utf-8")
    assert "旧摘要。" in note_text                      # 原卡不动
    assert not (tmp_path / "inspirations" / "proposals" / "key2020.md").exists()
    assert any("维持原卡" in n for n in outcome.notes)
    assert (tmp_path / "articles" / "processed" / "paper.md").is_file()  # 原文照常归档


def test_literature_missing_note_review_is_shape_error(tmp_path):
    source = _source(tmp_path)
    project = _project(tmp_path, with_note=False)
    with pytest.raises(ValueError, match="E-ARTICLE-SHAPE"):
        _apply(project, source, note=None)
    assert source.exists()   # fail-closed：零写盘


def test_note_verdict_inconsistent_with_project_is_shape_error(tmp_path):
    source = _source(tmp_path)
    project = _project(tmp_path)   # key2020 已存在
    with pytest.raises(ValueError, match="E-ARTICLE-SHAPE"):
        _apply(project, source, note=NoteReview(verdict="new"))
    assert source.exists()


def test_bib_key_must_be_in_bib(tmp_path):
    source = _source(tmp_path)
    project = _project(tmp_path)
    with pytest.raises(ValueError, match="E-ARTICLE-KEY"):
        _apply(project, source, bib_key="ghostkey")
    assert source.exists()


def test_fact_without_data_match_not_landed(tmp_path):
    source = _source(tmp_path)
    project = _project(tmp_path, with_note=False)
    match = ArticleMatchOutput(
        fact_data=[ArticleFactMatch(key="f1", data_ids=[])],
        claim_cites=[ArticleClaimMatch(key="c1", claim_type="cited",
                                       cites=["key2020"])],
        placeholders=[])
    outcome = _apply(project, source, note=NoteReview(verdict="new"), match=match)
    landed = {p.name for p in outcome.written_cards}
    assert "fact-02.md" not in landed          # 闭包拦截：宁可少落
    assert "claim-02.md" in landed
    assert any("需补充 data 关联" in n for n in outcome.notes)


def test_claim_conflict_recorded_in_report(tmp_path):
    source = _source(tmp_path)
    project = _project(tmp_path, with_note=False)
    review = _review(note=NoteReview(verdict="new"), classifications=[
        ArticleClassification(key="f1", verdict="new"),
        ArticleClassification(key="c1", verdict="conflict", against=["claim-01"],
                              reason="方向相反")])
    outcome = _apply(project, source, note=NoteReview(verdict="new"), review=review)
    report = outcome.report.read_text(encoding="utf-8")
    assert "方向相反" in report and "claim-02" in report


def test_card_supplement_demoted_when_target_missing(tmp_path):
    source = _source(tmp_path)
    project = _project(tmp_path, with_note=False)
    review = _review(note=NoteReview(verdict="new"), classifications=[
        ArticleClassification(key="f1", verdict="supplement", against=["data-01"],
                              merged_statement="合并陈述")])
    outcome = _apply(project, source, note=NoteReview(verdict="new"), review=review)
    assert any("降级为新建草稿卡" in n for n in outcome.notes)


def test_source_must_be_in_articles(tmp_path):
    project = _project(tmp_path)
    outside = tmp_path / "elsewhere.md"
    outside.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="articles"):
        _apply(project, outside, note=NoteReview(verdict="new"))


def test_report_sections_written(tmp_path):
    source = _source(tmp_path)
    project = _project(tmp_path, with_note=False)
    outcome = _apply(project, source, note=NoteReview(verdict="new"))
    report = outcome.report.read_text(encoding="utf-8")
    for section in ("## note 判定", "## claim 分类与依据", "## fact→data 关联建议",
                    "## 成卡覆盖审查", "## 丢弃与提示"):
        assert section in report
    assert outcome.report == tmp_path / "generated" / "articles" / "paper-report.md"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_parse_apply.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 `src/weft/engine/parse/apply.py`**

```python
"""A1 聚合（parse 设计 §4–§5）：节点输出 → 落盘。

纯脚本无 LLM。落盘规则同 inspire（宁可少落，不可落出坏项目）+ note 三档判定：
- fact 至少关联到一张现有 data 卡才落盘，否则丢弃并进报告；
- claim.supports 只解析为本次随之落盘的 fact id（按构造保证无悬空）；
- note（文献模式）：new → 写草稿卡；supplement → 完整新 note 提案；unchanged → 零写入；
- 任何前置校验失败在首次写盘前抛出，磁盘零残留。
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from weft.engine.card_writer import (
    all_card_ids,
    next_card_id,
    write_proposal,
    write_proposed_cards,
)
from weft.engine.parse.schemas import (
    ArticleCoverageOutput,
    ArticleExtractOutput,
    ArticleLogicOutput,
    ArticleMatchOutput,
    ArticleReviewOutput,
)
from weft.store.project import Project


@dataclass
class ArticleApplyOutcome:
    written_cards: list[Path] = field(default_factory=list)
    proposals: list[Path] = field(default_factory=list)
    report: Path | None = None
    notes: list[str] = field(default_factory=list)   # 丢弃/缺口提示（CLI 逐行 WARN）


def apply_article(project: Project, *, source: Path, logic: ArticleLogicOutput,
                  extract: ArticleExtractOutput, review: ArticleReviewOutput,
                  match: ArticleMatchOutput, coverage: ArticleCoverageOutput,
                  bib_key: str | None = None) -> ArticleApplyOutcome:
    root = project.root
    articles = root / "articles"
    if source.parent != articles or not source.is_file():
        raise ValueError(f"文章文件必须在 {articles} 下：{source}")

    literature = bib_key is not None
    if literature and bib_key not in project.bib_keys:
        raise ValueError(f"[E-ARTICLE-KEY] --key 不在 bib 中：{bib_key}")

    # —— note 判定一致性（先于一切写盘，计划 P4）——
    note_review = review.note
    if literature and note_review is None:
        raise ValueError("[E-ARTICLE-SHAPE] 文献模式 P3 未输出 note 判定")
    if literature:
        existing_note = project.notes.get(bib_key)
        if note_review.verdict == "new" and existing_note is not None:
            raise ValueError(
                f"[E-ARTICLE-SHAPE] note 判定 new，但 {bib_key} 已存在（与索引不一致）")
        if (note_review.verdict in ("supplement", "unchanged")
                and existing_note is None):
            raise ValueError(
                f"[E-ARTICLE-SHAPE] note 判定 {note_review.verdict}，"
                f"但 {bib_key} 不存在（与索引不一致）")

    cls_by_key = {c.key: c for c in review.classifications}
    fact_match = {m.key: m for m in match.fact_data}
    claim_match = {m.key: m for m in match.claim_cites}
    used = all_card_ids(project)
    outcome = ArticleApplyOutcome()
    contradictions: list[str] = []

    # —— 前置处理：非法 supplement 降级为 new（同 inspire：模型会拿 data 卡当目标）——
    demoted: set[str] = set()
    claimed_targets: set[str] = set()
    for card in extract.cards:
        cls = cls_by_key.get(card.key)
        if cls is not None and cls.verdict == "supplement":
            target = cls.against[0] if cls.against else None
            if target is None or (target not in project.facts
                                  and target not in project.claims):
                demoted.add(card.key)
                outcome.notes.append(
                    f"草案 {card.key} 的补充目标 {target or '（未填）'} "
                    "不是现存 fact/claim 卡，降级为新建草稿卡")
            elif target in claimed_targets:
                demoted.add(card.key)
                outcome.notes.append(
                    f"草案 {card.key} 的补充目标 {target} 已有先到的提案，"
                    "降级为新建草稿卡（两条补充需人工合并）")
            else:
                claimed_targets.add(target)
    archive = articles / "processed" / source.name
    if archive.exists():
        raise ValueError(f"归档重名，拒绝覆盖：{archive}")

    def _verdict(key: str) -> str:
        if key in demoted:
            return "new"
        cls = cls_by_key.get(key)
        return cls.verdict if cls is not None else "new"

    # —— id 分配 ——
    landing_facts: dict[str, str] = {}    # 临时 key → 真实 fact id
    fact_data: dict[str, list[str]] = {}
    landing_claims: dict[str, str] = {}
    claim_needs: dict[str, bool] = {}
    supplement_specs: list[tuple[str, str]] = []   # (目标卡 id, 临时 key)

    for card in extract.cards:
        verdict = _verdict(card.key)
        if verdict == "supplement":
            supplement_specs.append((cls_by_key[card.key].against[0], card.key))
            continue
        if card.kind == "fact":
            matched = fact_match.get(card.key)
            data_ids = [d for d in (matched.data_ids if matched else [])
                        if d in project.data_cards]
            if not data_ids:
                outcome.notes.append(
                    f"草案 {card.key}（fact）未关联到任何 data 卡，未落盘——需补充 data 关联")
                continue
            landing_facts[card.key] = next_card_id(used, "fact")
            fact_data[card.key] = data_ids
        else:
            landing_claims[card.key] = next_card_id(used, "claim")
            claim_needs[card.key] = card.needs_citation

    # —— 内部连接（只在两端的卡都落盘时解析）；支持方向落在 fact.supports 上 ——
    fact_supports: dict[str, list[str]] = {k: [] for k in landing_facts}
    for link in extract.links:
        if link.from_ in landing_facts and link.to in landing_claims:
            fact_supports[link.from_].append(landing_claims[link.to])

    # —— 构建草稿卡（fact/claim + 文献模式的 note）——
    entries: list[tuple[str, dict]] = []
    note_lines: list[str] = []
    note_proposal: tuple[str, dict] | None = None
    for card in extract.cards:
        verdict = _verdict(card.key)
        origin = f"文章 {source.name}"
        if card.key in landing_facts:
            entries.append(("fact", {
                "id": landing_facts[card.key], "status": "draft",
                "data": fact_data[card.key], "statement": card.statement,
                "supports": fact_supports[card.key],
                "comment": f"来源：{origin}（草案 {card.key}）",
            }))
        elif card.key in landing_claims:
            cls = cls_by_key.get(card.key)
            m = claim_match.get(card.key)
            claim_type = m.claim_type if m is not None else (
                "cited" if claim_needs[card.key] else "uncited")
            cites = [k for k in (m.cites if m is not None else [])
                     if k in project.bib_keys]
            if m is not None and m.claim_type == "cited" and not cites:
                outcome.notes.append(
                    f"claim {landing_claims[card.key]} 分类 cited 但无文献匹配——缺文献"
                    + (f"（{m.reason}）" if m.reason else ""))
            if verdict == "conflict":
                against = "、".join(cls.against) or "（未指名）"
                contradictions.append(
                    f"{landing_claims[card.key]} ↔ {against}：{cls.reason}")
            entries.append(("claim", {
                "id": landing_claims[card.key], "status": "draft",
                "claim_type": claim_type, "statement": card.statement,
                "cites": cites,
                "comment": f"来源：{origin}（草案 {card.key}）",
            }))

    if literature:
        if note_review.verdict == "new":
            entries.append(("note", {
                "id": bib_key, "status": "draft",
                "summary": extract.summary,
                "comment": f"来源：文章 {source.name}（解析摘要）",
            }))
            note_lines.append(
                f"- 新建 note 卡 `metadata/notes/{bib_key}.md`（draft，审后 approve）")
        elif note_review.verdict == "supplement":
            fields = project.notes[bib_key].model_dump()
            fields["summary"] = note_review.merged_summary
            fields["status"] = "draft"
            fields["comment"] = (f"取代 {bib_key}（文章补充，来源：{source.name}；"
                                 f"{note_review.reason}）")
            note_proposal = (bib_key, fields)
            note_lines.append(
                f"- 补充提案 `inspirations/proposals/{bib_key}.md`"
                "（审后 `weft replace <目标卡id>` 应用）")
        else:
            note_lines.append(f"- 无实质更新，维持原 note 卡 {bib_key}")
            outcome.notes.append(f"note {bib_key} 无实质更新，维持原卡")

    outcome.written_cards = write_proposed_cards(project, entries)

    # —— 替换提案（结构化字段机械继承原卡；计划 P4：全部在草稿卡后、归档前）——
    for target, key in supplement_specs:
        cls = cls_by_key[key]
        original = project.facts.get(target) or project.claims[target]
        fields = original.model_dump()
        fields["statement"] = cls.merged_statement
        fields["status"] = "draft"
        fields["comment"] = f"取代 {target}（文章补充，来源：{source.name}；{cls.reason}）"
        outcome.proposals.append(write_proposal(project, target, fields))
    if note_proposal is not None:
        outcome.proposals.append(
            write_proposal(project, note_proposal[0], note_proposal[1]))

    # —— 原文归档 ——
    archive.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(archive))

    # —— 报告 ——
    report = root / "generated" / "articles" / f"{source.stem}-report.md"
    outcome.report = _write_article_report(
        report, source, logic, contradictions, outcome.written_cards,
        outcome.proposals, match, outcome.notes, coverage, note_lines)
    return outcome


def _write_article_report(report: Path, source: Path, logic: ArticleLogicOutput,
                          contradictions: list[str], cards: list[Path],
                          proposals: list[Path], match: ArticleMatchOutput,
                          notes: list[str], coverage: ArticleCoverageOutput,
                          note_lines: list[str]) -> Path:
    lines = [f"# 文章解析报告：{source.name}", ""]
    lines += ["## 逻辑核查（建议性）", ""]
    lines += [f"- {issue}" for issue in logic.issues] or ["- （无）"]
    lines += ["", "## note 判定", ""]
    lines += note_lines or ["- （拆解模式，不产 note）"]
    lines += ["", "## 矛盾（需人工仲裁）", ""]
    lines += [f"- {c}" for c in contradictions] or ["- （无）"]
    lines += ["", "## 新建草稿卡", ""]
    lines += [f"- {p.relative_to(report.parents[2]).as_posix()}" for p in cards] \
        or ["- （无）"]
    lines += ["", "## 替换提案（审后 `weft replace <目标卡id>` 应用）", ""]
    lines += [f"- {p.relative_to(report.parents[2]).as_posix()}"
              for p in proposals] or ["- （无）"]
    lines += ["", "## claim 分类与依据", ""]
    lines += [f"- {m.key}: {m.claim_type}"
              + (f" cites={','.join(m.cites)}" if m.cites else "")
              + (f"（{m.reason}）" if m.reason else "")
              for m in match.claim_cites] or ["- （无）"]
    lines += ["", "## fact→data 关联建议", ""]
    lines += [f"- {m.key}: data={','.join(m.data_ids) or '（未匹配——需补充）'}"
              for m in match.fact_data] or ["- （无）"]
    lines += ["", "## 匹配与缺口", ""]
    for m in match.claim_cites:
        if m.claim_type == "cited" and not m.cites:
            lines.append(f"- 缺文献：{m.key}（{m.reason or '未说明'}）")
    for p in match.placeholders:
        if p.matched_fact:
            lines.append(f"- 占位“{p.text}”匹配现有卡 {p.matched_fact}")
        else:
            lines.append(f"- 占位“{p.text}”无匹配 fact——需补充")
    if not any(m.claim_type == "cited" and not m.cites for m in match.claim_cites) \
            and not match.placeholders:
        lines.append("- （无）")
    lines += ["", "## 成卡覆盖审查", ""]
    missed = [c for c in coverage.coverage if not c.covered]
    lines.append(f"- 覆盖 {len(coverage.coverage) - len(missed)}"
                 f"/{len(coverage.coverage)} 个要点")
    for c in missed:
        lines.append(f"- 未成卡：“{c.sentence}”——{c.suggestion}")
    lines += ["", "## 丢弃与提示", ""]
    lines += [f"- {n}" for n in notes] or ["- （无）"]
    lines.append("")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return report
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_parse_apply.py -q`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: parse A1 聚合——note 三档判定、落盘闭包、归档与解析报告（parse 设计 §4-5、§10）"
```

---

### Task 9: ScriptedLLMClient 增加文章分支（`--mock` 依赖）

**Files:**
- Modify: `src/weft/engine/clients.py`（mock 响应 + `_respond` 分支）
- Modify: `tests/test_clients.py`（追加 1 例）

- [ ] **Step 1: 写失败测试（追加到 tests/test_clients.py）**

```python
def test_scripted_parse_branches():
    """文章解析 mock 响应：与 make_minimal_project 自洽（key2020 / data-01）。"""
    import json

    from weft.engine.clients import ScriptedLLMClient

    client = ScriptedLLMClient()
    extract = json.loads(client._respond("【文章·卡片拆解】\n文章全文：\nx"))
    assert extract["summary"] and extract["cards"][0]["key"] == "f1"
    review = json.loads(client._respond("【文章·现有卡审查】\n草案：\nx"))
    assert review["note"]["verdict"] == "new"
    match = json.loads(client._respond("【文章·匹配】\n索引：\nx"))
    assert match["claim_cites"][0]["cites"] == ["key2020"]
    logic = json.loads(client._respond("【文章·逻辑核查】\n全文：\nx"))
    assert logic["issues"] == []
    cover = json.loads(client._respond("【文章·成卡覆盖】\n草案：\nx"))
    assert cover["coverage"] == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_clients.py -q -k parse`
Expected: FAIL（走通用兜底分支，返回 paragraph 形状）

- [ ] **Step 3: 实现——`src/weft/engine/clients.py`**

类属性区（`_INSPIRE_MATCH` 之后）追加：

```python
    _PARSE_EXTRACT = json.dumps(
        {"summary": "（mock 摘要）本文研究了搅拌对溶解速率的影响。",
         "cards": [{"key": "f1", "kind": "fact", "statement": "（mock 事实）搅拌加速溶解。",
                    "placeholder": False, "needs_citation": False},
                   {"key": "c1", "kind": "claim", "statement": "（mock 观点）搅拌是主要因素。",
                    "placeholder": False, "needs_citation": False}],
         "links": [{"from": "f1", "to": "c1"}]}, ensure_ascii=False)
    _PARSE_REVIEW = json.dumps(
        {"classifications": [{"key": "f1", "verdict": "new"},
                             {"key": "c1", "verdict": "new"}],
         "note": {"verdict": "new", "reason": "", "merged_summary": ""}},
        ensure_ascii=False)
    _PARSE_MATCH = json.dumps(
        {"fact_data": [{"key": "f1", "data_ids": ["data-01"]}],
         "claim_cites": [{"key": "c1", "claim_type": "cited", "cites": ["key2020"],
                          "reason": "（mock）本篇文献"}],
         "placeholders": []}, ensure_ascii=False)
```

`_respond` 中 `【灵感·成卡覆盖】` 分支之后追加：

```python
        if "【文章·逻辑核查】" in prompt:
            return json.dumps({"issues": self.logic_issues}, ensure_ascii=False)
        if "【文章·卡片拆解】" in prompt:
            return self._PARSE_EXTRACT
        if "【文章·现有卡审查】" in prompt:
            return self._PARSE_REVIEW
        if "【文章·匹配】" in prompt:
            return self._PARSE_MATCH
        if "【文章·成卡覆盖】" in prompt:
            return json.dumps({"coverage": []}, ensure_ascii=False)
```

并把类 docstring 的分支列表补一行 `- 【文章·…】：parse 管线各节点默认响应（与 make_minimal_project 自洽，key2020）。`

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_clients.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: ScriptedLLMClient 文章分支——parse 管线 mock 冒烟底座（parse 设计 §6）"
```

---

### Task 10: CLI `weft parse`

**Files:**
- Modify: `src/weft/cli.py`（新增 parse 命令，放在 inspire 之后）
- Create: `tests/test_cli_parse.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_cli_parse.py`：

```python
"""CLI：weft parse（双模式、闸门、收件箱）。"""
import os
from typer.testing import CliRunner

from weft.cli import app
from tests.helpers import make_minimal_project, write_card

runner = CliRunner()


def _article(root, name="paper.md", text="一篇关于搅拌加速溶解的文章，认为搅拌是主因。"):
    path = root / "articles" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_cli_parse_mock_end_to_end_decompose(tmp_path):
    make_minimal_project(tmp_path)
    source = _article(tmp_path)
    result = runner.invoke(app, ["parse", str(source), str(tmp_path), "--mock"])
    assert result.exit_code == 0, result.output
    assert "已写入 metadata/facts/fact-02.md" in result.output
    assert "claims/cited/claim-02.md" in result.output   # mock match 恒 cited（P11）
    assert (tmp_path / "articles" / "processed" / "paper.md").is_file()
    assert not source.exists()
    report = tmp_path / "generated" / "articles" / "paper-report.md"
    assert report.is_file() and "报告" in result.output


def test_cli_parse_mock_end_to_end_literature_note(tmp_path):
    make_minimal_project(tmp_path)
    (tmp_path / "metadata" / "notes" / "key2020.md").unlink()  # mock note 判定为 new
    source = _article(tmp_path)
    result = runner.invoke(app, ["parse", str(source), str(tmp_path),
                                 "--key", "key2020", "--mock"])
    assert result.exit_code == 0, result.output
    assert "已写入 metadata/notes/key2020.md" in result.output
    claim = tmp_path / "metadata" / "claims" / "cited" / "claim-02.md"
    assert claim.is_file()
    assert "key2020" in claim.read_text(encoding="utf-8")   # 次级引用落 cites


def test_cli_parse_rejects_key_not_in_bib(tmp_path):
    make_minimal_project(tmp_path)
    source = _article(tmp_path)
    result = runner.invoke(app, ["parse", str(source), str(tmp_path),
                                 "--key", "ghostkey", "--mock"])
    assert result.exit_code == 1
    assert "E-ARTICLE-KEY" in result.output
    assert source.exists()   # 闸门拒绝，收件箱不动


def test_cli_parse_rejects_file_outside_articles(tmp_path):
    make_minimal_project(tmp_path)
    outside = tmp_path / "elsewhere.md"
    outside.write_text("x", encoding="utf-8")
    result = runner.invoke(app, ["parse", str(outside), str(tmp_path)])
    assert result.exit_code == 1
    assert "articles" in result.output


def test_cli_parse_picks_oldest_without_arg(tmp_path):
    make_minimal_project(tmp_path)
    newer = _article(tmp_path, "new.md")
    older = _article(tmp_path, "old.txt")
    os.utime(newer, (2000000000, 2000000000))
    os.utime(older, (1000000000, 1000000000))
    result = runner.invoke(app, ["parse", str(tmp_path), "--mock"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "articles" / "processed" / "old.txt").is_file()
    assert newer.is_file()   # 只处理最旧的一个（.txt 同样收）


def test_cli_parse_empty_inbox_exits_1(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["parse", str(tmp_path)])
    assert result.exit_code == 1
    assert "收件箱" in result.output


def test_cli_parse_validation_gate(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "facts", "fact-09",
               {"id": "fact-09", "data": ["data-99"], "statement": "s",
                "status": "draft"})
    source = _article(tmp_path)
    result = runner.invoke(app, ["parse", str(source), str(tmp_path), "--mock"])
    assert result.exit_code == 1
    assert "拒绝" in result.output
    assert source.exists()


def test_cli_parse_real_client_failure_is_clean(tmp_path):
    """无配置走真实客户端 → 干净 ERROR，不甩 traceback。"""
    make_minimal_project(tmp_path)
    source = _article(tmp_path)
    result = runner.invoke(app, ["parse", str(source), str(tmp_path)])
    assert result.exit_code == 1
    assert result.output.startswith("ERROR")
    assert "Traceback" not in result.output
    assert source.exists()


def test_cli_replace_note_proposal_end_to_end(tmp_path):
    """parse 产出的 note 提案经 weft replace 应用（CLI 级闭环）。"""
    make_minimal_project(tmp_path)
    proposal = tmp_path / "inspirations" / "proposals" / "key2020.md"
    proposal.parent.mkdir(parents=True, exist_ok=True)
    proposal.write_text(
        "---\nid: key2020\nstatus: draft\nsummary: 旧摘要，补充了实验细节。\n"
        'comment: "取代 key2020（文章补充）"\n---\n', encoding="utf-8")
    result = runner.invoke(app, ["replace", "key2020", str(tmp_path)])
    assert result.exit_code == 0, result.output
    new_text = (tmp_path / "metadata" / "notes" / "key2020.md").read_text(encoding="utf-8")
    assert "实验细节" in new_text
    assert (tmp_path / "archive" / "cards" / "notes" / "key2020.md").is_file()
    assert not proposal.exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cli_parse.py -q`
Expected: FAIL（`parse` 命令不存在）

- [ ] **Step 3: 实现——`src/weft/cli.py` 在 `inspire` 命令之后新增**

```python
@app.command()
def parse(
    target: Path = typer.Argument(
        None, help="文章 md/txt（须在 articles/ 下）或项目根目录；缺省取当前项目收件箱最旧一个"),
    project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录"),
    key: str = typer.Option(None, "--key",
                            help="文献模式：bib key（必须已在 bib；不给 = 拆解模式）"),
    mock: bool = typer.Option(False, "--mock", help="免 key 假客户端（管线冒烟）"),
) -> None:
    """解析一篇文章 → 草稿卡 + 替换提案 + 处理报告（parse 管线，fail-closed）。"""
    from weft.engine import DraftError, make_client
    from weft.engine.parse.apply import apply_article
    from weft.engine.parse.run import ParseError, run_parse

    file: Path | None = target
    if target is not None and target.is_dir():
        # 单位置用法：weft parse <项目根>（同 validate/inspire 的习惯）
        project_dir, file = target, None

    project, load_diags = load_project(project_dir)
    diagnostics = load_diags + validate_project(project)
    if any(d.is_error for d in diagnostics):
        _print_diagnostics(diagnostics)
        typer.echo("—— 校验存在错误，拒绝处理文章")
        raise typer.Exit(code=1)
    if key is not None and key not in project.bib_keys:
        _print_diagnostics([Diagnostic(
            Level.ERROR, "E-ARTICLE-KEY", "articles", None,
            f"--key 不在 bib 中：{key}")])
        raise typer.Exit(code=1)

    inbox = project.root / "articles"
    if file is None:
        candidates = sorted(p for pattern in ("*.md", "*.txt")
                            for p in (inbox.glob(pattern) if inbox.is_dir() else []))
        if not candidates:
            typer.echo(f"ERROR 文章收件箱为空：{inbox}")
            raise typer.Exit(code=1)
        source = min(candidates, key=lambda p: p.stat().st_mtime)
    else:
        source = file if file.is_absolute() else Path.cwd() / file
        if (not source.is_file() or source.suffix.lower() not in (".md", ".txt")
                or source.resolve().parent != inbox.resolve()):
            typer.echo(f"ERROR 文章文件必须是 {inbox} 下的 .md/.txt：{file}")
            raise typer.Exit(code=1)

    text = source.read_text(encoding="utf-8")
    try:
        result = run_parse(project, text,
                           client=make_client(mock, project_root=project.root),
                           source=source.name, bib_key=key)
        outcome = apply_article(project, source=source, logic=result.logic,
                                extract=result.extract, review=result.review,
                                match=result.match, coverage=result.coverage,
                                bib_key=key)
    except (ParseError, DraftError, ValueError, OSError) as exc:
        typer.echo(f"ERROR {exc}")
        raise typer.Exit(code=1) from exc
    if result.resumed:
        typer.echo("本次为断点续跑：已完成节点取自上次快照（generated/articles/.runs/）")
    for path in outcome.written_cards:
        typer.echo(f"已写入 {path.relative_to(project.root).as_posix()}")
    for path in outcome.proposals:
        typer.echo(f"已生成替换提案 {path.relative_to(project.root).as_posix()}"
                   "（审后 weft replace 应用）")
    typer.echo(f"报告 {outcome.report.relative_to(project.root).as_posix()}")
    for warning in result.warnings:
        typer.echo(f"WARN {warning}")
    for note in outcome.notes:
        typer.echo(f"WARN {note}")
    warnings = [d for d in diagnostics if not d.is_error]
    if warnings:
        _print_diagnostics(warnings)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cli_parse.py -q`
Expected: 9 passed

- [ ] **Step 5: 全量测试**

Run: `.venv/Scripts/python.exe -m pytest tests -q`
Expected: 390 passed, 1 deselected（342 基线 + Task1 +2 + Task3 +2 + Task5 +6 + Task6 +5 + Task7 +11 + Task8 +12 + Task9 +1 + Task10 +9 = 390；smoke 在 Task 11 追加后再 +1 deselected）

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: CLI weft parse——双模式文章解析命令，E-ARTICLE-KEY 前置闸门、收件箱最旧优先（parse 设计 §6）"
```

---

### Task 11: 真实 LLM 冒烟（`-m smoke`，默认排除）

**Files:**
- Modify: `tests/test_smoke_real_llm.py`（追加 1 例）

- [ ] **Step 1: 追加冒烟测试**

```python
@pytest.mark.skipif(not os.environ.get("WEFT_SMOKE_LLM"),
                    reason="设 WEFT_SMOKE_LLM=1 并配置 LLM 环境变量后才真正调用")
def test_real_llm_parses_article(tmp_path):
    """文献模式真实冒烟：key 取样例项目任一 note id（= bib key）。"""
    work = tmp_path / "proj"
    shutil.copytree(SAMPLE, work)
    for name in ("config.json", ".env"):   # 用户提供：LLM 配置在 SpecModule 目录
        src = SPECMODULE / name
        if src.exists():
            shutil.copy(src, work / name)
    note_key = next((work / "metadata" / "notes").glob("*.md")).stem
    (work / "articles").mkdir(exist_ok=True)
    article = work / "articles" / "smoke.md"
    article.write_text(
        "本文研究温度对反应速率的影响。实验表明，升温显著提高反应速率，"
        "升温 10 K 速率约提高一倍。作者认为热激活是主要机制，"
        "并指出搅拌条件的控制对重复性至关重要。\n",
        encoding="utf-8")
    result = runner.invoke(app, ["parse", str(article), str(work),
                                 "--key", note_key])
    assert result.exit_code == 0, result.output
    assert (work / "generated" / "articles" / "smoke-report.md").is_file()
```

- [ ] **Step 2: 确认默认排除 + 冒烟链路语法正确**

Run: `.venv/Scripts/python.exe -m pytest tests/test_smoke_real_llm.py -q`
Expected: `2 deselected`（draft + parse 两个冒烟都默认跳过；不设 WEFT_SMOKE_LLM 不触网）

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "test: parse 真实 LLM 冒烟——文献模式端到端（-m smoke 双保险门）"
```

---

### Task 12: 文档回填 + 计数登记（合并前收尾）

**Files:**
- Modify: `AGENTS.md`（必读文档、常用命令计数、CLI 清单、红线 4、红线 5）
- Modify: `docs/roadmap.md`（扩展场景 #1 状态）
- Modify: 本计划文档（执行期实际计数回填）

- [ ] **Step 1: AGENTS.md 五处更新**

1. 必读文档清单追加一行（放在 inspire 设计之后、WebUI 样式之前）：

```markdown
- `docs/superpowers/specs/2026-09-28-weft-parse-design.md` — 文章解析管线设计定案（统一管线双模式：文献/拆解、note 三档判定、E-ARTICLE-* 诊断码）；其计划文档 `2026-09-28-weft-parse.md` 含执行期决策 P1–P4
```

2. 常用命令全量测试注释改为实际计数（预期 `# 全量测试（390 passed, 2 deselected）`，以实测为准）。

3. CLI 清单行加 `parse`：

```markdown
.venv/Scripts/weft.exe --help                           # CLI：init / validate / graph / review / draft / assemble / render / inspire / parse / replace / missing-cites / serve
```

4. 红线 4 白名单路径更新——把 `engine/inspire/cards.py` 改为 `engine/card_writer.py`，并把快照目录扩为两处：

```markdown
4. **路径白名单**：AI 产物唯一落盘点是 `engine/drafts.py::write_draft` 的 `drafts/<part_id>.md` 与 `engine/card_writer.py` 的 `metadata/` 草稿卡 + `inspirations/proposals/` 提案（均固定 LF，写入前归一化 CRLF）。draft 管线的 SpecModule 以零残留模式运行（`persist/status_file/keep_records/stream_log` 全 False）；inspire/parse 管线例外——开启 persist 断点续跑，运行快照只落 `generated/inspirations/.runs/` 与 `generated/articles/.runs/`（weft 受管目录），其余任何位置不得出现 `.specmodule/` 残留。
```

5. 红线 5 总表指向追加：`…、2026-09-04-weft-inspire.md（E-INSPIRE-SHAPE / E-INSPIRE-FAILED）、2026-09-28-weft-parse.md（E-ARTICLE-SHAPE / E-ARTICLE-FAILED / E-ARTICLE-KEY / W-ARTICLE-LONG）`。

- [ ] **Step 2: roadmap.md 扩展场景 #1 标记完成**

把：

```markdown
1. **文章解析**：AI 从现成文章抽取 fact/claim 草稿卡 → 人工审阅；cited 缺引文 → 提醒补文献。
```

改为：

```markdown
1. **文章解析** ✅（2026-09-28 落地，设计定案 `docs/superpowers/specs/2026-09-28-weft-parse-design.md`）：`weft parse` SpecModule 五节点管线（逻辑核查 / 拆解+摘要 / 对照审查 / 匹配 / 覆盖），统一管线按 `--key` 分文献模式（note 卡 + 次级引用 claim）与拆解模式（fact/claim，data 闭包）；同 key note 三档判定（new 直落 / supplement 提案 / unchanged 零写入）；run 机械件提炼 `engine/pipeline.py`、受控写入器提炼 `engine/card_writer.py`（inspire 同步复用）。
```

- [ ] **Step 3: 全量测试拿最终计数并回填**

Run: `.venv/Scripts/python.exe -m pytest tests -q`
Expected: **390 passed, 2 deselected**（与计划预期一致；若有偏差，回填本计划头部与 AGENTS.md 为实际值，并在下方执行记录注明原因）

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "docs: AGENTS/roadmap 回填——parse 管线入必读清单与红线 4/5，扩展场景 #1 完成"
```

---

## 执行记录（执行期回填）

| Task | 实际测试计数 | 偏差与原因 |
|---|---|---|
| （执行时填写） | | |
