# weft 语义可见性实施计划（编号 → 内容/语义的展示层翻译）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `weft review`/graph 产物/WebUI 在展示编号之处就近显示语义摘要，并提供 `weft show <id>` 速览命令；WebUI 新建 data/fact/claim 卡解锁语义 id（与 CLI N4 对齐）。

**Architecture:** 新增纯函数模块 `src/weft/labels.py` 作为"key 字段 + 摘要"单一来源（web 的 `_KEY_FIELD` 收编于此）；graph 索引在构造点注入 `summary`；WebUI 以标签映射注入模板，checkbox/option 的 value 保持裸 id、仅展示文案附加摘要。schema、诊断码、表单解析逻辑零改动。

**Tech Stack:** Python 3 + pydantic（已有）、FastAPI + Jinja2（已有）、pytest + CliRunner/TestClient。

**基线：** 602 passed, 2 deselected。**完成预期：625 passed, 2 deselected**（新增 23 个测试）。

**工作目录：** worktree `.worktrees/semantic-visibility`（分支 `semantic-visibility`）。测试命令统一为：

```bash
.venv/Scripts/python.exe -m pytest tests -q        # 全量
.venv/Scripts/python.exe -m pytest tests/test_xxx.py -v   # 聚焦
```

---

## File Structure

| 文件 | 动作 | 职责 |
|---|---|---|
| `src/weft/labels.py` | 新建 | KEY_FIELD / cap / find_card / entity_digest / label_map / KIND_ATTRS |
| `src/weft/web/common.py` | 修改 | KIND_ATTRS 改从 labels 导入（消除双份定义） |
| `src/weft/cli.py` | 修改 | `_print_review` 附摘要列；新增 `weft show` |
| `src/weft/graphgen/index.py` | 修改 | `build_index` 实体加 `summary` 键 |
| `src/weft/graphgen/writer.py` | 修改 | orphans.md 行尾附摘要 |
| `src/weft/web/card_forms.py` | 修改 | 新增 `build_labels` |
| `src/weft/web/routes/cards.py` | 修改 | `_KEY_FIELD` 删除改导入；4 处表单上下文注入 `labels` |
| `src/weft/web/routes/parts.py` | 修改 | `_panel_ctx` 注入 `use_labels`；`_node_form_ctx` 注入 `entity_labels` |
| `src/weft/web/templates/card_form.html` | 修改 | auto id 去 readonly；multiselect/select 文案带摘要 |
| `src/weft/web/templates/part_panel.html` | 修改 | uses 单元格带摘要 |
| `src/weft/web/templates/node_form.html` | 修改 | 新增"实体速查"块 |
| `tests/test_labels.py` | 新建 | 8 个测试 |
| `tests/test_cli.py` | 修改 | +3 个 review 摘要测试 |
| `tests/test_graphgen.py` | 修改 | +2 个 summary 测试 |
| `tests/test_graphgen_writer.py` | 修改 | +1 个 orphans 摘要测试 |
| `tests/test_cli_show.py` | 新建 | 4 个 show 测试 |
| `tests/test_web_card_new.py` | 修改 | 1 个测试去 readonly 断言 +2 个新测试 |
| `tests/test_web_parts.py` / `tests/test_web_node_edit.py` | 修改 | 各 +1 |
| `tests/golden/graph.json`、`examples/paper-demo/generated/*` | 再生成 | graph.json 加 summary 键的预期演进 |

---

### Task 1: `labels.py` 语义标签单一来源

**Files:**
- Create: `src/weft/labels.py`
- Create: `tests/test_labels.py`
- Modify: `src/weft/web/common.py:14-16`（KIND_ATTRS 改导入）

- [ ] **Step 1: 写失败测试** `tests/test_labels.py`

```python
"""labels：key 字段映射、截断、实体摘要、批量标签（语义可见性 T1）。"""
from weft.labels import KIND_ATTRS, KEY_FIELD, cap, entity_digest, find_card, label_map
from weft.models.cards import (
    ClaimCard, DataCard, FactCard, MethodCard, NoteCard, ParamCard,
)
from weft.models.narrative import NarrativePart, Node, Use
from tests.helpers import build_project


def _project(**overrides):
    base = dict(
        data=[DataCard(id="data-01", status="approved",
                       description="60°C 速率-时间测量值")],
        facts=[FactCard(id="fact-01", data=["data-01"], statement="温度提高速率。",
                        status="approved")],
        claims=[ClaimCard(id="claim-01", claim_type="uncited",
                          statement="温度有正效应。", status="approved")],
        notes=[NoteCard(id="key2020", summary="文献概括。", status="approved")],
        methods=[MethodCard(id="qpcr", statement="qPCR 三步法。", protocol="p",
                            status="approved")],
        params=[ParamCard(id="qpcr-main", method="qpcr", status="approved")],
    )
    base.update(overrides)
    return build_project(**base)


def test_key_field_mapping():
    assert KEY_FIELD == {"data": "description", "fact": "statement",
                         "claim": "statement", "note": "summary",
                         "method": "statement", "param": "method"}


def test_cap_truncates_long_text():
    assert cap("x" * 41) == "x" * 40 + "…"
    assert cap("短文本") == "短文本"


def test_entity_digest_reads_key_field_per_kind():
    project = _project()
    assert entity_digest(project, "data-01") == "60°C 速率-时间测量值"
    assert entity_digest(project, "fact-01") == "温度提高速率。"
    assert entity_digest(project, "claim-01") == "温度有正效应。"
    assert entity_digest(project, "key2020") == "文献概括。"
    assert entity_digest(project, "qpcr") == "qPCR 三步法。"
    assert entity_digest(project, "qpcr-main") == "qpcr"   # param → method 引用 id


def test_entity_digest_empty_and_missing():
    project = _project(data=[DataCard(id="data-02", status="draft")])
    assert entity_digest(project, "data-02") == ""   # key 字段缺省为空
    assert entity_digest(project, "ghost") == ""     # 未命中实体


def test_entity_digest_custom_limit():
    project = _project()
    assert entity_digest(project, "fact-01", limit=3) == "温度提高" + "…"


def test_label_map_batch():
    labels = label_map(_project(), ["fact-01", "ghost", "data-01"])
    assert labels == {"fact-01": "温度提高速率。", "ghost": "",
                      "data-01": "60°C 速率-时间测量值"}


def test_find_card_across_kinds_and_unknown():
    project = _project()
    kind, card = find_card(project, "key2020")
    assert kind == "note" and card.summary == "文献概括。"
    assert find_card(project, "ghost") is None


def test_kind_attrs_match_project_tables():
    project = _project()
    for kind, attr in KIND_ATTRS.items():
        assert getattr(project, attr), kind
```

- [ ] **Step 2: 跑测试确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_labels.py -v
```
预期： collection ERROR（`ModuleNotFoundError: No module named 'weft.labels'`）。

- [ ] **Step 3: 实现** `src/weft/labels.py`

```python
"""实体语义标签（编号 → 内容摘要）：review / graph / show / WebUI 共用展示层。

纯数据层：只读 Project，不做 IO、不 import llm。key 字段映射沿用 WebUI 卡片
列表页既有约定（设计 D2）：param 的 key 字段是 method（引用 id），param 本就
slug 命名，不另造约定。
"""
from __future__ import annotations

from weft.store.project import Project

# kind → Project 属性名（models/cards.py 六类卡；web/common.py 同源导入）
KIND_ATTRS = {"data": "data_cards", "fact": "facts", "claim": "claims",
              "note": "notes", "method": "methods", "param": "params"}

KEY_FIELD = {"data": "description", "fact": "statement", "claim": "statement",
             "note": "summary", "method": "statement", "param": "method"}


def cap(text: str, limit: int = 40) -> str:
    """展示截断：超长加省略号（惯例同 digest._cap，上限按终端行宽取小）。"""
    return text if len(text) <= limit else text[:limit] + "…"


def find_card(project: Project, eid: str) -> tuple[str, object] | None:
    """按 id 找卡（六类全局命名空间）；未命中返回 None。"""
    for kind, attr in KIND_ATTRS.items():
        card = getattr(project, attr).get(eid)
        if card is not None:
            return kind, card
    return None


def entity_digest(project: Project, eid: str, limit: int = 40) -> str:
    """实体语义摘要（key 字段截断）；未命中或为空 → ""。"""
    found = find_card(project, eid)
    if found is None:
        return ""
    kind, card = found
    return cap(getattr(card, KEY_FIELD[kind], "") or "", limit)


def label_map(project: Project, ids) -> dict[str, str]:
    """批量 id → 摘要（模板一次注入）。"""
    return {eid: entity_digest(project, eid) for eid in ids}
```

- [ ] **Step 4: 跑测试确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_labels.py -v
```
预期： 8 passed。

- [ ] **Step 5: web/common.py 收编 KIND_ATTRS**

`src/weft/web/common.py`：删除第 14-16 行的字面定义（含注释行 `# kind → Project 属性名…`），在顶部 import 区（`from weft.web.discovery import ProjectEntry` 之前）加：

```python
from weft.labels import KIND_ATTRS
```

- [ ] **Step 6: 回归确认**

```bash
.venv/Scripts/python.exe -m pytest tests/test_web_cards.py tests/test_web_card_new.py tests/test_labels.py -q
```
预期： 全部 passed（web 行为不变）。

- [ ] **Step 7: 提交**

```bash
git add src/weft/labels.py tests/test_labels.py src/weft/web/common.py
git commit -m "feat: labels 语义标签单一来源——KEY_FIELD/cap/find_card/entity_digest/label_map，web KIND_ATTRS 收编"
```

---

### Task 2: `weft review` 输出附语义摘要列

**Files:**
- Modify: `src/weft/cli.py:89-111`（`_print_review`）
- Test: `tests/test_cli.py`（追加 3 个测试）

- [ ] **Step 1: 写失败测试**（追加到 `tests/test_cli.py` 末尾）

```python
def test_review_appends_card_digest(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "facts", "fact-02",
               {"id": "fact-02", "data": ["data-01"],
                "statement": "压力不影响产率。", "status": "draft"})
    result = runner.invoke(app, ["review", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "fact-02  metadata/facts/fact-02.md  ｜ 压力不影响产率。" in result.output


def test_review_appends_node_logic_digest(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "narrative" / "02-discussion", "part-01",
               {"id": "sec-02", "section": "Discussion",
                "nodes": [{"id": "para-02-01", "purpose": "interpret", "uses": [],
                           "logic": "把主结果与文献对照，指出一致性与差异",
                           "status": "draft"}]})
    result = runner.invoke(app, ["review", str(tmp_path)])
    assert result.exit_code == 0, result.output
    line = next(l for l in result.output.splitlines() if "sec-02/para-02-01" in l)
    assert "｜ 把主结果与文献对照" in line


def test_review_omits_empty_digest(tmp_path):
    # data-02 无 description → 不追加摘要段（行保持 path 结尾）
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "data", "data-02",
               {"id": "data-02", "refs": [], "status": "draft"})
    result = runner.invoke(app, ["review", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "data-02  metadata/data/data-02.md\n" in result.output
    assert "｜" not in result.output
```

- [ ] **Step 2: 跑测试确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_cli.py -v -k review
```
预期： 新增 3 个 FAIL（输出无 `｜` 段）。

- [ ] **Step 3: 实现**——`src/weft/cli.py` 改 `_print_review` 并加辅助函数：

```python
def _digest_suffix(digest: str) -> str:
    return f"  ｜ {digest}" if digest else ""


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
                typer.echo(f"  {label}  {cid}  {rel}"
                           f"{_digest_suffix(entity_digest(project, cid))}")
    if not entity_found:
        typer.echo("  （无）")
    typer.echo("待审阅叙事节点：")
    node_found = False
    for part in project.parts:
        for node in part.nodes:
            if node.status == "draft":
                node_found = True
                rel = project.part_paths[part.id].as_posix()
                typer.echo(f"  {part.id}/{node.id}  {rel}"
                           f"{_digest_suffix(cap(node.logic or '', 40))}")
    if not node_found:
        typer.echo("  （无）")
```

文件顶部 import 区加：`from weft.labels import cap, entity_digest`。

- [ ] **Step 4: 跑测试确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_cli.py -q
```
预期： 全部 passed（既有 review 子串断言不受影响）。

- [ ] **Step 5: 提交**

```bash
git add src/weft/cli.py tests/test_cli.py
git commit -m "feat: weft review 输出附语义摘要列（卡片 key 字段与节点 logic，空摘要省略）"
```

---

### Task 3: graph 产物带语义（graph.json `summary` + orphans.md 摘要 + 黄金再生成）

**Files:**
- Modify: `src/weft/graphgen/index.py:42-44`（实体构造加 summary）
- Modify: `src/weft/graphgen/writer.py:36-49`（orphans 行尾摘要）
- Test: `tests/test_graphgen.py`、`tests/test_graphgen_writer.py`
- 再生成: `tests/golden/graph.json`、`examples/paper-demo/generated/*`

- [ ] **Step 1: 写失败测试**——`tests/test_graphgen.py` 追加：

```python
def test_index_entities_carry_summary():
    project = _project(
        data=[DataCard(id="data-01", status="approved", description="测量值")],
        facts=[FactCard(id="fact-01", data=["data-01"], statement="温度提高速率。",
                        status="approved")],
    )
    entities = build_index(project)["entities"]
    assert entities["data-01"]["summary"] == "测量值"
    assert entities["fact-01"]["summary"] == "温度提高速率。"


def test_index_summary_empty_when_key_field_missing():
    project = _project()   # DataCard 无 description → summary 为 ""
    assert build_index(project)["entities"]["data-01"]["summary"] == ""
```

`tests/test_graphgen_writer.py` 追加：

```python
def test_orphans_md_appends_digest(tmp_path):
    project = _project(root=tmp_path, data=[
        DataCard(id="data-01", status="approved"),
        DataCard(id="data-02", status="draft", description="备选测量"),
    ])
    write_outputs(project, tmp_path / "generated")
    text = (tmp_path / "generated" / "orphans.md").read_text(encoding="utf-8")
    assert "data-02（data）— metadata/data-02.md：备选测量" in text
```

（空摘要保持旧行尾格式已由既有 `test_orphans_md_lists_paths` 覆盖——data-02 无描述。）

- [ ] **Step 2: 跑测试确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_graphgen.py tests/test_graphgen_writer.py -q
```
预期： 新增 3 个 FAIL（KeyError: 'summary' / 断言不含摘要）。

- [ ] **Step 3: 实现**——`index.py` 实体构造（原 42-44 行）改为：

```python
        for cid, card in cards.items():
            entities[cid] = {"kind": kind, "status": card.status,
                             "summary": getattr(card, KEY_FIELD[kind], "") or "",
                             "referenced_by": {k: [] for k in _REVERSE_KEYS}}
```

import 区加：`from weft.labels import KEY_FIELD`。

`writer.py` `_orphans_md` 的行构造（原 46-48 行）改为：

```python
    for group, ids in orphans.items():
        for eid in ids:
            path = project.card_paths.get(eid, Path("?")).as_posix()
            digest = entity_digest(project, eid)
            lines.append(f"- {eid}（{titles[group]}）— {path}"
                         + (f"：{digest}" if digest else ""))
```

import 区加：`from weft.labels import entity_digest`。

- [ ] **Step 4: 跑测试确认通过（除黄金测试外）**

```bash
.venv/Scripts/python.exe -m pytest tests/test_graphgen.py tests/test_graphgen_writer.py -q
```
预期： 全部 passed。

- [ ] **Step 5: 黄金文件与样例产物再生成**

```bash
.venv/Scripts/weft.exe graph examples/paper-demo
cp examples/paper-demo/generated/graph.json tests/golden/graph.json
.venv/Scripts/python.exe -m pytest tests/test_example_project.py -q
```
预期： 黄金比对通过；`git status` 可见 `tests/golden/graph.json`、`examples/paper-demo/generated/graph.json`、`examples/paper-demo/generated/orphans.md` 变更（used-metadata.json 应无变化，若有变更需停下核查）。

- [ ] **Step 6: 提交**

```bash
git add src/weft/graphgen/index.py src/weft/graphgen/writer.py tests/test_graphgen.py tests/test_graphgen_writer.py tests/golden/graph.json examples/paper-demo/generated/
git commit -m "feat: graph.json 实体带 summary 全文、orphans.md 行尾附语义摘要；黄金与样例产物再生成"
```

---

### Task 4: 新命令 `weft show <card_id>`

**Files:**
- Modify: `src/weft/cli.py`（import 区 + `review` 命令后新增 `show`；模块 docstring 命令清单加 `show`）
- Create: `tests/test_cli_show.py`

- [ ] **Step 1: 写失败测试** `tests/test_cli_show.py`

```python
"""weft show：卡片速览（语义字段全文 + 被引用关系）。"""
from typer.testing import CliRunner

from weft.cli import app
from tests.helpers import make_minimal_project, write_card

runner = CliRunner()


def test_show_prints_card_overview(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["show", "fact-01", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "# fact-01（fact 卡，approved）— metadata/facts/fact-01.md" in result.output
    assert "statement: 温度提高速率。" in result.output
    assert "data: data-01" in result.output
    assert "supports: claim-01" in result.output
    assert "被引用:" in result.output
    assert "nodes: para-01-01" in result.output


def test_show_without_backrefs(tmp_path):
    make_minimal_project(tmp_path)
    write_card(tmp_path / "metadata" / "data", "data-02",
               {"id": "data-02", "refs": [], "status": "draft"})
    result = runner.invoke(app, ["show", "data-02", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "被引用: （无）" in result.output


def test_show_unknown_id_exits_1(tmp_path):
    make_minimal_project(tmp_path)
    result = runner.invoke(app, ["show", "ghost", str(tmp_path)])
    assert result.exit_code == 1
    assert "ERROR 项目中不存在实体：ghost" in result.output


def test_show_reports_load_errors(tmp_path):
    result = runner.invoke(app, ["show", "x", str(tmp_path)])
    assert result.exit_code == 1
    assert "E-NOT-A-PROJECT" in result.output
```

- [ ] **Step 2: 跑测试确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_cli_show.py -v
```
预期： 4 个 FAIL（`show` 命令不存在）。

- [ ] **Step 3: 实现**——`src/weft/cli.py`：

模块 docstring（第 1 行）命令清单中 `review` 后插入 `show`。import 区加 `import json`（若无）与 `from weft.graphgen.index import build_index`、`from weft.labels import find_card`。`review` 命令之后新增：

```python
@app.command()
def show(
    card_id: str = typer.Argument(..., help="卡片 id（六类通用，全局命名空间）"),
    project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录"),
) -> None:
    """按 id 打印卡片速览：key 字段全文 + 引用关系 + 被引用（编号→语义→关系）。"""
    project, load_diags = load_project(project_dir)
    if any(d.is_error for d in load_diags):
        _print_diagnostics(load_diags)
        raise typer.Exit(code=1)
    found = find_card(project, card_id)
    if found is None:
        # 无码 ERROR 行：与 weft graph 的 OSError 先例一致，不新增诊断码（D7）
        typer.echo(f"ERROR 项目中不存在实体：{card_id}")
        raise typer.Exit(code=1)
    kind, card = found
    rel = project.card_paths[card_id].as_posix()
    typer.echo(f"# {card_id}（{kind} 卡，{card.status}）— {rel}")
    for name, value in card.model_dump().items():
        if name in ("id", "status") or (name == "comment" and not value):
            continue
        typer.echo(_format_field(name, value))
    refs = build_index(project)["entities"][card_id]["referenced_by"]
    back = [(group, ids) for group, ids in refs.items() if ids]
    if not back:
        typer.echo("被引用: （无）")
        return
    typer.echo("被引用:")
    for group, ids in back:
        typer.echo(f"  {group}: {', '.join(ids)}")


def _format_field(name: str, value) -> str:
    if value is None:
        value = "（无）"
    elif isinstance(value, list):
        value = ", ".join(str(v) for v in value) or "（无）"
    elif isinstance(value, dict):
        value = json.dumps(value, ensure_ascii=False) or "（无）"
    return f"{name}: {value}"
```

- [ ] **Step 4: 跑测试确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_cli_show.py tests/test_cli.py -q
```
预期： 全部 passed。

- [ ] **Step 5: 提交**

```bash
git add src/weft/cli.py tests/test_cli_show.py
git commit -m "feat: weft show 命令——按 id 打印卡片速览（全文语义字段 + 被引用关系，无码 ERROR 退出 1）"
```

---

### Task 5: WebUI 新建卡 id 解锁只读（data/fact/claim）

**Files:**
- Modify: `src/weft/web/templates/card_form.html:16`（去 readonly）
- Test: `tests/test_web_card_new.py`（改 1 + 新增 1）

- [ ] **Step 1: 改测试**——`tests/test_web_card_new.py`：

`test_new_form_prefills_next_id` 的断言 `'value="fact-02"' in resp.text and 'readonly' in resp.text` 改为：

```python
    assert 'value="fact-02"' in resp.text and 'readonly' not in resp.text
```

追加测试：

```python
def test_create_custom_semantic_id(tmp_path):
    client, root = make_client(tmp_path)
    resp = client.post("/p/demo/cards/fact/new", data={
        "id": "rate-jumps-above-60c", "data": ["data-01"],
        "statement": "语义 id 可直接落盘。", "supports": [],
        "status": "draft", "comment": ""}, follow_redirects=False)
    assert resp.status_code == 303
    assert (root / "demo" / "metadata" / "facts" / "rate-jumps-above-60c.md").exists()
```

- [ ] **Step 2: 跑测试确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_web_card_new.py -v
```
预期： `test_new_form_prefills_next_id` FAIL（readonly 仍在）；新测试 PASS（服务端守卫本就放行语义 id——这正是"仅 UI 层锁"的证据）。

- [ ] **Step 3: 实现**——`card_form.html` 第 16 行：

```html
    <input name="id" value="{{ prefilled_id }}" placeholder="留空随机？否——预填自动编号，可改为语义 id（全局唯一）">
```

改为（保留预填、去掉 readonly，placeholder 精简）：

```html
    <input name="id" value="{{ prefilled_id }}" placeholder="预填自动编号，可改为语义 id（全局唯一）">
```

- [ ] **Step 4: 跑测试确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_web_card_new.py -q
```
预期： 全部 passed。

- [ ] **Step 5: 提交**

```bash
git add src/weft/web/templates/card_form.html tests/test_web_card_new.py
git commit -m "feat: WebUI 新建 data/fact/claim 卡解锁 id 只读（保留自动编号预填，与 CLI N4 语义命名对齐）"
```

---

### Task 6: WebUI 摘要注入（引用控件 / uses 单元格 / 实体速查）

**Files:**
- Modify: `src/weft/web/card_forms.py`（新增 `build_labels`）
- Modify: `src/weft/web/routes/cards.py`（4 处表单上下文加 `labels`）
- Modify: `src/weft/web/routes/parts.py`（`_panel_ctx` 加 `use_labels`；`_node_form_ctx` 加 `entity_labels`）
- Modify: `src/weft/web/templates/card_form.html`、`part_panel.html`、`node_form.html`
- Test: `tests/test_web_card_new.py`（+2）、`tests/test_web_parts.py`（+1）、`tests/test_web_node_edit.py`（+1）

- [ ] **Step 1: 写失败测试**

`tests/test_web_card_new.py` 追加：

```python
def test_multiselect_options_show_digest(tmp_path):
    client, root = make_client(tmp_path)
    from tests.helpers import write_card
    write_card(root / "demo" / "metadata" / "data", "data-02",
               {"id": "data-02", "refs": [], "description": "备用测量数据",
                "status": "approved"})
    resp = client.get("/p/demo/cards/fact/new")
    assert resp.status_code == 200
    assert "data-02 · 备用测量数据" in resp.text
    assert 'value="data-02"' in resp.text          # 提交值仍是裸 id


def test_param_method_select_shows_digest(tmp_path):
    client, root = make_client(tmp_path)
    from tests.helpers import write_card
    write_card(root / "demo" / "metadata" / "methods", "qpcr",
               {"id": "qpcr", "statement": "qPCR 三步法。", "protocol": "p",
                "status": "approved"})
    resp = client.get("/p/demo/cards/param/new")
    assert resp.status_code == 200
    assert "qpcr · qPCR 三步法。" in resp.text
```

`tests/test_web_parts.py` 追加（沿用该文件既有的取面板写法；若其以 `client.get("/p/demo/parts")` 取面板，则断言作用于响应全文）：

```python
def test_part_panel_uses_show_digest(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/parts")
    assert resp.status_code == 200
    # fact-01（statement 温度提高速率。）被 para-01-01 使用
    assert "fact-01(evidence) · 温度提高速率。" in resp.text
```

`tests/test_web_node_edit.py` 追加：

```python
def test_node_edit_shows_entity_quicklist(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/parts/sec-01/nodes/para-01-01")
    assert resp.status_code == 200
    assert "实体速查" in resp.text
    assert "fact-01 · 温度提高速率。" in resp.text
```

（若 `test_web_parts.py`/`test_web_node_edit.py` 的既有 URL/断言风格不同，以该文件现状为准调整访问路径，断言目标不变。）

- [ ] **Step 2: 跑测试确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_web_card_new.py tests/test_web_parts.py tests/test_web_node_edit.py -v
```
预期： 新增 4 个 FAIL。

- [ ] **Step 3: 实现**

`card_forms.py` 末尾追加（import 区加 `from weft.labels import cap, label_map`）：

```python
def build_labels(project: Project) -> dict[str, dict[str, str]]:
    """引用控件的标签映射：choices_key → {id: 摘要}（展示附加，提交值不变）。"""
    return {
        "figure_refs": {k: cap(v.caption, 40) for k, v in project.figures.items()},
        "data_ids": label_map(project, sorted(project.data_cards)),
        "claim_ids": label_map(project, sorted(project.claims)),
        "bib_keys": label_map(project, sorted(project.bib_keys)),
        "method_ids": label_map(project, sorted(project.methods)),
        "claim_type": {},
    }
```

`routes/cards.py`：删除 `_KEY_FIELD` 定义（38-39 行），`_table` 内 `getattr(card, _KEY_FIELD[kind], "")` 改为 `getattr(card, KEY_FIELD[kind], "")` 并从 `weft.labels` 导入 `KEY_FIELD`；四处模板上下文（`card_new_get`、`card_new_post.rerender`、`card_edit_get`、`card_edit_post.rerender`）在 `"choices": build_choices(...)` 后统一加：

```python
             "labels": build_labels(entry.project),
```

（import 行加 `build_labels`。）

`routes/parts.py`：`_panel_ctx` 返回 dict 增加：

```python
            "use_labels": label_map(
                project, [u.id for n in part.nodes for u in n.uses]),
```

`_node_form_ctx`（第 117-122 行）返回 dict 中 `"entity_ids"` 行后加：

```python
            "entity_labels": label_map(project, sorted(_known_ids(project))),
```

import 行加 `from weft.labels import label_map`。

`templates/card_form.html`：multiselect 分支改为：

```html
  {% elif spec.widget == "multiselect" %}
  <div class="multi">
    {% for c in choices[spec.choices] %}
    {% set lbl = labels[spec.choices].get(c, '') %}
    <label class="check"><input type="checkbox" name="{{ spec.name }}" value="{{ c }}"
      {% if c in values.get(spec.name, []) %}checked{% endif %}> {{ c }}{% if lbl %} · {{ lbl }}{% endif %}</label>
    {% endfor %}
  </div>
```

select 分支的 `<option>` 文案同理：

```html
    <option value="{{ c }}" {% if values.get(spec.name) == c %}selected{% endif %}>{{ c }}{% if labels[spec.choices].get(c, '') %} · {{ labels[spec.choices][c] }}{% endif %}</option>
```

`templates/part_panel.html` 第 26 行 uses 单元格改为：

```html
          <td>{% for u in node.uses %}{{ u.id }}({{ u.role }}){% if use_labels.get(u.id) %} · {{ use_labels[u.id] }}{% endif %} {% endfor %}</td>
```

`templates/node_form.html`：`entity-ids` datalist 之后（第 33 行后）加"实体速查"块：

```html
  <div class="label">实体速查（id · 内容摘要）</div>
  <ul class="entity-ref">
    {% for eid in entity_ids %}
    <li><code>{{ eid }}</code>{% if entity_labels.get(eid) %} · {{ entity_labels[eid] }}{% endif %}</li>
    {% endfor %}
  </ul>
```

- [ ] **Step 4: 跑测试确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_web_card_new.py tests/test_web_parts.py tests/test_web_node_edit.py tests/test_web_cards.py tests/test_web_misc.py -q
```
预期： 全部 passed（含编辑表单复用同模板的回归）。

- [ ] **Step 5: 提交**

```bash
git add src/weft/web/card_forms.py src/weft/web/routes/cards.py src/weft/web/routes/parts.py src/weft/web/templates/card_form.html src/weft/web/templates/part_panel.html src/weft/web/templates/node_form.html tests/test_web_card_new.py tests/test_web_parts.py tests/test_web_node_edit.py
git commit -m "feat: WebUI 引用控件/uses 单元格/实体速查显示「id · 语义摘要」（checkbox value 不变）"
```

---

### Task 7: 文档同步 + 全量验证

**Files:**
- Modify: `docs/manual.md`（命令参考加 `weft show`；第 5 节前加语义命名约定小节；目录同步）
- Modify: `docs/roadmap.md`（M4 加一行 ✅）
- Modify: `AGENTS.md`（CLI 命令清单加 `show`）

- [ ] **Step 1: manual.md**

§7 命令参考在 `### weft review` 小节后插入：

```markdown
### weft show

```bash
weft show <card_id> [project_dir]
```

按 id 打印卡片速览（六类通用）：头行（id / 卡种 / status / 路径）、全部字段全文
（列表逗号连接、映射按 JSON）、被引用关系（哪些 fact/claim/param/节点引用了它）。
未知 id 打印 `ERROR 项目中不存在实体：<id>` 并退出 1。适合从 review/诊断里的编号
就地查内容，不必开文件。
```

§5 开头（"## 5. 元数据卡片"之后）加约定段：

```markdown
> **命名约定**：`weft new card` 的 id 显式必填、从不自动编号——新建 data/fact/claim
> 卡**优先用语义 id**（如 `rate-jumps-above-60c`），让 review/诊断/引用处的编号自带
> 语义；自动编号（data-01 式）仅作缺省回退（WebUI 新建表单会预填，可改）。id 即文件
> 名，全卡种全局唯一；落盘后改名需手工同步所有引用点，故不做 rename 工具。
```

目录（§9 若列有命令条目）同步补 `weft show`。

- [ ] **Step 2: roadmap.md** M4 列表（`weft new` 行之后）加：

```markdown
- 语义可见性 ✅（2026-10-12）：`weft review` 摘要列、graph.json `summary`、orphans 摘要、`weft show <id>` 速览、WebUI 引用控件/uses/实体速查带「id · 摘要」、WebUI 新建卡 id 解锁语义命名。设计见 `docs/superpowers/specs/2026-10-12-weft-semantic-visibility-design.md`。
```

- [ ] **Step 3: AGENTS.md** "常用命令"节 CLI 命令清单 `review` 后加 `show`。

- [ ] **Step 4: 全量测试 + 计数回填**

```bash
.venv/Scripts/python.exe -m pytest tests -q
```
预期： **625 passed, 2 deselected**（602 + 23：labels 8、review 3、graph 3、show 4、web 解锁 1、web 摘要 4）。把实际数字回填本计划头部与本行；若有偏差，先查明原因再继续。

- [ ] **Step 5: 提交**

```bash
git add docs/manual.md docs/roadmap.md AGENTS.md docs/superpowers/plans/2026-10-12-weft-semantic-visibility.md
git commit -m "docs: 语义可见性落地——manual 命令参考与命名约定、roadmap M4、AGENTS 命令清单、计划计数回填"
```

---

## 合并与收尾（主会话执行，不属计划任务）

1. 全量绿后在 worktree 提交完毕，回主仓库：`git merge semantic-visibility`（main，--no-ff 或快进均可，遵循仓库习惯）；
2. 删除：`git worktree remove .worktrees/semantic-visibility` + `git branch -d semantic-visibility`；
3. `git push`（main 跟踪 origin/main）；
4. 主仓库 `.venv` 若 editable 指向未变则无需重装（本 worktree 用独立 venv，不影响主仓）。

## 设计偏离回填

执行期如偏离设计定案（D1–D10），须回填至本节并注明决策编号与理由。
