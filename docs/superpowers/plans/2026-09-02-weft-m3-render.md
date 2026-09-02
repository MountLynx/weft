# weft M3 渲染层实施计划（paper.qmd 拼接 + References/Figures + assets 约定 + weft render）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现设计定案 `docs/superpowers/specs/2026-09-02-weft-m3-render-design.md`：`weft assemble` 增产项目根 `paper.qmd`（chapter 原样并入 + References refs div + Figures/Tables 字面编号）、投稿资源约定 `assets/`（样例项目迁移）、`render.py` quarto 子进程封装与 CLI `weft render`（docx 默认），打通卡片→叙事→生成→组装→Quarto 全闭环。

**Architecture:** 纯脚本无 LLM。`assemble/paper.py`（新增，paper 级纯函数：References 定位块 + Figures/Tables 字面编号）被 `assemble/merge.py`（chapter 合并后追加写 `paper.qmd`）复用；`paper_file` 文件名经 weft.yaml 配置进 `Project`；`weft/render.py`（新增，顶层模块，不 import specmodule，不碰分层红线）封装 quarto 子进程，CLI `weft render` 只做加载与转发。图表链路整体不走 crossref（设计 §3/§6），weft 是图编号唯一权威。

**Tech Stack:** Python 3.11+，pydantic 2，typer，pytest；外部依赖 Quarto CLI（本机已装 1.9.38，仅 render 与冒烟触达）。

**基线：** main @ 6cccac7，`219 passed, 1 deselected`。测试命令统一（**worktree 内执行时必须加 `PYTHONPATH=src` 前缀**——worktree 无 `.venv`，用主仓库 venv，PYTHONPATH 使 import 解析到 worktree 的 src，先于 site-packages 的 editable 指回 main；已实测）：

```bash
cd "C:/Users/xingy/Desktop/开发/weft/.worktrees/m3-render"
PYTHONPATH=src "C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe" -m pytest tests -q
```

下文各任务 `Run:` 里的 `.venv/Scripts/python.exe -m pytest tests -q` 均指此形式（在 worktree 根目录执行）。执行按 AGENTS.md 工作流约定走 worktree（`.worktrees/m3-render`，Task 1 已建），完成后合回 main 并删除 worktree/分支；提交只到本地 main，**不要 push**。

**测试计数台账（精确登记）：**

| 任务 | 新增 | 修订既有 | 累计（passed, 1 deselected） |
|---|---|---|---|
| 基线 | — | — | 219 |
| Task 2 paper_file 配置 | +2 | 0 | 221 |
| Task 3 paper 级纯函数 | +4 | 0 | 225 |
| Task 4 assemble_project 产 paper.qmd | 0 | 4（test_assemble 3 + test_cli_assemble 1） | 225 |
| Task 5 render.py 封装 | +5 | 0 | 230 |
| Task 6 CLI weft render | +6 | 0 | 236 |
| Task 7 样例迁移 + 黄金 | +1 | 1（test_sample_draft_then_assemble_full_chain） | 237 |
| Task 8 文档收尾 | 0 | 0 | 237（全量回归确认） |

**范围裁定（执行者不要自加工作）：**

- 设计 §6 明确不做：图表正文内插入、crossref 图表编号（label/编号链路整体不用）、Quarto 子图语法、子图引用的标记与校验、`reference-section-title` 协调（weft 写死标题）。
- `weft init` 模板是 M4 的事，本计划只把样例项目迁到 assets 约定（`_quarto.yml` 固定写法即未来模板）。
- 标题/作者/摘要等前置信息不归 weft（设计 §1）——不碰 `index.qmd`；paper.qmd 不用 `{{< include >}}`（chapter 正文原样并入，方案 B）。
- 校验零新增（设计 §5）：图引用为纯文本不校验，figures.yaml 既有校验不变；**本计划不新增任何诊断码**（render 的失败走 CLI 层直打 `ERROR`，同既有 OSError 处理先例）。

---

## 设计决策（执行期不再重新讨论；冒烟若推翻预期，回填本表并修订对应任务）

1. **paper.qmd 字节布局**：`"\n\n".join([chapter 正文（各 rstrip("\n")，目录序）] + [References 块] + [Figures 块（有 fig 键时）] + [Tables 块（有 tbl 键时）]) + "\n"`，固定 LF、单尾换行。块内定义见 Task 3 代码，黄金比对钉死字节。
2. **Figures/Tables 划分与编号**：键前缀 `tbl-` → `# Tables {.unnumbered}`（前缀字面 `Table`）；其余键 → `# Figures {.unnumbered}`（前缀字面 `Fig.`）。编号 N = **figures.yaml 键序**（loader dict 保序，即 yaml 文件出现序，不是字典序）；图条目 = `![]({figures_dir}/{key}.png)` + 空行 + `**Fig. N** <caption>`；表条目 = 仅 `**Table N** <caption>`（无图片行——validation 先例注释"表格是排版产物不是图片文件"，表体由人在 docx 里贴在图注旁）。空 caption 兜底 `.rstrip()`，产出 `**Fig. N**`。
3. **subfigs 不进渲染**（设计 §3/§6）：子图实际在同一张图片文件内，只渲染主 caption；正文对子图的引用是纯文本（`Fig. 1a`），weft 不校验不展开。
4. **图路径 = `{figures_dir}/{key}.png`**：扩展名固定 `.png`（与 validation `W-FIGURE-FILE-MISSING` 的检查形状一致）；相对项目根，与 paper.qmd 位置一致（设计 §1）。
5. **References 只写定位 div**：`# References {.unnumbered}` + 空行 + `::: {#refs}`/`:::`；weft 不生成任何条目；样例 `_quarto.yml` 不得设 `reference-section-title`（两边都写会重复标题）。
6. **paper_file 配置**：weft.yaml `paper_file`，默认 `"paper.qmd"`，loader `str()` 宽松读取（同 `figures_dir` 先例，无取值校验、无新诊断码）；`Project.paper_file` 字段供 assemble 写、render 读。
7. **assemble_project 恒写 paper.qmd**：含 strict 报错时的部分 chapter（与"健康 chapter 照常产出"同语义，fail-open 落盘、CLI 以诊断定退出码）；paper 路径在 `written` 列表**末尾**。
8. **render 错误模型**：`QuartoNotFoundError`（quarto 不在 PATH）/`QuartoRenderError`（paper 缺失或 quarto 非零退出）两个异常类，CLI 捕获后 `ERROR <消息>` + 退出码 1；**render 不重跑 validate 闸门**（assemble 已闸），仅要求项目可加载（load 诊断有 error → 退出码 1，同 `review` 先例）。
9. **render 子进程语义**：`quarto render <paper_file> --to <fmt>`，`cwd=project_root`，捕获 stdout/stderr（encoding=utf-8, errors=replace），失败时随异常透传；输出路径 = `paper.with_suffix("." + to)`（paper.qmd --to docx → paper.docx）。
10. **样例迁移零 card 改动**：只动 `assets/`（bib 移入 + 新增 style.csl/template.docx）、`_quarto.yml` 重写、新增键级图 `figures/fig-01.png`（paper.qmd 按键引用；既有子图级 refs（fig-01a/b）与文件原样保留）——graph 黄金文件与 `validate` 0 错误 0 提醒均不受扰动。
11. **执行期修订（Task 1 渲染冒烟，2026-09-02）**：Quarto 1.9.38 实测——refs div 位置被替换为文献列表且带 `# References` 标题；`number-sections: true` 下正文节获得编号、`.unnumbered` 的 References/Figures 不编号；docx 对无名 `::: div` 无可见残留（不产生空段落）。三项均符合设计预期，无任务修订。冒烟产物在系统临时目录，未入库。
12. **执行期修订（Task 7 渲染冒烟，2026-09-02）**：citeproc 默认只渲染**被引用**的条目（未设 `nocite`）——冒烟草稿必须含 `[@key]` 引文，References 下才有条目。已实测：草稿含 `（[@smith2020]）` 时正文渲染 `[1]`、References 下出现 elsevier-with-titles 数字条目；未引用的 doe2021 不出现（正确默认，无需 nocite）。Task 7 Step 7 的冒烟草稿与目检预期已按此修正。

## 新增诊断码

无（设计 §5 校验无新增；render 失败走 CLI 层 `ERROR` 直出，不进诊断码体系，同 OSError 先例）。

## 文件结构

```text
src/weft/
├── assemble/
│   ├── __init__.py          # 不动（仍只导出 assemble_project）
│   ├── paper.py             # 新增：paper 级纯函数（References 定位块 + Figures/Tables 字面编号 + 全文拼装）
│   └── merge.py             # 修改：chapter 合并后追加写项目根 paper.qmd
├── render.py                # 新增：quarto 子进程封装（顶层模块，不 import specmodule）
├── store/
│   ├── project.py           # 修改：+paper_file 字段（默认 "paper.qmd"）
│   └── loader.py            # 修改：_load_config 读 weft.yaml paper_file
└── cli.py                   # 修改：+weft render 命令；assemble docstring 提及 paper.qmd
tests/
├── test_store_config.py     # 修改：+paper_file 2 测试
├── test_assemble_paper.py   # 新增：paper 级纯函数 4 测试
├── test_assemble.py         # 修改：3 测试预期加 paper.qmd
├── test_cli_assemble.py     # 修改：1 测试加输出断言
├── test_render.py           # 新增：render.py 5 测试（全 monkeypatch，不依赖 quarto）
├── test_cli_render.py       # 新增：CLI render 6 测试
├── test_example_project.py  # 修改：+黄金比对 1 测试；全链路测试补 paper.qmd 断言
└── golden/paper.qmd         # 新增：样例 paper.qmd 黄金文件（测试内做 CRLF→LF 归一，防 Windows 检出差异）
examples/paper-demo/
├── assets/                  # 新增：references.bib（自根移入）/ style.csl / template.docx
├── figures/fig-01.png       # 新增：键级图（fig-01a.png 副本；paper.qmd Figures 节按 key 引用）
└── _quarto.yml              # 重写：设计 §4 固定写法
```

---

### Task 1: 计划入库 + Quarto 行为冒烟（设计 §5 要求动工先做）

**Files:**
- Commit: `docs/superpowers/plans/2026-09-02-weft-m3-render.md`（本文件）
- 冒烟产物：系统临时目录（**不入库**）

- [ ] **Step 1: 建 worktree 并提交本计划**

```bash
cd "C:/Users/xingy/Desktop/开发/weft"
git worktree add .worktrees/m3-render -b m3-render
cd .worktrees/m3-render
git add docs/superpowers/plans/2026-09-02-weft-m3-render.md
git commit -m "docs: M3 渲染层实施计划（paper.qmd/render/assets）"
```

- [ ] **Step 2: 搭最小冒烟项目（系统临时目录，验证 refs div 替换、.unnumbered 在 number-sections 下的表现、docx 对 ::: div 的处理）**

```bash
SMOKE=$(mktemp -d) && cd "$SMOKE" && mkdir -p assets
cat > assets/references.bib <<'EOF'
@article{doe2021,
  author = {Doe, John},
  title = {Catalysis across temperature gradients},
  journal = {Catalysis Today},
  year = {2021}
}
EOF
cat > _quarto.yml <<'EOF'
project:
  type: default
number-sections: true
bibliography: assets/references.bib
EOF
cp "C:/Users/xingy/Desktop/开发/weft/examples/paper-demo/figures/fig-01a.png" fig.png
cat > paper.qmd <<'EOF'
See [@doe2021] for details.

# Results

Numbered body section.

# References {.unnumbered}

::: {#refs}
:::

# Figures {.unnumbered}

![](fig.png)

**Fig. 1** Smoke caption.
EOF
quarto render paper.qmd --to docx
```

Expected: 退出码 0，生成 `paper.docx`。

- [ ] **Step 3: 检查产物并回填设计决策表**

```bash
quarto pandoc paper.docx -t plain
```

核对三点并（如有出入）回填本计划"设计决策"表：(a) 文献条目（Doe 2021）出现在 `# References` 标题之下（refs div 被替换），而非文档末尾无标题堆叠；(b) `number-sections: true` 下 Results 有编号、References/Figures 无编号（可开 docx 目检）；(c) docx 中 `::: div` 无可见残留（无空段落/字面 `:::`）。全部符合预期即在设计决策表补一条"冒烟符合预期"；有出入则修订受影响任务的代码与测试预期，并在该条记录差异。

---

### Task 2: weft.yaml `paper_file` 配置（Project 字段 + loader）

**Files:**
- Modify: `src/weft/store/project.py:33`（assemble_mode 字段后）
- Modify: `src/weft/store/loader.py:240`（`_load_config` 的 assemble_mode 块后）
- Test: `tests/test_store_config.py`（文件末尾追加）

- [ ] **Step 1: 写失败测试（tests/test_store_config.py 末尾追加）**

```python
def test_paper_file_defaults_paper_qmd(tmp_path):
    make_minimal_project(tmp_path)
    project, diagnostics = load_project(tmp_path)
    assert diagnostics == []
    assert project.paper_file == "paper.qmd"


def test_paper_file_override(tmp_path):
    make_minimal_project(tmp_path)
    write_yaml(tmp_path / "weft.yaml", {"paper_file": "manuscript.qmd"})
    project, diagnostics = load_project(tmp_path)
    assert diagnostics == []
    assert project.paper_file == "manuscript.qmd"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_store_config.py -q`
Expected: 2 failed（`AttributeError: 'Project' object has no attribute 'paper_file'`）

- [ ] **Step 3: 最小实现**

`src/weft/store/project.py` —— `assemble_mode` 字段后加一行：

```python
    assemble_mode: str = "strict"         # weft.yaml assemble_mode：strict | lenient
    paper_file: str = "paper.qmd"         # weft.yaml paper_file：拼装产物文件名（M3 设计 §1）
```

`src/weft/store/loader.py` —— `_load_config` 中 assemble_mode 校验块之后加：

```python
    project.paper_file = str(weft_cfg.get("paper_file", "paper.qmd"))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_store_config.py -q`
Expected: `16 passed`（14 既有 + 2 新增）

- [ ] **Step 5: 提交**

```bash
git add src/weft/store/project.py src/weft/store/loader.py tests/test_store_config.py
git commit -m "feat: weft.yaml 新增 paper_file 配置（默认 paper.qmd）"
```

---

### Task 3: `assemble/paper.py` paper 级纯函数

**Files:**
- Create: `src/weft/assemble/paper.py`
- Test: `tests/test_assemble_paper.py`（新建）

- [ ] **Step 1: 写失败测试（新建 tests/test_assemble_paper.py）**

```python
"""paper 级拼装：References refs div、Figures/Tables 字面编号、chapter 原样并入（M3 设计 §1-§3）。"""
from tests.helpers import build_project
from weft.assemble.paper import assemble_paper
from weft.models.figures import FigureEntry


def test_back_matter_figures_tables_literal_numbering():
    # 键序即编号（非字典序）：fig-02 先出现 → Fig. 1；tbl-* 前缀分流入 Tables
    project = build_project(figures={
        "fig-02": FigureEntry(caption="第二图"),
        "fig-01": FigureEntry(caption="第一图"),
        "tbl-01": FigureEntry(caption="第一表"),
    })
    paper = assemble_paper(project, [])
    assert paper == (
        "# References {.unnumbered}\n\n::: {#refs}\n:::\n\n"
        "# Figures {.unnumbered}\n\n"
        "![](figures/fig-02.png)\n\n**Fig. 1** 第二图\n\n"
        "![](figures/fig-01.png)\n\n**Fig. 2** 第一图\n\n"
        "# Tables {.unnumbered}\n\n**Table 1** 第一表\n"
    )


def test_back_matter_refs_div_only_when_no_figures():
    project = build_project()
    assert assemble_paper(project, []) == (
        "# References {.unnumbered}\n\n::: {#refs}\n:::\n")


def test_assemble_paper_chapters_joined_in_given_order():
    # chapter 原样并入（rstrip 尾换行后单空行分隔），References 殿后
    project = build_project()
    paper = assemble_paper(project, ["# results\n\n正文一。\n",
                                     "# discussion\n\n正文二。\n"])
    assert paper == ("# results\n\n正文一。\n\n"
                     "# discussion\n\n正文二。\n\n"
                     "# References {.unnumbered}\n\n::: {#refs}\n:::\n")


def test_figures_dir_override_and_empty_caption():
    project = build_project(figures={"fig-01": FigureEntry()},
                            figures_dir="assets/figs")
    paper = assemble_paper(project, [])
    assert "![](assets/figs/fig-01.png)" in paper
    assert "**Fig. 1**\n" in paper      # 空 caption rstrip 兜底，不留尾随空格
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_assemble_paper.py -q`
Expected: 4 failed（`ModuleNotFoundError: No module named 'weft.assemble.paper'`）

- [ ] **Step 3: 实现 src/weft/assemble/paper.py（新建）**

```python
"""paper 级拼装（M3 设计 §1-§3）：chapter qmd 原样并入 + References/Figures/Tables。

References 只写 citeproc 定位 div（条目由 Quarto 依 _quarto.yml bibliography 生成，
weft 不生成任何条目）；Figures/Tables 由 figures.yaml 确定性生成，字面编号 = 键序，
不走 crossref（docx 投稿所见即所得；v1 §7"首次出现处插入"已作废）。
"""
from __future__ import annotations

from weft.store.project import Project

_REFERENCES_DIV = "# References {.unnumbered}\n\n::: {#refs}\n:::"
_FIG_PREFIX = "Fig."
_TBL_PREFIX = "Table"
_TBL_KEY = "tbl-"


def _back_matter(project: Project) -> str:
    """References 定位块 +（有则）Figures / Tables 节；figures.yaml 键序即编号。"""
    blocks = [_REFERENCES_DIV]
    fig_keys = [k for k in project.figures if not k.startswith(_TBL_KEY)]
    tbl_keys = [k for k in project.figures if k.startswith(_TBL_KEY)]
    if fig_keys:
        lines = ["# Figures {.unnumbered}", ""]
        for n, key in enumerate(fig_keys, start=1):
            lines += [f"![]({project.figures_dir}/{key}.png)", "",
                      f"**{_FIG_PREFIX} {n}** {project.figures[key].caption}".rstrip(),
                      ""]
        blocks.append("\n".join(lines).rstrip("\n"))
    if tbl_keys:
        lines = ["# Tables {.unnumbered}", ""]
        for n, key in enumerate(tbl_keys, start=1):
            lines += [f"**{_TBL_PREFIX} {n}** {project.figures[key].caption}".rstrip(),
                      ""]
        blocks.append("\n".join(lines).rstrip("\n"))
    return "\n\n".join(blocks)


def assemble_paper(project: Project, chapter_texts: list[str]) -> str:
    """paper.qmd 全文：chapter 正文（目录序、原样并入）+ References/Figures。LF 单尾换行。"""
    body = [text.rstrip("\n") for text in chapter_texts]
    body.append(_back_matter(project))
    return "\n\n".join(body) + "\n"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_assemble_paper.py -q`
Expected: `4 passed`

- [ ] **Step 5: 提交**

```bash
git add src/weft/assemble/paper.py tests/test_assemble_paper.py
git commit -m "feat: assemble paper 级纯函数（References refs div + Figures/Tables 字面编号）"
```

---

### Task 4: `assemble_project` 产出项目根 paper.qmd

**Files:**
- Modify: `src/weft/assemble/merge.py`（docstring、import、chapter 合并循环之后）
- Modify: `src/weft/cli.py:171-174`（assemble docstring）
- Test: `tests/test_assemble.py`（改 3 个测试）、`tests/test_cli_assemble.py`（改 1 个测试）

- [ ] **Step 1: 改测试使其先红**

`tests/test_assemble.py` —— 三个断言了 `written` 的测试整体替换为（新增 paper.qmd 预期与内容断言）：

```python
def test_assemble_project_writes_tree_and_chapter_merge(tmp_path):
    _tree_project(tmp_path)
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    (drafts / "sec-01.md").write_text(
        "<!-- weft:run=ab part=sec-01 -->\n\n"
        "<!-- weft:node=para-01-01 uses=fact-01 -->\n第一段正文。\n",
        encoding="utf-8")
    project, diagnostics = load_project(tmp_path)
    assert diagnostics == []
    written, asm_diags = assemble_project(project)
    assert asm_diags == []
    # part 标题级别 = 目录深度+1（两级目录 → ###）；chapter 合并按目录序补 #/##
    # paper.qmd 恒产出且在 written 末尾（设计决策 7）
    assert [p.relative_to(tmp_path).as_posix() for p in written] == [
        "generated/01-results/01-startup/part-01.qmd",
        "generated/01-results.qmd",
        "paper.qmd"]
    part_qmd = tmp_path / "generated" / "01-results" / "01-startup" / "part-01.qmd"
    assert part_qmd.read_text(encoding="utf-8") == "### SNDPR 启动性能\n\n第一段正文。\n"
    merged = (tmp_path / "generated" / "01-results.qmd").read_text(encoding="utf-8")
    assert merged == ("# results\n\n## startup\n\n"
                      "### SNDPR 启动性能\n\n第一段正文。\n\n")
    paper = (tmp_path / "paper.qmd").read_text(encoding="utf-8")
    assert paper == ("# results\n\n## startup\n\n### SNDPR 启动性能\n\n第一段正文。\n\n"
                     "# References {.unnumbered}\n\n::: {#refs}\n:::\n")
    raw = part_qmd.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")


def test_strict_missing_draft_errors_and_writes_nothing(tmp_path):
    # 混合夹具：sec-01 两个 approved 节点（para-01-01 有草段、para-01-02 缺），
    # 健康 sec-02 照常拼装——钉住 strict 报首缺节点、sec-01 整体跳过、其余 part 照常
    write_card(tmp_path / "metadata" / "data", "data-01",
               {"id": "data-01", "refs": [], "status": "approved"})
    write_card(tmp_path / "narrative" / "01-results" / "01-startup", "part-01",
               {"id": "sec-01", "section": "SNDPR 启动性能",
                "nodes": [
                    {"id": "para-01-01", "purpose": "describe", "uses": [],
                     "status": "approved"},
                    {"id": "para-01-02", "purpose": "interpret", "uses": [],
                     "status": "approved"}]})
    write_card(tmp_path / "narrative" / "01-results", "part-02",
               {"id": "sec-02", "section": "总览",
                "nodes": [{"id": "para-02-01", "purpose": "describe", "uses": [],
                           "status": "approved"}]})
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    (drafts / "sec-01.md").write_text(
        "<!-- weft:node=para-01-01 -->\n第一段有草稿。\n", encoding="utf-8")
    (drafts / "sec-02.md").write_text(
        "<!-- weft:node=para-02-01 -->\n健康段落。\n", encoding="utf-8")
    project, _ = load_project(tmp_path)
    written, asm_diags = assemble_project(project, mode="strict")
    assert [d.code for d in asm_diags] == ["E-ASSEMBLE-MISSING-DRAFT"]
    assert asm_diags[0].path == "narrative/01-results/01-startup/part-01.md"
    assert asm_diags[0].field == "para-01-02"   # 首个缺段节点，而非有草稿的那个
    # paper.qmd 恒产出（含 strict 报错时的部分 chapter），殿后于 written
    assert written == [tmp_path / "generated" / "01-results" / "part-02.qmd",
                       tmp_path / "generated" / "01-results.qmd",
                       tmp_path / "paper.qmd"]
    # sec-01 整体跳过：无 part qmd、chapter 合并无其子节标题
    assert not (tmp_path / "generated" / "01-results" / "01-startup").exists()
    merged = (tmp_path / "generated" / "01-results.qmd").read_text(encoding="utf-8")
    assert merged == "# results\n\n## 总览\n\n健康段落。\n\n"


def test_lenient_missing_draft_assembles_available_paragraphs(tmp_path):
    # v1 §7 语义：lenient 只跳缺段节点；part 标题级别 = 单层目录 +1 → ##
    write_card(tmp_path / "metadata" / "data", "data-01",
               {"id": "data-01", "refs": [], "status": "approved"})
    write_card(tmp_path / "narrative" / "01-results", "part-01",
               {"id": "sec-01", "section": "结果",
                "nodes": [
                    {"id": "para-01-01", "purpose": "describe", "uses": [],
                     "status": "approved"},
                    {"id": "para-01-02", "purpose": "interpret", "uses": [],
                     "status": "approved"}]})
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    (drafts / "sec-01.md").write_text(
        "<!-- weft:node=para-01-01 -->\n只有第一段。\n", encoding="utf-8")
    project, _ = load_project(tmp_path)
    written, asm_diags = assemble_project(project, mode="lenient")
    assert asm_diags == []
    assert (tmp_path / "generated" / "01-results" / "part-01.qmd").read_text(
        encoding="utf-8") == "## 结果\n\n只有第一段。\n"
    assert [p.name for p in written] == ["part-01.qmd", "01-results.qmd", "paper.qmd"]
```

`tests/test_cli_assemble.py` —— `test_assemble_writes_part_and_chapter_qmd` 整体替换（加一行输出断言）：

```python
def test_assemble_writes_part_and_chapter_qmd(tmp_path):
    _approved_draft(tmp_path)
    result = runner.invoke(app, ["assemble", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "generated/01-results/part-01.qmd" in result.output
    assert "generated/01-results.qmd" in result.output
    assert "已写入 paper.qmd" in result.output
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_assemble.py tests/test_cli_assemble.py -q`
Expected: 4 failed（written 列表缺 `paper.qmd` / 输出缺 `已写入 paper.qmd`）

- [ ] **Step 3: 实现 merge.py 修改**

`src/weft/assemble/merge.py` —— 模块 docstring 首行改为：

```python
"""chapter 级 qmd 合并 + 项目根 paper.qmd 拼装：目录序遍历，heading 层级 chapter→#、子节→##/###（v1.1 §4.4；M3 设计 §1）。
```

import 区（`from weft.assemble.parts import ...` 之后）加：

```python
from weft.assemble.paper import assemble_paper
```

`assemble_project` 的 docstring 补一句（首行之后）：

```python
    """全项目拼装：part qmd（镜像 narrative 树）+ chapter 级合并 qmd + 项目根 paper.qmd。

    paper.qmd 恒产出（含 strict 报错时的部分 chapter）；strict（默认）下
    approved 节点缺已批准草稿段 → E-ASSEMBLE-MISSING-DRAFT，
    该 part 跳过、其余照常（决策 13）；lenient 只跳缺段节点。
    返回 (写入路径, 诊断)，paper 路径在 written 末尾。
    """
```

chapter 合并 for 循环**整体替换**为（原循环的 `chapter_texts.values()` 是 `(子节路径, qmd)` 元组列表，不能直接传给 assemble_paper；改为同时积累 chapter 正文 `chapter_bodies`，循环后写 paper.qmd）：

```python
    chapter_bodies: dict[str, str] = {}
    for chapter, entries in chapter_texts.items():
        lines = [f"# {heading_text(chapter)}", ""]
        seen_dirs: set[tuple[str, ...]] = set()
        for sub_path, qmd in entries:
            for depth in range(1, len(sub_path) + 1):
                prefix = sub_path[:depth]
                if prefix not in seen_dirs:
                    seen_dirs.add(prefix)
                    lines += [f"{'#' * (depth + 1)} {heading_text(prefix[-1])}", ""]
            lines.append(qmd.rstrip("\n"))
            lines.append("")
        chapter_text = "\n".join(lines) + "\n"
        chapter_path = gen_root / f"{chapter}.qmd"
        chapter_path.write_text(chapter_text, encoding="utf-8", newline="\n")
        written.append(chapter_path)
        chapter_bodies[chapter] = chapter_text

    paper_path = project.root / project.paper_file
    paper_path.write_text(assemble_paper(project, list(chapter_bodies.values())),
                          encoding="utf-8", newline="\n")
    written.append(paper_path)
```

（与原循环逐行对照：仅把 `"\n".join(lines) + "\n"` 提为 `chapter_text` 变量复用，循环逻辑不变；paper 用的必须是新积累的 `chapter_bodies.values()`。）

`src/weft/cli.py` —— `assemble` 命令 docstring 改为：

```python
    """拼装已批准草稿 → generated/…/part-NN.qmd、chapter 级合并 qmd 与项目根 paper.qmd。

    纯脚本无 LLM（v1.1 §4.4；paper.qmd 拼接见 M3 设计 §1-§3）；
    strict/lenient 经 weft.yaml assemble_mode 配置。
    """
```

- [ ] **Step 4: 跑测试确认通过 + 全量回归**

Run: `.venv/Scripts/python.exe -m pytest tests/test_assemble.py tests/test_cli_assemble.py -q` → `10 passed`（6 + 4）
Run: `.venv/Scripts/python.exe -m pytest tests -q` → `225 passed, 1 deselected`

- [ ] **Step 5: 提交**

```bash
git add src/weft/assemble/merge.py src/weft/cli.py tests/test_assemble.py tests/test_cli_assemble.py
git commit -m "feat: assemble_project 产出项目根 paper.qmd（正文 + References + Figures/Tables）"
```

---

### Task 5: `weft/render.py` quarto 子进程封装

**Files:**
- Create: `src/weft/render.py`
- Test: `tests/test_render.py`（新建）

- [ ] **Step 1: 写失败测试（新建 tests/test_render.py）**

```python
"""render：quarto 子进程封装（M3 设计 §5）。测试全 monkeypatch，不依赖 quarto 安装。"""
import subprocess

import pytest

from weft.render import QuartoNotFoundError, QuartoRenderError, render_paper


def test_render_paper_invokes_quarto_with_defaults(monkeypatch, tmp_path):
    (tmp_path / "paper.qmd").write_text("# T\n", encoding="utf-8")
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["cwd"] = kwargs["cwd"]
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("weft.render.shutil.which", lambda name: "quarto.exe")
    monkeypatch.setattr("weft.render.subprocess.run", fake_run)
    out = render_paper(tmp_path)
    assert seen["cmd"] == ["quarto.exe", "render", "paper.qmd", "--to", "docx"]
    assert seen["cwd"] == tmp_path
    assert out == tmp_path / "paper.docx"


def test_render_paper_passes_format_through(monkeypatch, tmp_path):
    (tmp_path / "paper.qmd").write_text("# T\n", encoding="utf-8")
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("weft.render.shutil.which", lambda name: "quarto")
    monkeypatch.setattr("weft.render.subprocess.run", fake_run)
    out = render_paper(tmp_path, to="html")
    assert seen["cmd"][-1] == "html"
    assert out == tmp_path / "paper.html"


def test_render_paper_quarto_missing(monkeypatch, tmp_path):
    monkeypatch.setattr("weft.render.shutil.which", lambda name: None)
    with pytest.raises(QuartoNotFoundError, match="quarto.org"):
        render_paper(tmp_path)


def test_render_paper_quarto_failure_carries_output(monkeypatch, tmp_path):
    (tmp_path / "paper.qmd").write_text("# T\n", encoding="utf-8")
    monkeypatch.setattr("weft.render.shutil.which", lambda name: "quarto")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")

    monkeypatch.setattr("weft.render.subprocess.run", fake_run)
    with pytest.raises(QuartoRenderError, match="boom"):
        render_paper(tmp_path)


def test_render_paper_missing_paper_qmd(monkeypatch, tmp_path):
    # 钉 which 保证无 quarto 的机器也走到"缺 paper"分支（测试密封性）
    monkeypatch.setattr("weft.render.shutil.which", lambda name: "quarto")
    with pytest.raises(QuartoRenderError, match="weft assemble"):
        render_paper(tmp_path)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_render.py -q`
Expected: 5 failed（`ModuleNotFoundError: No module named 'weft.render'`）

- [ ] **Step 3: 实现 src/weft/render.py（新建）**

```python
"""quarto 子进程封装（M3 设计 §5）：渲染拼装产物（paper_file），docx 默认目标。

CLI 层模块，不 import specmodule/llm（分层红线只约束到"全项目仅 engine/ 可碰"，
本模块与 graphgen/assemble 同级为纯脚本层）。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class QuartoNotFoundError(RuntimeError):
    """quarto 可执行文件不在 PATH。"""


class QuartoRenderError(RuntimeError):
    """paper.qmd 缺失，或 quarto render 非零退出。"""


def render_paper(project_root: Path, *, paper_file: str = "paper.qmd",
                 to: str = "docx") -> Path:
    """渲染 <project_root>/<paper_file>；成功返回输出文件路径（如 paper.docx）。

    stdout/stderr 被捕获，失败时随异常携带，便于 CLI 透传。
    """
    quarto = shutil.which("quarto")
    if quarto is None:
        raise QuartoNotFoundError(
            "未找到 quarto 可执行文件；请安装 Quarto（https://quarto.org）并加入 PATH")
    paper = project_root / paper_file
    if not paper.exists():
        raise QuartoRenderError(f"未找到 {paper_file}，请先运行 weft assemble")
    completed = subprocess.run(
        [quarto, "render", paper_file, "--to", to],
        cwd=project_root, capture_output=True, text=True,
        encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise QuartoRenderError(
            f"quarto render 失败（退出码 {completed.returncode}）：{detail}")
    return paper.with_suffix(f".{to}")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_render.py -q`
Expected: `5 passed`

- [ ] **Step 5: 提交**

```bash
git add src/weft/render.py tests/test_render.py
git commit -m "feat: render.py quarto 子进程封装（docx 默认目标）"
```

---

### Task 6: CLI `weft render`

**Files:**
- Modify: `src/weft/cli.py`（assemble 命令之后追加）
- Test: `tests/test_cli_render.py`（新建）

- [ ] **Step 1: 写失败测试（新建 tests/test_cli_render.py）**

```python
"""weft render 命令：默认参数与 paper_file 传参、--to 透传、错误退出码、加载闸门。"""
from typer.testing import CliRunner

from weft.cli import app
from weft.render import QuartoNotFoundError, QuartoRenderError
from tests.helpers import make_minimal_project, write_yaml

runner = CliRunner()


def test_render_invokes_wrapper_with_defaults(monkeypatch, tmp_path):
    make_minimal_project(tmp_path)
    seen = {}

    def fake_render(root, *, paper_file, to):
        seen["root"] = root
        seen["paper_file"] = paper_file
        seen["to"] = to
        return root / "paper.docx"

    monkeypatch.setattr("weft.render.render_paper", fake_render)
    result = runner.invoke(app, ["render", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "已生成 paper.docx" in result.output
    assert seen["paper_file"] == "paper.qmd"
    assert seen["to"] == "docx"
    assert seen["root"] == tmp_path.resolve()   # load_project 内部 resolve


def test_render_uses_paper_file_config(monkeypatch, tmp_path):
    make_minimal_project(tmp_path)
    write_yaml(tmp_path / "weft.yaml", {"paper_file": "manuscript.qmd"})
    seen = {}

    def fake_render(root, *, paper_file, to):
        seen["paper_file"] = paper_file
        return root / "manuscript.docx"

    monkeypatch.setattr("weft.render.render_paper", fake_render)
    result = runner.invoke(app, ["render", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert seen["paper_file"] == "manuscript.qmd"


def test_render_to_option_passthrough(monkeypatch, tmp_path):
    make_minimal_project(tmp_path)
    seen = {}

    def fake_render(root, *, paper_file, to):
        seen["to"] = to
        return root / "paper.html"

    monkeypatch.setattr("weft.render.render_paper", fake_render)
    result = runner.invoke(app, ["render", "--to", "html", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert seen["to"] == "html"


def test_render_quarto_missing_exits_1(monkeypatch, tmp_path):
    make_minimal_project(tmp_path)

    def fake_render(root, *, paper_file, to):
        raise QuartoNotFoundError("未找到 quarto 可执行文件")

    monkeypatch.setattr("weft.render.render_paper", fake_render)
    result = runner.invoke(app, ["render", str(tmp_path)])
    assert result.exit_code == 1
    assert "ERROR 未找到 quarto 可执行文件" in result.output


def test_render_error_exits_1_with_detail(monkeypatch, tmp_path):
    make_minimal_project(tmp_path)

    def fake_render(root, *, paper_file, to):
        raise QuartoRenderError("quarto render 失败（退出码 1）：boom")

    monkeypatch.setattr("weft.render.render_paper", fake_render)
    result = runner.invoke(app, ["render", str(tmp_path)])
    assert result.exit_code == 1
    assert "boom" in result.output


def test_render_load_errors_exits_1(tmp_path):
    result = runner.invoke(app, ["render", str(tmp_path)])
    assert result.exit_code == 1
    assert "E-NOT-A-PROJECT" in result.output
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cli_render.py -q`
Expected: 6 failed（typer 无 render 命令，`exit_code == 2`）

- [ ] **Step 3: 实现 cli.py 的 render 命令（assemble 命令之后追加）**

```python
@app.command()
def render(
    project_dir: Path = typer.Argument(Path("."), help="weft 项目根目录"),
    to: str = typer.Option("docx", "--to", help="目标格式（quarto --to，默认 docx）"),
) -> None:
    """渲染拼装产物（weft.yaml paper_file，默认 paper.qmd）→ 目标格式。

    需先 weft assemble；不重复校验闸门（assemble 已闸），仅要求项目可加载。
    """
    from weft import render as render_mod

    project, load_diags = load_project(project_dir)
    if any(d.is_error for d in load_diags):
        _print_diagnostics(load_diags)
        raise typer.Exit(code=1)
    try:
        out_path = render_mod.render_paper(project.root,
                                           paper_file=project.paper_file, to=to)
    except (render_mod.QuartoNotFoundError, render_mod.QuartoRenderError) as exc:
        typer.echo(f"ERROR {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"已生成 {out_path.relative_to(project.root).as_posix()}")
```

- [ ] **Step 4: 跑测试确认通过 + 全量回归**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cli_render.py -q` → `6 passed`
Run: `.venv/Scripts/python.exe -m pytest tests -q` → `236 passed, 1 deselected`

- [ ] **Step 5: 提交**

```bash
git add src/weft/cli.py tests/test_cli_render.py
git commit -m "feat: CLI weft render 命令（docx 默认目标）"
```

---

### Task 7: 样例项目迁移 assets/ 约定 + paper.qmd 黄金文件

**Files:**
- Move: `examples/paper-demo/references.bib` → `examples/paper-demo/assets/references.bib`
- Create: `examples/paper-demo/assets/style.csl`、`examples/paper-demo/assets/template.docx`
- Create: `examples/paper-demo/figures/fig-01.png`（fig-01a.png 副本）
- Rewrite: `examples/paper-demo/_quarto.yml`
- Test: `tests/test_example_project.py`（+1 黄金测试、改全链路测试）、`tests/golden/paper.qmd`（新建）

- [ ] **Step 1: 迁移 assets 三件套**

```bash
cd "C:/Users/xingy/Desktop/开发/weft/.worktrees/m3-render"   # 全程在 worktree 内执行
mkdir -p examples/paper-demo/assets
git mv examples/paper-demo/references.bib examples/paper-demo/assets/references.bib
curl -sL -o examples/paper-demo/assets/style.csl \
  https://raw.githubusercontent.com/citation-style-language/styles/master/elsevier-with-titles.csl
head -c 80 examples/paper-demo/assets/style.csl   # 应见 <?xml / <style
```

若网络不可用：换任意本地可得的合法 CSL（如 Zotero 安装目录内的 elsevier-with-titles.csl），并在设计决策表记录来源；不得伪造空文件。

template.docx 用 quarto/pandoc 默认参考文档生成（python 子进程落盘，规避 Windows shell 二进制重定向风险）：

```bash
"C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe" -c "
import subprocess
from pathlib import Path
out = subprocess.run(['quarto', 'pandoc', '--print-default-data-file', 'reference.docx'],
                     capture_output=True, check=True).stdout
Path('examples/paper-demo/assets/template.docx').write_bytes(out)
print(len(out))
"
"C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe" -c "import zipfile; print(zipfile.is_zipfile('examples/paper-demo/assets/template.docx'))"
```

Expected: 打印非零字节数，随后 `True`。

- [ ] **Step 2: 重写 _quarto.yml 与补键级图**

`examples/paper-demo/_quarto.yml` 整体替换为设计 §4 固定写法（**不得出现 reference-section-title**，见设计决策 5）：

```yaml
project:
  type: default

bibliography: assets/references.bib

csl: assets/style.csl

format:
  docx:
    reference-doc: assets/template.docx
```

键级图（paper.qmd Figures 节按 figures.yaml 键引用；子图级 refs 与既有文件保持原样，见设计决策 10）：

```bash
cp examples/paper-demo/figures/fig-01a.png examples/paper-demo/figures/fig-01.png
```

- [ ] **Step 3: 写黄金测试（tests/test_example_project.py 追加）并改全链路测试**

追加黄金测试（人工写死的草稿保证字节确定，不依赖 mock 客户端输出）：

```python
def test_sample_assemble_paper_qmd_matches_golden(tmp_path):
    # M3 验收：正文 + References + Figures/Tables 三部分、字节确定（黄金比对；
    # golden 侧做 CRLF→LF 归一，防 Windows autocrlf 检出差异）
    work = _copy_sample(tmp_path)
    (work / "drafts").mkdir()
    (work / "drafts" / "sec-03.md").write_text(
        "<!-- weft:node=para-03-01 uses=fact-01 -->\n"
        "60 °C 的初始反应速率比 25 °C 高 42%（[@smith2020]）。\n", encoding="utf-8")
    (work / "drafts" / "sec-04.md").write_text(
        "<!-- weft:node=para-04-01 -->\n结果与热激活催化机制的解释一致。\n",
        encoding="utf-8")
    result = runner.invoke(app, ["assemble", str(work)])
    assert result.exit_code == 0, result.output
    raw = (work / "paper.qmd").read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    golden = (GOLDEN / "paper.qmd").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert raw.decode("utf-8") == golden
```

`test_sample_draft_then_assemble_full_chain` 整体替换（末尾补 paper.qmd 断言）：

```python
def test_sample_draft_then_assemble_full_chain(tmp_path):
    # v1.1 §7 回归：样例迁移后 draft --mock/assemble 链路（validate/graph 由兄弟测试覆盖）
    work = _copy_sample(tmp_path)
    assert runner.invoke(app, ["draft", "sec-03", "--mock", str(work)]).exit_code == 0
    # sec-04 的 para-04-01 approved 但无草稿 → strict 会报错；lenient 跳过
    write_yaml(work / "weft.yaml", {"assemble_mode": "lenient"})
    result = runner.invoke(app, ["assemble", str(work)])
    assert result.exit_code == 0, result.output
    part_qmd = work / "generated" / "03-results" / "part-01.qmd"
    assert part_qmd.exists()
    merged = (work / "generated" / "03-results.qmd").read_text(encoding="utf-8")
    assert "# results" in merged and "## Results" in merged
    paper = (work / "paper.qmd").read_text(encoding="utf-8")
    assert "# References {.unnumbered}" in paper and "# Figures {.unnumbered}" in paper
```

- [ ] **Step 4: 跑黄金测试确认失败（golden 文件未建）**

Run: `.venv/Scripts/python.exe -m pytest tests/test_example_project.py::test_sample_assemble_paper_qmd_matches_golden -q`
Expected: 1 failed（`FileNotFoundError: ... golden\\paper.qmd`）

- [ ] **Step 5: 生成并核对黄金文件（先落盘实际产物，人工逐行核对后入库）**

```bash
PYTHONPATH=src "C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe" -c "
import shutil, tempfile
from pathlib import Path
tmp = Path(tempfile.mkdtemp())
work = tmp / 'proj'
shutil.copytree('examples/paper-demo', work)
(work / 'drafts').mkdir()
(work / 'drafts' / 'sec-03.md').write_text(
    '<!-- weft:node=para-03-01 uses=fact-01 -->\n'
    '60 °C 的初始反应速率比 25 °C 高 42%（[@smith2020]）。\n', encoding='utf-8')
(work / 'drafts' / 'sec-04.md').write_text(
    '<!-- weft:node=para-04-01 -->\n结果与热激活催化机制的解释一致。\n', encoding='utf-8')
from weft.store.loader import load_project
from weft.assemble import assemble_project
project, diags = load_project(work)
assert not diags, diags
written, asm_diags = assemble_project(project)
assert not asm_diags, asm_diags
print((work / 'paper.qmd').read_text(encoding='utf-8'))
"
```

人工核对输出与下方预期**逐字节一致**后，将其原样（LF、单尾换行）写入 `tests/golden/paper.qmd`：

```markdown
# results

## Results

60 °C 的初始反应速率比 25 °C 高 42%（[@smith2020]）。

# discussion

## Discussion

结果与热激活催化机制的解释一致。

# References {.unnumbered}

::: {#refs}
:::

# Figures {.unnumbered}

![](figures/fig-01.png)

**Fig. 1** 不同温度下的反应速率随时间变化。误差线表示三次重复的标准差。

# Tables {.unnumbered}

**Table 1** 各温度条件下的反应条件与初始速率汇总。
```

（依据：03-results/04-discussion 均为 chapter 直下 part → 标题级别 ##；figures.yaml 键序 fig-01 → Fig. 1、tbl-01 → Table 1；caption 取自 `examples/paper-demo/metadata/figures.yaml`。）

编辑器保存后把黄金文件统一为 LF、单尾换行（核对打印的尾部应为 `汇总。\n'`）：

```bash
"C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe" -c "
from pathlib import Path
p = Path('tests/golden/paper.qmd')
text = p.read_text(encoding='utf-8').replace('\r\n', '\n')
p.write_text(text, encoding='utf-8', newline='\n')
print(repr(text[-30:]))
"
```

- [ ] **Step 6: 跑样例全套 + 全量回归**

Run: `.venv/Scripts/python.exe -m pytest tests/test_example_project.py -q` → `6 passed`（5 既有 + 1 新增；validate 仍 0 错误 0 提醒）
Run: `.venv/Scripts/python.exe -m pytest tests -q` → `237 passed, 1 deselected`

- [ ] **Step 7: 人工渲染冒烟（验收路径，非测试）**

```bash
SMOKE=$(mktemp -d) && cp -r examples/paper-demo "$SMOKE/proj" && cd "$SMOKE/proj"
mkdir -p drafts
printf '<!-- weft:node=para-03-01 uses=fact-01 -->\n样例段落一（[@smith2020]）。\n' > drafts/sec-03.md
printf '<!-- weft:node=para-04-01 -->\n样例段落二。\n' > drafts/sec-04.md
WT="C:/Users/xingy/Desktop/开发/weft/.worktrees/m3-render"
PYTHONPATH="$WT/src" "C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe" -c "
import sys; sys.argv = ['weft', 'assemble', '.']
from weft.cli import app; app()"
PYTHONPATH="$WT/src" "C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe" -c "
import sys; sys.argv = ['weft', 'render', '.']
from weft.cli import app; app()"
ls -la paper.docx
```

（worktree 无 `.venv`，不能直接用主仓库 `weft.exe`——其 editable 安装指回 main 的 src，不含本分支新功能；用 `PYTHONPATH=<worktree>/src` 的 python shim 调 CLI。）

Expected: `weft assemble` 退出码 0 并列出 paper.qmd；`weft render` 打印 `已生成 paper.docx`。打开 docx 目检（citeproc 默认只渲染被引条目，见设计决策 12）：References 下有 smith2020 的数字条目（elsevier-with-titles 样式，正文 `[1]`）；未引用的 doe2021 不出现；Figures 里有图与 `Fig. 1` 图注；Tables 有 `Table 1` 图注。冒烟产生的 `drafts/` 在临时目录，不入库。

- [ ] **Step 8: 提交**

```bash
cd "C:/Users/xingy/Desktop/开发/weft/.worktrees/m3-render"
git add examples/paper-demo tests/golden/paper.qmd tests/test_example_project.py
git commit -m "chore: 样例项目迁移 assets/ 投稿资源约定并登记 paper.qmd 黄金文件"
```

---

### Task 8: 文档收尾 + 全量回归

**Files:**
- Modify: `docs/roadmap.md`（M3 状态）
- Modify: `AGENTS.md`（CLI 清单 + 必读文档）

- [ ] **Step 1: roadmap.md 更新**

"当前状态"段改为 v1.1 与 M3 均已合入的表述（M3 渲染层完成，剩 M4）；"M3 渲染层"标题改为 `## M3 渲染层 ✅（2026-09-02 合入 main）`，三条 ⬜ 项改 ✅ 并按实际交付微调措辞（paper.qmd 拼接、assets 约定、`render.py` + `weft render` docx 默认）；保留"动工冒烟钉死三个 Quarto 行为"的结论一句（见设计决策 11）。

- [ ] **Step 2: AGENTS.md 更新**

- 常用命令注释行：`# CLI：validate / graph / review / draft / assemble` → 追加 `/ render`。
- 必读文档列表追加一行：`docs/superpowers/specs/2026-09-02-weft-m3-render-design.md — M3 渲染层设计定案（paper.qmd 拼接、References refs div、Figures 字面编号、assets 约定）`。

- [ ] **Step 3: 全量回归（最终计数）**

Run: `.venv/Scripts/python.exe -m pytest tests -q`
Expected: `237 passed, 1 deselected`

- [ ] **Step 4: 提交**

```bash
git add docs/roadmap.md AGENTS.md
git commit -m "docs: M3 渲染层收尾——roadmap/AGENTS 更新"
```

合回 main（AGENTS 工作流约定）：

```bash
cd "C:/Users/xingy/Desktop/开发/weft"
git merge --no-ff m3-render -m "feat: M3 渲染层——paper.qmd 拼接、assets 约定、weft render（合 m3-render）"
git worktree remove .worktrees/m3-render
git branch -d m3-render
```

---

## 自查记录（Self-Review）

- **Spec 覆盖**：设计 §1 拼接与 paper_file（Task 2/3/4）、§2 References 定位 div（Task 3，`_quarto.yml` 无 reference-section-title 见 Task 7 模板）、§3 Figures/Tables 字面编号与不走 crossref（Task 3）、§4 assets 三件套与样例迁移（Task 7）、§5 实现范围（assemble 扩展 Task 4、render.py+CLI Task 5/6、无新增校验、黄金比对 Task 7、动工冒烟 Task 1）、§6 明确不做（范围裁定）——逐条有任务。
- **占位符扫描**：无 TBD/TODO；所有代码步骤含完整代码与预期输出。
- **类型一致性**：`assemble_paper(project: Project, chapter_texts: list[str]) -> str`（Task 3 定义、Task 4 调用）；`render_paper(project_root, *, paper_file, to) -> Path`（Task 5 定义、Task 6 调用）；`Project.paper_file: str = "paper.qmd"`（Task 2 定义、Task 4/6 使用）；异常名 `QuartoNotFoundError`/`QuartoRenderError` 两处一致。
