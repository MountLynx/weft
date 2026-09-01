# paperflow 设计文档（工作名，可改）

- 日期：2026-09-01
- 状态：设计 v1 定案；数据结构 v1 冻结
- 位置：`C:\Users\xingy\Desktop\开发\paperflow`（独立 Python 包）

## 1. 背景与目标

工程化 AI 学术写作程序：把论文拆解为**元数据**与**叙事流**，只有二者必须有人参与审阅；行文、语言、格式交给 AI，在 Markdown 中进行，Quarto 负责拓展与转化。

设计原则：

1. 元数据独立维护：原子卡片（Markdown + YAML frontmatter），每张卡最小可审阅、可引用。
2. 关系单向存储（fact→data、fact→claim、narrative→实体），反向索引由脚本生成，不手写。
3. 叙事流负责逻辑顺序与元数据选用；未被叙事流引用的元数据不进终稿。
4. AI 只把 `status: approved` 的结构化内容展开为行文，永不改写已审阅的 frontmatter；AI 产物只落在 `drafts/` 与 `generated/`。
5. 单人使用，CLI 优先；审阅历史靠 git；GUI 为远期可选项（Tauri 壳 + sidecar，见 §10）。

### 1.1 选型结论（备查）

- 新建 Python 包，SpecModule 作为嵌入式 LLM 工作流引擎（`call_harness` API，版本锁定，`engine/` 层隔离 API 漂移）。
- 否决 pandown 一站式工作台路线：pandown 已整体并入 claude-prism（2026-08-31 spec 确认），独立分叉会碎片化；且无 LLM、无 Quarto 实现，以编辑器 GUI 为中心与"薄人审 + AI 行文"错位。
- 否决 itemmanage 路线：SQLite-first 与"Markdown 卡片是唯一事实源"根本冲突，条目关系、审阅流、导出全需新造。
- 核心语言不用 Rust：SpecModule 仅 Python；schema 探索期强类型是阻力；Rust 的 YAML/frontmatter 与 LLM 生态明显更弱；性能不构成议题（延迟瓶颈是 LLM 调用）。"真正的本地程序"后置为 Tauri 壳，引擎保持 Python。

## 2. 核心概念

四个层次：

| 层 | 内容 | 谁维护 |
|---|---|---|
| 元数据层 | data / fact / claim / note 原子卡片 | 人创建、人审阅；AI 可产草稿卡 |
| 图注层 | `metadata/figures.yaml` | 人（图注是论文面向文本，归写作系统） |
| 叙事层 | `narrative/*.md` 节与有序节点 | 人创建、人审阅 |
| 生成层 | `drafts/`（AI 行文）+ `generated/`（脚本产物） | AI / 脚本，人审阅 drafts |

实体关系（单向）：

```text
data ◀──fact.data── fact ──fact.supports──▶ claim
                                   claim_type: uncited | cited
                                   cited: cites ──▶ .bib key ──▶ note(id=bib key)
narrative.uses ──▶ fact / claim
```

- 图的位置由 `fact → data.refs` 推导；图本体、绘图脚本、原始文件属于外部数据可视化系统，写作系统只认 `refs` 编号与 `figures/` 目录约定。多张 data 卡可指向同一张图。
- 引文没有实体卡：`cites` 直接存项目 bib 的 key；书目数据唯一来源是项目 `.bib`；note 卡只存"给 AI 看的文献概括"。
- 叙事节点只引用 fact/claim；图表在文中的落点由 fact→data→refs 链推导。

审阅边界：人审阅 = 元数据卡片 + 叙事流（status 字段）；AI 写入仅限 `drafts/` 与 `generated/`（路径白名单在 engine 适配器强制执行）。

## 3. 数据结构 v1（冻结）

### 3.1 data 卡（`metadata/data/data-01.md`，文件名 = id）

```yaml
id: data-01
refs: [fig-01a]        # 最终 crossref 编号,子图级;表格用 tbl-xx;列表(通常一个),
                       # 兼容一个数据项喂多个子图;可为空(不对应任何图的数据)
source: "../../data/raw/run3.csv"   # 可选,AI 溯源用:路径/URL/说明
description: "60°C与25°C下三组重复的反应速率测量"  # 给 AI 看的数据内容说明
status: draft
comment: ""            # 可选审阅备注
```

- `refs` 是内部标识（Quarto label 形式 `fig-01a`），与 Elsevier 编号 `Fig. 1a` 一一对应；论文中的显示形式（`Fig. 1a` / `Table 1` / `图1a`）由 `_quarto.yml` 的 crossref 配置决定，卡片不存显示文本。

### 3.2 fact 卡（`metadata/facts/fact-01.md`）

```yaml
id: fact-01
data: [data-01, data-02]   # 引用的数据项,≥1
statement: "在60 °C时反应速率比25 °C提高42%（p < 0.01）。"
supports: [claim-01]       # 支持的观点,可为空(纯记录性事实)
status: draft
comment: ""
```

### 3.3 claim 卡（单一类型 + 属性分两类）

```yaml
id: claim-01
claim_type: uncited        # uncited(基于自身数据的评价/结论) | cited(推论/与其他研究比较)
statement: "温度升高对反应速率有显著正效应。"
cites: []                  # cited 时填 bib key 列表;cited 且空 → "缺引文提醒"
status: draft
comment: ""
```

- 不拆成两种卡：两类共同点远多于差异（都被 supports/uses 引用、同一审阅流、都是解析产出对象），类别翻转（审阅时改判）只需改一个字段；拆卡则要挪文件迁移且 ID 空间分裂。
- **目录名 = 属性值**：`metadata/claims/uncited/`、`metadata/claims/cited/`；loader 校验目录与 `claim_type` 一致，不符报错。
- ID 全局统一命名空间（不区分类别）。

### 3.4 note 文献笔记卡（`metadata/notes/smith2020.md`，id = bib key）

```yaml
id: smith2020
summary: "Smith等提出热激活催化机制,核心证据是……(读后概括,AI 行文依据)"
pdf: "../pdfs/smith2020.pdf"   # 可选
status: draft
comment: ""
```

不做书目卡（书目字段与 .bib/Zotero 冗余）。校验分级：key 不在 .bib → 错误；key 在 .bib 但无笔记卡 → 警告（该引文处 AI 只能凭条目本身行文）。

### 3.5 叙事节（`narrative/03-results.md`，正文区只放审阅备注/AI 大纲说明，不放终稿）

```yaml
id: sec-03
section: "Results"
order: 3
nodes:
  - id: para-03-01
    purpose: describe        # 固定词表: describe | interpret | compare | transition
    uses:                    # 只能引 fact/claim
      - {id: fact-01, role: evidence}      # role 词表: evidence | conclusion |
      - {id: claim-01, role: conclusion}   #   comparison | background | counterpoint
    logic: "先主结果，再补充次要结果"        # 自由文本
    status: draft
    comment: ""
```

### 3.6 图注层（`metadata/figures.yaml`，无 status，人工直接维护）

```yaml
fig-01:
  caption: "不同温度下的反应速率。误差线表示三个重复的标准差。"
  subfigs:
    a: "60 °C 速率曲线"
    b: "25 °C 速率曲线"
tbl-01:
  caption: "各组反应条件与产率汇总。"
```

结构直接映射 Quarto 的 fig/subfig 层级；子图注挂 `subfigs`，供组装时生成子图级 crossref。

### 3.7 bib 与项目配置

bib 路径直接读 `_quarto.yml` 的 `bibliography` 字段（单一事实源，Quarto 项目本就有）；图表编号的显示形式同样全部由 `_quarto.yml` crossref 配置决定（`fig-prefix`、`tbl-prefix`、子图样式等）——投 Elsevier 风格期刊即设 `fig-prefix: "Fig."`、`tbl-prefix: "Table"`，换目标期刊只改这里，卡片与 figures.yaml 不动。可选 `paperflow.yaml` 覆盖（如 `figures_dir`）。无需独立配置文件。

### 3.8 目录结构

```text
project/
├── _quarto.yml
├── index.qmd
├── references.bib
├── metadata/
│   ├── data/*.md
│   ├── facts/*.md
│   ├── claims/
│   │   ├── uncited/*.md
│   │   └── cited/*.md
│   ├── notes/*.md
│   └── figures.yaml
├── narrative/*.md
├── figures/          # {ref}.png|pdf 约定命名
├── data/             # 原始数据(data.source 指向)
├── drafts/           # AI 行文产物,人审后并入
└── generated/        # graph.json、used-metadata.json、*.qmd(脚本产物)
```

### 3.9 ID 约定

- `data-01` / `fact-01` / `claim-01`：两位零填充，不够进位；全局唯一；文件名 = id。
- note 卡 id = bib key 本身（如 `smith2020`）。
- `refs` 子图级编号：`fig-01a`（图 `fig-01` 子图 `a`）、`tbl-01`。
- 叙事节点：`para-03-01`（节号-段号）。

### 3.10 审阅状态

- `status: draft | approved | rejected`，单字段，唯一事实源；`rejected` = 明确否决（校验器不再报警、生成器不读取）。
- 可选 `comment:` 字段记录审阅备注；不设 reviewer/date（单人使用；日期与历史在 git）。
- 生成器只读取 `status: approved` 的实体与叙事节点。

## 4. 校验规则

| 级别 | 规则 |
|---|---|
| 错误（阻断生成） | id 重复 / 文件名与 id 不符；悬空引用（`data`、`supports`、`uses` 指向不存在的 id）；fact.data 为空；cites key 不在 .bib；note 的 key 不在 .bib；data.refs 不在 figures.yaml；claims 目录与 claim_type 不一致 |
| 提醒（不阻断） | cited 且 cites 为空（缺引文提醒——服务文章解析与灵感式写作场景）；uncited 却无任何 fact 支持；图文件缺失（`figures/{ref}` 不存在）；figures.yaml 有图但无任何 data 引用；孤儿实体（未被任何 narrative 引用）；note 缺 summary；purpose/role 值不在词表（软词表，超集放行便于探索） |
| 生成时 | 草稿中 `[@key]` 必须在 bib 内（硬校验）；`[@key]` 不属于本段所用 claim 的 cites（软提醒）；草稿标注引用的实体 id 必须属于该叙事节点的 uses |

校验不过 → 拒绝生成，报错定位到文件+字段。

## 5. 架构分层

```text
src/paperflow/
├── models/        # pydantic 模型:Data/Fact/Claim/Note/NarrativeSection/Node/Use
├── store/         # 卡片与叙事文件的加载/查询/保存、ID 唯一性、frontmatter 解析
├── validation/    # §4 全部规则
├── graphgen/      # 反向索引 → generated/graph.json;used-metadata.json;孤儿报告
├── engine/        # ★ SpecModule 适配器:全项目唯一 import specmodule 的模块
│   ├── spec_build.py   # 叙事节 → Spec/Tasklist
│   └── run.py          # 运行/恢复;产物归一化写入 drafts/;路径白名单
├── assemble/      # 叙事 + 已批准草稿 → generated/*.qmd
├── render.py      # quarto 子进程封装
└── cli.py         # typer 入口
```

关键规则：SpecModule 的 API 漂移被隔离在 `engine/` 一层，其余模块只依赖本项目接口。

依赖：`specmodule`（版本锁定；bring-up 阶段可 `pip install -e` 指向本地仓库便于共同演进，稳定后切 PyPI 固定版）、`pydantic`、`python-frontmatter`、`typer`、`pyyaml`。

## 6. 生成流水线（SpecModule 映射）

一次章节生成 = 一个 SpecModule run：

1. spec 携带该叙事节点引用的已审阅实体全文（statement、description、source、caption、claim_type、cites、note.summary）。
2. 每个 narrative node → 一个 harness task，结构化输出：`{段落文本, 引用的实体 id, [@citekey] 列表}`。
3. script task 做生成后校验（§4 生成时三规则）。
4. SpecModule 中途对齐检查（align）承担"行文不得越过已审观点"；审阅约束经 prompt_extra 注入。
5. run 产物归一化写入 `drafts/<section>.md`，每段前加 HTML 注释溯源（node id + 实体 id + run id），供人审与回溯。
6. `MockLLMClient` 用于无 API key 的管线测试；断点续跑/回滚复用 SpecModule 原生能力。

## 7. 组装与渲染

`assemble` 按 nodes 顺序拼接该节已批准的草稿段落；节点无已批准草稿时 strict 报错 / lenient 跳过（经 `paperflow.yaml` 配置，默认 strict）。图表按 fact→data→refs 首次出现处插入，图注取自 figures.yaml，crossref 使用 Quarto 语法（`@fig-01a` / `@tbl-01`，子图级）；编号显示形式（如 Elsevier 的 `Fig. 1a`、`Table 1`）由 `_quarto.yml` crossref 配置决定，组装只产出 label 引用。引文 `[@key]` 交由 Quarto citeproc 依 `.bib` 渲染。输出 `generated/<section>.qmd` → `quarto render` 出 HTML/PDF/DOCX。

## 8. CLI 命令面

| 命令 | 作用 |
|---|---|
| `paperflow validate` | §4 全部校验,报告错误与提醒 |
| `paperflow graph` | 生成 graph.json / used-metadata.json / 孤儿报告 |
| `paperflow review` | 按类型列出未审阅实体与叙事节点清单 |
| `paperflow draft <section>` | 对指定叙事节执行生成(SpecModule run) |
| `paperflow assemble <section>` | 拼装已批准草稿 → generated/*.qmd |
| `paperflow render [section]` | quarto render |

## 9. 里程碑

- **M1 数据层**：models + store + validation + graphgen + `validate`/`graph`/`review` 命令。纯数据层，不碰 LLM；以"结果与讨论"的真实样例数据验收。
- **M2 生成层**：engine 适配器 + 单章节（03-results + 04-discussion）端到端生成到 `drafts/`；先 MockLLMClient 后真实 LLM。
- **M3 渲染层**：assemble + `render`，打通 卡片→叙事→生成→组装→Quarto 全闭环。
- **M4 打磨**：断点续跑/回滚接入 CLI、溯源注释完善、文档与示例项目模板（`paperflow init`）。

## 10. 扩展场景（roadmap，架构已预留）

- **文章解析**：AI 从现成文章抽取 fact/claim 草稿卡（status: draft）→ 人工审阅；claim 两类支撑"自动分类为 cited 但缺引文 → 提醒补文献"。
- **灵感式写作**：随手记 → 解析成事实/观点草稿卡 → 自动匹配图表（data.refs）→ 标注缺文献处。
- **pyzotero 同步**：从 Zotero collection 自动生成/更新 note 卡与 PDF。
- **数据处理/绘图管理集成**：外部系统管理图与数据的真实生成，双方以 `data.refs` 编号 + `figures/` 命名约定为契约。
- **Tauri 壳（远期可选）**：PyInstaller 冻结 Python 引擎作 sidecar，前端仅做审阅队列等薄 UI；schema 冻结后才启动。

## 11. 测试策略与风险

测试：pydantic 校验单测；graphgen / assemble 黄金文件测试；MockLLMClient 端到端管线测试（无 key 可跑）；真实 LLM 冒烟测试用 pytest marker 默认跳过（沿用 SpecModule 做法）。

风险与对策：

| 风险 | 对策 |
|---|---|
| SpecModule 0.1.x API 未稳定 | 版本锁定 + `engine/` 单点隔离；适配层接口按本项目需要定义 |
| schema 演进破坏既有卡片 | v1 已冻结；如需变更，走手工迁移脚本 + validate 全量校验 |
| AI 行文越过已审观点 | align 对齐检查 + 生成时实体引用校验 + drafts 溯源注释三重防护 |
