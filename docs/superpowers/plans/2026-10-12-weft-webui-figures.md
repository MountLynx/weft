# WebUI figures.yaml 管理 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** WebUI 新增"图表"页——`metadata/figures.yaml` 图注注册表的列表查看与图注条目新增/编辑/删除，编辑逻辑落 src 层纯函数引擎。

**Architecture:** 引擎 `src/weft/figures_edit.py` 自读自写磁盘（fail-closed：解析失败拒绝一切写、删除被引用键阻断），WebUI 路由 `src/weft/web/routes/figures.py` 薄封装，错误经 `FiguresEditError` 回显表单/列表 banner。模板两个（列表 + 共用表单），子导航加"图表"。

**Tech Stack:** FastAPI + Jinja2（服务端渲染，无新 JS）、pyyaml、pydantic（复用 `FigureEntry`）、pytest + fastapi.testclient。

**设计定案：** `docs/superpowers/specs/2026-10-12-weft-webui-figures-design.md`（决策 F1–F12；本计划引用 F 编号不重复论证）。

**执行约定：**
- 功能开发用 git worktree（`.worktrees/`，见 superpowers:using-git-worktrees），完成后合回 main。
- 全量测试命令：`.venv/Scripts/python.exe -m pytest tests -q`；当前基线 **651 passed, 2 deselected**。
- 本计划新增测试 **39 个**（引擎 27 + WebUI 12），预期全量 **690 passed, 2 deselected**；执行完回填实际数字到"验收与计数"一节。

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `src/weft/figures_edit.py` | 新建 | figures.yaml 编辑引擎：load/编号/键名校验/增改删/确定性重写（纯函数，不 import web/fastapi） |
| `src/weft/web/routes/figures.py` | 新建 | 路由：列表、新增、编辑、删除；表单解析与 banner 回显 |
| `src/weft/web/templates/figures.html` | 新建 | 列表页模板 |
| `src/weft/web/templates/figure_form.html` | 新建 | 新增/编辑共用表单模板 |
| `src/weft/web/templates/base.html` | 修改 | 子导航加 `("figures", "图表", true)` |
| `src/weft/web/routes/__init__.py` | 修改 | `register_all` 注册 figures 路由 |
| `tests/test_figures_edit.py` | 新建 | 引擎单测（27 个） |
| `tests/test_web_figures.py` | 新建 | 路由测试（12 个） |
| `tests/test_web_subnav.py` | 修改 | slug 元组与活动态用例补 figures |
| `AGENTS.md` | 修改 | 红线 5 码表增补 E-FIG-* |
| `docs/roadmap.md` | 修改 | M4 加一行 |

---

### Task 1: 引擎——FiguresEditError + load_for_edit（E-FIG-LOAD）

**Files:**
- Create: `src/weft/figures_edit.py`
- Test: `tests/test_figures_edit.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_figures_edit.py`：

```python
"""figures_edit 引擎单测（webui figures 设计定案，决策 F1–F12）。"""
import pytest

from weft.figures_edit import (
    FiguresEditError,
    load_for_edit,
)


def _write_yaml(root, text: str) -> None:
    (root / "metadata").mkdir(parents=True, exist_ok=True)
    (root / "metadata" / "figures.yaml").write_text(text, encoding="utf-8")


def test_load_missing_returns_empty(tmp_path):
    assert load_for_edit(tmp_path) == {}


def test_load_parses_in_key_order(tmp_path):
    _write_yaml(tmp_path,
                "fig-02:\n  caption: 第二张\n"
                "fig-01:\n  caption: 第一张\n  subfigs:\n    a: 左\n")
    entries = load_for_edit(tmp_path)
    assert list(entries) == ["fig-02", "fig-01"]
    assert entries["fig-01"].caption == "第一张"
    assert entries["fig-01"].subfigs == {"a": "左"}


def test_load_rejects_top_level_list(tmp_path):
    _write_yaml(tmp_path, "- a\n- b\n")
    with pytest.raises(FiguresEditError) as excinfo:
        load_for_edit(tmp_path)
    assert excinfo.value.code == "E-FIG-LOAD"


def test_load_rejects_bad_entry(tmp_path):
    _write_yaml(tmp_path, "fig-01:\n  caption: 1\n  subfigs: not-a-map\n")
    with pytest.raises(FiguresEditError) as excinfo:
        load_for_edit(tmp_path)
    assert excinfo.value.code == "E-FIG-LOAD"
    assert "fig-01" in excinfo.value.message


def test_load_rejects_malformed_yaml(tmp_path):
    _write_yaml(tmp_path, "fig-01: [unclosed\n")
    with pytest.raises(FiguresEditError) as excinfo:
        load_for_edit(tmp_path)
    assert excinfo.value.code == "E-FIG-LOAD"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_figures_edit.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'weft.figures_edit'`）

- [ ] **Step 3: 最小实现**

创建 `src/weft/figures_edit.py`：

```python
"""figures.yaml 编辑引擎（webui figures 设计定案）：纯函数，WebUI 路由薄封装。

figures.yaml 是人工直接维护的图注注册表；本引擎自读自写磁盘（F12）。
注册表有任何解析错误即拒绝一切写操作（E-FIG-LOAD，F3）——整文件重写
不保留注释、丢弃未知键（F2），若带病重写会静默吞掉 loader 宽松跳过的坏条目。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from pydantic import ValidationError

from weft.models.figures import FigureEntry

FIGURES_REL = "metadata/figures.yaml"

_PLAIN_YAML = re.compile(r"[\w][\w \-]*", re.UNICODE)
_UNSAFE_COMPONENT = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


class FiguresEditError(Exception):
    """figures.yaml 编辑失败（E-FIG-*）；WebUI banner 直接展示 code+message。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code} {message}")


def figures_path(root: Path) -> Path:
    return root / "metadata" / "figures.yaml"


def load_for_edit(root: Path) -> dict[str, FigureEntry]:
    """读 figures.yaml 为键序映射；文件缺失 = 空映射；任何解析失败 → E-FIG-LOAD。"""
    path = figures_path(root)
    if not path.exists():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise FiguresEditError("E-FIG-LOAD",
                               f"figures.yaml 不是合法 YAML：{exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise FiguresEditError("E-FIG-LOAD", "figures.yaml 顶层必须是映射")
    entries: dict[str, FigureEntry] = {}
    for key, value in raw.items():
        try:
            entries[str(key)] = FigureEntry.model_validate(value or {})
        except ValidationError as exc:
            raise FiguresEditError(
                "E-FIG-LOAD",
                f"图注条目解析失败（{key}）：{exc.errors()[0]['msg']}") from exc
    return entries
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_figures_edit.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add src/weft/figures_edit.py tests/test_figures_edit.py
git commit -m "feat: figures_edit 引擎 load 段——解析失败 E-FIG-LOAD fail-closed"
```

---

### Task 2: 引擎——键名校验 + next_figure_key + add_entry

**Files:**
- Modify: `src/weft/figures_edit.py`（文件末尾追加）
- Test: `tests/test_figures_edit.py`（追加）

- [ ] **Step 1: 写失败测试**

在 `tests/test_figures_edit.py` 追加（import 区补 `add_entry, ensure_figure_key, next_figure_key` 与 `from weft.scaffold import NewNameError, _ensure_component`）：

```python
VALID_KEYS = ["fig-01", "tbl-1", "x", "a-b-c", "中文图", "fig_01.v2"]
INVALID_KEYS = ["", "  x", "x  ", ".", "..", "a/b", "a\\b", "a:b", 'a"b',
                "a<b", "a|b", "a?b", "a*b", "a\nb", ".hidden", "x."]


def test_next_figure_key_from_existing():
    entries = {"fig-01": FigureEntry(), "fig-04": FigureEntry()}
    assert next_figure_key(entries, "fig-") == "fig-05"


def test_next_figure_key_ignores_suffix_and_other_prefix():
    entries = {"fig-01a": FigureEntry(), "tbl-02": FigureEntry(),
               "fig-intro": FigureEntry()}
    assert next_figure_key(entries, "fig-") == "fig-01"
    assert next_figure_key({}, "tbl-") == "tbl-01"


@pytest.mark.parametrize("value", VALID_KEYS)
def test_ensure_figure_key_accepts_safe(value):
    ensure_figure_key(value)  # 不抛即通过


@pytest.mark.parametrize("value", INVALID_KEYS)
def test_ensure_figure_key_rejects_unsafe(value):
    with pytest.raises(FiguresEditError) as excinfo:
        ensure_figure_key(value)
    assert excinfo.value.code == "E-FIG-NAME"


@pytest.mark.parametrize("value", VALID_KEYS + INVALID_KEYS)
def test_ensure_figure_key_matches_scaffold_rule(value):
    """F4：与 weft new 的 _ensure_component（N9）规则一致，样本集守卫。"""
    try:
        ensure_figure_key(value)
        ours = True
    except FiguresEditError:
        ours = False
    try:
        _ensure_component("key", value)
        theirs = True
    except NewNameError:
        theirs = False
    assert ours == theirs


def test_add_entry_explicit():
    entries = {"fig-01": FigureEntry(caption="旧")}
    out = add_entry(entries, "fig-02", "新图", {"a": "左"}, "fig-")
    assert list(out) == ["fig-01", "fig-02"]
    assert out["fig-02"].caption == "新图"
    assert out["fig-01"].caption == "旧"          # 原映射不被就地修改


def test_add_entry_auto_number():
    entries = {"fig-01": FigureEntry()}
    out = add_entry(entries, "", "自动", {}, "fig-")
    assert "fig-02" in out


def test_add_entry_collision():
    with pytest.raises(FiguresEditError) as excinfo:
        add_entry({"fig-01": FigureEntry()}, "fig-01", "x", {}, "fig-")
    assert excinfo.value.code == "E-FIG-COLLISION"


def test_add_entry_appends_tail():
    """键序即 assemble 编号：新键必须排尾部（F5）。"""
    entries = {"fig-03": FigureEntry(), "fig-01": FigureEntry()}
    out = add_entry(entries, "fig-09", "x", {}, "fig-")
    assert list(out) == ["fig-03", "fig-01", "fig-09"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_figures_edit.py -v`
Expected: 新增用例 FAIL（ImportError: cannot import name 'add_entry'）

- [ ] **Step 3: 最小实现**

在 `src/weft/figures_edit.py` 末尾追加：

```python
def ensure_figure_key(key: str) -> None:
    """键名是图片文件名 stem（figures/{key}.png），安全成分规则同 weft new N9（F4）。"""
    if (not key or key.startswith(".") or key.endswith(".")
            or key != key.strip() or _UNSAFE_COMPONENT.search(key)):
        raise FiguresEditError("E-FIG-NAME", f"键名非法：{key!r}")


def next_figure_key(entries: dict[str, FigureEntry], prefix: str) -> str:
    """{prefix}{n:02d}：同前缀数字键取 max+1（同 weft new part 编号语义，F5）。"""
    pat = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    nums = [int(m.group(1)) for k in entries if (m := pat.match(k))]
    return f"{prefix}{max(nums, default=0) + 1:02d}"


def add_entry(entries: dict[str, FigureEntry], key: str, caption: str,
              subfigs: dict[str, str], prefix: str) -> dict[str, FigureEntry]:
    """新键追加尾部（键序即 assemble 编号，F5）；非法键名/冲突 fail-closed 零写入。"""
    if not key:
        key = next_figure_key(entries, prefix)
    ensure_figure_key(key)
    if key in entries:
        raise FiguresEditError("E-FIG-COLLISION", f"键已存在：{key}")
    return {**entries, key: FigureEntry(caption=caption, subfigs=subfigs)}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_figures_edit.py -v`
Expected: 14 passed

- [ ] **Step 5: 提交**

```bash
git add src/weft/figures_edit.py tests/test_figures_edit.py
git commit -m "feat: figures_edit 增补段——键名安全校验、自动编号、add_entry"
```

---

### Task 3: 引擎——parse_subfigs + update_entry + remove_entry

**Files:**
- Modify: `src/weft/figures_edit.py`（文件末尾追加）
- Test: `tests/test_figures_edit.py`（追加）

- [ ] **Step 1: 写失败测试**

在 `tests/test_figures_edit.py` 追加（import 区补 `parse_subfigs, remove_entry, update_entry`）：

```python
def test_parse_subfigs_basic():
    assert parse_subfigs("a: 60°C\nb: 温度: 95% CI\n\n") == \
        {"a": "60°C", "b": "温度: 95% CI"}      # 首个冒号切分，空行跳过


@pytest.mark.parametrize("text", ["没有冒号", ": 说明", "a b: 说明", "   : x"])
def test_parse_subfigs_invalid(text):
    with pytest.raises(FiguresEditError) as excinfo:
        parse_subfigs(text)
    assert excinfo.value.code == "E-FIG-VALUE"


def test_update_entry_keeps_order():
    entries = {"fig-01": FigureEntry(caption="旧"), "fig-02": FigureEntry()}
    out = update_entry(entries, "fig-01", "新", {"b": "右"})
    assert list(out) == ["fig-01", "fig-02"]
    assert out["fig-01"].caption == "新"
    assert out["fig-01"].subfigs == {"b": "右"}


def test_update_entry_missing():
    with pytest.raises(FiguresEditError) as excinfo:
        update_entry({}, "fig-01", "x", {})
    assert excinfo.value.code == "E-FIG-COLLISION"


def test_remove_entry_ok():
    entries = {"fig-01": FigureEntry(), "fig-02": FigureEntry()}
    out = remove_entry(entries, "fig-01", {"data-01": {"fig-02"}})
    assert list(out) == ["fig-02"]


def test_remove_entry_blocked_direct():
    entries = {"fig-01": FigureEntry()}
    with pytest.raises(FiguresEditError) as excinfo:
        remove_entry(entries, "fig-01", {"data-01": {"fig-01"}})
    assert excinfo.value.code == "E-FIG-IN-USE"
    assert "data-01" in excinfo.value.message


def test_remove_entry_blocked_via_subfig():
    entries = {"fig-01": FigureEntry(subfigs={"a": "左"})}
    with pytest.raises(FiguresEditError) as excinfo:
        remove_entry(entries, "fig-01", {"data-01": {"fig-01a"}})
    assert excinfo.value.code == "E-FIG-IN-USE"


def test_remove_entry_blocked_rejected_card():
    """F6：rejected 卡也算引用——可能被重新批准，删除从严。"""
    entries = {"fig-01": FigureEntry()}
    with pytest.raises(FiguresEditError) as excinfo:
        remove_entry(entries, "fig-01", {"data-09": {"fig-01"}})
    assert excinfo.value.code == "E-FIG-IN-USE"


def test_remove_entry_missing():
    with pytest.raises(FiguresEditError) as excinfo:
        remove_entry({}, "fig-01", {})
    assert excinfo.value.code == "E-FIG-COLLISION"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_figures_edit.py -v`
Expected: 新增用例 FAIL（ImportError: cannot import name 'parse_subfigs'）

- [ ] **Step 3: 最小实现**

在 `src/weft/figures_edit.py` 末尾追加：

```python
def parse_subfigs(text: str) -> dict[str, str]:
    """textarea 逐行 `子图号: 说明`，首个冒号切分、空行跳过（F7）；非法 → E-FIG-VALUE。"""
    subfigs: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        sub, sep, caption = line.partition(":")
        sub = sub.strip()
        if not sep or not sub or re.search(r"\s", sub):
            raise FiguresEditError("E-FIG-VALUE", f"子图行格式非法：{line!r}")
        subfigs[sub] = caption.strip()
    return subfigs


def update_entry(entries: dict[str, FigureEntry], key: str, caption: str,
                 subfigs: dict[str, str]) -> dict[str, FigureEntry]:
    """键不可变（F8），只替换 caption/subfigs；键序保持。"""
    if key not in entries:
        raise FiguresEditError("E-FIG-COLLISION", f"键不存在：{key}")
    return {k: (FigureEntry(caption=caption, subfigs=subfigs)
                if k == key else v)
            for k, v in entries.items()}


def remove_entry(entries: dict[str, FigureEntry], key: str,
                 references: dict[str, set[str]]) -> dict[str, FigureEntry]:
    """被任何 data 卡（含 rejected，F6）refs 命中 `{key} ∪ {key+sub}` 即阻断。"""
    if key not in entries:
        raise FiguresEditError("E-FIG-COLLISION", f"键不存在：{key}")
    valid = {key, *(f"{key}{sub}" for sub in entries[key].subfigs)}
    hitting = sorted(cid for cid, refs in references.items() if refs & valid)
    if hitting:
        raise FiguresEditError(
            "E-FIG-IN-USE", f"{'、'.join(hitting)} 引用了 {key}，先解除引用再删除")
    return {k: v for k, v in entries.items() if k != key}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_figures_edit.py -v`
Expected: 23 passed

- [ ] **Step 5: 提交**

```bash
git add src/weft/figures_edit.py tests/test_figures_edit.py
git commit -m "feat: figures_edit 改删段——parse_subfigs、update_entry、remove_entry 引用阻断"
```

---

### Task 4: 引擎——write_figures_yaml（确定性重写）

**Files:**
- Modify: `src/weft/figures_edit.py`（文件末尾追加）
- Test: `tests/test_figures_edit.py`（追加）

- [ ] **Step 1: 写失败测试**

在 `tests/test_figures_edit.py` 追加（import 区补 `write_figures_yaml`）：

```python
def test_write_roundtrip_defaults_omitted(tmp_path):
    entries = {"fig-01": FigureEntry(caption="速率", subfigs={"a": "左"}),
               "fig-02": FigureEntry()}
    write_figures_yaml(tmp_path, entries)
    assert load_for_edit(tmp_path) == entries
    text = (tmp_path / "metadata" / "figures.yaml").read_text(encoding="utf-8")
    assert "fig-02:\n" in text and "fig-02:\n  caption" not in text  # 空条目裸键


def test_write_deterministic_lf(tmp_path):
    entries = {"fig-01": FigureEntry(caption="a"), "fig-02": FigureEntry()}
    p1 = write_figures_yaml(tmp_path, entries)
    b1 = p1.read_bytes()
    p2 = write_figures_yaml(tmp_path, entries)
    assert p2.read_bytes() == b1                     # 字节级确定（黄金可比对）
    assert b"\r" not in b1 and b1.endswith(b"\n")


def test_write_quotes_special_caption(tmp_path):
    entries = {"fig-01": FigureEntry(caption="速率: 95% CI")}
    write_figures_yaml(tmp_path, entries)
    assert load_for_edit(tmp_path)["fig-01"].caption == "速率: 95% CI"


def test_load_normalizes_crlf(tmp_path):
    _write_yaml(tmp_path, "fig-01:\r\n  caption: 速率\r\n")
    assert load_for_edit(tmp_path)["fig-01"].caption == "速率"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_figures_edit.py -v`
Expected: 新增用例 FAIL（ImportError: cannot import name 'write_figures_yaml'）

- [ ] **Step 3: 最小实现**

在 `src/weft/figures_edit.py` 末尾追加：

```python
def _dump_scalar(value: str) -> str:
    """简单词原样，含特殊字符走 JSON 双引号（合法 YAML 流标量；同 scaffold 惯例）。"""
    if _PLAIN_YAML.fullmatch(value):
        return value
    return json.dumps(value, ensure_ascii=False)


def write_figures_yaml(root: Path, entries: dict[str, FigureEntry]) -> Path:
    """确定性重写（F2）：键序保持、caption/subfigs 缺省省略、UTF-8 固定 LF。"""
    lines: list[str] = []
    for key, entry in entries.items():
        lines.append(f"{_dump_scalar(key)}:")
        if entry.caption:
            lines.append(f"  caption: {_dump_scalar(entry.caption)}")
        for sub, cap in entry.subfigs.items():
            lines.append(f"  {_dump_scalar(sub)}: {_dump_scalar(cap)}")
    text = ("\n".join(lines) + "\n") if lines else ""
    path = figures_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_figures_edit.py -v`
Expected: 27 passed

- [ ] **Step 5: 提交**

```bash
git add src/weft/figures_edit.py tests/test_figures_edit.py
git commit -m "feat: figures_edit 写入段——确定性重写（键序/缺省省略/LF/标量引用）"
```

---

### Task 5: WebUI——列表页路由 + figures.html + 子导航

**Files:**
- Create: `src/weft/web/routes/figures.py`
- Create: `src/weft/web/templates/figures.html`
- Modify: `src/weft/web/templates/base.html:31-37`（subnav 元组）
- Modify: `src/weft/web/routes/__init__.py`（register_all）
- Test: `tests/test_web_figures.py`（新建，本任务先写 3 个列表用例）
- Test: `tests/test_web_subnav.py`（补 figures 断言）

- [ ] **Step 1: 写失败测试**

创建 `tests/test_web_figures.py`：

```python
"""figures.yaml WebUI 路由测试（webui figures 设计定案）。

夹具项目（webutil→helpers.make_minimal_project）：figures.yaml 含 fig-01
（caption 速率曲线、子图 a），data-01 refs=[fig-01a]，figures/fig-01a.png 存在。
"""
import pytest

pytest.importorskip("fastapi")

from tests.helpers import write_yaml
from tests.webutil import make_client


def test_figures_page_lists_entries(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/figures")
    assert resp.status_code == 200
    assert "fig-01" in resp.text and "速率曲线" in resp.text
    assert 'href="/p/demo/cards/data/data-01"' in resp.text   # 引用卡链接
    assert "文件缺失" not in resp.text                          # fig-01a.png 存在
    assert "未被引用" not in resp.text                          # data-01 引用着
    assert 'href="/p/demo/figures"' in resp.text               # 子导航"图表"


def test_figures_page_markers(tmp_path):
    client, projects = make_client(tmp_path)
    write_yaml(projects / "demo" / "metadata" / "figures.yaml",
               {"fig-01": {"caption": "速率曲线", "subfigs": {"a": "60°C"}},
                "fig-02": {"caption": "没人用的图"}})
    resp = client.get("/p/demo/figures")
    assert resp.status_code == 200
    assert "文件缺失" in resp.text       # fig-02 无 png/pdf
    assert "未被引用" in resp.text       # 无 data 卡引用 fig-02


def test_figures_unknown_project_404(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/p/nope/figures").status_code == 404
```

在 `tests/test_web_subnav.py` 的 `test_dashboard_subnav_has_all_sections` 中把 slug 元组改为：

```python
    for slug in ("", "parts", "cards", "figures", "graph", "inspire", "diagnostics"):
```

并在 `test_subnav_active_follows_section` 的 `cases` 列表头部加入：

```python
        ("/p/demo/figures", "/p/demo/figures"),
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_figures.py tests/test_web_subnav.py -v`
Expected: test_figures_* FAIL（404，路由不存在）；subnav 元组断言 FAIL

- [ ] **Step 3: 实现路由与模板**

创建 `src/weft/web/routes/figures.py`：

```python
"""figures.yaml 路由（webui figures 设计定案）：列表 / 新增 / 编辑 / 删除。

注册顺序：/figures/new 必须先于 /figures/{key}（同 cards 先例）。
列表展示读 store 加载视图（figures.yaml 坏条目时页面仍可看，F3）；
一切写操作经 figures_edit 引擎自读自写磁盘（F12），错误回显 banner。
"""
from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse

from weft.figures_edit import (
    FiguresEditError,
    load_for_edit,
)
from weft.web.common import load_project_or_404, templates

router = APIRouter()


def _rows(entry) -> list[dict]:
    """列表行（F10）：类型判定 tbl- 前缀对齐 assemble；文件缺失标记对齐校验。"""
    project = entry.project
    refs_by_card = {cid: set(card.refs)
                    for cid, card in project.data_cards.items()}
    fig_dir = project.root / project.figures_dir
    rows = []
    for key, fig in project.figures.items():
        valid = {key, *(f"{key}{sub}" for sub in fig.subfigs)}
        used_by = sorted(cid for cid, refs in refs_by_card.items()
                         if refs & valid)
        rows.append({
            "key": key, "caption": fig.caption, "subfigs": fig.subfigs,
            "kind": "table" if key.startswith("tbl-") else "figure",
            "used_by": used_by,
            "file_missing": (key.startswith("fig-")
                             and not (fig_dir / f"{key}.png").exists()
                             and not (fig_dir / f"{key}.pdf").exists()),
            "unused": not used_by})
    return rows


@router.get("/p/{pid}/figures")
def figures_page(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    load_error = None
    try:
        load_for_edit(entry.project.root)
    except FiguresEditError as exc:
        load_error = f"{exc.code} {exc.message}"
    return templates.TemplateResponse(
        request, "figures.html",
        {"entry": entry, "rows": _rows(entry), "load_error": load_error})


def register(app: FastAPI) -> None:
    app.include_router(router)
```

（新增/编辑/删除路由在 Task 6 追加到本文件；`new` 路由届时插在 `figures_page` 之后、`{key}` 路由之前。）

创建 `src/weft/web/templates/figures.html`：

```html
{% extends "base.html" %}
{% block title %}图表 · {{ entry.pid }}{% endblock %}
{% block content %}
<h2>图表注册表 · {{ entry.pid }}</h2>
{% if load_error %}<div class="banner error">
  <div><b>figures.yaml 不可编辑</b>: {{ load_error }}（请手工修复后刷新）</div>
</div>{% endif %}
{% if error is defined and error %}<div class="banner error"><div>{{ error }}</div></div>{% endif %}
{% if rows %}
<table class="list">
  <thead><tr><th>键</th><th>类型</th><th>caption</th><th>子图</th><th>被引用</th><th>标记</th><th></th></tr></thead>
  <tbody>
  {% for r in rows %}
    <tr>
      <td><code>{{ r.key }}</code></td>
      <td>{{ "表格" if r.kind == "table" else "图" }}</td>
      <td>{{ r.caption | truncate(60) }}</td>
      <td>{% for s in r.subfigs %}{{ s }}{% if not loop.last %}、{% endif %}{% endfor %}</td>
      <td>{% for cid in r.used_by %}<a href="/p/{{ entry.pid }}/cards/data/{{ cid }}">{{ cid }}</a>{% if not loop.last %}、{% endif %}{% else %}—{% endfor %}</td>
      <td>{% if r.file_missing %}<span class="badge rejected">文件缺失</span>{% endif %}
          {% if r.unused %}<span class="badge draft">未被引用</span>{% endif %}</td>
      <td>{% if not load_error %}<a href="/p/{{ entry.pid }}/figures/{{ r.key }}">编辑</a>{% endif %}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{% else %}
<p>figures.yaml 为空。</p>
{% endif %}
{% if not load_error %}<p><a href="/p/{{ entry.pid }}/figures/new">＋ 新增图注条目</a></p>{% endif %}
<p><a href="/p/{{ entry.pid }}/">返回总览</a></p>
{% endblock %}
```

修改 `src/weft/web/templates/base.html`，subnav 元组（`cards` 之后）插入一行：

```html
        ("figures", "图表", true),
```

修改 `src/weft/web/routes/__init__.py` 的 `register_all`，在 `cards.register(app)` 之后加：

```python
    from weft.web.routes import figures as figures_routes

    figures_routes.register(app)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_figures.py tests/test_web_subnav.py -v`
Expected: test_web_figures 3 passed + test_web_subnav 5 passed；再跑全量确认无回归：`.venv/Scripts/python.exe -m pytest tests -q`，预期 661 passed, 2 deselected（651 + 3 新增，subnav 是改断言不加数）

- [ ] **Step 5: 提交**

```bash
git add src/weft/web/routes/figures.py src/weft/web/templates/figures.html src/weft/web/templates/base.html src/weft/web/routes/__init__.py tests/test_web_figures.py tests/test_web_subnav.py
git commit -m "feat: WebUI 图表页——figures.yaml 列表（类型/引用/文件缺失/未被引用标记）与子导航"
```

---

### Task 6: WebUI——新增/编辑/删除路由 + figure_form.html

**Files:**
- Modify: `src/weft/web/routes/figures.py`（追加路由）
- Create: `src/weft/web/templates/figure_form.html`
- Test: `tests/test_web_figures.py`（追加 9 个用例）

- [ ] **Step 1: 写失败测试**

在 `tests/test_web_figures.py` 追加：

```python
def _yaml_path(projects):
    return projects / "demo" / "metadata" / "figures.yaml"


def test_figure_new_auto_number(tmp_path):
    client, projects = make_client(tmp_path)
    resp = client.get("/p/demo/figures/new")
    assert resp.status_code == 200 and 'name="prefix"' in resp.text
    resp = client.post("/p/demo/figures/new",
                       data={"prefix": "fig", "key": "", "caption": "新图",
                             "subfigs": "a: 左"}, follow_redirects=False)
    assert resp.status_code == 303
    text = _yaml_path(projects).read_text(encoding="utf-8")
    assert "fig-02:" in text and "新图" in text


def test_figure_new_explicit_key(tmp_path):
    client, projects = make_client(tmp_path)
    resp = client.post("/p/demo/figures/new",
                       data={"prefix": "tbl", "key": "tbl-01", "caption": "表一",
                             "subfigs": ""}, follow_redirects=False)
    assert resp.status_code == 303
    assert "tbl-01:" in _yaml_path(projects).read_text(encoding="utf-8")


def test_figure_new_collision_rerender(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.post("/p/demo/figures/new",
                       data={"prefix": "fig", "key": "fig-01", "caption": "x",
                             "subfigs": ""})
    assert resp.status_code == 200
    assert "E-FIG-COLLISION" in resp.text


def test_figure_new_invalid_name_rerender(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.post("/p/demo/figures/new",
                       data={"prefix": "fig", "key": "a/b", "caption": "x",
                             "subfigs": ""})
    assert resp.status_code == 200
    assert "E-FIG-NAME" in resp.text


def test_figure_edit_get_prefills(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.get("/p/demo/figures/fig-01")
    assert resp.status_code == 200
    assert "速率曲线" in resp.text and "a: 60°C" in resp.text


def test_figure_edit_post_updates_keeps_order(tmp_path):
    client, projects = make_client(tmp_path)
    write_yaml(_yaml_path(projects),
               {"fig-01": {"caption": "速率曲线", "subfigs": {"a": "60°C"}},
                "fig-02": {"caption": "第二张"}})
    resp = client.post("/p/demo/figures/fig-01",
                       data={"caption": "改过的题注", "subfigs": "b: 右"},
                       follow_redirects=False)
    assert resp.status_code == 303
    text = _yaml_path(projects).read_text(encoding="utf-8")
    assert text.index("fig-01:") < text.index("fig-02:")   # 键序保持
    assert "改过的题注" in text and "b: 右" in text


def test_figure_delete_ok(tmp_path):
    client, projects = make_client(tmp_path)
    write_yaml(_yaml_path(projects),
               {"fig-01": {"caption": "速率曲线", "subfigs": {"a": "60°C"}},
                "fig-02": {"caption": "没人用"}})
    resp = client.post("/p/demo/figures/fig-02/delete",
                       follow_redirects=False)
    assert resp.status_code == 303
    text = _yaml_path(projects).read_text(encoding="utf-8")
    assert "fig-02" not in text and "fig-01:" in text


def test_figure_delete_blocked_in_use(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.post("/p/demo/figures/fig-01/delete")
    assert resp.status_code == 200
    assert "E-FIG-IN-USE" in resp.text and "data-01" in resp.text


def test_broken_yaml_list_viewable_writes_refused(tmp_path):
    """F3：解析失败 → 列表可看、转只读；一切写操作回 E-FIG-LOAD。"""
    client, projects = make_client(tmp_path)
    _yaml_path(projects).write_text("fig-01: [unclosed\n", encoding="utf-8")
    page = client.get("/p/demo/figures")
    assert page.status_code == 200 and "E-FIG-LOAD" in page.text
    assert "新增图注条目" not in page.text
    for url, data in (("/p/demo/figures/new",
                       {"prefix": "fig", "key": "", "caption": "x",
                        "subfigs": ""}),
                      ("/p/demo/figures/fig-01",
                       {"caption": "x", "subfigs": ""}),
                      ("/p/demo/figures/fig-01/delete", {})):
        resp = client.post(url, data=data)
        assert resp.status_code == 200 and "E-FIG-LOAD" in resp.text, url
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_figures.py -v`
Expected: 新增 9 用例 FAIL（404 / AssertionError）

- [ ] **Step 3: 实现路由与表单模板**

在 `src/weft/web/routes/figures.py`：import 区补 `from urllib.parse import quote` 不需要（键名已过安全校验，直接拼 URL）；补引擎 import `add_entry, parse_subfigs, remove_entry, update_entry, write_figures_yaml`。在 `figures_page` 之后、`register` 之前插入：

```python
_PREFIXES = {"fig": "fig-", "tbl": "tbl-"}


def _form(request: Request, entry, key: str | None, values: dict,
          errors: dict):
    if key is None:
        action = f"/p/{entry.pid}/figures/new"
    else:
        action = f"/p/{entry.pid}/figures/{key}"
    return templates.TemplateResponse(
        request, "figure_form.html",
        {"entry": entry, "key": key, "values": values, "action": action,
         "cancel_url": f"/p/{entry.pid}/figures", "errors": errors})


def _values(caption: str, subfigs_text: str, prefix: str) -> dict:
    return {"caption": caption, "subfigs_text": subfigs_text, "prefix": prefix}


@router.get("/p/{pid}/figures/new")
def figure_new_get(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    return _form(request, entry, None, _values("", "", "fig"), {})


@router.post("/p/{pid}/figures/new")
async def figure_new_post(request: Request, pid: str):
    entry = load_project_or_404(request, pid)
    form = await request.form()
    return _submit(request, entry, None, form)


@router.get("/p/{pid}/figures/{key}")
def figure_edit_get(request: Request, pid: str, key: str):
    entry = load_project_or_404(request, pid)
    fig = entry.project.figures.get(key)
    if fig is None:
        raise HTTPException(status_code=404, detail="图注条目不存在")
    subfigs_text = "\n".join(f"{s}: {c}" for s, c in fig.subfigs.items())
    return _form(request, entry, key, _values(fig.caption, subfigs_text, "fig"),
                 {})


@router.post("/p/{pid}/figures/{key}")
async def figure_edit_post(request: Request, pid: str, key: str):
    entry = load_project_or_404(request, pid)
    form = await request.form()
    return _submit(request, entry, key, form)


@router.post("/p/{pid}/figures/{key}/delete")
def figure_delete(request: Request, pid: str, key: str):
    entry = load_project_or_404(request, pid)
    project = entry.project
    references = {cid: set(card.refs)
                  for cid, card in project.data_cards.items()}
    try:
        entries = remove_entry(load_for_edit(project.root), key, references)
        write_figures_yaml(project.root, entries)
    except FiguresEditError as exc:
        return templates.TemplateResponse(
            request, "figures.html",
            {"entry": entry, "rows": _rows(entry), "load_error": None,
             "error": f"{exc.code} {exc.message}"})
    return RedirectResponse(f"/p/{pid}/figures", status_code=303)


def _submit(request: Request, entry, key: str | None, form):
    caption = str(form.get("caption", "")).strip()
    subfigs_text = str(form.get("subfigs", ""))
    prefix = str(form.get("prefix", "fig"))
    values = _values(caption, subfigs_text, prefix)
    try:
        subfigs = parse_subfigs(subfigs_text)
        entries = load_for_edit(entry.project.root)
        if key is None:
            entries = add_entry(entries, str(form.get("key", "")).strip(),
                                caption, subfigs, _PREFIXES.get(prefix, "fig-"))
        else:
            entries = update_entry(entries, key, caption, subfigs)
        write_figures_yaml(entry.project.root, entries)
    except FiguresEditError as exc:
        return _form(request, entry, key, values,
                     {"figures": f"{exc.code} {exc.message}"})
    return RedirectResponse(f"/p/{entry.pid}/figures", status_code=303)
```

（文件顶部 import 区同步补齐：`HTTPException` 已在 Task 5 引入；补 `from weft.figures_edit import FiguresEditError, add_entry, load_for_edit, parse_subfigs, remove_entry, update_entry, write_figures_yaml`。）

创建 `src/weft/web/templates/figure_form.html`：

```html
{% extends "base.html" %}
{% block title %}{{ "新增图注条目" if key is none else "编辑图注 " + key }} · {{ entry.pid }}{% endblock %}
{% block content %}
<h2>{{ "新增图注条目" if key is none else "编辑图注 " + key }}</h2>
{% if errors %}<div class="banner error">
  {% for k, v in errors.items() %}<div><b>{{ k }}</b>: {{ v }}</div>{% endfor %}
</div>{% endif %}
<form method="post" action="{{ action }}">
  {% if key is none %}
  <fieldset>
    <legend>类型（键名留空时决定自动编号前缀）</legend>
    <label class="check"><input type="radio" name="prefix" value="fig"
      {% if values.get("prefix", "fig") == "fig" %}checked{% endif %}> fig-（图）</label>
    <label class="check"><input type="radio" name="prefix" value="tbl"
      {% if values.get("prefix") == "tbl" %}checked{% endif %}> tbl-（表）</label>
  </fieldset>
  <label>键名（留空自动编号；作为 figures/ 图片文件名）
    <input name="key" value="{{ values.get('key', '') }}" placeholder="如 fig-03">
  </label>
  {% endif %}
  <label>caption<textarea name="caption" rows="2">{{ values.get("caption", "") }}</textarea></label>
  <label>子图（每行一条 `子图号: 说明`，如 `a: 60°C`）<textarea name="subfigs" rows="4">{{ values.get("subfigs_text", "") }}</textarea></label>
  <button type="submit">保存</button>
  <a href="{{ cancel_url }}">取消</a>
</form>
{% if key is not none %}
<form method="post" action="{{ action }}/delete" style="margin-top: 1rem;">
  <button type="submit">删除此条目</button>
</form>
{% endif %}
{% endblock %}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_figures.py -v`
Expected: 12 passed；全量：`.venv/Scripts/python.exe -m pytest tests -q` 预期 **670 passed, 2 deselected**（651 + 3 + 9 + subnav 断言更新不加数）

- [ ] **Step 5: 提交**

```bash
git add src/weft/web/routes/figures.py src/weft/web/templates/figure_form.html tests/test_web_figures.py
git commit -m "feat: WebUI 图表页增改删——自动编号/冲突与键名校验回显、删除引用阻断、解析失败只读"
```

---

### Task 7: 文档回填 + 全量验证 + 计数登记

**Files:**
- Modify: `AGENTS.md`（红线 5 码表）
- Modify: `docs/roadmap.md`（M4 一行）
- Modify: `docs/superpowers/plans/2026-10-12-weft-webui-figures.md`（本文件，回填实际计数）

- [ ] **Step 1: AGENTS.md 红线 5 增补**

在红线 5 的 `2026-10-10-weft-new-template-design.md`（E-NEW-NAME / E-NEW-COLLISION）` 之后、`；新增码必须进表` 之前插入：

```markdown
、`2026-10-12-weft-webui-figures-design.md`（E-FIG-LOAD / E-FIG-NAME / E-FIG-COLLISION / E-FIG-IN-USE / E-FIG-VALUE）
```

- [ ] **Step 2: roadmap.md M4 增补**

在"改名对齐 `weft rename` ✅"一行之后插入：

```markdown
- WebUI 图表管理 ✅（2026-10-12）：figures.yaml 图表页（键序列表 + 引用卡链接 + 文件缺失/未被引用标记）与图注条目新增/编辑/删除；`figures_edit` 纯函数引擎（解析失败 E-FIG-LOAD 拒绝一切写、删除被引用键 E-FIG-IN-USE 阻断、fig-/tbl- 自动编号、确定性 LF 重写）。设计见 `docs/superpowers/specs/2026-10-12-weft-webui-figures-design.md`。
```

- [ ] **Step 3: 全量测试**

Run: `.venv/Scripts/python.exe -m pytest tests -q`
Expected: **670 passed, 2 deselected**（如与预期不符，先修回归再继续）

- [ ] **Step 4: 回填实际计数到本文件"验收与计数"一节并提交**

```bash
git add AGENTS.md docs/roadmap.md docs/superpowers/plans/2026-10-12-weft-webui-figures.md
git commit -m "docs: WebUI 图表管理落地——AGENTS 红线 5 码表 E-FIG-*、roadmap M4、计数回填（670 passed 实证）"
```

（提交信息中的数字以 Step 3 实际输出为准。）

## 验收与计数

- 引擎测试 `tests/test_figures_edit.py`：**27 个**
- WebUI 测试 `tests/test_web_figures.py`：**12 个**
- `tests/test_web_subnav.py`：断言更新，无新增
- 全量预期：651 + 39 = **670 passed, 2 deselected**
- 实际执行结果：（执行后回填）

## 自查记录（计划完成时已核）

1. **Spec 覆盖**：F1→Task 1–4/引擎文件位置；F2→Task 4 重写语义+测试；F3→Task 1 E-FIG-LOAD + Task 6 broken-yaml 用例；F4→Task 2 校验+parity 测试；F5→Task 2 编号+尾插测试；F6→Task 3 rejected 用例；F7→Task 3 parse_subfigs；F8→Task 3 update 键不可变；F9/F11→范围内不实现（无任务需要）；F10→Task 5 `_rows` 标记；F12→Task 5/6 引擎自读自写 + 列表读 store 视图。页面规格（路由表、模板字段）→Task 5/6；诊断码表→Task 1–3 各码均有断言；测试策略→两测试文件 + subnav 更新 + AGENTS/roadmap→Task 7。无缺口。
2. **占位符扫描**：所有代码步骤给出完整代码；无 TBD/TODO/"适当处理"。
3. **类型一致性**：`FiguresEditError(code, message)` 全计划一致；`load_for_edit(root) -> dict[str, FigureEntry]`、`add_entry(entries, key, caption, subfigs, prefix)`、`update_entry(entries, key, caption, subfigs)`、`remove_entry(entries, key, references)`、`parse_subfigs(text)`、`write_figures_yaml(root, entries)`、`_form(request, entry, key, values, errors)`、`_values(caption, subfigs_text, prefix)`、`_rows(entry)` 各 Task 间签名一致。
