# weft 使用手册

> weft —— 元数据为经线、叙事流为纬线的 AI 学术写作引擎。
> 本手册面向 weft 的日常使用者，覆盖从建项目到导出投稿稿的完整流程。
> 内容基于 weft 0.1.0（数据结构 v1 冻结 + v1.1 增补 + draft v2 管线）。

---

## 目录

1. [核心理念](#1-核心理念)
2. [安装与环境要求](#2-安装与环境要求)
3. [五分钟上手](#3-五分钟上手)
4. [项目目录结构](#4-项目目录结构)
5. [元数据卡片（经线）](#5-元数据卡片经线)
6. [叙事流（纬线）](#6-叙事流纬线)
7. [命令参考](#7-命令参考)
8. [生成管线详解](#8-生成管线详解)
9. [灵感式写作（inspire → replace）](#9-灵感式写作inspire--replace)
10. [配置文件](#10-配置文件)
11. [诊断码总表](#11-诊断码总表)
12. [常见工作流与最佳实践](#12-常见工作流与最佳实践)
13. [已知限制](#13-已知限制)

---

## 1. 核心理念

weft 把一篇论文拆成两个正交的层面：

- **经线：元数据卡片**（`metadata/` 下的原子 Markdown+YAML 卡）。data / fact / claim / note / method / param 六类卡，每张卡只承载一个最小事实单元。**人写、人审**。
- **纬线：叙事流**（`narrative/<chapter>/…/part-*.md`）。每个 part 由若干**节点**组成，节点声明"本段用哪些卡、按什么逻辑组织"。**人写、人审**。

分工铁律：**人只审卡片与叙事流，AI 只写 `drafts/` 与 `generated/`**。AI 从不改动你的卡片和叙事文件；你也不必手写正文——正文由生成与拼装流水线产出。

质量保障是三道闸门：

1. **加载永不中断**：单卡解析失败转为 `E-PARSE` 诊断后继续加载，一次看全所有问题；
2. **校验闸门**：`weft validate` 汇报全部错误（阻断）与提醒（不阻断），任何 error 都会挡住下游命令；
3. **生成硬规则**：生成中引文必须真实存在于 bib、占位符不得越界，违反即整体失败且不落盘（fail-closed）。

---

## 2. 安装与环境要求

| 依赖 | 要求 | 用途 |
|------|------|------|
| Python | ≥ 3.11 | 运行 weft |
| Quarto | 需安装并加入 PATH | 仅 `weft render` 需要 |
| LLM 配置 | config.json + .env | `weft draft` / `weft inspire` 真实生成需要（可用 `--mock` 免 key） |

安装（项目根目录执行）：

```bash
.venv/Scripts/python.exe -m pip install -e ".[dev]"   # Windows venv
# 或通用写法
python -m pip install -e .
```

安装后得到 `weft` 命令（入口 `weft.cli:app`）。查看帮助：

```bash
weft --help
weft <命令> --help
```

Windows 注意：weft 已自动把 stdout/stderr 切到 UTF-8，中文诊断在任意终端编码下均不会乱码；所有生成文件固定 LF 换行。

---

## 3. 五分钟上手

```bash
# ① 建项目骨架（目标目录必须为空，否则拒绝写入）
weft init my-paper
cd my-paper

# ② 写元数据卡片与叙事节点（第 5、6 节），然后自查
weft validate        # 0 错误 0 提醒为理想态；错误必须清零

# ③ 看还剩哪些没审
weft review          # 列出所有 status: draft 的卡与节点

# ④ 把卡片和节点 frontmatter 里的 status 改成 approved 后，生成该 part 的段落草稿
weft draft sec-01    # 产物：drafts/sec-01.md

# ⑤ 全部 part 生成完后，拼装成 Quarto 文档
weft assemble        # 产物：generated/**/*.qmd + paper.qmd

# ⑥ 渲染成投稿稿
weft render          # 默认 --to docx，产出 paper.docx
```

辅助命令：

```bash
weft graph           # 反向索引 + 孤儿实体报告（generated/graph.json 等）
weft missing-cites   # 列出缺文献的 cited 卡
weft inspire         # 把一段灵感笔记自动拆成草稿卡（见第 9 节）
```

---

## 4. 项目目录结构

`weft init` 生成的骨架：

```
my-paper/
├── _quarto.yml            # Quarto 配置：bibliography / csl / format
├── weft.yaml              # weft 配置：figures_dir / assemble_mode / paper_file
├── index.qmd              # Quarto 主文档（标题；正文不写在这里）
├── overview.md            # 研究总述：注入每次生成的全文背景
├── assets/
│   └── references.bib     # 文献库（唯一引用来源）
├── figures/               # 图表文件：<ref>.png 或 .pdf
├── inspirations/          # 灵感收件箱（第 9 节）
├── metadata/              # —— 经线：全部元数据卡（人写人审）——
│   ├── figures.yaml       # 图注注册表
│   ├── data/              # data 卡
│   ├── facts/             # fact 卡
│   ├── notes/             # note 卡（id = bib key）
│   ├── methods/           # method 卡（slug 命名）
│   │   └── params/        # param 卡（位于 methods 子目录！）
│   └── claims/
│       ├── cited/         # claim_type: cited 的 claim 卡
│       └── uncited/       # claim_type: uncited 的 claim 卡
└── narrative/             # —— 纬线：叙事流（人写人审）——
    └── 01-introduction/
        └── part-01.md
```

运行期产生的目录（受 weft 管理，一般不手工编辑）：

| 目录 | 产生者 | 内容 |
|------|--------|------|
| `drafts/` | `weft draft` | 每个 part 一个段落草稿文件，带溯源注释 |
| `generated/` | `weft graph` / `assemble` / `inspire` | 反向索引、拼装 qmd、paper.qmd、灵感报告与运行快照 |
| `inspirations/proposals/` | `weft inspire` | 替换提案（审后用 `weft replace` 应用） |
| `inspirations/processed/` | `weft inspire` | 已处理灵感的原文归档 |
| `archive/cards/<类型>/` | `weft replace` | 被替换下来的旧卡 |

约定：

- **part 文件必须位于 `narrative/<chapter>/` 子目录**（至少一层章目录；可再建子节目录多级嵌套）。章/子节目录名带数字前缀（`01-introduction`）决定拼装顺序，前缀数字不进标题。
- 六类卡共用一个**全局 id 命名空间**：任何卡的 id 都不能与其它卡重复。
- `claim_type` 必须与所在目录一致（cited 卡放 `claims/cited/`，uncited 放 `claims/uncited/`），否则 `E-CLAIM-DIR-MISMATCH`。
- **卡片文件名必须等于卡 id**（`fact-01.md` 的 id 必须是 `fact-01`），否则 `E-FILENAME-MISMATCH`。
- v1 时代的扁平 part 文件（直接放在 `narrative/` 下）需先迁移：`python -m weft.migrations.v1_1`。

---

## 5. 元数据卡片（经线）

所有卡片共用三个字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | str | 全局唯一；必须与文件名一致 |
| `status` | `draft` / `approved` / `rejected` | 审阅状态。**只有 approved 的卡才会进入生成**；rejected 卡豁免全部提醒类校验（错误不豁免） |
| `comment` | str | 审阅备注，可空 |

YAML 未知键一律报错（`extra="forbid"`）——拼错字段名会被 `E-PARSE` 抓住，而不是被静默忽略。

### 5.1 data 卡 —— `metadata/data/<id>.md`

一条数据集（一次实验、一组测量）的描述。

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

| 字段 | 说明 |
|------|------|
| `refs` | 子图级 Quarto label 列表（如 `fig-01a`、`tbl-01`），必须先在 `figures.yaml` 注册，可为空 |
| `source` | 原始数据来源（任意路径/说明），可省 |
| `description` | 数据描述；会随 fact 进入生成提示，写清楚"是什么、怎么测" |

### 5.2 fact 卡 —— `metadata/facts/<id>.md`

从数据中读出的一个**事实陈述**。`data` 为空在模型层即非法。

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

| 字段 | 说明 |
|------|------|
| `data` | ≥ 1 个 data 卡 id（哪些数据支持这条事实） |
| `statement` | 事实陈述；AI 只能原样使用，不得改写数值 |
| `supports` | 该事实支持的 claim 卡 id 列表，可空 |

### 5.3 claim 卡 —— `metadata/claims/{cited|uncited}/<id>.md`

论文要主张的一个**论断**。单一 `claim_type` 属性决定引文机制：

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

| 字段 | 说明 |
|------|------|
| `claim_type` | `uncited`：本研究内部推理得到的论断，**禁止带任何 [@key]**；`cited`：需要文献支撑的论断 |
| `cites` | bib key 列表（`cited` 时必填；为空只提醒 `W-CLAIM-CITED-NO-CITES`，生成时该处占位符会被移除并提醒缺文献） |
| `statement` | 论断陈述 |

配套提醒：`uncited` claim 若没有任何非 rejected 的 fact 支持它 → `W-CLAIM-UNSUPPORTED`。

### 5.4 note 卡 —— `metadata/notes/<bibkey>.md`

**id 就是 bib key** 的阅读笔记。它的 summary 是 AI 行文时对这条文献的唯一了解来源。

```markdown
---
id: doe2021
summary: "Doe 等报道了 Pt 基催化体系在 25–80 °C 区间的速率数据，表观活化能 52 kJ/mol，可作为本工作的对照体系。"
status: approved
comment: ""
---
```

- note 的 id 必须真实存在于 bib（`E-NOTE-NOT-IN-BIB`）。
- summary 缺省容忍但会提醒 `W-NOTE-NO-SUMMARY`——没有 summary，AI 在该引文处只能凭 bib 条目行文。
- 反向提醒：某 bib key 被引用（claim.cites / derived_from）但没建 note 卡 → `W-NOTE-MISSING`。

### 5.5 method 卡 —— `metadata/methods/<slug>.md`

无参数的**操作协议**，库级复用载体（同一方法跨项目复制文件即可）。slug 命名（如 `qpcr-ddct`），并入全局 id 命名空间。

```markdown
---
id: qpcr-ddct
statement: "以管家基因归一化的 ΔΔCt 相对定量法。"
protocol: |
  1. 反应体系 20 μL …
  2. 三步法 40 循环 …
derived_from: [livak2001]
status: approved
comment: ""
---
```

| 字段 | 说明 |
|------|------|
| `protocol` | 操作协议全文（编号步骤） |
| `derived_from` | 方法出处 bib key（语义同 cites） |

### 5.6 param 卡 —— `metadata/methods/params/<slug>.md`

**本项目具体实验参数**（每篇论文不同、需逐项核对的事实）。注意目录是 `methods/params/` 子目录，沿用"目录名 = 属性"模式。

```markdown
---
id: param-qpcr-main
method: qpcr-ddct
values:
  酶: "TB Green Premix"
  变性温度: "95 °C"
  循环数: 40
derived_from: []
status: approved
comment: ""
---
```

| 字段 | 说明 |
|------|------|
| `method` | 所属 method 卡 id；悬空是校验错误（`E-DANGLING-REF`） |
| `values` | 自由键值字典；AI 行文时数值与单位必须与这里完全一致 |

### 5.7 figures.yaml —— 图注注册表

`metadata/figures.yaml`：人工直接维护、无 status 字段、解析宽松（未知键忽略）。

```yaml
fig-01:
  caption: "不同温度下的反应速率随时间变化。误差线表示三次重复的标准差。"
  subfigs:
    a: "60 °C 下的速率曲线"
    b: "25 °C 下的速率曲线"
tbl-01:
  caption: "各温度条件下的反应条件与初始速率汇总。"
```

- **顶层键 = Quarto label**。data 卡 `refs` 引用的合法值 = 顶层键 ∪ 键+子图后缀（`fig-01`、`fig-01a`…）。
- **图文件校验是逐 ref 的**：data 卡 refs 里出现的每个 `fig-*` label（含子图 label）都要求 `figures/<label>.png` 或 `.pdf` 存在（缺了只是提醒 `W-FIGURE-FILE-MISSING`）；`tbl-*` 是表格排版产物，不检查文件。paper.qmd 的 Figures 节嵌入的则是**主键**图 `figures/<key>.png`（如上例最终嵌 `fig-01.png`，子图文件用于校验与生成提示的图注）。
- 键序即编号：拼装时 `fig-*` 依键序编为 `Fig. 1, 2, …`，`tbl-*` 编为 `Table 1, 2, …`（Fig 与 Table 分开计数）。**想调图表编号就调键序**。

---

## 6. 叙事流（纬线）

### 6.1 part 文件

`narrative/<chapter>/part-*.md` 是**生产与寻址单位**：位置由目录路径 + 文件名前缀决定，`weft draft <part_id>` 按 frontmatter 里的 `id` 寻址。

```markdown
---
id: sec-03
section: Results
nodes:
- id: para-03-01
  purpose: describe
  uses:
  - id: fact-01
    role: evidence
  - id: claim-01
    role: conclusion
  logic: 先报告主结果（温度对速率的影响，引用 fig-01a/b），再给出结论句
  status: approved
  comment: ''
- id: para-03-02
  purpose: describe
  uses:
  - id: fact-02
    role: evidence
  logic: 报告产率汇总（tbl-01），说明温度不影响产率
  status: draft
  comment: ''
---
审阅备注可以写在正文区（不进入任何产物）。
```

frontmatter 字段：

| 字段 | 说明 |
|------|------|
| `id` | part id，全局唯一；`weft draft` 的寻址单位 |
| `section` | 该 part 的节标题文本（拼装时的标题） |
| `workflow` | 可选。显式指定生成工作流（`introduction`/`methods`/`results`/`discussion`）；不合法的值是错误 `E-WORKFLOW-UNKNOWN` |
| `nodes` | 节点列表，**每个节点 = 一段正文** |

### 6.2 节点字段

| 字段 | 说明 |
|------|------|
| `id` | 节点 id，全局唯一（`para-03-01` 风格） |
| `purpose` | 本段写作意图，软词表：`describe` / `interpret` / `compare` / `transition`。越表只提醒 `W-PURPOSE-VOCAB` |
| `uses` | 本段引用的实体：`{id, role}` 列表。合法目标是 fact / claim / method / param；悬空引用是错误 `E-DANGLING-REF` |
| `role` | 该卡在本段论证中的角色，软词表：`evidence` / `conclusion` / `comparison` / `background` / `counterpoint`。越表只提醒 `W-ROLE-VOCAB` |
| `logic` | 本段叙事策略（给 AI 的行文依据），建议写清组织顺序与侧重 |
| `status` | 节点审阅状态；**只有 approved 节点会被生成与拼装** |
| `comment` | 审阅备注 |

关于 `role` 与卡片自身语义的关系：卡片类型（fact/claim）回答"这条内容**是什么**"，是全局固有属性；`role` 回答"它**在本段论证里起什么作用**"，是局部使用关系。同一张卡被多个段落引用时可以在不同段落扮演不同角色（如同一 cited claim 在引言作 `background`、在讨论作 `counterpoint`）——这正是把该语义放在使用点而不是卡上的原因。`role` 与 `purpose` 都只是给生成模型的提示信号，不参与任何硬校验。

素材完备性：fact/claim 卡会以**全文**进入生成提示（fact 附所引 data 的描述与图注、claim 附分类与 cites/note 摘要）；method/param 卡当前合法但全文不进入生成提示（见第 13 节）。**没写进卡里的内容 AI 一概不知道**，也不会被写进正文（校验项：不得引入 uses 之外的事实）。

### 6.3 生成风格路由（chapter → workflow）

`weft draft` 对每个 part 选择一种工作流，决定提示词风格与采样温度：

| 工作流 | 匹配方式 | 温度 | 风格 |
|--------|----------|------|------|
| `introduction` | 目录名剥数字前缀后以 `introduction` 开头，或 `workflow` 显式指定 | 0.5 | 综述性正文，依据 claim 卡 |
| `methods` | 同上，`methods` 开头 | 0.2 | 格式化展开协议与参数，几乎不"创作"，不写引注 |
| `results` | 同上，`results` 开头；**也是兜底默认** | 0.3 | 报告结果 |
| `discussion` | 同上，`discussion` 开头 | 0.6 | 对比、解释与归因 |

判定顺序：part 显式 `workflow` 字段 → 章目录名前缀匹配 → `results` 兜底。显式值拼错是 fail-closed 错误（`E-WORKFLOW-UNKNOWN`），不会静默落到 results。

---

## 7. 命令参考

所有命令的 `<project_dir>` 缺省为当前目录。退出码约定：**0 = 成功（有提醒也算成功）；1 = 失败（任何 error / 闸门拒绝 / 生成失败）**。

诊断输出格式：

```
ERROR <路径> [<码>] 字段 <字段>: <消息>
WARN  <路径> [<码>] 字段 <字段>: <消息>
```

### weft init

```
weft init [项目目录]        # 缺省当前目录
```

生成最小合法项目骨架（第 4 节的目录树），init 后即可通过 `weft validate`（0 错误 0 提醒）。目标目录已存在且**非空**（或是文件）→ 报 `E-INIT-COLLISION`，退出码 1，**不写入任何文件**。

### weft validate

```
weft validate [project_dir]
```

运行全部校验（第 11 节），打印所有诊断与汇总行 `—— N 个错误，M 个提醒`；有错误退出码 1。这是使用最频繁的命令——每次改完卡/叙事都应跑一遍。

### weft review

```
weft review [project_dir]
```

按类型列出所有 `status: draft` 的待办：**data / fact / claim / note 四类实体卡**与全部叙事节点（method/param 卡暂不在列，可用 `weft validate` 的孤儿报告辅助检查）。项目加载失败（error 级诊断）退出码 1。

### weft graph

```
weft graph [project_dir]
```

校验通过后生成三份反向索引产物：

- `generated/graph.json` —— 全量实体反向索引（含 rejected；每实体含 `kind`/`status`/`referenced_by{facts,claims,methods,params,nodes}`）；
- `generated/used-metadata.json` —— 被叙事流引用的实体集合；
- `generated/orphans.md` —— 孤儿实体报告（未被任何叙事节点引用，含间接可达）。

可达语义：种子 = 节点 uses 直接引用的 fact/claim/method/param；扩展边 = fact.data → data、fact.supports → claim、param.method → method。校验有错误时拒绝生成（退出码 1）。

### weft draft

```
weft draft <part_id> [project_dir] [--mock]
```

对指定 part 内**每个 approved 节点**依次执行六节点生成管线（第 8 节），段落按节点序写入 `drafts/<part_id>.md`（该文件每次全量重写）。

前置闸门（全部通过才开始生成，否则退出码 1 且不写任何文件）：

1. `validate` 无 error；
2. part id 存在（否则 `E-PART-NOT-FOUND`）；
3. part 内至少一个 approved 节点（否则 `E-NOTHING-TO-DRAFT`）。

运行期行为：

- `overview.md` 作为研究总述注入每次生成的全文背景（没有该文件也能跑）；
- 跨段上下文：本 part 已生成的段落 + **前一个 part 草稿文件的末段**（按 narrative 目录序，所以生成整个项目时按章序逐 part 执行 `weft draft` 即可获得自然衔接）；
- 硬规则在 run 内抛错 → 退出码 1 且 **drafts 零写入**（fail-closed）：占位符越界（`E-DRAFT-USES`）、残余未解析占位符（`E-DRAFT-SHAPE`）、正文出现不在 bib 的 `[@key]`（`E-CITE-NOT-IN-BIB`）；
- LLM 输出不合 schema / harness 失败 → `E-DRAFT-SHAPE` / `E-DRAFT-FAILED`，退出码 1；
- 软提醒（如 `W-REF-EMPTY` 图表未关联、`W-CITES-EMPTY` cited claim 缺文献）打印为 WARN，不阻断。

`--mock`：使用内置假客户端（免 API key），用于体验管线流程与调试。

### weft assemble

```
weft assemble [project_dir]
```

纯脚本无 LLM。把已批准草稿拼装成 Quarto 文档：

- **part 级**：`generated/narrative/<chapter>/…/part-NN.qmd`（镜像 narrative 目录树）；part 标题级别 = 目录深度 + 1（章 = `#`）；
- **章级**：`generated/<chapter>.qmd`，标题文本 = 目录名剥数字前缀、`-`/`_` 转空格；
- **项目级**：`paper.qmd`（或 `weft.yaml paper_file`）= 各章正文（目录序）+ References 定位块 + Figures/Tables。

拼装规则：

- 只取 **approved 节点**的段落，按 `<!-- weft:node=… -->` 溯源注释切块；**输出不含任何 weft 注释**；
- References 只写 citeproc 定位 div（`::: {#refs}`），条目由 Quarto 依 `_quarto.yml` 的 bibliography 生成；
- Figures / Tables 节由 figures.yaml 确定性生成：`Fig. N` 配 `figures/<key>.png` 图与 caption，`Table N` 配 caption，键序即编号；无图则省略相应节；
- **strict 模式**（默认）：approved 节点缺草稿段 → `E-ASSEMBLE-MISSING-DRAFT`，该 part 跳过、其余照常，最后退出码 1；**lenient**（`weft.yaml assemble_mode: lenient`）：只跳过缺段节点，不报错；
- `paper.qmd` 恒产出（即使 strict 有失败项，便于部分预览）。

手工润色的合法姿势：直接编辑 `drafts/<part>.md` 里注释之后的段落文本（保留注释行），再 `weft assemble` 即可让手改进入成稿。

### weft render

```
weft render [project_dir] [--to docx]
```

调用 `quarto render` 渲染拼装产物（`weft.yaml paper_file`，默认 `paper.qmd`）为目标格式，默认 docx。不重复校验闸门（assemble 已闸）。常见失败：quarto 不在 PATH；`paper.qmd` 不存在（提示先 `weft assemble`）。成功输出 `paper.docx`（或对应后缀）。

投稿资源就位后，在 `_quarto.yml` 打开 `csl` 与 `reference-doc` 注释即可套用期刊样式（`assets/` 约定：`references.bib` / `style.csl` / `template.docx`）。

### weft inspire

```
weft inspire [灵感md | 项目根] [project_dir] [--mock]
```

把一段灵感笔记自动拆成草稿卡 + 替换提案 + 处理报告（详见第 9 节）。灵感文件必须位于项目的 `inspirations/` 目录下；省略文件参数时自动取收件箱里**最旧**的一个 `.md`。

### weft replace

```
weft replace <card_id> [project_dir]
```

应用替换提案 `inspirations/proposals/<card_id>.md`：新卡内容替换旧卡，旧卡归档到 `archive/cards/<类型目录>/`，提案文件删除。安全设计：

- 目标卡或提案不存在、提案 id 与目标不一致 → 拒绝；
- **先在内存里做替换并跑全量校验**，有任何 error 即拒绝且磁盘零改动；
- 归档位置已有同名旧卡 → 拒绝覆盖。

### weft missing-cites

```
weft missing-cites [project_dir]
```

列出 `claim_type: cited` 但 `cites` 为空的卡（非 rejected）——你的缺文献清单。纯数据层报告，不阻断、不影响退出码。

---

## 8. 生成管线详解

`weft draft` 对每个 approved 节点各跑一次六节点 SpecModule run：

```
[g 起草（占位符）] → [c1 校验，fix 覆盖] → [l 跨段衔接] → [p 润色]
                  → [c2 复检（fix 覆盖）] → [f 脚本：占位符确定性填充]
```

| 节点 | 职责 | 输出 |
|------|------|------|
| g | 依据 uses 实体全文 + purpose/logic 起草段落，图表与引文位置写占位符 | 段落文本 |
| c1 | 审查：内容与卡片一致、覆盖全部要点、占位符合法、无裸 [@key]；不通过给出修正全文 | `{"verdict": "pass|fix", …}` |
| l | 基于本 part 已生成段落与前一 part 末段做衔接优化（不改事实与占位符；"后一 part 首段"为预留上下文，CLI 当前不传入） | 段落文本 |
| p | 学术语言润色（事实不偏移、风格正式克制、占位符原样保留） | 段落文本 |
| c2 | 复检，重点防润色引入的事实偏移 | `{"verdict": "pass|fix", …}` |
| f | 确定性脚本：把占位符替换为字面编号 / [@key]，并执行硬规则闸门 | 终稿段落 |

任一 c 节点判 fix 即以其修正文本覆盖工作文本；最终取覆盖链 `g → c1? → l → p → c2?` 的最后一个有效输出。

**占位符体系**（AI 只写占位符，系统填充真实引用——保证引文 100% 来自 bib）：

- `{{fact-xx}}` → 该 fact 所引 data 的全部图表 ref，替换为字面编号文本（如 `Fig. 1a`；`tbl-*` → `Table 1`），多个 ref 以"; "连接。fact 未关联任何 ref → 占位符移除 + `W-REF-EMPTY` 提醒；
- `{{claim-xx}}`（仅 `cited` claim）→ 替换为 `[@key1; @key2]`（单个引用块，多键同块，避免 citeproc 渲染双层括号）。cites 为空 → 占位符移除 + `W-CITES-EMPTY` 提醒；
- `uncited` claim 直接陈述，禁止占位符；全文禁止真实 `[@key]` 与 `{{…}}` 以外的任何标记。

**drafts 文件格式**（`drafts/<part_id>.md`，固定 LF）：

```markdown
<!-- weft:run=<run_id> part=sec-03 -->

<!-- weft:node=para-03-01 uses=fact-01,claim-01 -->
（段落文本，占位符已填充……）

<!-- weft:node=para-03-02 uses=fact-02 -->
（段落文本……）
```

溯源注释只属于 drafts：`weft assemble` 据此切块，拼装产物不含注释。未生成节点（draft/rejected）不出现在草稿里。

**SpecModule 零残留**：draft 管线以 `persist/status_file/keep_records/stream_log` 全 False 运行，除 `drafts/<part_id>.md` 外不在任何位置留下运行痕迹。

---

## 9. 灵感式写作（inspire → replace）

适用场景：读到一篇相关论文、冒出一个想法，先记下来，稍后让 AI 把它纳入卡片体系。

### 9.1 流程

```bash
# ① 把灵感笔记（自由格式 Markdown，无 frontmatter 要求）放进收件箱
cp 我的笔记.md <项目>/inspirations/2026-09-05-idea.md

# ② 处理（省略文件名则自动取最旧一个）
weft inspire

# ③ 按报告审阅草稿卡：该改的改、该 reject 的 reject
weft review

# ④ "补充"类改动会生成替换提案，确认提案内容后应用
weft replace <目标卡id>
```

### 9.2 管线（T1–T5）

| 节点 | 职责 |
|------|------|
| T1 逻辑核查 | 建议性检查灵感内部逻辑矛盾（不阻断） |
| T2 卡片拆解 | 灵感 → 拟建卡草案（fact/claim 陈述）+ 内部连接 |
| T3 现有卡审查 | 每条草案对照现有卡分类：`new`（新卡）/ `conflict`（与现有卡矛盾）/ `supplement`（补充现有卡，必须给出合并后陈述） |
| T4 匹配 | fact → 关联现有 data 卡；claim → 分类 cited/uncited 并匹配文献 key；文中占位表述 → 匹配现有 fact |
| T5 成卡覆盖 | 逐句对账灵感原文与草案卡，漏掉的要点进报告 |

### 9.3 落盘（自洽闭包）

- **新建草稿卡** → `metadata/facts|claims/...`，`status: draft`、`comment` 注明灵感来源，id 自动顺延分配（`fact-03`、`claim-04`…）；
- **硬规则**：fact 草案必须关联到至少一张**现有** data 卡，否则不落盘、进报告（宁可少落）；claim 的 cites 只保留真实存在于 bib 的 key；`fact.supports` 只指向本次随之落盘的 claim；
- **补充（supplement）** → 不动现有卡，生成完整新卡提案到 `inspirations/proposals/<目标卡id>.md`，人工审后 `weft replace` 应用；补充目标不是现存卡时自动降级为新建；
- **矛盾（conflict）** → 不自动仲裁，写入报告"矛盾（需人工仲裁）"节；
- **原文归档** → `inspirations/processed/<原名>`；**处理报告** → `generated/inspirations/<stem>-report.md`（逻辑核查、矛盾、新建卡、提案、匹配缺口、覆盖审查、丢弃提示一览）；
- **断点续跑**：管线开启 persist，每步快照落在 `generated/inspirations/.runs/`；同一灵感失败后重跑自动续，已完成节点不重复调用 LLM；
- **fail-closed**：LLM 输出不合 schema（`E-INSPIRE-SHAPE`）或运行失败（`E-INSPIRE-FAILED`）→ 退出码 1，已成功的节点靠快照保留。

---

## 10. 配置文件

### 10.1 weft.yaml（全部键可省略）

```yaml
# figures_dir: figures      # 图表目录（data 卡 refs 指向其中的 Quarto label）
# assemble_mode: strict     # strict | lenient：part 拼装失败是否阻断 assemble
# paper_file: paper.qmd     # assemble 拼装产物（weft render 的渲染对象）
```

### 10.2 _quarto.yml（Quarto 标准）

`bibliography` 是 weft 的**唯一引用来源**：claim.cites / method.derived_from / note id 都以其中的 key 为准（支持字符串或字符串列表）。投稿资源约定：

```yaml
project:
  type: default
bibliography: assets/references.bib
csl: assets/style.csl          # 期刊样式（可选）
format:
  docx:
    reference-doc: assets/template.docx   # 期刊模板（可选）
```

### 10.3 LLM 配置（真实生成需要）

`weft draft` / `weft inspire` 不带 `--mock` 时需要底层 specmodule 的 LLM 配置。weft 以**项目根**为配置根，查找顺序（高 → 低）：

1. 环境变量（项目根 `.env` 先加载并入，已存在的键不覆盖）；
2. 项目根的 `config.json`。

`config.json` 声明 providers 与 models（字段形状参照 specmodule 的 `config.example.json`）；`.env` 存 API key（providers 里 `api_key_env` 指向的变量名）。**`.env` 含密钥，务必加入 .gitignore，任何密钥不得入库。**

配置构造失败时命令直接报错：`真实 LLM 客户端构造失败（检查 config.json / .env）`。

### 10.4 overview.md（研究总述）

不设 schema：写清研究问题、体系、核心贡献与章节逻辑即可。`weft draft` 把它整篇注入 g 节点作为全文定位背景（提示语明确要求"不要复述"）。没有该文件也能生成，但段落会缺少全局视野。

---

## 11. 诊断码总表

`E-*` = 错误（阻断：所在命令退出码 1，或挡住下游闸门）；`W-*` = 提醒（不阻断）。新增码必须登记进本表。

### 加载层（任何命令都会带出；永不中断加载）

| 码 | 级别 | 含义 |
|----|------|------|
| `E-NOT-A-PROJECT` | E | 目录缺少 `_quarto.yml` 与 `metadata/`，不是 weft 项目根 |
| `E-PARSE` | E | 单卡/YAML/配置解析失败（编码、语法、字段校验）；单卡失败转诊断后继续加载其余 |
| `E-FILENAME-MISMATCH` | E | 卡片文件名 ≠ 卡 id |
| `E-DUPLICATE-ID` | E | 实体 id / part id / 节点 id 重复（实体全局一个命名空间） |
| `E-CLAIM-DIR-MISMATCH` | E | claim 卡所在目录与 `claim_type` 不符 |
| `E-PART-NO-CHAPTER` | E | part 文件不在 `narrative/<chapter>/` 子目录内 |
| `E-BIB-MISSING` | E | `_quarto.yml` 的 bibliography 指向的文件不存在 |

### 校验层（validate 及所有下游闸门）

| 码 | 级别 | 含义 |
|----|------|------|
| `E-DANGLING-REF` | E | 悬空引用：fact.data / fact.supports / param.method / 节点 uses 指向不存在的实体（uses 合法目标 = fact/claim/method/param） |
| `E-CITES-NOT-IN-BIB` | E | claim.cites 的 key 不在 bib |
| `E-DERIVED-FROM-NOT-IN-BIB` | E | method/param 的 derived_from key 不在 bib |
| `E-NOTE-NOT-IN-BIB` | E | note 卡的 id（bib key）不在 bib |
| `E-REFS-NOT-IN-FIGURES` | E | data.refs 的编号未在 figures.yaml 注册 |
| `E-WORKFLOW-UNKNOWN` | E | part.workflow 不在词表（introduction/methods/results/discussion） |
| `W-CLAIM-CITED-NO-CITES` | W | cited claim 的 cites 为空（缺引文提醒） |
| `W-CLAIM-UNSUPPORTED` | W | uncited claim 没有任何非 rejected 的 fact 支持它 |
| `W-FIGURE-FILE-MISSING` | W | `figures/<ref>.png|pdf` 文件缺失（仅 fig-*） |
| `W-FIGURE-UNUSED` | W | figures.yaml 的图没有被任何 data 卡引用 |
| `W-ORPHAN` | W | 孤儿实体：未被任何叙事节点引用（含间接可达） |
| `W-NOTE-NO-SUMMARY` | W | note 缺 summary（该引文处 AI 只能凭 bib 条目行文） |
| `W-NOTE-MISSING` | W | 引文在 bib 中但没有对应 note 卡 |
| `W-PURPOSE-VOCAB` | W | 节点 purpose 越出软词表（describe/interpret/compare/transition） |
| `W-ROLE-VOCAB` | W | uses.role 越出软词表（evidence/conclusion/comparison/background/counterpoint） |

rejected 卡/节点豁免全部 W 级校验；E 级不豁免。

### init / draft 管线

| 码 | 级别 | 含义 |
|----|------|------|
| `E-INIT-COLLISION` | E | `weft init` 目标目录非空，未写入任何文件 |
| `E-PART-NOT-FOUND` | E | `weft draft` 的 part id 不存在 |
| `E-NOTHING-TO-DRAFT` | E | part 内没有 approved 节点 |
| `E-DRAFT-SHAPE` | E | LLM 输出不合 schema / 存在未解析占位符 / harness 节点 failed |
| `E-DRAFT-FAILED` | E | SpecModule run 基础设施失败 / 节点 aborted / 未产出段落（fail-closed） |
| `E-DRAFT-USES` | E | 占位符越界：引用了不属于本节点 uses 的实体 |
| `E-CITE-NOT-IN-BIB` | E | 生成文本中出现的 `[@key]` 不在项目 bib |
| `W-REF-EMPTY` | W | `{{fact-xx}}` 的 fact 未关联任何图表 ref，占位符已移除 |
| `W-CITES-EMPTY` | W | `{{claim-xx}}` 的 cited claim cites 为空，占位符已移除（缺文献） |

draft 管线诊断的 path 统一为 `drafts/<part>.md`、field 为 `<节点id>.<字段>`。生成失败时 **drafts 零写入**。

### assemble / render / inspire

| 码 | 级别 | 含义 |
|----|------|------|
| `E-ASSEMBLE-MISSING-DRAFT` | E | strict 模式下 approved 节点没有已批准草稿段（该 part 跳过，其余照常，整体退出码 1；lenient 只跳节点） |
| `E-INSPIRE-SHAPE` | E | inspire 节点输出不合 schema / 不可读（整链不落盘） |
| `E-INSPIRE-FAILED` | E | inspire run 失败 / aborted / 节点未完成（已完成节点有快照可续跑） |

`weft render` 的两类失败（quarto 不在 PATH、渲染失败）以普通 ERROR 行输出，不带诊断码。

---

## 12. 常见工作流与最佳实践

### 12.1 从零写一篇论文（推荐节拍）

1. `weft init` → 填 `overview.md`（研究总述先行，后面每段生成都吃它的红利）；
2. 按章推进：先建该章的 data/fact/claim 卡（含 figures.yaml 注册与图文件），再写 part 节点；
3. 每完成一批卡：`weft validate` → `weft review` → 把确认过的卡/节点 `status` 改 `approved`；
4. 按 narrative 目录序逐 part `weft draft`（顺序执行让跨段衔接自然累积）；
5. 读 `drafts/*.md`，不满意就改卡/节点再重跑 `weft draft`（全量重写该 part），或直接手改段落（保留 `weft:node` 注释行）；
6. `weft assemble` → `weft render` → 拿到 `paper.docx`。

### 12.2 数据更新后同步正文

改数据 → 更新 data/fact 卡的 statement → `weft validate` → 重跑受影响 part 的 `weft draft` → `weft assemble`。全文引用一律经占位符由卡派生，不存在"正文漏改"问题。

### 12.3 增量拼装与 partial 成稿

写完一章就想看效果：`weft assemble` 用 lenient 模式（`weft.yaml` 里 `assemble_mode: lenient`），未完成的部分自然缺席，`paper.qmd` 也能渲染预览。投稿前切回 strict 查漏。

### 12.4 文献管理

- note 卡的 summary 写"这篇文献说了什么、对我的论文有什么用"——它是 AI 引用行文时的唯一依据；
- `weft missing-cites` 随时查缺文献；`weft graph` 的 `graph.json` 可回答"这条引文被哪些卡/节点用到"；
- 新读一篇论文 → 直接走 inspire 管线，T3 会告诉你它与现有卡是 new / conflict / supplement。

### 12.5 调试生成质量

- 段落写偏 → 检查节点 `logic` 是否说清了组织顺序；`purpose`/`role` 是否恰当；
- 段落衔接生硬 → 确认按章序生成（前一 part 的草稿末段是上下文来源）；
- 想试管线不想花 token → `weft draft <part> --mock`；
- 温度由章类决定（methods 0.2 最保守 / discussion 0.6 最放飞），可用 part.workflow 显式改道。

---

## 13. 已知限制

1. **param 卡目录**：权威位置是 `metadata/methods/params/`（loader 只扫描这里）；当前 `weft init` 生成的空目录是 `metadata/params/`（不含 `methods/`），init 用户建 param 卡时请自行放到 `metadata/methods/params/`。
2. **method/param 卡不进入生成提示**：uses 引用 method/param 合法（校验与反向索引均支持），但 draft v2 的实体 bundle 只注入 fact/claim 全文；methods 章的实际素材目前主要靠节点 `logic` 承载。
3. **图表编号是字面编号**：Fig./Table 编号取 figures.yaml 键序，不走 Quarto crossref；正文引用点与图表节的编号一致性由"键序唯一"保证，调编号 = 调键序。
4. **References 条目由 Quarto 生成**：weft 只写定位 div，需要 `_quarto.yml` 的 bibliography 配置正确；`weft render` 前 bib 变更会直接反映在渲染结果里。

---

*本手册对应的实现：`src/weft/`（cli / store / validation / engine / assemble / graphgen / render / scaffold）；设计定案见 `docs/superpowers/specs/`，执行期决策见 `docs/superpowers/plans/`。若手册与实现不符，以实现为准并欢迎修订本手册。*
