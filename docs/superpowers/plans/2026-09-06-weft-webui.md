# weft WebUI 实施计划（2026-09-06）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 weft 构建可部署到服务器的 FastAPI + htmx WebUI，覆盖浏览、审阅、卡片/节点编辑、draft/inspire 生成（SSE 实时进度流），供学校 LLM 开发比赛部署演示。

**Architecture:** `src/weft/web/` 是 weft 公共 API 之上的薄壳（设计文档 `docs/superpowers/specs/2026-09-06-weft-webui-design.md`）：读操作进程内调 `load_project`/`validate_project`，写操作走新增 `store/writer.py`（pydantic 校验后 LF 落盘），生成走提炼出的 engine 共享 runner（`cli.draft` 同步接线复用）。前端 Jinja2 + htmx（vendor 本地），SSE 用原生 EventSource。

**Tech Stack:** Python 3.11 / FastAPI / uvicorn / Jinja2 / htmx / pytest（TestClient + 既有 `ScriptedLLMClient`）。

---

## 必读上下文（执行者开工前）

1. `AGENTS.md` — 架构红线（分层/白名单/诊断码/生成闸门）、Windows 注意事项、提交规范。
2. `docs/superpowers/specs/2026-09-06-weft-webui-design.md` — 本计划的设计定案。
3. 关键现有 API（已实测核实，直接使用勿再猜）：
   - `weft.store.loader.load_project(root) -> tuple[Project, list[Diagnostic]]`
   - `weft.validation.validate_project(project) -> list[Diagnostic]`
   - `Diagnostic(level, code, path, field, message)`、`d.is_error`（`weft/diagnostics.py`）
   - `Project` 属性：`root/data_cards/facts/claims/notes/methods/params/parts/figures/bib_keys/card_paths/part_paths/part_chapters`（`store/project.py`）
   - `weft.engine.make_client(mock: bool, project_root: Path | None)`、`run_draft(project, part, node, *, client, workflow, overview, prior_paragraphs, prev_tail, next_head=None) -> DraftResult`（`engine/run.py:107`）
   - `weft.engine.drafts.render_draft_markdown(part, paragraphs_by_node, run_id) -> str`、`write_draft(project, part_id, content) -> Path`
   - `weft.workflow.resolve_workflow(part, chapter_dir) -> str`、`PURPOSE_VOCAB`/`ROLE_VOCAB`（`validation/rules.py:13-14`）、`WORKFLOW_VOCAB`
   - `weft.graphgen.writer.write_outputs(project, out_dir) -> list[Path]`；`graph.json` 顶层为实体反向索引（`{id: {kind, status, referenced_by: {facts, claims, methods, params, nodes}}}`，`graphgen/index.py:29`）
   - inspire：`run_inspire(project, text, *, client, source) -> InspireResult`（字段 logic/extract/review/match/coverage/resumed）、`apply_inspiration(project, *, source, logic, extract, review, match, coverage) -> ApplyOutcome`（字段 written_cards/proposals/report/notes）
   - 卡片模型（`models/cards.py`，`extra="forbid"`）：`_Card(id, status, comment)` + 各类字段；claim 的 `claim_type` 决定目录（loader 强制一致）；实体 id 全局唯一（data/fact/claim/note/method/param 共用命名空间）
   - 叙事 part 文件 = frontmatter（`NarrativePart` 模型）+ markdown 正文（`store/loader.py:147`）；`NarrativePart(id, section, workflow, nodes)`、`Node(id, purpose, uses: list[Use], logic, status, comment)`、`Use(id, role)`
   - 测试：`tests/helpers.py` 的 `make_minimal_project(root)`（校验 0 错 0 醒，part id=`sec-01`，1 个 approved 节点 `para-01-01`）与 `write_card(directory, name, meta, body="")`
4. 执行环境：Windows + Git Bash；命令一律 `.venv/Scripts/python.exe -m pytest …`；生成文件固定 LF；提交信息中文 conventional commit；**不要 push**。

## 文件结构

```text
src/weft/web/
├── __init__.py          # create_app(projects_root)（Task 1 建，Task 5 完善模板/静态挂载）
├── common.py            # templates、KIND_* 映射、load_entry_or_404 等共享 helpers（Task 5）
├── discovery.py         # 项目扫描识别（Task 4）
├── runs.py              # RunManager/Run/sse_stream：per-project 锁 + 事件队列（Task 11）
├── card_forms.py        # FieldSpec/FIELD_SPECS/表单解析（Task 7）
├── routes/
│   ├── __init__.py      # register_all(app)（Task 5）
│   ├── core.py          # /、/p/{pid}/ 总览、graph、diagnostics、files（Task 5/12）
│   ├── cards.py         # 卡片列表/详情/审阅/编辑/新建（Task 6/7/8）
│   ├── parts.py         # 叙事工作台/节点编辑/生成触发/SSE 路由（Task 9/10/11）
│   └── inspire.py       # 灵感页/提案应用（Task 13）
├── templates/           # base/index/dashboard/unavailable/cards/card_detail/card_form/
│                        # parts/part_panel/run_console/node_form/inspire/diagnostics/
│                        # graph/file_view（各 Task 内给出完整内容）
└── static/              # webui.css、webui.js、htmx.min.js、cytoscape.min.js（vendor）
src/weft/store/writer.py     # save_card/create_card/next_card_id/save_part（Task 2）
src/weft/engine/part_draft.py # DraftEvent/run_part_draft 共享 runner（Task 3）
tests/webutil.py             # WebUI 测试公共夹具（Task 5）
tests/test_web_app.py test_store_writer.py test_part_draft.py test_web_discovery.py
tests/test_web_pages.py test_web_cards.py test_web_card_edit.py test_web_card_new.py
tests/test_web_parts.py test_web_node_edit.py test_web_generate.py test_web_misc.py
tests/test_web_inspire.py
修改：pyproject.toml（[web] 依赖组）、src/weft/cli.py（serve 子命令 + draft 接线 runner）、
     src/weft/engine/inspire/apply.py（提炼 apply_proposal）、docs/roadmap.md、docs/webui.md
```

工作方式：**Task 0 建 git worktree 执行**（AGENTS.md 约定，主区未提交改动互不影响）。每任务 TDD（先红后绿）+ 提交。

## 精确测试计数登记

| 任务 | 新增测试数 |
|---|---|
| T1 依赖+app 骨架+serve | 2 |
| T2 store/writer | 6 |
| T3 engine runner | 2 |
| T4 discovery | 3 |
| T5 首页+仪表盘 | 3 |
| T6 卡片列表/详情/审阅 | 5 |
| T7 卡片编辑 | 4 |
| T8 卡片新建 | 3 |
| T9 叙事工作台 | 5 |
| T10 节点编辑(uses) | 2 |
| T11 生成+SSE | 3 |
| T12 graph/诊断/files | 4 |
| T13 inspire | 4 |
| **合计** | **46** |

基线 260 passed（AGENTS.md 记录，1 deselected）；全部完成预期 **306 passed**。若基线已漂移，以执行时实测为准并在本表回填。

---

### Task 0: 建 worktree

- [ ] 在主工作区执行：

```bash
git worktree add .worktrees/weft-webui -b weft-webui main
cd .worktrees/weft-webui
.venv/Scripts/python.exe -m pip install -e ".[dev,web]" 2>/dev/null || echo "web 组未建，Task 1 后重装"
.venv/Scripts/python.exe -m pytest tests -q   # 确认基线绿
```

后续所有命令都在 `.worktrees/weft-webui` 内执行。完成后按 AGENTS.md 合回 main 并删除 worktree/分支。

---

### Task 1: `[web]` 依赖组 + create_app 骨架 + `weft serve` 子命令

**Files:**
- Modify: `pyproject.toml`（`[project.optional-dependencies]`）
- Create: `src/weft/web/__init__.py`
- Modify: `src/weft/cli.py`（文件末尾追加 serve 命令）
- Test: `tests/test_web_app.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_web_app.py
"""WebUI 骨架与 serve 子命令。"""
from pathlib import Path

from fastapi.testclient import TestClient
from helpers import make_minimal_project
from typer.testing import CliRunner

import weft.cli as cli_mod
from weft.web import create_app


def test_create_app_health(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/healthz").json() == {"ok": True}


def test_serve_invokes_uvicorn(tmp_path: Path, monkeypatch):
    import uvicorn

    captured = {}

    def fake_run(app, host=None, port=None):
        captured["host"], captured["port"], captured["app"] = host, port, app

    monkeypatch.setattr(uvicorn, "run", fake_run)
    projects = tmp_path / "projects"
    make_minimal_project(projects / "demo")
    result = CliRunner().invoke(
        cli_mod.app, ["serve", str(projects), "--host", "127.0.0.1", "--port", "8123"])
    assert result.exit_code == 0
    assert captured["port"] == 8123 and captured["host"] == "127.0.0.1"
    assert captured["app"].state.projects_root == projects.resolve()
```

注：tests 目录无 `__init__` 约束，`from helpers import …` 与现有 `test_cli_*.py` 一致（pythonpath=["."]）。

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_app.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'weft.web'`）

- [ ] **Step 3: 实现**

`pyproject.toml` 的 optional-dependencies 改为：

```toml
[project.optional-dependencies]
dev = ["pytest>=8"]
web = ["fastapi>=0.110", "uvicorn>=0.29", "jinja2>=3.1", "python-multipart>=0.0.9"]
```

```python
# src/weft/web/__init__.py
"""weft WebUI（webui 设计 §1）：weft 公共 API 之上的 FastAPI 薄壳。

分层红线：本包不得 import module_harness / llm（红线 1）；生成一律经 weft.engine 公共 API。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

_STATIC_DIR = Path(__file__).parent / "static"


def create_app(projects_root: Path) -> FastAPI:
    app = FastAPI(title="weft WebUI", docs_url=None, redoc_url=None)
    app.state.projects_root = Path(projects_root).resolve()
    from weft.web.routes import register_all

    register_all(app)
    if _STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    return app
```

先建空的 `src/weft/web/routes/__init__.py`：

```python
"""路由注册中心（webui 设计 §3）。"""
from __future__ import annotations

from fastapi import FastAPI


def register_all(app: FastAPI) -> None:
    from weft.web.routes import core

    core.register(app)
```

```python
# src/weft/web/routes/core.py（本任务只放占位 router，Task 5 起填充路由）
"""核心页面路由：项目列表 / 项目总览 / graph / 诊断 / 文件预览。"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


def register(app) -> None:
    app.include_router(router)
```

`src/weft/cli.py` 末尾追加（放在文件末尾，import 函数内做以便未装 [web] 时其余命令可用）：

```python
@app.command()
def serve(
    projects_root: Path = typer.Argument(..., help="weft 论文项目根目录（扫描一级子目录）"),
    host: str = typer.Option("127.0.0.1", "--host", help="监听地址；部署用 0.0.0.0"),
    port: int = typer.Option(8000, "--port", help="监听端口"),
) -> None:
    """启动 WebUI（webui 设计 §10）：weft serve <projects_root> --host 0.0.0.0 --port 8000。"""
    try:
        import uvicorn
    except ImportError as exc:
        typer.echo("ERROR WebUI 依赖未安装：pip install 'weft[web]'")
        raise typer.Exit(code=1) from exc
    from weft.web import create_app

    create_app(projects_root)   # 启动前构建一次：根目录非法立刻失败
    uvicorn.run(create_app(projects_root), host=host, port=port)
```

- [ ] **Step 4: 安装依赖并跑测试通过**

Run: `.venv/Scripts/python.exe -m pip install -e ".[dev,web]" && .venv/Scripts/python.exe -m pytest tests/test_web_app.py -v`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add pyproject.toml src/weft/web src/weft/cli.py tests/test_web_app.py
git commit -m "feat: WebUI 骨架——[web] 依赖组、create_app 与 weft serve 子命令"
```

---

### Task 2: store/writer.py —— 卡片/叙事保存

**Files:**
- Create: `src/weft/store/writer.py`
- Test: `tests/test_store_writer.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_store_writer.py
"""store 写回：save_card / create_card / next_card_id / save_part（webui 设计 §4.2）。"""
from pathlib import Path

import pytest

from helpers import make_minimal_project, write_card
from weft.models.cards import ClaimCard, DataCard, FactCard
from weft.store.loader import load_project
from weft.store.writer import create_card, next_card_id, save_card, save_part


def _load(tmp_path: Path):
    project, diags = load_project(make_minimal_project(tmp_path))
    assert not any(d.is_error for d in diags)
    return project


def test_save_card_round_trip(tmp_path: Path):
    project = _load(tmp_path)
    fact = project.facts["fact-01"]
    saved = save_card(project.root, fact.model_copy(update={"comment": "看过，没问题"}))
    assert saved == project.root / "metadata" / "facts" / "fact-01.md"
    project2, diags = load_project(project.root)
    assert not any(d.is_error for d in diags)
    assert project2.facts["fact-01"].comment == "看过，没问题"


def test_save_card_normalizes_crlf_and_lf(tmp_path: Path):
    project = _load(tmp_path)
    card = project.facts["fact-01"].model_copy(update={"comment": "a\r\nb"})
    path = save_card(project.root, card)
    raw = path.read_bytes()
    assert b"\r" not in raw


def test_claim_type_change_moves_file(tmp_path: Path):
    project = _load(tmp_path)
    old_rel = project.card_paths["claim-01"].as_posix()
    claim = project.claims["claim-01"].model_copy(
        update={"claim_type": "cited", "cites": ["key2020"]})
    new_path = save_card(project.root, claim, old_rel=old_rel)
    assert new_path == project.root / "metadata" / "claims" / "cited" / "claim-01.md"
    assert not (project.root / old_rel).exists()
    project2, diags = load_project(project.root)
    assert not any(d.is_error for d in diags)
    assert "claim-01" in project2.claims


def test_create_card_rejects_duplicate(tmp_path: Path):
    project = _load(tmp_path)
    dup = DataCard(id="data-01", status="draft")
    with pytest.raises(FileExistsError):
        create_card(project.root, dup)


def test_next_card_id_skips_used_and_carries(tmp_path: Path):
    project = _load(tmp_path)
    assert next_card_id(project, "data") == "data-02"
    (project.root / "metadata" / "data" / "data-02.md").write_text(
        "---\nid: data-02\nstatus: draft\n---\n", encoding="utf-8")
    (project.root / "metadata" / "data" / "data-03.md").write_text(
        "---\nid: data-03\nstatus: draft\n---\n", encoding="utf-8")
    project2, diags = load_project(project.root)
    assert not any(d.is_error for d in diags)
    assert next_card_id(project2, "data") == "data-04"
    for n in range(4, 10):   # data-04..data-09 全占 → 进位到 data-10
        (project.root / "metadata" / "data" / f"data-{n:02d}.md").write_text(
            f"---\nid: data-{n:02d}\nstatus: draft\n---\n", encoding="utf-8")
    project3, _ = load_project(project.root)
    assert next_card_id(project3, "data") == "data-10"


def test_save_part_round_trip(tmp_path: Path):
    project = _load(tmp_path)
    part_path = project.root / project.part_paths["sec-01"]
    import frontmatter
    post = frontmatter.load(part_path)
    post.body = "审阅备注：正文区不放终稿。"
    part_path.write_text(frontmatter.dumps(post), encoding="utf-8")

    project, _ = load_project(project.root)
    part = project.parts[0]
    part.nodes[0].comment = "改过 comment"
    saved = save_part(project, part)
    assert saved == part_path
    project2, diags = load_project(project.root)
    assert not any(d.is_error for d in diags)
    part2 = next(p for p in project2.parts if p.id == "sec-01")
    assert part2.nodes[0].comment == "改过 comment"
    assert "审阅备注" in part_path.read_text(encoding="utf-8")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_store_writer.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'weft.store.writer'`）

- [ ] **Step 3: 实现**

```python
# src/weft/store/writer.py
"""卡片/叙事文件写回（spec §5 store 层"保存"职责补齐；webui 设计 §4.2）。

只服务"人写"场景（WebUI 审阅与编辑）。AI 产物落盘白名单不受影响（红线 4）。
写入固定 LF（落盘前归一化 CRLF）。claim 的 claim_type 决定目录（loader 强制一致），
save_card 按卡当前字段计算规范路径；old_rel 不同即为迁移，旧文件删除。
"""
from __future__ import annotations

from pathlib import Path

import frontmatter

from weft.models.cards import (
    ClaimCard,
    DataCard,
    FactCard,
    MethodCard,
    NoteCard,
    ParamCard,
)
from weft.models.narrative import NarrativePart
from weft.store.project import Project

_CARD_DIRS = [(DataCard, "metadata/data"), (FactCard, "metadata/facts"),
              (NoteCard, "metadata/notes"), (MethodCard, "metadata/methods"),
              (ParamCard, "metadata/params")]


def card_relpath(card) -> str:
    """卡片规范相对路径（posix）；文件名 = id（spec §3.9）。"""
    if isinstance(card, ClaimCard):
        return f"metadata/claims/{card.claim_type}/{card.id}.md"
    for model, directory in _CARD_DIRS:
        if isinstance(card, model):
            return f"{directory}/{card.id}.md"
    raise TypeError(f"未知卡片类型：{type(card).__name__}")


def _dump(card) -> str:
    text = frontmatter.dumps(frontmatter.Post("", **card.model_dump()))
    return text.replace("\r\n", "\n").replace("\r", "\n")


def save_card(root: Path, card, *, old_rel: str | None = None) -> Path:
    """写回卡片；claim_type 变更（old_rel 与新路径不同）时迁移文件。"""
    rel = card_relpath(card)
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dump(card), encoding="utf-8", newline="\n")
    if old_rel is not None and old_rel != rel:
        (root / old_rel).unlink()
    return path


def create_card(root: Path, card) -> Path:
    path = root / card_relpath(card)
    if path.exists():
        raise FileExistsError(f"卡片已存在：{card_relpath(card)}")
    return save_card(root, card)


def next_card_id(project: Project, prefix: str) -> str:
    """下一可用实体 id：全局唯一命名空间，两位零填充进位（spec §3.9）。"""
    used = set(project.card_paths)
    n = 1
    while f"{prefix}-{n:02d}" in used:
        n += 1
    return f"{prefix}-{n:02d}"


def save_part(project: Project, part: NarrativePart) -> Path:
    """叙事 part 写回：frontmatter 重序列化为 part.model_dump()，正文原样保留。"""
    path = project.root / project.part_paths[part.id]
    body = frontmatter.load(path).body
    text = frontmatter.dumps(frontmatter.Post(body, **part.model_dump()))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    path.write_text(text, encoding="utf-8", newline="\n")
    return path
```

- [ ] **Step 4: 跑测试通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_store_writer.py -v`
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add src/weft/store/writer.py tests/test_store_writer.py
git commit -m "feat: store/writer.py——卡片写回（LF 归一、claim_type 迁移）、id 分配与 part 写回"
```

---

### Task 3: engine/part_draft.py 共享 runner + cli.draft 接线

**Files:**
- Create: `src/weft/engine/part_draft.py`
- Modify: `src/weft/cli.py:129-207`（draft 命令体内循环改为调 runner）
- Test: `tests/test_part_draft.py`

**事件生命周期归 runner 所有**（run_started → node_started/node_finished|node_failed(×N) → draft_written → run_finished；失败路径 run_failed 后抛异常）——调用方只捕获异常，不重复发事件（设计决策 D1）。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_part_draft.py
"""共享 runner：事件序列、结果、缺 approved 节点的失败路径。"""
from pathlib import Path

import pytest

from helpers import make_minimal_project
from weft.engine import DraftError, ScriptedLLMClient
from weft.engine.part_draft import run_part_draft
from weft.store.loader import load_project


def test_event_sequence_and_result(tmp_path: Path):
    root = make_minimal_project(tmp_path)
    project, diags = load_project(root)
    assert not any(d.is_error for d in diags)
    part = project.parts[0]
    events: list = []
    result = run_part_draft(project, part, client=ScriptedLLMClient(),
                            on_event=events.append)
    kinds = [e.kind for e in events]
    assert kinds[0] == "run_started"
    assert kinds.count("node_started") == kinds.count("node_finished") == 1
    assert "draft_written" in kinds
    assert kinds[-1] == "run_finished"
    assert result.paragraphs["para-01-01"]
    assert result.run_id
    assert (root / "drafts" / "sec-01.md").exists()


def test_nothing_to_draft_raises_and_emits_run_failed(tmp_path: Path):
    root = make_minimal_project(tmp_path)
    project, _ = load_project(root)
    part = project.parts[0]
    part.nodes[0].status = "draft"
    events: list = []
    with pytest.raises(DraftError):
        run_part_draft(project, part, client=ScriptedLLMClient(),
                       on_event=events.append)
    assert events[-1].kind == "run_failed"
    assert "E-NOTHING-TO-DRAFT" in events[-1].message
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_part_draft.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'weft.engine.part_draft'`）

- [ ] **Step 3: 实现 runner**

```python
# src/weft/engine/part_draft.py
"""按 part 的草稿生成编排：CLI（cli.draft）与 WebUI 共用的唯一路径（webui 设计 §1.1）。

事件生命周期归本函数所有；on_event 收到 DraftEvent(kind, node_id, message)。
编排语义与原 cli.draft 逐行等价（前文传递 prev_tail 取更早 part 草稿末段，M2 决策）。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from weft.engine.draft_rules import DraftError, DraftRuleError
from weft.engine.drafts import render_draft_markdown, write_draft
from weft.engine.run import run_draft
from weft.models.narrative import NarrativePart
from weft.store.project import Project
from weft.workflow import resolve_workflow


@dataclass(frozen=True)
class DraftEvent:
    kind: str                # run_started|node_started|node_finished|node_failed|draft_written|run_finished|run_failed
    node_id: str | None = None
    message: str = ""


@dataclass
class PartDraftResult:
    paragraphs: dict[str, str]
    reminders: list[str]
    run_id: str
    path: Path


def run_part_draft(project: Project, part: NarrativePart, *, client,
                   on_event=None) -> PartDraftResult:
    """闸门（validate 无 error）由调用方负责；本函数编排单 part 全部 approved 节点。"""
    def emit(kind: str, node_id: str | None = None, message: str = "") -> None:
        if on_event is not None:
            on_event(DraftEvent(kind, node_id, message))

    approved = [n for n in part.nodes if n.status == "approved"]
    if not approved:
        message = "[E-NOTHING-TO-DRAFT] part 内没有 status: approved 的叙事节点"
        emit("run_started", message=part.id)
        emit("run_failed", message=message)
        raise DraftError(message)

    overview_path = project.root / "overview.md"
    overview = overview_path.read_text(encoding="utf-8") if overview_path.exists() else ""
    workflow = resolve_workflow(part, project.part_chapters[part.id])
    emit("run_started", message=f"{part.id}（workflow={workflow}，{len(approved)} 节点）")

    paragraphs: dict[str, str] = {}
    all_reminders: list[str] = []
    run_id = ""
    try:
        for node in approved:
            tail = None
            for other in project.parts:
                if other.id == part.id:
                    break
                draft_file = project.root / "drafts" / f"{other.id}.md"
                if draft_file.exists():
                    blocks = [ln for ln in draft_file.read_text(encoding="utf-8").splitlines()
                              if ln.strip() and not ln.startswith("<!--")]
                    if blocks:
                        tail = blocks[-1]
            emit("node_started", node.id)
            try:
                result = run_draft(project, part, node, client=client,
                                   workflow=workflow, overview=overview,
                                   prior_paragraphs=[paragraphs[n.id] for n in approved
                                                     if n.id in paragraphs],
                                   prev_tail=tail)
            except (DraftRuleError, DraftError) as exc:
                emit("node_failed", node.id, str(exc))
                raise
            paragraphs[node.id] = result.paragraph
            all_reminders.extend(result.reminders)
            run_id = result.run_id
            emit("node_finished", node.id,
                 f"{len(result.reminders)} 条提醒" if result.reminders else "完成")
    except Exception as exc:
        emit("run_failed", message=str(exc))
        raise

    content = render_draft_markdown(part, paragraphs, run_id)
    try:
        path = write_draft(project, part.id, content)
    except OSError as exc:
        emit("run_failed", message=str(exc))
        raise DraftError(f"无法写入 drafts/：{exc}") from exc
    emit("draft_written", message=path.relative_to(project.root).as_posix())
    emit("run_finished", message=f"{len(paragraphs)} 段，run={run_id}")
    return PartDraftResult(paragraphs=paragraphs, reminders=all_reminders,
                           run_id=run_id, path=path)
```

- [ ] **Step 4: cli.draft 接线（保持行为/输出不变）**

`src/weft/cli.py` draft 命令体中，`approved = [n for n in part.nodes …]` 检查与诊断（E-NOTHING-TO-DRAFT）**保留不动**；其后从 `warnings = …` 到 `except (DraftRuleError, DraftError)` 循环及收尾替换为：

```python
    warnings = [d for d in diagnostics if not d.is_error]
    client = make_client(mock, project_root=project.root)
    try:
        result = run_part_draft(project, part, client=client)
    except (DraftRuleError, DraftError) as exc:
        typer.echo(f"ERROR {exc}")
        raise typer.Exit(code=1) from exc
    for reminder in result.reminders:
        typer.echo(f"WARN {reminder}")
    typer.echo(
        f"已写入 {result.path.relative_to(project.root).as_posix()}"
        f"（{len(result.paragraphs)} 段，run={result.run_id}）")
    if warnings:
        _print_diagnostics(warnings)
```

函数顶部局部 import 行改为：

```python
    from weft.engine import DraftError, DraftRuleError, make_client
    from weft.engine.part_draft import run_part_draft
```

（删除原 `render_draft_markdown/write_draft/resolve_workflow` 的局部 import。）

- [ ] **Step 5: 跑新测试 + CLI 回归**

Run: `.venv/Scripts/python.exe -m pytest tests/test_part_draft.py tests/test_cli_draft.py tests/test_engine_run.py -v`
Expected: 全部 passed（现有 CLI 测试是行为守护）

- [ ] **Step 6: 提交**

```bash
git add src/weft/engine/part_draft.py src/weft/cli.py tests/test_part_draft.py
git commit -m "feat: engine/part_draft 共享 runner（带事件回调），cli.draft 接线复用"
```

---

### Task 4: web/discovery.py 项目扫描

**Files:**
- Create: `src/weft/web/discovery.py`
- Test: `tests/test_web_discovery.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_web_discovery.py
"""项目扫描：识别、忽略非项目、损坏项目不阻断。"""
from pathlib import Path

from helpers import make_minimal_project, write_card
from weft.web.discovery import scan_projects


def test_scan_lists_weft_project(tmp_path: Path):
    make_minimal_project(tmp_path / "demo")
    entries = scan_projects(tmp_path)
    assert [e.pid for e in entries] == ["demo"]
    entry = entries[0]
    assert entry.available and entry.project is not None
    assert entry.n_cards == 4 and entry.n_errors == 0


def test_scan_ignores_plain_dir(tmp_path: Path):
    make_minimal_project(tmp_path / "demo")
    (tmp_path / "empty").mkdir()
    assert [e.pid for e in scan_projects(tmp_path)] == ["demo"]


def test_broken_project_marked_unavailable(tmp_path: Path):
    make_minimal_project(tmp_path / "demo")
    write_card(tmp_path / "demo" / "metadata" / "data", "oops",
               {"id": "data-01", "status": "draft"})   # 文件名≠id → 加载错误
    entries = scan_projects(tmp_path)
    assert entries[0].available is False and entries[0].project is None
    assert any(d.is_error for d in entries[0].diagnostics)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_discovery.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

```python
# src/weft/web/discovery.py
"""项目扫描（webui 设计 §2）：projects_root 一级子目录中识别 weft 论文项目。

识别判据 = 子目录含 metadata/。损坏项目不阻断列表（available=False，红线 3 精神）。
每次请求重扫：单用户演示场景项目小，保证永远新鲜（设计决策 D7）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from weft.diagnostics import Diagnostic
from weft.store.loader import load_project
from weft.store.project import Project
from weft.validation import validate_project

_KIND_ATTRS = (("data", "data_cards"), ("fact", "facts"), ("claim", "claims"),
               ("note", "notes"), ("method", "methods"), ("param", "params"))


@dataclass
class ProjectEntry:
    pid: str
    path: Path
    available: bool
    diagnostics: list[Diagnostic] = field(default_factory=list)
    project: Project | None = None

    @property
    def n_cards(self) -> int:
        if self.project is None:
            return 0
        return sum(len(getattr(self.project, attr)) for _, attr in _KIND_ATTRS)

    @property
    def n_errors(self) -> int:
        return sum(1 for d in self.diagnostics if d.is_error)

    @property
    def n_warnings(self) -> int:
        return sum(1 for d in self.diagnostics if not d.is_error)


def scan_projects(root: Path) -> list[ProjectEntry]:
    entries: list[ProjectEntry] = []
    if not root.is_dir():
        return entries
    for child in sorted(root.iterdir()):
        if not child.is_dir() or not (child / "metadata").is_dir():
            continue
        entries.append(_inspect(child))
    return entries


def _inspect(path: Path) -> ProjectEntry:
    project, load_diags = load_project(path)
    if any(d.is_error for d in load_diags):
        return ProjectEntry(pid=path.name, path=path, available=False,
                            diagnostics=load_diags)
    diagnostics = load_diags + validate_project(project)
    return ProjectEntry(pid=path.name, path=path,
                        available=not any(d.is_error for d in diagnostics),
                        diagnostics=diagnostics, project=project)
```

- [ ] **Step 4: 跑测试通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_discovery.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add src/weft/web/discovery.py tests/test_web_discovery.py
git commit -m "feat: WebUI 项目扫描 discovery——识别/统计/损坏项目不阻断"
```

---

### Task 5: 共享 helpers + 基础模板 + 首页 + 总览仪表盘

**Files:**
- Create: `src/weft/web/common.py`、`src/weft/web/templates/base.html`、`index.html`、`dashboard.html`、`unavailable.html`、`src/weft/web/static/webui.css`
- Modify: `src/weft/web/routes/__init__.py`、`src/weft/web/routes/core.py`
- Create: `tests/webutil.py`、`tests/test_web_pages.py`
- Vendor: `src/weft/web/static/htmx.min.js`

- [ ] **Step 1: 写失败测试**

```python
# tests/webutil.py
"""WebUI 测试夹具：tmp projects 根 + TestClient。"""
from pathlib import Path

from fastapi.testclient import TestClient

from helpers import make_minimal_project
from weft.web import create_app


def make_client(tmp_path: Path) -> tuple[TestClient, Path]:
    projects = tmp_path / "projects"
    projects.mkdir(parents=True, exist_ok=True)
    make_minimal_project(projects / "demo")
    return TestClient(create_app(projects)), projects
```

```python
# tests/test_web_pages.py
"""首页项目列表与项目总览仪表盘。"""
import pytest
from webutil import make_client


def test_index_lists_projects(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "demo" in resp.text and "weft" in resp.text


def test_dashboard_shows_stats_and_queue(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/", follow_redirects=False)
    assert resp.status_code == 200
    assert "待审阅" in resp.text and "诊断" in resp.text


def test_unknown_project_404(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/p/nope/").status_code == 404
```

注：`make_minimal_project` 全部 approved（无 draft），仪表盘待审队列为空属正常；后续编辑任务会制造 draft 卡再回来补断言。

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_pages.py -v`
Expected: FAIL（404，路由未注册）

- [ ] **Step 3: 实现 common.py 与模板**

```python
# src/weft/web/common.py
"""WebUI 共享 helpers：模板、卡种映射、项目解析（webui 设计 §3/§4.1）。"""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.templating import Jinja2Templates

from weft.web.discovery import ProjectEntry

_TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))

# kind → Project 属性名（models/cards.py 六类卡）
KIND_ATTRS = {"data": "data_cards", "fact": "facts", "claim": "claims",
              "note": "notes", "method": "methods", "param": "params"}
KIND_LABELS = {"data": "data 卡", "fact": "fact 卡", "claim": "claim 卡",
               "note": "note 卡", "method": "method 卡", "param": "param 卡"}


def load_entry_or_404(request: Request, pid: str) -> ProjectEntry:
    from weft.web.discovery import scan_projects

    for entry in scan_projects(request.app.state.projects_root):
        if entry.pid == pid:
            return entry
    raise HTTPException(status_code=404, detail="项目不存在")


def load_project_or_404(request: Request, pid: str) -> ProjectEntry:
    entry = load_entry_or_404(request, pid)
    if not entry.available or entry.project is None:
        raise HTTPException(status_code=404, detail="项目不可用")
    return entry
```

```html
<!-- src/weft/web/templates/base.html -->
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{% block title %}weft{% endblock %} · weft WebUI</title>
<link rel="stylesheet" href="/static/webui.css">
<script src="/static/htmx.min.js" defer></script>
<script src="/static/webui.js" defer></script>
</head>
<body>
<nav class="topnav">
  <a class="brand" href="/">weft · AI 学术写作引擎</a>
  {% block nav %}{% endblock %}
</nav>
<main>
{% block content %}{% endblock %}
</main>
</body>
</html>
```

```html
<!-- src/weft/web/templates/index.html -->
{% extends "base.html" %}
{% block title %}项目列表{% endblock %}
{% block content %}
<h2>weft 论文项目</h2>
<p class="subtitle">根目录：{{ projects_root }}</p>
{% if entries %}
<table class="list">
  <thead><tr><th>项目</th><th>状态</th><th>卡片</th><th>诊断</th><th></th></tr></thead>
  <tbody>
  {% for e in entries %}
    <tr>
      <td>{{ e.pid }}</td>
      <td>{% if e.available %}<span class="badge approved">可用</span>
          {% else %}<span class="badge rejected">不可用</span>{% endif %}</td>
      <td>{{ e.n_cards }}</td>
      <td>E: {{ e.n_errors }} · W: {{ e.n_warnings }}</td>
      <td><a href="/p/{{ e.pid }}/">打开</a></td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{% else %}
<p>未发现 weft 项目——根目录下需存在含 <code>metadata/</code> 的子目录。</p>
{% endif %}
{% endblock %}
```

```html
<!-- src/weft/web/templates/dashboard.html -->
{% extends "base.html" %}
{% block title %}{{ entry.pid }} 总览{% endblock %}
{% block content %}
<h2>项目：{{ entry.pid }}
  {% if not entry.available %}<span class="badge rejected">不可用</span>{% endif %}</h2>
<div class="stats">
  <div class="stat"><b>{{ entry.n_cards }}</b><span>卡片</span></div>
  <div class="stat"><b>{{ entry.project.parts | length }}</b><span>叙事 part</span></div>
  <div class="stat"><b>{{ status_counts["approved"] }}</b><span>approved</span></div>
  <div class="stat"><b>{{ status_counts["draft"] }}</b><span>draft 待审</span></div>
  <div class="stat {% if entry.n_errors %}bad{% endif %}"><b>{{ entry.n_errors }}</b><span>错误</span></div>
  <div class="stat"><b>{{ entry.n_warnings }}</b><span>提醒</span></div>
</div>
<h3>待审阅队列</h3>
{% if review_queue %}
<table class="list">
  <thead><tr><th>类型</th><th>id</th><th>位置</th><th>操作</th></tr></thead>
  <tbody>
  {% for item in review_queue %}
    <tr>
      <td>{{ item.kind }}</td><td>{{ item.id }}</td><td><code>{{ item.rel }}</code></td>
      <td><a href="{{ item.url }}">审阅</a></td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{% else %}<p>（无待审阅项）</p>{% endif %}
<h3>快捷入口</h3>
<p>
  <a href="/p/{{ entry.pid }}/parts">叙事工作台</a> ·
  <a href="/p/{{ entry.pid }}/cards">卡片</a> ·
  <a href="/p/{{ entry.pid }}/graph">元数据图谱</a> ·
  <a href="/p/{{ entry.pid }}/inspire">灵感</a> ·
  <a href="/p/{{ entry.pid }}/diagnostics">诊断（{{ entry.n_errors }} E / {{ entry.n_warnings }} W）</a>
</p>
{% endblock %}
```

```html
<!-- src/weft/web/templates/unavailable.html -->
{% extends "base.html" %}
{% block title %}{{ pid }} 不可用{% endblock %}
{% block content %}
<h2>项目 {{ pid }} 无法加载</h2>
<ul>
{% for d in diagnostics %}<li>{{ "ERROR" if d.is_error else "WARN" }} {{ d.path }} [{{ d.code }}] {{ d.message }}</li>{% endfor %}
</ul>
<p><a href="/">返回项目列表</a></p>
{% endblock %}
```

```css
/* src/weft/web/static/webui.css */
* { box-sizing: border-box; }
body { margin: 0; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; color: #24292f; }
.topnav { display: flex; gap: 24px; align-items: center; padding: 12px 24px; background: #1f2933; }
.topnav a { color: #e4e7eb; text-decoration: none; }
.topnav .brand { font-weight: 700; }
main { max-width: 1100px; margin: 0 auto; padding: 16px 24px; }
table.list { border-collapse: collapse; width: 100%; margin: 8px 0; }
table.list th, table.list td { border: 1px solid #d0d7de; padding: 6px 10px; text-align: left; font-size: 14px; }
table.list thead { background: #f6f8fa; }
.badge { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 12px; color: #fff; }
.badge.approved { background: #1a7f37; } .badge.draft { background: #bf8700; }
.badge.rejected { background: #cf222e; }
.stats { display: flex; gap: 12px; margin: 12px 0; flex-wrap: wrap; }
.stat { border: 1px solid #d0d7de; border-radius: 8px; padding: 10px 16px; text-align: center; min-width: 90px; }
.stat b { display: block; font-size: 22px; } .stat span { font-size: 12px; color: #57606a; }
.stat.bad b { color: #cf222e; }
button { padding: 4px 12px; cursor: pointer; }
button.ok { border-color: #1a7f37; } button.bad { border-color: #cf222e; }
.tabs { display: flex; gap: 6px; margin: 10px 0; flex-wrap: wrap; }
.tab { border: 1px solid #d0d7de; background: #f6f8fa; padding: 6px 14px; border-radius: 6px 6px 0 0; }
.tab.active { background: #1f2933; color: #fff; }
.cols { display: flex; gap: 16px; align-items: flex-start; }
.cols > div { flex: 1; }
.console, .run-log, .draft-preview pre { border: 1px solid #d0d7de; border-radius: 6px; padding: 10px; }
.run-log { font-family: Consolas, monospace; font-size: 13px; min-height: 120px; max-height: 340px; overflow: auto; background: #0d1117; color: #c9d1d9; }
.run-log .log-run_failed { color: #f85149; } .run-log .log-run_finished { color: #3fb950; }
.run-log .log-draft_written { color: #d29922; }
.banner { border: 1px solid #cf222e; background: #ffebe9; padding: 8px 12px; border-radius: 6px; margin: 10px 0; }
.field-error { color: #cf222e; font-size: 12px; }
form label { display: block; margin: 8px 0; }
form textarea { width: 100%; }
.multi { display: flex; flex-wrap: wrap; gap: 8px; }
.check { margin-right: 10px; font-size: 14px; }
```

- [ ] **Step 4: 接线路由**

`src/weft/web/routes/__init__.py` 整体替换：

```python
"""路由注册中心（webui 设计 §3）。"""
from __future__ import annotations

from fastapi import FastAPI


def register_all(app: FastAPI) -> None:
    from weft.web.routes import core

    core.register(app)
```

`src/weft/web/routes/core.py` 整体替换：

```python
"""核心页面路由：项目列表 / 项目总览仪表盘（graph、诊断、文件预览在 Task 12 扩充）。"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Request

from weft.web.common import KIND_ATTRS, load_entry_or_404, templates

router = APIRouter()


@router.get("/")
def index(request: Request):
    from weft.web.discovery import scan_projects

    entries = scan_projects(request.app.state.projects_root)
    return templates.TemplateResponse(
        request, "index.html",
        {"entries": entries,
         "projects_root": str(request.app.state.projects_root)})


@router.get("/p/{pid}/")
def dashboard(request: Request, pid: str):
    entry = load_entry_or_404(request, pid)
    if not entry.available:
        return templates.TemplateResponse(
            request, "unavailable.html",
            {"pid": pid, "diagnostics": entry.diagnostics})
    project = entry.project
    status_counts = Counter()
    review_queue: list[dict] = []
    for kind, attr in KIND_ATTRS.items():
        table = getattr(project, attr)
        status_counts.update(card.status for card in table.values())
        for cid, card in table.items():
            if card.status == "draft":
                review_queue.append({
                    "kind": kind, "id": cid,
                    "rel": project.card_paths[cid].as_posix(),
                    "url": f"/p/{pid}/cards/{kind}/{cid}"})
    for part in project.parts:
        for node in part.nodes:
            status_counts[node.status] += 1
            if node.status == "draft":
                review_queue.append({
                    "kind": "叙事节点", "id": node.id,
                    "rel": project.part_paths[part.id].as_posix(),
                    "url": f"/p/{pid}/parts/{part.id}/nodes/{node.id}"})
    return templates.TemplateResponse(
        request, "dashboard.html",
        {"entry": entry, "project": project, "review_queue": review_queue,
         "status_counts": status_counts})
```

- [ ] **Step 5: vendor htmx + 跑测试**

```bash
mkdir -p src/weft/web/static
curl -L -o src/weft/web/static/htmx.min.js https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js \
  || curl -L -o src/weft/web/static/htmx.min.js https://cdnjs.cloudflare.com/ajax/libs/htmx/1.9.12/htmx.min.js
ls -la src/weft/web/static/htmx.min.js   # >100KB 即成功；都失败则从本机 pip 缓存/其他项目拷贝同版本文件
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_pages.py -v`
Expected: 3 passed

- [ ] **Step 6: 提交**

```bash
git add src/weft/web tests/webutil.py tests/test_web_pages.py
git commit -m "feat: WebUI 首页与项目总览仪表盘（扫描列表、统计、待审队列）"
```

---

### Task 6: 卡片列表 / 详情 / 审阅

**Files:**
- Modify: `src/weft/web/routes/__init__.py`、`src/weft/web/routes/cards.py`（新建）
- Create: `src/weft/web/templates/cards.html`、`card_detail.html`
- Test: `tests/test_web_cards.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_web_cards.py
"""卡片列表、详情与审阅（status/comment 写回）。"""
from pathlib import Path

from helpers import write_card
from weft.store.loader import load_project
from webutil import make_client


def test_cards_overview_and_list(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/p/demo/cards").status_code == 200
    resp = client.get("/p/demo/cards/fact")
    assert resp.status_code == 200 and "fact-01" in resp.text


def test_card_detail_renders(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/cards/fact/fact-01")
    assert resp.status_code == 200
    assert "fact-01" in resp.text and "温度提高速率" in resp.text


def test_unknown_kind_404(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/p/demo/cards/bogus").status_code == 404
    assert client.get("/p/demo/cards/fact/fact-99").status_code == 404


def test_review_updates_file(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/cards/fact/fact-01/status",
                       data={"status": "rejected", "comment": "表述有误"})
    assert resp.status_code == 303
    project, diags = load_project(root / "demo")
    assert not any(d.is_error for d in diags)
    assert project.facts["fact-01"].status == "rejected"
    assert project.facts["fact-01"].comment == "表述有误"


def test_review_invalid_status_400(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/cards/fact/fact-01/status",
                       data={"status": "bogus", "comment": ""})
    assert resp.status_code == 400
    project, _ = load_project(root / "demo")
    assert project.facts["fact-01"].status == "approved"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_cards.py -v`
Expected: FAIL（404）

- [ ] **Step 3: 实现路由与模板**

`src/weft/web/routes/__init__.py` 的 `register_all` 增加一行（后续任务同法追加 cards 之外的模块）：

```python
def register_all(app: FastAPI) -> None:
    from weft.web.routes import cards, core

    core.register(app)
    cards.register(app)
```

```python
# src/weft/web/routes/cards.py
"""卡片路由（webui 设计 §3/§4）：总览、列表、详情、审阅、编辑、新建。

路由注册顺序：/cards/{kind}/new 必须先于 /cards/{kind}/{card_id} 注册（设计文档注）。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from weft.store.writer import save_card
from weft.web.common import KIND_ATTRS, KIND_LABELS, load_project_or_404, templates

router = APIRouter()

_STATUSES = ("draft", "approved", "rejected")
# 列表页展示的"关键字段"（有则显示），按卡种
_KEY_FIELD = {"data": "description", "fact": "statement", "claim": "statement",
              "note": "summary", "method": "statement", "param": "method"}


def _table(request: Request, pid: str, kind: str):
    if kind not in KIND_ATTRS:
        raise HTTPException(status_code=404, detail="未知卡种")
    entry = load_project_or_404(request, pid)
    return entry, getattr(entry.project, KIND_ATTRS[kind])


@router.get("/p/{pid}/cards")
def cards_overview(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    counts = {kind: len(getattr(entry.project, attr))
              for kind, attr in KIND_ATTRS.items()}
    return templates.TemplateResponse(
        request, "cards.html",
        {"entry": entry, "counts": counts, "labels": KIND_LABELS})


@router.get("/p/{pid}/cards/{kind}")
def card_list(request: Request, pid: str, kind: str):
    entry, table = _table(request, pid, kind)
    rows = []
    for cid, card in sorted(table.items()):
        rows.append({
            "id": cid, "status": card.status,
            "key": getattr(card, _KEY_FIELD[kind], "") or "",
            "rel": entry.project.card_paths[cid].as_posix()})
    return templates.TemplateResponse(
        request, "cards.html",
        {"entry": entry, "kind": kind, "rows": rows, "labels": KIND_LABELS,
         "counts": {k: len(getattr(entry.project, a))
                    for k, a in KIND_ATTRS.items()}})


@router.get("/p/{pid}/cards/{kind}/{card_id}")
def card_detail(request: Request, pid: str, kind: str, card_id: str):
    entry, table = _table(request, pid, kind)
    card = table.get(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="卡片不存在")
    return templates.TemplateResponse(
        request, "card_detail.html",
        {"entry": entry, "kind": kind, "card": card,
         "rel": entry.project.card_paths[card_id].as_posix(),
         "fields": {k: v for k, v in card.model_dump().items()
                    if k not in ("id", "status", "comment")}})


@router.post("/p/{pid}/cards/{kind}/{card_id}/status")
async def card_review(request: Request, pid: str, kind: str, card_id: str):
    entry, table = _table(request, pid, kind)
    card = table.get(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="卡片不存在")
    form = await request.form()
    status = str(form.get("status", ""))
    if status not in _STATUSES:
        raise HTTPException(status_code=400, detail="非法 status")
    new_card = card.model_copy(update={"status": status,
                                       "comment": str(form.get("comment", ""))})
    save_card(entry.project.root, new_card,
              old_rel=entry.project.card_paths[card_id].as_posix())
    return RedirectResponse(f"/p/{pid}/cards/{kind}/{card_id}", status_code=303)
```

```html
<!-- src/weft/web/templates/cards.html -->
{% extends "base.html" %}
{% block title %}{{ entry.pid }} 卡片{% endblock %}
{% block nav %}
{% for k, c in counts.items() %}<a href="/p/{{ entry.pid }}/cards/{{ k }}">{{ labels[k] }}（{{ c }}）</a>{% endfor %}
{% endblock %}
{% block content %}
<h2>{{ labels.get(kind, "卡片") if kind is defined else "卡片总览" }} · {{ entry.pid }}</h2>
{% if kind is defined %}
<table class="list">
  <thead><tr><th>id</th><th>status</th><th>关键字段</th><th>位置</th><th></th></tr></thead>
  <tbody>
  {% for r in rows %}
    <tr>
      <td>{{ r.id }}</td>
      <td><span class="badge {{ r.status }}">{{ r.status }}</span></td>
      <td>{{ r.key | truncate(60) }}</td>
      <td><code>{{ r.rel }}</code></td>
      <td><a href="/p/{{ entry.pid }}/cards/{{ kind }}/{{ r.id }}">详情</a></td>
    </tr>
  {% endfor %}
  </tbody>
</table>
<p><a href="/p/{{ entry.pid }}/cards/{{ kind }}/new">＋ 新建{{ labels[kind] }}</a></p>
{% endif %}
{% endblock %}
```

```html
<!-- src/weft/web/templates/card_detail.html -->
{% extends "base.html" %}
{% block title %}{{ card.id }}{% endblock %}
{% block content %}
<h2>{{ kind }} 卡 {{ card.id }}
  <span class="badge {{ card.status }}">{{ card.status }}</span></h2>
<p><code>{{ rel }}</code></p>
<table class="list">
  {% for k, v in fields.items() %}
  <tr><th>{{ k }}</th><td><code>{{ v }}</code></td></tr>
  {% endfor %}
  <tr><th>comment</th><td>{{ card.comment or "（无）" }}</td></tr>
</table>
<h3>审阅</h3>
<form method="post" action="/p/{{ entry.pid }}/cards/{{ kind }}/{{ card.id }}/status">
  <button class="ok" type="submit" name="status" value="approved">✅ 批准</button>
  <button class="bad" type="submit" name="status" value="rejected">❌ 否决</button>
  <button type="submit" name="status" value="draft">↩ 退回 draft</button>
  <label>comment<input name="comment" value="{{ card.comment }}"></label>
</form>
<p><a href="/p/{{ entry.pid }}/cards/{{ kind }}/{{ card.id }}/edit">✏️ 编辑</a> ·
   <a href="/p/{{ entry.pid }}/cards/{{ kind }}">返回列表</a></p>
{% endblock %}
```

- [ ] **Step 4: 跑测试通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_cards.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add src/weft/web/routes/cards.py src/weft/web/templates/cards.html src/weft/web/templates/card_detail.html tests/test_web_cards.py
git commit -m "feat: WebUI 卡片列表/详情/审阅（status+comment 写回 writer）"
```

---

### Task 7: card_forms.py + 卡片编辑

**Files:**
- Create: `src/weft/web/card_forms.py`
- Modify: `src/weft/web/routes/cards.py`（追加 edit 路由；new 路由 Task 8 加，注册顺序已在文件内自然满足——new 追加在 Task 8，且放在 `/{card_id}/edit` 之后仍不冲突，因为 `/new` 与 `/{card_id}` 是不同前缀段数）
- Modify: `src/weft/web/templates/card_form.html`（新建）
- Test: `tests/test_web_card_edit.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_web_card_edit.py
"""卡片编辑表单：渲染、写回、校验错误回显、claim_type 迁移。"""
from pathlib import Path

from weft.store.loader import load_project
from webutil import make_client


def test_edit_form_renders_fields(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/cards/fact/fact-01/edit")
    assert resp.status_code == 200
    assert "statement" in resp.text and "data-01" in resp.text  # data 多选已勾选


def test_edit_save_round_trip(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/cards/fact/fact-01/edit", data={
        "data": ["data-01"], "statement": "改后的陈述。", "supports": ["claim-01"],
        "status": "approved", "comment": "ok"})
    assert resp.status_code == 303
    project, diags = load_project(root / "demo")
    assert not any(d.is_error for d in diags)
    assert project.facts["fact-01"].statement == "改后的陈述。"


def test_edit_validation_error_rerenders(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/cards/fact/fact-01/edit", data={
        "data": [], "statement": "", "supports": [],   # data 空违反 min_length=1
        "status": "approved", "comment": ""})
    assert resp.status_code == 200
    assert "data" in resp.text and ("at least 1" in resp.text or "min_length" in resp.text
                                    or "1" in resp.text)
    project, _ = load_project(root / "demo")
    assert project.facts["fact-01"].statement == "温度提高速率。"   # 未落盘


def test_claim_type_edit_moves_file(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/cards/claim/claim-01/edit", data={
        "claim_type": "cited", "cites": ["key2020"], "statement": "温度有正效应。",
        "status": "approved", "comment": ""})
    assert resp.status_code == 303
    assert (root / "demo" / "metadata" / "claims" / "cited" / "claim-01.md").exists()
    assert not (root / "demo" / "metadata" / "claims" / "uncited" / "claim-01.md").exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_card_edit.py -v`
Expected: FAIL（404，edit 路由不存在）

- [ ] **Step 3: 实现 card_forms.py**

```python
# src/weft/web/card_forms.py
"""卡片编辑表单规格（webui 设计 §4.1）：字段 → 控件映射 + 表单解析。

引用类字段全部下拉/多选，选项来自项目加载结果（从源头杜绝悬空引用）；
词表字段用 datalist 允许超集（模型层放行，校验层提醒）。
"""
from __future__ import annotations

from dataclasses import dataclass

import yaml
from weft.models.cards import (
    ClaimCard,
    DataCard,
    FactCard,
    MethodCard,
    NoteCard,
    ParamCard,
)
from weft.store.project import Project


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    widget: str            # text | textarea | yaml_map | select | multiselect
    choices: str | None = None
    required: bool = False


FIELD_SPECS: dict[str, list[FieldSpec]] = {
    "data": [FieldSpec("refs", "refs（图号）", "multiselect", "figure_refs"),
             FieldSpec("source", "source（路径/URL/说明）", "text"),
             FieldSpec("description", "description", "textarea")],
    "fact": [FieldSpec("data", "data（依赖的 data 卡）", "multiselect", "data_ids", required=True),
             FieldSpec("statement", "statement", "textarea", required=True),
             FieldSpec("supports", "supports（支持的 claim）", "multiselect", "claim_ids")],
    "claim": [FieldSpec("claim_type", "claim_type", "select", "claim_type", required=True),
              FieldSpec("statement", "statement", "textarea", required=True),
              FieldSpec("cites", "cites（bib key）", "multiselect", "bib_keys")],
    "note": [FieldSpec("summary", "summary", "textarea"),
             FieldSpec("pdf", "pdf（文件路径，可选）", "text")],
    "method": [FieldSpec("statement", "statement", "textarea", required=True),
               FieldSpec("protocol", "protocol", "textarea", required=True),
               FieldSpec("derived_from", "derived_from（bib key）", "multiselect", "bib_keys")],
    "param": [FieldSpec("method", "method（method 卡）", "select", "method_ids", required=True),
              FieldSpec("values", "values（YAML 映射）", "yaml_map"),
              FieldSpec("derived_from", "derived_from（bib key）", "multiselect", "bib_keys")],
}

KIND_MODELS = {"data": DataCard, "fact": FactCard, "claim": ClaimCard,
               "note": NoteCard, "method": MethodCard, "param": ParamCard}
KIND_ID_WIDGET = {"data": "auto", "fact": "auto", "claim": "auto",
                  "note": "bibkey", "method": "slug", "param": "slug"}
KIND_PREFIX = {"data": "data", "fact": "fact", "claim": "claim"}


def build_choices(kind: str, project: Project) -> dict[str, list[str]]:
    return {"figure_refs": sorted(project.figures),
            "data_ids": sorted(project.data_cards),
            "claim_ids": sorted(project.claims),
            "bib_keys": sorted(project.bib_keys),
            "method_ids": sorted(project.methods),
            "claim_type": ["uncited", "cited"]}


def form_to_meta(kind: str, form, *, is_new: bool, card_id: str | None
                 ) -> tuple[dict, dict[str, str]]:
    """表单 → 模型 meta 字典；(meta, 字段级错误)。id 一律服务端裁定。"""
    meta: dict = {}
    errors: dict[str, str] = {}
    for spec in FIELD_SPECS[kind]:
        if spec.widget == "multiselect":
            meta[spec.name] = [str(v) for v in form.getlist(spec.name)]
        elif spec.widget == "yaml_map":
            raw = str(form.get(spec.name) or "").strip()
            parsed: dict = {}
            if raw:
                try:
                    loaded = yaml.safe_load(raw)
                except yaml.YAMLError as exc:
                    errors.setdefault(spec.name, f"YAML 解析失败：{exc}")
                    loaded = {}
                if not isinstance(loaded, dict):
                    errors.setdefault(spec.name, "必须是 YAML 映射（键: 值）")
                    loaded = {}
                parsed = loaded
            meta[spec.name] = parsed
        else:
            meta[spec.name] = str(form.get(spec.name) or "").strip()
    meta["status"] = str(form.get("status", "draft")) or "draft"
    meta["comment"] = str(form.get("comment", ""))
    meta["id"] = str(form.get("id") or "").strip() if is_new else (card_id or "")
    return meta, errors


def validation_errors(exc) -> dict[str, str]:
    """pydantic ValidationError → {字段: 首条消息}。"""
    out: dict[str, str] = {}
    for err in exc.errors():
        key = ".".join(str(p) for p in err["loc"]) or "__all__"
        out.setdefault(key, err["msg"])
    return out


def values_for_template(kind: str, card) -> dict:
    """model_dump → 模板渲染值；param.values 字典转 YAML 文本。"""
    values = card.model_dump()
    if kind == "param":
        values["values"] = yaml.safe_dump(values.get("values") or {},
                                          allow_unicode=True, sort_keys=False)
    return values


def form_to_values(kind: str, form) -> dict:
    """提交表单 → 模板回显值：multiselect 保持列表，其余为字符串（校验失败重渲染用）。"""
    values: dict = {}
    for spec in FIELD_SPECS[kind]:
        if spec.widget == "multiselect":
            values[spec.name] = [str(v) for v in form.getlist(spec.name)]
        else:
            values[spec.name] = str(form.get(spec.name) or "")
    values["status"] = str(form.get("status", "draft"))
    values["comment"] = str(form.get("comment", ""))
    if form.get("id") is not None:
        values["id"] = str(form.get("id"))
    return values
```

- [ ] **Step 4: 模板 card_form.html + edit 路由**

```html
<!-- src/weft/web/templates/card_form.html -->
{% extends "base.html" %}
{% block title %}{{ form_title }}{% endblock %}
{% block content %}
<h2>{{ form_title }}</h2>
{% if errors %}<div class="banner error">
  {% for k, v in errors.items() %}<div><b>{{ k }}</b>: {{ v }}</div>{% endfor %}
</div>{% endif %}
<form method="post" action="{{ action }}">
  {% if is_new %}
  <label>id（文件名 = id）
    {% if id_widget == "bibkey" %}
    <select name="id">{% for k in id_choices %}<option value="{{ k }}">{{ k }}</option>{% endfor %}</select>
    {% elif id_widget == "slug" %}
    <input name="id" value="{{ prefilled_id }}" placeholder="slug-id（全局唯一，如 prep-stir-01）">
    {% else %}
    <input name="id" value="{{ prefilled_id }}" readonly>
    {% endif %}
  </label>
  {% endif %}
  {% for spec in specs %}
  <label>{{ spec.label }}{% if spec.required %} *{% endif %}</label>
  {% if spec.widget == "text" %}
  <input name="{{ spec.name }}" value="{{ values.get(spec.name, '') }}">
  {% elif spec.widget == "textarea" %}
  <textarea name="{{ spec.name }}" rows="3">{{ values.get(spec.name, '') }}</textarea>
  {% elif spec.widget == "yaml_map" %}
  <textarea name="{{ spec.name }}" rows="5">{{ values.get(spec.name, '') }}</textarea>
  {% elif spec.widget == "select" %}
  <select name="{{ spec.name }}">
    {% for c in choices[spec.choices] %}
    <option value="{{ c }}" {% if values.get(spec.name) == c %}selected{% endif %}>{{ c }}</option>
    {% endfor %}
  </select>
  {% elif spec.widget == "multiselect" %}
  <div class="multi">
    {% for c in choices[spec.choices] %}
    <label class="check"><input type="checkbox" name="{{ spec.name }}" value="{{ c }}"
      {% if c in values.get(spec.name, []) %}checked{% endif %}> {{ c }}</label>
    {% endfor %}
  </div>
  {% endif %}
  {% if errors.get(spec.name) %}<div class="field-error">{{ errors[spec.name] }}</div>{% endif %}
  {% endfor %}
  <label>status
    <select name="status">
      {% for s in ["draft", "approved", "rejected"] %}
      <option value="{{ s }}" {% if values.get("status", "draft") == s %}selected{% endif %}>{{ s }}</option>
      {% endfor %}
    </select>
  </label>
  <label>comment<textarea name="comment" rows="2">{{ values.get("comment", "") }}</textarea></label>
  <button type="submit">保存</button>
  <a href="{{ cancel_url }}">取消</a>
{% endblock %}
```

`routes/cards.py` 追加（注意：加在 detail 路由之后即可，`/{card_id}/edit` 段数不同于 `/new`，无吞并问题；Task 8 的 `/new` 路由必须插在 `/{card_id}` **之前**）：

```python
@router.get("/p/{pid}/cards/{kind}/{card_id}/edit")
def card_edit_get(request: Request, pid: str, kind: str, card_id: str):
    entry, table = _table(request, pid, kind)
    card = table.get(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="卡片不存在")
    return templates.TemplateResponse(
        request, "card_form.html",
        {"pid": pid, "kind": kind, "form_title": f"编辑 {KIND_LABELS[kind]} {card_id}",
         "action": f"/p/{pid}/cards/{kind}/{card_id}/edit",
         "cancel_url": f"/p/{pid}/cards/{kind}/{card_id}",
         "is_new": False, "id_widget": None, "prefilled_id": "", "id_choices": [],
         "specs": FIELD_SPECS[kind],
         "values": values_for_template(kind, card),
         "choices": build_choices(kind, entry.project), "errors": {}})


@router.post("/p/{pid}/cards/{kind}/{card_id}/edit")
async def card_edit_post(request: Request, pid: str, kind: str, card_id: str):
    entry, table = _table(request, pid, kind)
    old_card = table.get(card_id)
    if old_card is None:
        raise HTTPException(status_code=404, detail="卡片不存在")
    form = await request.form()

    def rerender(errors: dict[str, str], values: dict):
        return templates.TemplateResponse(
            request, "card_form.html",
            {"pid": pid, "kind": kind,
             "form_title": f"编辑 {KIND_LABELS[kind]} {card_id}",
             "action": f"/p/{pid}/cards/{kind}/{card_id}/edit",
             "cancel_url": f"/p/{pid}/cards/{kind}/{card_id}",
             "is_new": False, "id_widget": None, "prefilled_id": "", "id_choices": [],
             "specs": FIELD_SPECS[kind], "values": values,
             "choices": build_choices(kind, entry.project), "errors": errors})

    meta, errors = form_to_meta(kind, form, is_new=False, card_id=card_id)
    card = None
    if not errors:
        try:
            card = KIND_MODELS[kind].model_validate(meta)
        except ValidationError as exc:
            errors = validation_errors(exc)
            card = None
    if card is None:
        return rerender(errors, form_to_values(kind, form))
    save_card(entry.project.root, card,
              old_rel=entry.project.card_paths[card_id].as_posix())
    return RedirectResponse(f"/p/{pid}/cards/{kind}/{card_id}", status_code=303)
```

文件头 import 增加：

```python
from pydantic import ValidationError

from weft.web.card_forms import (
    KIND_MODELS,
    FIELD_SPECS,
    build_choices,
    form_to_meta,
    form_to_values,
    validation_errors,
    values_for_template,
)
```

- [ ] **Step 5: 跑测试通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_card_edit.py -v`
Expected: 4 passed

- [ ] **Step 6: 提交**

```bash
git add src/weft/web/card_forms.py src/weft/web/routes/cards.py src/weft/web/templates/card_form.html tests/test_web_card_edit.py
git commit -m "feat: WebUI 卡片编辑——字段规格化表单、校验错误回显、claim_type 迁移"
```

---

### Task 8: 卡片新建

**Files:**
- Modify: `src/weft/web/routes/cards.py`（**`/new` 两个路由必须插在 `/{card_id}` 路由定义之前**）
- Test: `tests/test_web_card_new.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_web_card_new.py
"""卡片新建：id 自动分配/预填、创建落盘、重名拒绝。"""
from pathlib import Path

from weft.store.loader import load_project
from webutil import make_client


def test_new_form_prefills_next_id(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/cards/fact/new")
    assert resp.status_code == 200
    assert 'value="fact-02"' in resp.text and 'readonly' in resp.text


def test_create_writes_card(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/cards/fact/new", data={
        "id": "fact-02", "data": ["data-01"], "statement": "新事实。",
        "supports": [], "status": "draft", "comment": ""})
    assert resp.status_code == 303
    project, diags = load_project(root / "demo")
    assert not any(d.is_error for d in diags)
    assert project.facts["fact-02"].statement == "新事实。"


def test_create_duplicate_id_rejected(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/cards/fact/new", data={
        "id": "fact-01", "data": ["data-01"], "statement": "重复 id。",
        "supports": [], "status": "draft", "comment": ""})
    assert resp.status_code == 200   # 回显错误，不落盘
    assert "fact-01" in resp.text
    project, _ = load_project(root / "demo")
    assert project.facts["fact-01"].statement == "温度提高速率。"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_card_new.py -v`
Expected: FAIL（404）

- [ ] **Step 3: 实现**

`routes/cards.py` 中，在 `card_list`（`/p/{pid}/cards/{kind}`）之后、`card_detail`（`/p/{pid}/cards/{kind}/{card_id}`）**之前**插入：

```python
@router.get("/p/{pid}/cards/{kind}/new")
def card_new_get(request: Request, pid: str, kind: str):
    if kind not in KIND_ATTRS:
        raise HTTPException(status_code=404, detail="未知卡种")
    entry = load_project_or_404(request, pid)
    widget = KIND_ID_WIDGET[kind]
    prefilled = ""
    id_choices: list[str] = []
    if widget == "auto":
        prefilled = next_card_id(entry.project, KIND_PREFIX[kind])
    elif widget == "bibkey":
        id_choices = sorted(entry.project.bib_keys)
    blank = {"status": "draft", "comment": ""}
    if kind == "param":
        blank["values"] = ""
    return templates.TemplateResponse(
        request, "card_form.html",
        {"pid": pid, "kind": kind,
         "form_title": f"新建 {KIND_LABELS[kind]}",
         "action": f"/p/{pid}/cards/{kind}/new",
         "cancel_url": f"/p/{pid}/cards/{kind}",
         "is_new": True, "id_widget": widget, "prefilled_id": prefilled,
         "id_choices": id_choices, "specs": FIELD_SPECS[kind],
         "values": blank, "choices": build_choices(kind, entry.project),
         "errors": {}})


@router.post("/p/{pid}/cards/{kind}/new")
async def card_new_post(request: Request, pid: str, kind: str):
    if kind not in KIND_ATTRS:
        raise HTTPException(status_code=404, detail="未知卡种")
    entry = load_project_or_404(request, pid)
    form = await request.form()

    def rerender(errors: dict[str, str]):
        widget = KIND_ID_WIDGET[kind]
        prefilled = (next_card_id(entry.project, KIND_PREFIX[kind])
                     if widget == "auto" else "")
        id_choices = sorted(entry.project.bib_keys) if widget == "bibkey" else []
        return templates.TemplateResponse(
            request, "card_form.html",
            {"pid": pid, "kind": kind, "form_title": f"新建 {KIND_LABELS[kind]}",
             "action": f"/p/{pid}/cards/{kind}/new",
             "cancel_url": f"/p/{pid}/cards/{kind}",
             "is_new": True, "id_widget": widget, "prefilled_id": prefilled,
             "id_choices": id_choices, "specs": FIELD_SPECS[kind],
             "values": form_to_values(kind, form),
             "choices": build_choices(kind, entry.project), "errors": errors})

    meta, errors = form_to_meta(kind, form, is_new=True, card_id=None)
    card = None
    if not errors:
        try:
            card = KIND_MODELS[kind].model_validate(meta)
        except ValidationError as exc:
            errors = validation_errors(exc)
    if card is not None:
        try:
            create_card(entry.project.root, card)
        except FileExistsError as exc:
            errors = {"id": str(exc)}
            card = None
    if card is None:
        return rerender(errors)
    return RedirectResponse(f"/p/{pid}/cards/{kind}/{card.id}", status_code=303)
```

import 行补 `create_card`、`next_card_id`、`KIND_ID_WIDGET`、`KIND_PREFIX`、`form_to_values`。

- [ ] **Step 4: 跑测试通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_card_new.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add src/weft/web/routes/cards.py tests/test_web_card_new.py
git commit -m "feat: WebUI 卡片新建——id 自动分配/bib key 选择/slug 输入，重名拒绝"
```

---

### Task 9: 叙事工作台（part 页签 + 节点审阅）

**Files:**
- Create: `src/weft/web/routes/parts.py`、`src/weft/web/templates/parts.html`、`part_panel.html`
- Modify: `src/weft/web/routes/__init__.py`
- Test: `tests/test_web_parts.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_web_parts.py
"""叙事工作台：页签、part 面板、节点审阅。"""
from pathlib import Path

from weft.store.loader import load_project
from webutil import make_client


def test_parts_page_renders_tabs(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/parts")
    assert resp.status_code == 200
    assert "sec-01" in resp.text and "para-01-01" in resp.text


def test_part_panel_partial(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/parts/sec-01")
    assert resp.status_code == 200
    assert "para-01-01" in resp.text and "approved" in resp.text


def test_node_review_updates_file(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/parts/sec-01/nodes/para-01-01/status",
                       data={"status": "rejected", "comment": "逻辑不对"})
    assert resp.status_code == 303
    project, diags = load_project(root / "demo")
    assert not any(d.is_error for d in diags)
    node = next(n for p in project.parts for n in p.nodes if n.id == "para-01-01")
    assert node.status == "rejected" and node.comment == "逻辑不对"


def test_unknown_part_404(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/p/demo/parts/sec-99").status_code == 404


def test_part_workflow_override_updates_file(tmp_path):
    """part 级 workflow 显式路由覆盖（webui 设计 §5，词表同 CLI）。"""
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/parts/sec-01/workflow",
                       data={"workflow": "methods"}, follow_redirects=False)
    assert resp.status_code == 303
    project, diags = load_project(root / "demo")
    assert not any(d.is_error for d in diags)
    part = next(p for p in project.parts if p.id == "sec-01")
    assert part.workflow == "methods"
    # 清空恢复自动路由
    client.post("/p/demo/parts/sec-01/workflow", data={"workflow": ""})
    project2, _ = load_project(root / "demo")
    part2 = next(p for p in project2.parts if p.id == "sec-01")
    assert part2.workflow is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_parts.py -v`
Expected: FAIL（404）

- [ ] **Step 3: 实现**

`routes/__init__.py` 的 register_all 追加：

```python
    from weft.web.routes import parts as parts_routes

    parts_routes.register(app)
```

```python
# src/weft/web/routes/parts.py
"""叙事工作台（webui 设计 §5）：part 页签、节点审阅、节点编辑（Task 10）、生成（Task 11）。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from weft.store.writer import save_part
from weft.web.common import load_project_or_404, templates
from weft.workflow import WORKFLOW_VOCAB

router = APIRouter()

_STATUSES = ("draft", "approved", "rejected")


def _find_part(entry, part_id: str):
    for part in entry.project.parts:
        if part.id == part_id:
            return part
    raise HTTPException(status_code=404, detail="叙事 part 不存在")


def _find_node(part, node_id: str):
    for node in part.nodes:
        if node.id == node_id:
            return node
    raise HTTPException(status_code=404, detail="叙事节点不存在")


def _draft_text(project, part_id: str) -> str | None:
    path = project.root / "drafts" / f"{part_id}.md"
    return path.read_text(encoding="utf-8") if path.exists() else None


def _panel_ctx(entry, part) -> dict:
    project = entry.project
    return {"entry": entry, "pid": entry.pid, "part": part,
            "nodes": part.nodes, "draft_text": _draft_text(project, part.id),
            "workflow_vocab": list(WORKFLOW_VOCAB)}


@router.get("/p/{pid}/parts")
def parts_page(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    if not entry.project.parts:
        raise HTTPException(status_code=404, detail="项目没有叙事 part")
    first = entry.project.parts[0]
    return templates.TemplateResponse(
        request, "parts.html",
        {"entry": entry, "pid": pid, "parts": entry.project.parts,
         "current": first.id, **_panel_ctx(entry, first)})


@router.get("/p/{pid}/parts/{part_id}")
def part_panel(request: Request, pid: str, part_id: str):
    entry = load_project_or_404(request, pid)
    part = _find_part(entry, part_id)
    return templates.TemplateResponse(request, "part_panel.html",
                                      _panel_ctx(entry, part))


@router.post("/p/{pid}/parts/{part_id}/nodes/{node_id}/status")
async def node_review(request: Request, pid: str, part_id: str, node_id: str):
    entry = load_project_or_404(request, pid)
    part = _find_part(entry, part_id)
    node = _find_node(part, node_id)
    form = await request.form()
    status = str(form.get("status", ""))
    if status not in _STATUSES:
        raise HTTPException(status_code=400, detail="非法 status")
    part.nodes[part.nodes.index(node)] = node.model_copy(
        update={"status": status, "comment": str(form.get("comment", ""))})
    save_part(entry.project, part)
    return RedirectResponse(f"/p/{pid}/parts/{part_id}", status_code=303)


@router.post("/p/{pid}/parts/{part_id}/workflow")
async def part_workflow(request: Request, pid: str, part_id: str):
    """part 级 workflow 显式路由覆盖（空值 = 清除，走 chapter 自动路由）。"""
    entry = load_project_or_404(request, pid)
    part = _find_part(entry, part_id)
    form = await request.form()
    workflow = str(form.get("workflow", "")).strip()
    if workflow and workflow not in WORKFLOW_VOCAB:
        raise HTTPException(status_code=400, detail="未知 workflow（词表见 E-WORKFLOW-UNKNOWN）")
    part.workflow = workflow or None
    save_part(entry.project, part)
    return RedirectResponse(f"/p/{pid}/parts/{part_id}", status_code=303)
```

注：`part.nodes.index(node)` 依赖 pydantic 模型 `__eq__`（按字段比较）——同 part 内字段完全相同的两个节点会命中第一个，但 node id 在 part 内唯一（loader 校验），安全。

```html
<!-- src/weft/web/templates/parts.html -->
{% extends "base.html" %}
{% block title %}叙事工作台 · {{ pid }}{% endblock %}
{% block content %}
<h2>叙事工作台 · {{ pid }}</h2>
<div class="tabs">
{% for p in parts %}
  <a class="tab {% if p.id == current %}active{% endif %}"
     href="/p/{{ pid }}/parts/{{ p.id }}"
     hx-get="/p/{{ pid }}/parts/{{ p.id }}" hx-target="#panel" hx-swap="innerHTML">{{ p.id }}</a>
{% endfor %}
</div>
<div id="panel">{% include "part_panel.html" %}</div>
{% endblock %}
```

```html
<!-- src/weft/web/templates/part_panel.html -->
<div class="part-panel">
  <h3>{{ part.id }}（{{ part.section }}）</h3>
  <form method="post" action="/p/{{ pid }}/parts/{{ part.id }}/workflow" class="wf-form">
    <label>workflow 覆盖（空 = 按章节自动路由）：
      <select name="workflow">
        <option value="" {% if not part.workflow %}selected{% endif %}>（自动）</option>
        {% for w in workflow_vocab %}
        <option value="{{ w }}" {% if part.workflow == w %}selected{% endif %}>{{ w }}</option>
        {% endfor %}
      </select>
    </label>
    <button type="submit">设置</button>
  </form>
  <div class="cols">
    <div>
      <table class="list">
        <thead><tr><th>#</th><th>节点</th><th>purpose</th><th>status</th><th>uses</th><th>审阅</th></tr></thead>
        <tbody>
        {% for node in nodes %}
        <tr>
          <td>{{ loop.index }}</td>
          <td><a href="/p/{{ pid }}/parts/{{ part.id }}/nodes/{{ node.id }}">{{ node.id }}</a></td>
          <td>{{ node.purpose }}</td>
          <td><span class="badge {{ node.status }}">{{ node.status }}</span></td>
          <td>{% for u in node.uses %}{{ u.id }}({{ u.role }}) {% endfor %}</td>
          <td>
            <form method="post" action="/p/{{ pid }}/parts/{{ part.id }}/nodes/{{ node.id }}/status">
              <input type="hidden" name="status" value="approved">
              <button class="ok" type="submit">✅</button>
            </form>
            <form method="post" action="/p/{{ pid }}/parts/{{ part.id }}/nodes/{{ node.id }}/status">
              <input type="hidden" name="status" value="rejected">
              <button class="bad" type="submit">❌</button>
            </form>
          </td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
    <div class="console">
      <div class="label">生成控制台（仅此 part）</div>
      <form method="post" action="/p/{{ pid }}/parts/{{ part.id }}/generate"
            hx-post="/p/{{ pid }}/parts/{{ part.id }}/generate"
            hx-target="#run-log" hx-swap="innerHTML">
        <label class="check"><input type="checkbox" name="mock" value="1"> mock 模式（免 key）</label>
        <button type="submit">▶ 生成本 part</button>
      </form>
      <div id="run-log" class="run-log"></div>
    </div>
  </div>
  {% if draft_text is not none %}
  <div class="draft-preview">
    <div class="label">当前草稿 drafts/{{ part.id }}.md</div>
    <pre>{{ draft_text }}</pre>
  </div>
  {% endif %}
</div>
```

- [ ] **Step 4: 跑测试通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_parts.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add src/weft/web/routes/parts.py src/weft/web/routes/__init__.py src/weft/web/templates/parts.html src/weft/web/templates/part_panel.html tests/test_web_parts.py
git commit -m "feat: WebUI 叙事工作台——part 页签、节点列表与快捷审阅"
```

---

### Task 10: 节点编辑（uses 成对编辑）

**Files:**
- Modify: `src/weft/web/routes/parts.py`（追加两个路由）
- Create: `src/weft/web/templates/node_form.html`、`src/weft/web/static/webui.js`
- Test: `tests/test_web_node_edit.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_web_node_edit.py
"""节点编辑：uses 成对编辑、悬空引用阻断。"""
from pathlib import Path

from weft.store.loader import load_project
from webutil import make_client


def test_node_edit_form_renders(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/parts/sec-01/nodes/para-01-01")
    assert resp.status_code == 200
    assert "fact-01" in resp.text and "evidence" in resp.text


def test_node_edit_updates_uses(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/parts/sec-01/nodes/para-01-01", data={
        "purpose": "describe", "logic": "改后的逻辑。",
        "use_id": ["fact-01", "claim-01"], "use_role": ["evidence", "conclusion"],
        "status": "approved", "comment": ""})
    assert resp.status_code == 303
    project, diags = load_project(root / "demo")
    assert not any(d.is_error for d in diags)
    node = next(n for p in project.parts for n in p.nodes if n.id == "para-01-01")
    assert [(u.id, u.role) for u in node.uses] == [("fact-01", "evidence"),
                                                   ("claim-01", "conclusion")]
    assert node.logic == "改后的逻辑。"


def test_node_edit_dangling_use_blocked(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/parts/sec-01/nodes/para-01-01", data={
        "purpose": "describe", "logic": "",
        "use_id": ["fact-99"], "use_role": ["evidence"],
        "status": "approved", "comment": ""})
    assert resp.status_code == 200 and "fact-99" in resp.text   # 回显，未落盘
    project, _ = load_project(root / "demo")
    node = next(n for p in project.parts for n in p.nodes if n.id == "para-01-01")
    assert [u.id for u in node.uses] == ["fact-01"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_node_edit.py -v`
Expected: FAIL（404）

- [ ] **Step 3: 实现**

`routes/parts.py` 追加（import：`from pydantic import ValidationError`；`from weft.models.narrative import Node, Use`；`from weft.validation.rules import PURPOSE_VOCAB, ROLE_VOCAB`）：

```python
def _known_ids(project) -> set[str]:
    known: set[str] = set()
    for attr in ("data_cards", "facts", "claims", "notes", "methods", "params"):
        known |= set(getattr(project, attr))
    return known


def _node_form_ctx(entry, part, node, values, errors):
    project = entry.project
    return {"pid": entry.pid, "part": part, "node": node,
            "purpose_vocab": sorted(PURPOSE_VOCAB), "role_vocab": sorted(ROLE_VOCAB),
            "entity_ids": sorted(_known_ids(project)), "values": values,
            "errors": errors}


@router.get("/p/{pid}/parts/{part_id}/nodes/{node_id}")
def node_edit_get(request: Request, pid: str, part_id: str, node_id: str):
    entry = load_project_or_404(request, pid)
    part = _find_part(entry, part_id)
    node = _find_node(part, node_id)
    values = node.model_dump()
    values["use_id"] = [u.id for u in node.uses]
    values["use_role"] = [u.role for u in node.uses]
    return templates.TemplateResponse(
        request, "node_form.html",
        _node_form_ctx(entry, part, node, values, {}))


@router.post("/p/{pid}/parts/{part_id}/nodes/{node_id}")
async def node_edit_post(request: Request, pid: str, part_id: str, node_id: str):
    entry = load_project_or_404(request, pid)
    part = _find_part(entry, part_id)
    node = _find_node(part, node_id)
    form = await request.form()
    # 回显值手工构造：uses 两列保持列表（模板按 use_id 长度循环），其余为标量
    values = {"purpose": str(form.get("purpose", "")),
              "logic": str(form.get("logic", "")),
              "status": str(form.get("status", "draft")),
              "comment": str(form.get("comment", "")),
              "use_id": [str(v) for v in form.getlist("use_id")],
              "use_role": [str(v) for v in form.getlist("use_role")]}
    uses = [Use(id=str(i).strip(), role=str(r).strip())
            for i, r in zip(form.getlist("use_id"), form.getlist("use_role"))
            if str(i).strip()]
    try:
        new_node = Node(id=node_id, purpose=str(form.get("purpose", "")).strip(),
                        uses=uses, logic=str(form.get("logic", "")),
                        status=str(form.get("status", "draft")),
                        comment=str(form.get("comment", "")))
    except ValidationError as exc:
        errors = {(".".join(str(p) for p in e["loc"]) or "__all__"): e["msg"]
                  for e in exc.errors()}
        return templates.TemplateResponse(
            request, "node_form.html",
            _node_form_ctx(entry, part, node, values, errors))
    bad = [u.id for u in new_node.uses if u.id not in _known_ids(entry.project)]
    if bad:
        return templates.TemplateResponse(
            request, "node_form.html",
            _node_form_ctx(entry, part, node, values,
                           {"uses": "实体不存在：" + "、".join(sorted(set(bad)))}))
    part.nodes[part.nodes.index(node)] = new_node
    save_part(entry.project, part)
    return RedirectResponse(f"/p/{pid}/parts/{part_id}", status_code=303)
```

```html
<!-- src/weft/web/templates/node_form.html -->
{% extends "base.html" %}
{% block title %}节点 {{ node.id }}{% endblock %}
{% block content %}
<h2>节点 {{ node.id }}（{{ part.id }}）
  <span class="badge {{ node.status }}">{{ node.status }}</span></h2>
{% if errors %}<div class="banner error">
  {% for k, v in errors.items() %}<div><b>{{ k }}</b>: {{ v }}</div>{% endfor %}
</div>{% endif %}
<form method="post" action="/p/{{ pid }}/parts/{{ part.id }}/nodes/{{ node.id }}">
  <label>purpose（词表可选，允许自定义）
    <input name="purpose" value="{{ values.get('purpose', '') }}" list="purpose-vocab">
  </label>
  <datalist id="purpose-vocab">{% for p in purpose_vocab %}<option value="{{ p }}">{% endfor %}</datalist>
  <label>logic（写作逻辑说明）
    <textarea name="logic" rows="4">{{ values.get('logic', '') }}</textarea>
  </label>
  <div class="label">uses（本节点使用的实体：id + role 成对）</div>
  <div id="use-rows">
    {% for i in range(values.get('use_id', []) | length) %}
    <div class="use-row">
      <input name="use_id" value="{{ values['use_id'][i] }}" list="entity-ids" placeholder="实体 id">
      <input name="use_role" value="{{ values['use_role'][i] }}" list="role-vocab" placeholder="role">
      <button type="button" onclick="this.parentNode.remove()">移除</button>
    </div>
    {% endfor %}
    <div class="use-row">
      <input name="use_id" value="" list="entity-ids" placeholder="实体 id">
      <input name="use_role" value="" list="role-vocab" placeholder="role">
      <button type="button" onclick="this.parentNode.remove()">移除</button>
    </div>
  </div>
  <button type="button" onclick="addUseRow()">＋ 添加 use</button>
  <datalist id="entity-ids">{% for eid in entity_ids %}<option value="{{ eid }}">{% endfor %}</datalist>
  <datalist id="role-vocab">{% for r in role_vocab %}<option value="{{ r }}">{% endfor %}</datalist>
  <label>status
    <select name="status">
      {% for s in ["draft", "approved", "rejected"] %}
      <option value="{{ s }}" {% if values.get('status', 'draft') == s %}selected{% endif %}>{{ s }}</option>
      {% endfor %}
    </select>
  </label>
  <label>comment<textarea name="comment" rows="2">{{ values.get('comment', '') }}</textarea></label>
  <button type="submit">保存节点</button>
  <a href="/p/{{ pid }}/parts/{{ part.id }}">返回工作台</a>
</form>
{% endblock %}
```

```javascript
// src/weft/web/static/webui.js
// weft WebUI 交互：SSE 进度流（Task 11 消费）+ uses 行克隆（webui 设计 §5/§6）。
function addUseRow() {
  const rows = document.getElementById("use-rows");
  if (!rows) return;
  const tpl = rows.querySelector(".use-row");
  const clone = tpl.cloneNode(true);
  clone.querySelectorAll("input").forEach(function (el) { el.value = ""; });
  rows.appendChild(clone);
}

function connectRunStream(scope) {
  (scope || document).querySelectorAll("[data-run-id]").forEach(function (el) {
    if (el.dataset.streamBound) return;
    el.dataset.streamBound = "1";
    const src = new EventSource(el.dataset.eventsUrl);
    src.onmessage = function (m) {
      const ev = JSON.parse(m.data);
      const line = document.createElement("div");
      line.className = "log-" + ev.kind;
      line.textContent = (ev.node_id ? ev.node_id + " · " : "") +
        ev.kind + (ev.message ? " — " + ev.message : "");
      el.appendChild(line);
      if (ev.kind === "run_finished" || ev.kind === "run_failed") {
        src.close();
        const panel = el.closest("[data-panel-url]");
        if (panel && window.htmx) {
          htmx.ajax("GET", panel.dataset.panelUrl, panel);   // 完成后刷新面板（草稿预览）
        }
      }
    };
  });
}

document.addEventListener("DOMContentLoaded", function () { connectRunStream(document); });
document.addEventListener("htmx:afterSwap", function (evt) { connectRunStream(evt.target); });
```

（webui.js 亦可提前到 Task 5 一并提交；此处为最小依赖放本任务，Task 11 依赖其 `connectRunStream`。）

- [ ] **Step 4: 跑测试通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_node_edit.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add src/weft/web/routes/parts.py src/weft/web/templates/node_form.html src/weft/web/static/webui.js tests/test_web_node_edit.py
git commit -m "feat: WebUI 节点编辑——uses 成对编辑、悬空引用就地阻断"
```

---

### Task 11: 生成运行管理 + 触发 + SSE

**Files:**
- Create: `src/weft/web/runs.py`、`src/weft/web/templates/run_console.html`
- Modify: `src/weft/web/routes/parts.py`（generate + SSE 路由）、`src/weft/web/__init__.py`（挂 RunManager）
- Test: `tests/test_web_generate.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_web_generate.py
"""生成触发、SSE 事件序列、闸门拒绝、per-project 锁。"""
import json
import re

from helpers import make_minimal_project, write_card
from weft.store.loader import load_project
from weft.web.runs import RunManager
from webutil import make_client


def test_run_manager_lock():
    mgr = RunManager()
    run = mgr.try_start("p1")
    assert run is not None
    assert mgr.try_start("p1") is None      # 同项目串行
    assert mgr.try_start("p2") is not None  # 异项目互不影响
    mgr.finish("p1", run)
    assert mgr.try_start("p1") is not None


def test_generate_sse_event_sequence(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/parts/sec-01/generate", data={"mock": "1"})
    assert resp.status_code == 200
    match = re.search(r'data-run-id="([0-9a-f]+)"', resp.text)
    assert match, resp.text
    events = []
    with client.stream("GET", f"/p/demo/runs/{match.group(1)}/events") as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))
    kinds = [e["kind"] for e in events]
    assert kinds[0] == "run_started"
    assert kinds.count("node_started") == 1 and kinds.count("node_finished") == 1
    assert "draft_written" in kinds
    assert kinds[-1] == "run_finished"
    assert (root / "demo" / "drafts" / "sec-01.md").exists()


def test_generate_gate_rejects_with_errors(tmp_path):
    client, root = make_client(tmp_path)
    write_card(root / "demo" / "metadata" / "data", "oops",
               {"id": "data-01", "status": "draft"})   # 文件名≠id → 校验错误
    resp = client.post("/p/demo/parts/sec-01/generate", data={"mock": "1"})
    assert resp.status_code == 200
    assert "校验存在错误" in resp.text
    assert 'data-run-id' not in resp.text
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_generate.py -v`
Expected: FAIL（模块/路由不存在）

- [ ] **Step 3: 实现 runs.py**

```python
# src/weft/web/runs.py
"""生成运行管理（webui 设计 §6）：per-project 锁 + 内存事件队列 + SSE 流。

事件经 SimpleQueue 缓冲：晚连接的 SSE 消费者仍能取到全部历史事件（队列未消费不丢），
测试因此与线程时序无关。单人演示场景，无持久化。
"""
from __future__ import annotations

import json
import queue
import threading
import uuid
from dataclasses import dataclass

_TERMINAL = ("run_finished", "run_failed")


@dataclass(frozen=True)
class RunEvent:
    kind: str
    node_id: str | None = None
    message: str = ""


class Run:
    def __init__(self, run_id: str) -> None:
        self.id = run_id
        self.error: str | None = None
        self._queue: queue.SimpleQueue = queue.SimpleQueue()
        self._done = threading.Event()

    def emit(self, event: RunEvent) -> None:
        self._queue.put(event)

    def finish(self) -> None:
        self._done.set()

    def stream_sse(self):
        """阻塞消费事件 → SSE 行；终态事件后结束。"""
        while True:
            try:
                ev = self._queue.get(timeout=10)
            except queue.Empty:
                if self._done.is_set():
                    return
                continue
            payload = json.dumps({"kind": ev.kind, "node_id": ev.node_id,
                                  "message": ev.message}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
            if ev.kind in _TERMINAL:
                return


class RunManager:
    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._mu = threading.Lock()

    def try_start(self, project_key: str) -> Run | None:
        with self._mu:
            lock = self._locks.setdefault(project_key, threading.Lock())
            if not lock.acquire(blocking=False):
                return None
            run = Run(uuid.uuid4().hex[:12])
            self._runs[run.id] = run
            return run

    def get(self, run_id: str) -> Run | None:
        with self._mu:
            return self._runs.get(run_id)

    def finish(self, project_key: str, run: Run) -> None:
        with self._mu:
            self._locks[project_key].release()
        run.finish()
```

- [ ] **Step 4: 接线 generate 路由与 SSE**

`src/weft/web/__init__.py` 的 `create_app` 中，`register_all(app)` 之前加：

```python
    from weft.web.runs import RunManager

    app.state.runs = RunManager()
```

`routes/parts.py` 追加（import 增：`from fastapi.responses import HTMLResponse, RedirectResponse`（RedirectResponse 已有）、`from weft.engine import DraftError, make_client`、`from weft.engine.part_draft import run_part_draft`、`from weft.validation import validate_project`、`from weft.store.loader import load_project`、`from weft.web.runs import RunEvent`、`threading`）：

```python
@router.post("/p/{pid}/parts/{part_id}/generate")
async def generate(request: Request, pid: str, part_id: str):
    entry = load_project_or_404(request, pid)
    form = await request.form()
    mock = str(form.get("mock", "")) == "1"

    # 闸门（红线 6）：新生成快照，load + validate，有 error 即拒绝
    project, load_diags = load_project(entry.path)
    diagnostics = load_diags + validate_project(project)
    if any(d.is_error for d in diagnostics):
        banner = "".join(
            f'<div class="field-error">{"ERROR" if d.is_error else "WARN"} '
            f'{d.path} [{d.code}] {d.message}</div>'
            for d in diagnostics if d.is_error)
        html = (f'<div class="banner error"><div>校验存在错误，拒绝生成</div>{banner}</div>'
                f'<div id="run-log" class="run-log"></div>')
        return HTMLResponse(html)
    part = _find_part_by_project(project, part_id)
    run = request.app.state.runs.try_start(pid)
    if run is None:
        return HTMLResponse(
            '<div class="banner error">已有生成任务在运行，请等待完成</div>'
            '<div id="run-log" class="run-log"></div>', status_code=409)

    def worker() -> None:
        try:
            client = make_client(mock, project_root=project.root)
            run_part_draft(project, part, client=client, on_event=lambda e: run.emit(
                RunEvent(e.kind, e.node_id, e.message)))
        except Exception as exc:            # runner 已发过 run_failed 事件
            run.error = str(exc)
        finally:
            request.app.state.runs.finish(pid, run)

    threading.Thread(target=worker, daemon=True).start()
    return templates.TemplateResponse(
        request, "run_console.html",
        {"pid": pid, "part_id": part_id, "run_id": run.id})


@router.get("/p/{pid}/runs/{run_id}/events")
def sse_events(request: Request, pid: str, run_id: str):
    run = request.app.state.runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    from fastapi.responses import StreamingResponse

    return StreamingResponse(run.stream_sse(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})
```

`routes/parts.py` 增加辅助函数（generate 用新快照查 part，不复用 entry.project）：

```python
def _find_part_by_project(project, part_id: str):
    for part in project.parts:
        if part.id == part_id:
            return part
    raise HTTPException(status_code=404, detail="叙事 part 不存在")
```

```html
<!-- src/weft/web/templates/run_console.html -->
<div id="run-log" class="run-log" data-run-id="{{ run_id }}"
     data-events-url="/p/{{ pid }}/runs/{{ run_id }}/events"
     data-panel-url="/p/{{ pid }}/parts/{{ part_id }}">
  <div class="label">生成进度（实时）· run={{ run_id }}</div>
</div>
```

- [ ] **Step 5: 跑测试通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_generate.py -v`
Expected: 3 passed

- [ ] **Step 6: 提交**

```bash
git add src/weft/web/runs.py src/weft/web/__init__.py src/weft/web/routes/parts.py src/weft/web/templates/run_console.html tests/test_web_generate.py
git commit -m "feat: WebUI 生成触发与 SSE 实时进度流（per-project 锁、闸门拒绝）"
```

---

### Task 12: graph / 诊断 / 文件预览（含路径穿越防护）

**Files:**
- Modify: `src/weft/web/routes/core.py`（追加 4 个路由）
- Create: `src/weft/web/templates/graph.html`、`diagnostics.html`、`file_view.html`、`src/weft/web/static/cytoscape.min.js`（vendor）
- Test: `tests/test_web_misc.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_web_misc.py
"""graph 页与生成按钮、诊断表、文件预览与穿越防护。"""
from pathlib import Path

from webutil import make_client


def test_diagnostics_lists_codes(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/diagnostics")
    assert resp.status_code == 200
    assert "错误" in resp.text and "提醒" in resp.text


def test_files_preview_and_traversal(tmp_path):
    client, root = make_client(tmp_path)
    (root / "demo" / "drafts").mkdir()
    (root / "demo" / "drafts" / "sec-01.md").write_text("<!-- weft:run=x -->\n正文",
                                                        encoding="utf-8")
    resp = client.get("/p/demo/files/drafts/sec-01.md")
    assert resp.status_code == 200 and "正文" in resp.text
    assert client.get("/p/demo/files/%2E%2E/metadata/facts/fact-01.md").status_code == 404
    assert client.get("/p/demo/files/metadata/facts/fact-01.md").status_code == 404


def test_graph_page_and_regenerate(tmp_path):
    client, root = make_client(tmp_path)
    page = client.get("/p/demo/graph")
    assert page.status_code == 200
    assert "生成图谱" in page.text          # 初始无 graph.json
    resp = client.post("/p/demo/graph/regenerate", follow_redirects=False)
    assert resp.status_code == 303
    assert (root / "demo" / "generated" / "graph.json").exists()
    page2 = client.get("/p/demo/graph")
    assert "cytoscape" in page2.text
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_misc.py -v`
Expected: FAIL（404）

- [ ] **Step 3: 实现**

`routes/core.py` 追加（import 增：`import json`、`from fastapi import HTTPException`、`from fastapi.responses import RedirectResponse`、`from weft.store.loader import load_project`、`from weft.validation import validate_project`、`from weft.graphgen.writer import write_outputs`）：

```python
@router.get("/p/{pid}/diagnostics")
def diagnostics_page(request: Request, pid: str):
    entry = load_entry_or_404(request, pid)
    return templates.TemplateResponse(
        request, "diagnostics.html", {"entry": entry})


@router.get("/p/{pid}/graph")
def graph_page(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    graph_path = entry.project.root / "generated" / "graph.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8")) if graph_path.exists() else None
    return templates.TemplateResponse(
        request, "graph.html", {"entry": entry, "graph": graph})


@router.post("/p/{pid}/graph/regenerate")
def graph_regenerate(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    project = entry.project
    if any(d.is_error for d in entry.diagnostics):
        return RedirectResponse(f"/p/{pid}/diagnostics", status_code=303)
    write_outputs(project, project.root / "generated")
    return RedirectResponse(f"/p/{pid}/graph", status_code=303)


_SAFE_ROOTS = ("drafts", "generated")


@router.get("/p/{pid}/files/{relpath:path}")
def file_view(request: Request, pid: str, relpath: str):
    entry = load_project_or_404(request, pid)
    root = entry.project.root.resolve()
    target = (root / relpath).resolve()
    parts = Path(relpath).parts
    allowed = (bool(parts) and parts[0] in _SAFE_ROOTS
               and (target == root or root in target.parents)
               and target.is_file())
    if not allowed:
        raise HTTPException(status_code=404, detail="文件不存在或不在白名单目录")
    return templates.TemplateResponse(
        request, "file_view.html",
        {"entry": entry, "rel": relpath,
         "text": target.read_text(encoding="utf-8", errors="replace")})
```

模板：

```html
<!-- src/weft/web/templates/diagnostics.html -->
{% extends "base.html" %}
{% block title %}诊断 · {{ entry.pid }}{% endblock %}
{% block content %}
<h2>诊断 · {{ entry.pid }}（{{ entry.n_errors }} 错误 / {{ entry.n_warnings }} 提醒）</h2>
<table class="list">
  <thead><tr><th>级别</th><th>码</th><th>位置</th><th>字段</th><th>消息</th></tr></thead>
  <tbody>
  {% for d in entry.diagnostics %}
  <tr>
    <td>{% if d.is_error %}<span class="badge rejected">ERROR</span>
        {% else %}<span class="badge draft">WARN</span>{% endif %}</td>
    <td><code>{{ d.code }}</code></td><td><code>{{ d.path }}</code></td>
    <td>{{ d.field or "" }}</td><td>{{ d.message }}</td>
  </tr>
  {% endfor %}
  </tbody>
</table>
<p><a href="/p/{{ entry.pid }}/">返回总览</a></p>
{% endblock %}
```

```html
<!-- src/weft/web/templates/graph.html -->
{% extends "base.html" %}
{% block title %}图谱 · {{ entry.pid }}{% endblock %}
{% block content %}
<h2>元数据图谱 · {{ entry.pid }}</h2>
{% if graph %}
<div id="graph" style="height: 70vh; border: 1px solid #d0d7de; border-radius: 6px;"></div>
<script id="graph-data" type="application/json">{{ graph | tojson }}</script>
<script src="/static/cytoscape.min.js"></script>
<script>
  const data = JSON.parse(document.getElementById("graph-data").textContent);
  const ents = data.entities || data;   // 防御：兼容顶层包装（执行时以实际 graph.json 为准核对）
  const palette = {data: "#8250df", fact: "#0969da", claim: "#1a7f37",
                   note: "#bf8700", method: "#cf222e", param: "#57606a"};
  const els = [];
  for (const [id, e] of Object.entries(ents)) {
    els.push({data: {id: id, label: id, kind: e.kind, color: palette[e.kind] || "#57606a"}});
    for (const [field, ids] of Object.entries(e.referenced_by || {})) {
      for (const src of ids) {
        els.push({data: {id: src + "->" + id + ":" + field, source: src, target: id}});
      }
    }
  }
  cytoscape({container: document.getElementById("graph"), elements: els,
    style: [{selector: "node", style: {"label": "data(label)", "background-color": "data(color)",
                                       "font-size": 10, width: 24, height: 24}},
            {selector: "edge", style: {width: 1, "line-color": "#d0d7de",
                                       "target-arrow-color": "#d0d7de",
                                       "curve-style": "bezier"}}],
    layout: {name: "cose", animate: false}});
</script>
{% else %}
<p>尚未生成 <code>generated/graph.json</code>。</p>
<form method="post" action="/p/{{ entry.pid }}/graph/regenerate">
  <button type="submit">生成图谱（非 LLM，秒级）</button>
</form>
{% endif %}
{% endblock %}
```

```html
<!-- src/weft/web/templates/file_view.html -->
{% extends "base.html" %}
{% block title %}{{ rel }}{% endblock %}
{% block content %}
<h2><code>{{ rel }}</code></h2>
<pre style="border: 1px solid #d0d7de; border-radius: 6px; padding: 12px; white-space: pre-wrap;">{{ text }}</pre>
<p><a href="/p/{{ entry.pid }}/">返回总览</a></p>
{% endblock %}
```

vendor cytoscape：

```bash
curl -L -o src/weft/web/static/cytoscape.min.js https://unpkg.com/cytoscape@3.30.2/dist/cytoscape.min.js \
  || curl -L -o src/weft/web/static/cytoscape.min.js https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.30.2/cytoscape.min.js
ls -la src/weft/web/static/cytoscape.min.js   # ~300KB 即成功
```

- [ ] **Step 4: 跑测试通过（核对 graph.json 结构）**

Run 前：执行一次 `.venv/Scripts/python.exe -m weft graph examples/paper-demo`（或任一 tmp 项目），`head -20 generated/graph.json` 核对顶层键确为实体索引；若发现顶层包装键不是 `entities`，只改 graph.html 的 `const ents = …` 一行。

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_misc.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add src/weft/web/routes/core.py src/weft/web/templates/graph.html src/weft/web/templates/diagnostics.html src/weft/web/templates/file_view.html src/weft/web/static/cytoscape.min.js tests/test_web_misc.py
git commit -m "feat: WebUI 图谱可视化/诊断表/产物预览（白名单防穿越）"
```

---

### Task 13: inspire 页（含 apply_proposal 提炼）

**Files:**
- Modify: `src/weft/engine/inspire/apply.py`（追加 `apply_proposal`）、`src/weft/cli.py`（replace 命令接线）
- Create: `src/weft/web/routes/inspire.py`、`src/weft/web/templates/inspire.html`
- Modify: `src/weft/web/routes/__init__.py`
- Test: `tests/test_web_inspire.py`（并在 `tests/test_inspire_apply.py` 补 1 个 apply_proposal 单元测试）

- [ ] **Step 1: 写失败测试**

`tests/test_inspire_apply.py` 末尾追加：

```python
def test_apply_proposal_replaces_and_archives(tmp_path):
    """提炼后的 apply_proposal（CLI 与 WebUI 共用）：新卡替换旧卡，旧卡归档。"""
    import frontmatter as fm

    from weft.engine.inspire.apply import apply_proposal

    root = make_minimal_project(tmp_path)
    project, diags = load_project(root)
    assert not any(d.is_error for d in diags)
    proposals = root / "inspirations" / "proposals"
    proposals.mkdir(parents=True)
    proposals.joinpath("claim-01.md").write_text(fm.dumps(fm.Post("", **{
        "id": "claim-01", "claim_type": "uncited",
        "statement": "搅拌是溶解的主要因素（提案版）。", "status": "draft"})),
        encoding="utf-8")
    old_path, archive_path = apply_proposal(project, "claim-01")
    assert old_path == root / "metadata" / "claims" / "uncited" / "claim-01.md"
    assert "搅拌是溶解的主要因素（提案版）" in old_path.read_text(encoding="utf-8")
    assert (root / "archive" / "cards" / "uncited" / "claim-01.md").exists()
    assert archive_path == root / "archive" / "cards" / "uncited" / "claim-01.md"
    assert not proposals.joinpath("claim-01.md").exists()
```

```python
# tests/test_web_inspire.py
"""灵感页：表单触发（mock）、SSE 完成、提案应用路由。"""
import json
import re
from pathlib import Path

import frontmatter as fm

from weft.store.loader import load_project
from webutil import make_client


def test_inspire_page_renders(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/inspire")
    assert resp.status_code == 200 and "灵感" in resp.text


def test_inspire_run_finishes_with_mock(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/inspire/run", data={
        "text": "搅拌 speed up dissolving，也许温度才是主因？", "mock": "1"})
    match = re.search(r'data-run-id="([0-9a-f]+)"', resp.text)
    assert match, resp.text
    events = []
    with client.stream("GET", f"/p/demo/runs/{match.group(1)}/events") as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))
    assert events[-1]["kind"] == "run_finished"
    project, _ = load_project(root / "demo")
    assert (root / "demo" / "inspirations").is_dir()   # 收件箱 + 报告已落盘


def test_apply_proposal_route(tmp_path):
    client, root = make_client(tmp_path)
    proposals = root / "demo" / "inspirations" / "proposals"
    proposals.mkdir(parents=True)
    proposals.joinpath("claim-01.md").write_text(fm.dumps(fm.Post("", **{
        "id": "claim-01", "claim_type": "uncited",
        "statement": "网页应用的提案。", "status": "draft"})), encoding="utf-8")
    resp = client.post("/p/demo/inspire/proposals/claim-01/apply",
                       follow_redirects=False)
    assert resp.status_code == 303
    assert "网页应用的提案" in (root / "demo" / "metadata" / "claims" / "uncited"
                                / "claim-01.md").read_text(encoding="utf-8")
    assert not proposals.joinpath("claim-01.md").exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_inspire_apply.py tests/test_web_inspire.py -v`
Expected: FAIL（`apply_proposal` 不存在；inspire 路由 404）

- [ ] **Step 3: 提炼 apply_proposal（engine/inspire/apply.py 末尾追加）**

```python
def apply_proposal(project: Project, card_id: str) -> tuple[Path, Path]:
    """应用替换提案 inspirations/proposals/<card_id>.md：新卡替换旧卡，旧卡归档 archive/。

    返回 (旧卡路径=新内容落点, 归档路径)。目标/提案不存在、id 不一致、校验闸门拒绝、
    归档重名、落盘失败一律 raise ValueError（磁盘零改动语义由调用方呈现）。
    CLI（cli.replace_proposal）与 WebUI 共用本函数（webui 设计 §3）。
    """
    import frontmatter

    from weft.engine.inspire.cards import _normalize
    from weft.models.cards import ClaimCard, FactCard

    proposal_path = project.root / "inspirations" / "proposals" / f"{card_id}.md"
    if card_id not in project.card_paths:
        raise ValueError(f"目标卡不存在：{card_id}")
    if not proposal_path.is_file():
        raise ValueError(f"替换提案不存在：{proposal_path}")
    old_rel = project.card_paths[card_id]
    old_path = project.root / old_rel
    is_fact = "facts" in old_rel.parts
    model = FactCard if is_fact else ClaimCard
    try:
        post = frontmatter.load(proposal_path)
        new_card = model.model_validate(post.metadata)
    except Exception as exc:
        raise ValueError(f"提案卡解析失败：{exc}") from exc
    if new_card.id != card_id:
        raise ValueError(f"提案卡 id {new_card.id} 与目标 {card_id} 不一致")

    # 闸门：内存替换后全量校验，有 error 即拒绝（磁盘零改动）
    table = project.facts if is_fact else project.claims
    table[card_id] = new_card
    gate_errors = [d for d in validate_project(project) if d.is_error]
    if gate_errors:
        raise ValueError("替换被校验闸门拒绝，磁盘未改动：" + "；".join(
            f"{d.code} {d.path} {d.message}" for d in gate_errors[:3]))

    archive_dir = project.root / "archive" / "cards" / old_rel.parent.name
    archive_path = archive_dir / old_rel.name
    if archive_path.exists():
        raise ValueError(f"归档重名，拒绝覆盖：{archive_path}")
    try:
        archive_dir.mkdir(parents=True, exist_ok=True)
        old_path.rename(archive_path)
        old_path.write_text(
            _normalize(proposal_path.read_text(encoding="utf-8")),
            encoding="utf-8", newline="\n")
        proposal_path.unlink()
    except OSError as exc:
        raise ValueError(f"替换落盘失败：{exc}") from exc
    return old_path, archive_path
```

（`apply.py` 头部 import 需确认已有 `from pathlib import Path`、`from weft.store.project import Project`、`from weft.validation import validate_project`，缺则补。）

`cli.py` 的 `replace_proposal` 命令体替换为（行为与输出消息保持等价）：

```python
    project, load_diags = load_project(project_dir)
    if any(d.is_error for d in load_diags):
        _print_diagnostics(load_diags)
        raise typer.Exit(code=1)
    try:
        new_path, archive_path = apply_proposal(project, card_id)
    except ValueError as exc:
        typer.echo(f"ERROR {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"已替换 {new_path.relative_to(project.root).as_posix()}")
    typer.echo(f"旧卡归档 {archive_path.relative_to(project.root).as_posix()}")
```

（局部 import：`from weft.engine.inspire.apply import apply_proposal`。）

- [ ] **Step 4: 实现 WebUI inspire 路由与模板**

`routes/__init__.py` register_all 追加：

```python
    from weft.web.routes import inspire as inspire_routes

    inspire_routes.register(app)
```

```python
# src/weft/web/routes/inspire.py
"""灵感页（webui 设计 §6）：输入文本段 → 后台 run_inspire+apply_inspiration → SSE → 提案应用。

收件箱文件由"人"经表单写入（inspirations/web-<时间戳>.md），非 AI 产物白名单问题；
inspire 落盘（草稿卡/proposals/报告/.runs 快照）全部走 engine 既有逻辑（红线 4 原样）。
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from weft.engine import make_client
from weft.engine.inspire.apply import apply_inspiration, apply_proposal
from weft.engine.inspire.run import run_inspire
from weft.store.loader import load_project
from weft.validation import validate_project
from weft.web.common import load_project_or_404, templates
from weft.web.runs import RunEvent

router = APIRouter()


@router.get("/p/{pid}/inspire")
def inspire_page(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    proposals_dir = entry.project.root / "inspirations" / "proposals"
    proposals = []
    if proposals_dir.is_dir():
        import frontmatter

        for path in sorted(proposals_dir.glob("*.md")):
            proposals.append({"id": path.stem})
    return templates.TemplateResponse(
        request, "inspire.html",
        {"entry": entry, "proposals": proposals})


@router.post("/p/{pid}/inspire/run")
async def inspire_run(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    form = await request.form()
    text = str(form.get("text", ""))
    mock = str(form.get("mock", "")) == "1"
    project, load_diags = load_project(entry.path)
    diagnostics = load_diags + validate_project(project)
    if any(d.is_error for d in diagnostics) or not text.strip():
        return HTMLResponse(
            '<div class="banner error">校验存在错误或灵感文本为空，拒绝处理</div>'
            '<div id="run-log" class="run-log"></div>')
    run = request.app.state.runs.try_start(pid)
    if run is None:
        return HTMLResponse(
            '<div class="banner error">已有任务在运行，请等待完成</div>'
            '<div id="run-log" class="run-log"></div>', status_code=409)

    def worker() -> None:
        try:
            source = project.root / "inspirations" / f"web-{time.strftime('%Y%m%d-%H%M%S')}.md"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(text.replace("\r\n", "\n").replace("\r", "\n"),
                              encoding="utf-8", newline="\n")
            run.emit(RunEvent("run_started", message=f"inspire：{source.name}"))
            result = run_inspire(project, text, client=make_client(
                mock, project_root=project.root), source=source.name)
            if result.resumed:
                run.emit(RunEvent("node_finished", message="断点续跑：已完成节点取自上次快照"))
            outcome = apply_inspiration(project, source=source, logic=result.logic,
                                        extract=result.extract, review=result.review,
                                        match=result.match, coverage=result.coverage)
            for p in outcome.written_cards:
                run.emit(RunEvent("node_finished",
                                  message=f"写入 {p.relative_to(project.root).as_posix()}"))
            run.emit(RunEvent("draft_written",
                              message=f"{len(outcome.proposals)} 张替换提案待审"))
            run.emit(RunEvent("run_finished",
                              message=f"报告 {outcome.report.relative_to(project.root).as_posix()}"))
        except Exception as exc:
            run.error = str(exc)
            run.emit(RunEvent("run_failed", message=str(exc)))
        finally:
            request.app.state.runs.finish(pid, run)

    threading.Thread(target=worker, daemon=True).start()
    return templates.TemplateResponse(
        request, "run_console.html",
        {"pid": pid, "part_id": "inspire", "run_id": run.id})


@router.post("/p/{pid}/inspire/proposals/{card_id}/apply")
def proposal_apply(request: Request, pid: str, card_id: str):
    entry = load_project_or_404(request, pid)
    try:
        apply_proposal(entry.project, card_id)
    except ValueError:
        return RedirectResponse(f"/p/{pid}/inspire", status_code=303)
    return RedirectResponse(f"/p/{pid}/inspire", status_code=303)
```

```html
<!-- src/weft/web/templates/inspire.html -->
{% extends "base.html" %}
{% block title %}灵感 · {{ entry.pid }}{% endblock %}
{% block content %}
<h2>灵感（inspire）· {{ entry.pid }}</h2>
<div class="cols">
  <div>
    <form method="post" action="/p/{{ entry.pid }}/inspire/run"
          hx-post="/p/{{ entry.pid }}/inspire/run" hx-target="#run-log" hx-swap="innerHTML">
      <label>灵感文本段（粘一段读到的东西，AI 提炼为卡片并生成替换提案）
        <textarea name="text" rows="8" placeholder="粘贴文本…"></textarea>
      </label>
      <label class="check"><input type="checkbox" name="mock" value="1"> mock 模式（免 key）</label>
      <button type="submit">▶ 处理灵感</button>
    </form>
    <div id="run-log" class="run-log"></div>
  </div>
  <div>
    <div class="label">待应用替换提案</div>
    {% if proposals %}
    <table class="list">
      <thead><tr><th>目标卡</th><th></th></tr></thead>
      <tbody>
      {% for p in proposals %}
      <tr>
        <td>{{ p.id }}</td>
        <td>
          <form method="post" action="/p/{{ entry.pid }}/inspire/proposals/{{ p.id }}/apply">
            <button type="submit">应用（旧卡归档）</button>
          </form>
        </td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
    {% else %}<p>（无提案——处理后生成）</p>{% endif %}
  </div>
</div>
{% endblock %}
```

- [ ] **Step 5: 跑测试通过 + inspire CLI 回归**

Run: `.venv/Scripts/python.exe -m pytest tests/test_inspire_apply.py tests/test_web_inspire.py tests/test_cli_inspire.py -v`
Expected: 全部 passed

- [ ] **Step 6: 提交**

```bash
git add src/weft/engine/inspire/apply.py src/weft/cli.py src/weft/web/routes/inspire.py src/weft/web/routes/__init__.py src/weft/web/templates/inspire.html tests/test_inspire_apply.py tests/test_web_inspire.py
git commit -m "feat: WebUI 灵感页——run_inspire 后台运行与提案应用（apply_proposal 提炼共用）"
```

---

### Task 14: vendor 收尾 + 全量回归

**Files:**
- Verify: `src/weft/web/static/{htmx.min.js, cytoscape.min.js, webui.css, webui.js}`

- [ ] **Step 1: 核对 vendor 文件齐全**

```bash
ls -la src/weft/web/static/
# htmx.min.js ~50KB、cytoscape.min.js ~300KB、webui.css、webui.js 均存在
```

- [ ] **Step 2: 手动冒烟（真实浏览器过一遍动线）**

```bash
SMOKE=$(mktemp -d)/projects
mkdir -p "$SMOKE" && cp -r examples/paper-demo "$SMOKE/demo"
rm -rf "$SMOKE/demo/drafts" "$SMOKE/demo/generated"/*   # 清掉历史产物从零演示
.venv/Scripts/python.exe -m weft serve "$SMOKE" --port 8300
```

浏览器过：项目列表 → 仪表盘 → 卡片编辑保存 → part 审阅 → mock 生成 SSE → 图谱 → 诊断 → 灵感 mock 处理。冒烟目录在系统 tmp，不进仓库。

- [ ] **Step 3: 全量回归**

Run: `.venv/Scripts/python.exe -m pytest tests -q`
Expected: **306 passed, 1 deselected**（260 基线 + 46 新增；若基线漂移按实际回填计划计数表）

- [ ] **Step 4: 提交**

```bash
git add -A src/weft/web/static
git commit -m "chore: WebUI 静态资源 vendor 收尾与全量回归（306 passed）"
```

---

### Task 15: 部署文档 + roadmap 更新

**Files:**
- Create: `docs/webui.md`
- Modify: `docs/roadmap.md`（M4 区块加 WebUI 行）

- [ ] **Step 1: 写 docs/webui.md**

```markdown
# weft WebUI 部署指南

设计定案：`docs/superpowers/specs/2026-09-06-weft-webui-design.md`。

## 安装与启动

```bash
pip install "weft[web]"
weft serve /srv/weft-projects --host 0.0.0.0 --port 8000
```

- `<projects_root>` 下的一级子目录中，凡含 `metadata/` 的即识别为 weft 论文项目，
  首页列出可选；演示前用 `weft init` 或拷贝 `examples/paper-demo` 准备多个示例项目。
- 浏览器打开 `http://<server>:8000`。

## LLM 配置

生成走 `weft.engine.make_client`：真实模式读取 config.json / .env / 环境变量
（SpecModule 回退链，`project_root` 取被打开的论文项目根）——服务器上在项目根或
进程环境配置 key。无 key 时勾选页面上的 **mock 模式**，用内置假客户端完整演示全流程。

## 安全提示

- 单人演示场景，未做认证：仅限内网/演示网络使用，勿暴露公网。
- 卡片/叙事编辑直接写盘（pydantic 校验 + LF 归一），建议项目置于 git 管理下以便回溯。
```

- [ ] **Step 2: roadmap.md M4 区块追加一行**

```markdown
- WebUI（比赛展示）：`weft serve` 服务器端 Web 应用 ✅（2026-09-06 设计定案，见 `docs/superpowers/specs/2026-09-06-weft-webui-design.md`）
```

（✅/🔨 状态按实际完成时点填写。）

- [ ] **Step 3: 全量回归 + 提交**

Run: `.venv/Scripts/python.exe -m pytest tests -q`
Expected: 304 passed（不变）

```bash
git add docs/webui.md docs/roadmap.md
git commit -m "docs: WebUI 部署指南与 roadmap 状态更新"
```

- [ ] **Step 4: 合回 main（AGENTS.md 约定）**

```bash
git checkout main && git merge --no-ff weft-webui -m "feat: WebUI——weft serve 服务器端 Web 应用（比赛展示）"
git worktree remove .worktrees/weft-webui && git branch -d weft-webui
```

---

## 设计决策（执行期定案回填区）

| # | 决策 | 理由 |
|---|---|---|
| D1 | 事件生命周期归 runner（`run_part_draft`）所有，worker 线程只捕获异常不再发事件 | 避免双发；web worker 与 CLI 输出共用同一路径 |
| D2 | 表单提交用普通 POST（303 重定向），htmx 仅用于 part 面板局部加载与生成控制台 | 交互面最小化，JS 失效时全流程仍可用 |
| D3 | SSE 事件走 `SimpleQueue` 缓冲，晚连接消费者可取全部历史 | 测试与线程时序无关；演示中浏览器晚连不丢事件 |
| D4 | 表单路由 `async def` + `await request.form()`（字段随卡种变化） | FastAPI 显式 Form 参数不适合动态字段集 |
| D5 | part 写回整体重序列化 frontmatter（YAML 排版可能与手写不同） | loader 用 pydantic 解析，语义等价；文件名 = id 不变 |
| D6 | 生成闸门错误返回 200 + 错误面板（非 409）；仅"重复触发"用 409 | 语义区分：闸门是业务拒绝，409 是并发冲突（设计 §6/§8） |
| D7 | discovery 每请求重扫根目录 | 项目小、单用户；保证编辑后立即可见，无缓存失效问题 |
| D8 | `node_review` 用 `part.nodes.index(node)` 定位 | part 内 node id 唯一（loader 校验），pydantic 按字段等值安全 |
| D9 | graph.json 顶层结构在 Task 4 执行时以实际输出核对一次，graph.html 只留一行适配 | 计划编写时示例项目无 graph.json 实物 |

## Self-Review 记录

- 规格覆盖：§0-§11 逐节对照——自查发现设计 §5 的 part 级 workflow 覆盖下拉最初遗漏，已在 Task 9 补齐（路由/模板/测试各一）；其余均在任务中有落点（诊断码不新增=无需任务；认证/删除/YAML 模式=非目标）。
- 占位符扫描：无 TBD/TODO；所有代码步骤含完整代码；curl 失败给出 cdnjs 备选与本机拷贝兜底。
- 类型一致性：`RunEvent/Run/RunManager`、`DraftEvent/PartDraftResult`、`FieldSpec/FIELD_SPECS`、`ProjectEntry`、`card_relpath/save_card/create_card/next_card_id/save_part`、`run_part_draft` 签名跨任务核对一致；自查修正三处回显值构造 bug（multiselect/单行 uses），统一收敛到 `form_to_values` 与 node POST 手工构造。
- 测试计数：T9 实际 5 个（含 workflow 覆盖），总数 46 → 全量预期 306。
