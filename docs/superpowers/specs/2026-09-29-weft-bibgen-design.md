# weft bibgen — 可选的 bib 自动生成与维护路径 设计定案

- 日期：2026-09-29
- 依据：线上展示需求（WebUI 现场演示、无 Zotero 环境）；Zotero Better BibTeX 源码机制调研（citekey 管理器、auto-export、导出缓存）；roadmap 扩展场景 #3 的前置铺垫
- 状态：设计已获用户逐节确认（brainstorm 决策表见文末 B1–B8）

## 1. 目标与非目标

**目标**：给 weft 增加一条**可选**的 bib 自动生成与维护路径（managed 模式）：`assets/references.bib` 从"人手写的真源"降级为**派生快照**，真源是 `metadata/notes/` 中**已批准且带书目字段（entry）的 note 卡**。现场演示中"AI 提案文献 → 人批准 → bib 即时出现新条目 → claim 可引用 → 生成闸门放行"全链路无需 Zotero/BBT。

借鉴 BBT 的核心思想：**bib 是派生物而非源**——真源在库（citekey 生成后持久 pin）、全量原子重写 + 稳定排序保证 diff 友好、确定性输出使"过期检测"退化为一次字节比较。

**非目标（YAGNI，明确不做）**：

- BBT 式 citekey 公式 DSL（一个 Python 函数 + 确定性后缀足够）。
- 文件监听常驻进程 / 事件总线（weft 内部的状态翻转钩子 + 手改靠 stale 提醒即可）。
- bib 文件级增量补丁（全量重写，BBT 同款）。
- 手改保护与合并（纯派生：managed 文件手改即丢，头注释明示）。
- Zotero API 联用（roadmap #3 依旧另案；将来 pyzotero 产的 note 卡恰好被本管线消费，天然合流）。
- CLI `weft bib propose` 命令（提案走 WebUI 与 parse 联动两条路径，需要时后补）。
- unmanaged 项目的任何行为变化（默认 `bib.managed: false`，旧项目零影响）。

## 2. 决策修订登记

本设计修订两项既有定案，理由如下：

| 旧决策 | 原内容 | 修订 | 理由 |
|---|---|---|---|
| v1 设计 L105 | "不做书目卡（书目字段与 .bib/Zotero 冗余）" | note 卡新增**可选** entry 字段 | 冗余论仅在"bib 是唯一真源"时成立；managed 模式下真源翻转为 note 卡、bib 为派生物，冗余不复存在。unmanaged 项目 entry 可选、不消费、无影响 |
| parse 设计 D4 | "weft 对 bib 只读（BBT auto-export 即外部提供方）" | 文件契约不变；managed 项目的 bib 目标文件改由 weft 自己生成 | 线上演示环境没有 Zotero/BBT 可用；weft 侧读取接口（`_quarto.yml` → 正则提 key）完全不变，D4 的"文件契约"本义保持 |

parse D4 否决"AI 写 bib"的三条理由在 managed 模式下的化解：元数据幻觉 → **人批准闸门**（只渲 approved）；落盘白名单扩散 → bib 渲染是**确定性代码**（非 AI 直接产物），AI 只写白名单内的 note 草稿卡；重复造轮子 → BBT 在演示环境不可用，且本实现是确定性渲染器而非完整导出器。

## 3. 配置与开关

- `weft.yaml` 新增段（默认缺省即 unmanaged）：

```yaml
bib:
  managed: true
```

- managed 项目的 `_quarto.yml` 的 `bibliography` 必须恰好指向**一个**文件（即生成目标，惯例 `assets/references.bib`），否则 `E-BIB-SHAPE`。纯派生定案（B4）：该文件 100% 生成、不接受手写；要手写条目的项目保持 unmanaged。
- `weft init` 模板：`weft.yaml` 写入 `bib: managed: false`（显式默认，新项目行为不变）。

**loader 唯一增量**：`Project` 增加 `bib_files: list[str]`（`_quarto.yml` bibliography 声明的文件路径列表），供 `E-BIB-SHAPE` 判形状与 sync 定位生成目标。key 提取逻辑（`_BIB_ENTRY` 正则 → `project.bib_keys`）一字不动。

## 4. schema 演进：note 卡 entry 字段（红线 2 登记）

NoteCard 新增可选嵌套字段，**加法演进、无需数据迁移**（旧卡不含 entry 照常加载；`extra="forbid"` 保持）：

```yaml
---
id: smith2020
status: approved
summary: 热激活催化在间歇反应器中的速率规律……   # 原字段，语义不动（AI 概括）
pdf: ''                                        # 原字段，不动
entry:                      # 新增；AI 提案时起草，人批准时可改
  type: article             # 受控词表，见下；缺省 article
  title: Thermally activated catalysis in batch reactors   # 必填
  author: [Smith, Jane, Lee, Kyung]   # list[str]，值按人写原样透传
  year: '2020'              # 必填；str | int
  journal: Journal of Thermal Chemistry
  volume: '12'              # 以下均可选：number/booktitle/publisher/pages/doi/url
  fields: {}                # 逃生舱：其余 BibTeX 字段名 → 值，原样透传
---
```

- `entry` 内部模型同样 `extra="forbid"`；必填仅 `title`、`year`。
- `type` 受控词表：`article / book / inproceedings / incollection / phdthesis / mastersthesis / techreport / manual / misc / online / unpublished`；词表外 → `W-BIB-ETYPE`（提醒不阻断，Quarto citeproc 对未知类型按 misc 兜底）。
- 语义不变量保持：**note 卡 id = bib key** 这条 v1 链路就是 managed 模式的真源身份，entry 只是给同一张卡补上"渲染成 BibTeX 所需的书目数据"。

## 5. 渲染器（确定性、全量原子重写）

新模块（建议 `src/weft/bibgen.py`，纯确定性代码，不 import llm——红线 1 无涉）：

- **输入**：store 中 `status == approved` 且带 `entry` 的 note 卡集合 + 生成目标路径。
- **输出**：整文件重写（tmp + `os.replace` 原子替换，固定 LF，UTF-8）。
- **确定性**（同输入 → 字节级同输出）：
  - 条目按 key ASCII 排序（BBT exportSort=citekey 的 versioning-friendly 思想）；
  - 字段固定顺序：title, author, year, journal, booktitle, publisher, volume, number, pages, doi, url, 然后按名字排序输出 `fields`；值为 None/空串的字段跳过；
  - `author` 以 ` and ` 连接；值一律 `{...}` 包裹、原样透传，不做转义引擎；
  - 头注释为**静态文本**（不含时间戳、版本号等易变内容）。
- **头注释**（声明派生身份与真源位置）：

```bibtex
% ----------------------------------------------------------
% 此文件由 weft 自动生成（weft.yaml: bib.managed = true）。
% 真源：metadata/notes/ 中 status: approved 且带 entry 的文献卡。
% 请勿手改——手改内容会在下次同步时丢失。新增文献请建文献卡。
% ----------------------------------------------------------
```

- **值安全闸**：任一字段值花括号不平衡 → `E-BIB-VALUE`，拒绝写入（坏值会损坏整个 bib 的 Quarto 解析）。
- **CLI**：`weft bib sync` 渲染并写入，报告条目数与相对上次的增删；unmanaged 项目调用直接报参数错误退出。`weft bib sync --check` 不写文件，当前文件 ≠ 确定性渲染 → `W-BIB-STALE` + 退出码 1（演示前/CI 自检）。

## 6. citekey 规则（BBT 语义简化版）

- key = note 卡 id = 文件名；**批准即 pin**，weft 永不自动改 key（对应 BBT `resetKeyOnChange=false`）。改 key = 人重命名卡文件。
- AI 提案起草 key：`第一作者姓小写 + 年份`（`smith2020`）；与既有 note id 冲突 → 确定性后缀 `a, b, c…`（BBT excelColumn 思想）；缺作者/年份时由 AI 按标题拟短 key，人批把关。
- 手工建卡：key 人定。字符集沿用现有 note id 约束（与正文 `[@key]` 正则兼容）。

## 7. 校验联动与新诊断码（红线 5 入表）

| 码 | 级别 | 含义 | 触发处 |
|---|---|---|---|
| `E-BIB-SHAPE` | 错误 | managed 配置形状非法：`bibliography` 不是恰好一个文件 / `weft.yaml` bib 段未知键 | `validate_project` |
| `E-BIB-VALUE` | 错误 | entry 字段值花括号不平衡，拒绝写入 bib | 渲染器 |
| `W-BIB-STALE` | 提醒 | managed 且 bib 文件 ≠ 确定性渲染（该跑 sync） | `validate_project` |
| `W-BIB-ETYPE` | 提醒 | `entry.type` 不在受控词表 | `validate_project` |

managed 模式语义微调：`E-NOTE-NOT-IN-BIB` 只查 **approved** note 卡（draft/rejected 豁免——提案尚未批准，本来就不该在 bib 里；这正是"提案 → 人批 → key 生效 → claim.cites 才引得了"的演示闸门序列）。approved 但缺 `entry` 的卡照样报 `E-NOTE-NOT-IN-BIB`，指引补字段。unmanaged 项目所有现有规则原样不动。`W-BIB-STALE` 不阻断：`weft draft` 的 validate 前置在 stale 时仍放行。

## 8. AI 提案路径（两条）

**路径 1 · WebUI 文献提案（演示主路径）**：note 卡表单新增"AI 补全条目"——人给线索（DOI/标题/摘要，任意组合），引擎小管线（`engine/` 内，红线 1 合规；零残留 persist 模式，同 draft 管线）提取书目字段并起草 key，经 `card_writer` 落 `metadata/notes/<key>.md`（`status: draft`）——**红线 4 落盘白名单已覆盖，零扩展**。人随后在 WebUI 审核、改字段/改 key、批准。

**路径 2 · parse 文献模式联动**：P2 节点（拆解）在文献模式下加产 entry 拟稿（type/title/author/year/卷期页/DOI——**有原文锚定，幻觉风险低**），A1 落盘时填进生成的 note 卡草稿。拆解模式不提取。实施计划中作为独立任务，可分期。

## 9. 触发与同步

- 渲染挂在 **note 卡状态翻转 approved** 的共享代码路径上（`weft review` CLI 与 WebUI 路由共用同一函数；实施时若现状无共享函数则先提取）。managed 项目下：批准 → 自动重渲 → 前端 flash"references.bib 已更新（N 条）"；渲染失败**不回滚批准**，报错提示 + `W-BIB-STALE` 可见。note 卡删除/改回 draft 同理触发重渲。
- 直接手改文件的场景（不经 weft 的编辑）由 `W-BIB-STALE` + `weft bib sync` 兜底——与 BBT"事件 + 防抖"不同，weft 是单进程单用户，钩子同步执行即可，无需防抖队列。

## 10. paper-demo 转换（线上展示基准）

`examples/paper-demo` 转 managed 作为公开展示样例：`weft.yaml` 开 `bib.managed: true`；`notes/smith2020.md` 补 entry（字段值取自现有手写条目）；`assets/references.bib` 重新生成为带头注释版本。约束：key 集合不变 → `project.bib_keys` 不变 → graph 黄金文件与 validate 基准全部保持绿色（M1 验收基准不破）。

## 11. 测试策略（TDD，精确计数登记于实施计划）

- schema：旧卡无 entry 可载（向后兼容）、entry `extra="forbid"`、year int/str 双收。
- 渲染器：同卡 byte-identical、key 排序、字段顺序、空值跳过、author 连接、头注释、原子写、`E-BIB-VALUE` 拦截、冲突后缀 minting。
- CLI：sync 全新渲染 / `--check` 过期退出码 / unmanaged 拒绝。
- validate：`E-BIB-SHAPE`、`W-BIB-STALE`、`W-BIB-ETYPE`、managed 下 `E-NOTE-NOT-IN-BIB`（draft 豁免 / approved 缺 entry 报错）、unmanaged 零变化回归。
- WebUI/引擎：批准路由 → bib 文件更新；AI 提案路由（tests/ 造假 LLM 响应）→ draft 卡落盘；分层守卫仍绿。
- parse 联动：文献模式 entry 提取（造假响应）。
- paper-demo：转换后 `validate_project` 零错误、黄金文件不变。

## 12. 文档与红线登记

- **红线 4**：写入点白名单补一条——`bibgen` 渲染器的 `assets/references.bib`（`_quarto.yml` bibliography 目标；weft 受管的**确定性**产物，非 AI 直接落盘）。
- **红线 5**：§7 四个新码入总表（AGENTS.md 与计划文档）。
- **AGENTS.md**：必读清单加本 spec；roadmap M4 增补本条目。
- `docs/manual.md` 增补 bib 一节——该文件当前在另一工作线进行中，合入后补（本 spec 不承诺时点）。

## 决策表（brainstorm 逐项确认）

| # | 决策 | 内容 |
|---|---|---|
| B1 | 场景 | WebUI 现场演示（无 Zotero）：演示中新增文献，bib 即时跟上 |
| B2 | 生成方式 | AI 提案 + 人批准 + 确定性渲染（否决：LLM 直接写 bib——D4 场景；纯手填——演示节奏慢） |
| B3 | 真源 | 扩展现有 note 卡（可选 entry 字段，走红线 2 加法演进）；否决独立文献卡（与 note id=key 一稿两卡）与独立 YAML（绕开卡片审核体系） |
| B4 | 派生纯度 | managed 文件 100% 生成、不收手写（否决生成+手写混合；手写需求留在 unmanaged） |
| B5 | 渲染策略 | 确定性全量原子重写 + key 排序 + 静态头注释（无时间戳），diff 友好，stale 检测=字节比较 |
| B6 | citekey | id=卡名批准即 pin；AI 起草 auth+year、冲突字母后缀、人批可改；不做公式 DSL |
| B7 | 诊断码 | 新增 E-BIB-SHAPE / E-BIB-VALUE / W-BIB-STALE / W-BIB-ETYPE；managed 下 E-NOTE-NOT-IN-BIB 只查 approved |
| B8 | 范围 | 路径 1 WebUI 提案 + 路径 2 parse 联动（可分期）；非目标见 §1 |
