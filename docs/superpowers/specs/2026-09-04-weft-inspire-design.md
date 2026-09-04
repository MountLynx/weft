# weft inspire — 灵感式写作 → 卡片管线 设计定案

- 日期：2026-09-04
- 依据：设计 v1 §10 扩展场景 2"灵感式写作"的落地；不动冻结的 v1 数据结构（§3）
- 状态：设计已获用户逐节确认（brainstorm 纪录见文末决策表）

## 1. 目标与非目标

**目标**：`inspirations/` 收件箱中的灵感 md（一次一个）经 SpecModule 多节点 AI 管线解析为草稿卡进入现有审阅体系；处理过程完成：与现有卡片的相关性对比、事实矛盾指出、claim 的 cited/uncited 自动分类与文献自动匹配（缺口清单）、fact→data 关联建议；另设 CLI 直查缺文献的 cited 卡。

**非目标（YAGNI，明确不做）**：
- 向量 RAG / embedding 检索基建（理由见 D6；卡片数千张以内不做）。
- 为占位内容自动建 data 卡或溯源原始数据。
- 从灵感生成 note 卡（note id = bib key，语义是文献摘要；灵感含文献要点应走文章解析场景）。
- AI 修改任何既有卡（含 comment 追加）——一切变更走"新卡提案 + 人工替换"。
- 全局卡库 / 跨项目检索基础设施（v1.1 既有立场）。
- T1 逻辑核查不阻断管线（灵感本是碎片，逻辑问题只进报告）。

## 2. 目录与文件约定

| 路径 | 用途 | 参与加载？ |
|---|---|---|
| `inspirations/*.md` | 灵感收件箱，一次处理一个 | 否 |
| `inspirations/processed/<原名>.md` | 处理后的原文归档（溯源保留） | 否 |
| `inspirations/proposals/<目标卡id>.md` | 替换提案暂存：完整新卡（原卡信息+补充整合，status: draft，comment 注明"取代 `<目标卡id>`"） | 否（metadata 扫描路径外，不撞 id） |
| `archive/cards/<类型>/<原文件名>` | `weft replace` 应用提案后的旧卡归档 | 否 |
| `generated/inspirations/<名>-report.md` | 处理报告（人审主界面） | 否 |
| `metadata/**` | 管线产出的草稿卡（status: draft）直接写入，进入现有审阅流 | 是 |

`weft init` 骨架顺带新增 `inspirations/` 空目录（scaffold 与 init 测试同步更新，计数登记于实施计划）。

## 3. 摘要索引（检索基建）

`src/weft/digest.py` 纯函数 `build_digest(project) -> str`：

- 每卡一行：`id | 类型 | status | statement | cites | data.refs / supports`；note 卡附 summary 全文；figures.yaml 附图题。
- **内存现算、不落盘**：每次管线运行时从已加载 Project 生成，零新鲜度问题，纯函数可单测。
- 用途：T3/T4 的穷举比对底料；后续卡片类 module（AI 审查建议、辅助构建、启发式 claim 建议）的公用件。
- 检索基建取舍见 D6：这是"最便宜的 llmwiki"，不是向量 RAG。

## 4. SpecModule 管线（`src/weft/engine/inspire/`）

复用 M2 通道②全部实测语义：flow 起始标记行单边、script 节点 view 键来自 `TaskDefinition.inputs`（V 任务 `inputs={tick: tick}`）、`reg.script(name)(fn)` 装饰器工厂、零残留四 False、run 层 firings 扫描 fail-closed。

| 节点 | 职责 | 输入 → 输出（均 pydantic 校验） |
|---|---|---|
| T1 逻辑核查 | 灵感全文写作逻辑检查（建议性） | 灵感全文 → 问题清单（进报告，不阻断） |
| T2 卡片拆解 | 拆出 fact/claim 拟建卡；新卡之间内部连接（supports/uses）；识别数据表述（→fact 卡）；标记"xxx 占位"类表述 | 灵感全文 → 拟建卡集 + 内部连接 + 占位清单 |
| T3 现有卡审查 | 拟建卡 × 摘要索引逐卡分类：**矛盾卡**（指名冲突的现有卡 id + 理由）/ **新建卡** / **补充卡**（生成含原卡全部信息的完整替换提案卡） | 拟建卡 + digest → 分类结果 + 提案卡 |
| T4 匹配 | claim 的 cited/uncited 分类与文献匹配（候选 = note 卡 summary 为主、bib 条目补充；匹配到 → cited + cites；语义上需文献但没找到 → cited 且 cites 留空，交给现有 `W-CLAIM-CITED-NO-CITES` 提醒；不需要 → uncited）；fact→data 卡关联（→ data.refs 建议）；占位 → 现有 fact 卡匹配，无则"需补充"提示 | 分类后卡集 + digest → 匹配/缺口清单 |
| A1 聚合 | 纯脚本无 LLM：校验各节点输出 → **落盘自洽闭包校验** → 写草稿卡 → 暂存提案 → 原文移 processed/ → 生成报告 | 前序全部输出 → 落盘三件套 |

**落盘规则（防污染校验闸门）**：schema 上 `fact.data` 为空、任何 `data`/`supports`/`uses` 悬空都是校验错误，草稿卡写入 metadata/ 会让整个项目 validate 挂掉。因此：fact 卡仅在 T4 关联到 ≥1 个现有 data 卡后才落盘（`data=[匹配到的 data id]`），关联不到 → 不落盘、报告提示"需补充 data"；claim.supports 只允许指向将随之落盘的新 fact 或既有 fact。A1 聚合时以"拟落盘卡 ∪ 既有卡"做引用闭包校验，任一悬空 → 该关联连通分量整体不落盘并在报告说明原因——宁可少落，不可落出坏项目。

**fail-closed**：任一 LLM 节点输出非法（schema 不符 / aborted / failed）→ 整链不落盘（与 draft 闸门同哲学）。T1 的"建议性"指其结论不阻断，输出格式仍须合法。

**报告结构**（`generated/inspirations/<名>-report.md`）：逻辑问题 / 新建卡（落盘路径）/ 矛盾（新卡 ↔ 现有卡 id + 理由）/ 替换提案（目标卡、提案路径）/ claim 分类与依据 / fact→data 关联建议 / 文献缺口 / 占位与需补充提示。

## 5. 红线扩展与诊断码

- 红线 4 扩展：AI 落盘点新增唯一受控写入器 `engine/inspire/cards.py::write_proposed_cards`（写 `metadata/` 草稿卡与 `inspirations/proposals/` 暂存，固定 LF）；守卫测试同步更新。`weft replace` 是人工指令，不属于 AI 落盘白名单约束。
- 新诊断码：`E-INSPIRE-SHAPE`（节点输出不合 schema）/ `E-INSPIRE-FAILED`（节点 aborted，fail-closed），path=`inspirations/<文件名>`；进诊断码总表（AGENTS.md 红线 5 指向的计划文档清单）。

## 6. CLI

| 命令 | 语义 |
|---|---|
| `weft inspire [<file>]` | 处理一个灵感。无参 = 收件箱中文件修改时间最旧的一个；显式路径仅限 `inspirations/` 内（防误处理任意文件）；`--mock` 复用免 key 管线冒烟；生成前要求项目可加载且校验无 error（同 draft 闸门） |
| `weft replace <目标卡id>` | 应用替换提案（`inspirations/proposals/<目标卡id>.md`）：提案卡写入 `metadata/<类型>/<id>.md`（status: draft，随后走正常审阅流）、旧卡移 `archive/cards/<类型>/`、提案文件删除；落盘前跑 schema 校验 + `validate_project` 闸门（有 error 即拒绝） |
| `weft missing-cites` | 列出 cites 为空的 cited 卡（id / 相对路径 / statement 摘要）；纯数据层零 LLM；只报告，恒退出码 0 |

## 7. 模块组织（为后续卡片类 module 铺路）

- `engine/inspire/` 自含 spec_build（Spec/Tasklist 构造）与 run（运行/恢复/firings 扫描）。
- 与 M2 `run.py` 实测重复的件（firings 扫描、结构化输出 JSON 解析、假客户端按 prompt 分流）随实现提炼为 `engine/` 平铺公用模块；**只提炼真重复的**，不过度预设目录结构（响应"不要一 module 一目录"）。
- `digest.py` 在数据层（不 import llm），engine 与未来 module 共用。

## 8. 测试策略

- digest 单测（含边界：空项目、note summary、figures 图题）。
- 各节点 prompt 构造单测 + JSON 解析 pydantic 单测；假客户端按节点分流（ScriptedLLMClient 模式扩展）。
- mock 端到端：落盘三件套断言（草稿卡内容与 status、提案暂存、原文归档、报告章节）。
- fail-closed 路径：坏 JSON / aborted → 磁盘零残留 + 对应 E-INSPIRE-*。
- CLI 三命令各若干例（含 inspire 路径限制、replace 闸门、missing-cites 输出格式）。
- 守卫测试：`test_engine_layering` 白名单扩展覆盖 `write_proposed_cards`。
- 真实 LLM 冒烟：`pytest -m smoke` 双保险门（同 M2）。
- 精确测试计数在实施计划中登记（含 init 骨架加目录的计数变化）。

## 9. 决策记录（brainstorm 结论）

| # | 决策 |
|---|---|
| D1 | 草稿卡直接写 `metadata/`，status 闸门审阅；红线 4 扩展受控写入器（用户选定） |
| D2 | 灵感收件箱 `inspirations/` + 处理后移 `processed/`（目录即状态，原文保留） |
| D3 | 图表匹配定性为 **data 关联**：灵感的数据表述 → fact 卡，fact 审查后匹配 data 卡；占位先匹配现有 fact、无则提示补充；不做自动建 data/原始数据溯源 |
| D4 | 路线 A（摘要索引 + 结构化解析）但改为 **SpecModule 多节点管线**：宁可多做不要出错，一节点一任务（T1 逻辑核查 / T2 拆解+内部连接 / T3 矛盾·新建·补充分类 / T4 匹配） |
| D5 | 补充卡 = 含原卡信息的完整新卡提案（draft 暂存），人工审后 `weft replace` 新卡替换 + 旧卡归档；AI 永不改既有卡 |
| D6 | 检索基建 = 内存摘要索引（穷举比对，矛盾核对不可依赖 top-k 召回），不做向量 RAG；零新依赖、可黄金测试；规模撑爆上下文再议 |
| D7 | 模块组织 = 模块 + 公用 harness/script 库，只提炼实测重复件，为卡片 AI 审查建议/辅助构建/启发式 claim 建议等后续 module 铺路 |
