# weft parse — 文章解析 → 卡片管线 设计定案

- 日期：2026-09-28
- 依据：设计 v1 §10 扩展场景 1"文章解析"；inspire 设计非目标中"note 卡归文章解析场景"的预留；roadmap 扩展场景 #1
- 状态：设计已获用户逐节确认（brainstorm 决策表见文末 D1–D9）

## 1. 目标与非目标

**目标**：`articles/` 收件箱中的完整文章 md/txt（一次一个）经 SpecModule 五节点 AI 管线解析为草稿卡进入现有审阅体系。两种模式走**同一条管线**，按是否给定 `--key` 自然分叉：

- **文献模式**（`--key` 给定）：解析他人论文/综述 → note 卡（id = bib key，summary 为结构化文献摘要）+ cited claim 素材（默认 cites=[key]）。
- **拆解模式**（无 `--key`）：解析自己的旧稿/长文 → fact/claim 拆解，fact 走 data 匹配闭包。

处理机制全部复用 inspire 已落地件：digest 穷举比对、矛盾/补充分类、fact→data 关联、落盘闭包 fail-closed、断点续跑、替换提案归档。

**非目标（YAGNI，明确不做）**：
- PDF/docx 直收（用户自转 md；未来 BBT/Zotero 导出亦可出 md）。
- method/param 卡抽取（roadmap 未提及；后续需要另立设计）。
- AI 写 bib / 自动生成 bib 条目——bib 维护路线定案为 **Zotero Better BibTeX 联用，weft 对 bib 只读**（见 D4）；BBT auto-export 即"外部 bib 提供方"，文件契约，weft 侧接口不变。
- WebUI 集成（后置，单人 CLI 优先）。
- 长文分块（现代模型上下文足够；超长出 W 提醒，不做切块拼接）。
- pyzotero 同步（roadmap #3，另案）。

## 2. 目录与文件约定

| 路径 | 用途 | 参与加载？ |
|---|---|---|
| `articles/*.md,*.txt` | 文章收件箱，一次解析一个 | 否 |
| `articles/processed/<原名>` | 处理后原文归档（溯源保留） | 否 |
| `generated/articles/<名>-report.md` | 处理报告（人审主界面） | 否 |
| `generated/articles/.runs/` | 断点续跑快照（weft 受管目录） | 否 |
| `inspirations/proposals/<目标卡id>.md` | 替换提案暂存（**与 inspire 共用 `PROPOSALS_DIR`**；`weft replace` 不关心提案来源） | 否 |
| `metadata/notes|facts|claims/**` | 管线产出的草稿卡（status: draft）直接写入，进入现有审阅流 | 是 |

`weft init` 骨架新增 `articles/` 空目录（scaffold 与 init 测试同步更新，计数变化登记于实施计划）。

## 3. 两种模式语义

| | 文献模式（`--key` 给定） | 拆解模式（无 `--key`） |
|---|---|---|
| 典型输入 | 他人发表论文/综述 | 自己的旧稿、报告、长文 |
| note 卡 | 产（id = key，summary = 结构化摘要） | 不产 |
| claim | **一律默认 cites=[key]**（次级引用语义：引你实际读到的这篇；对文中提及的他人工作也先引本篇，原始出处由人审时自行调整）；语义上确不需引文的判 uncited | 同 inspire：对照 note summary + bib 匹配 cites |
| fact | 照常抽取，但外部文献的事实通常匹配不到本项目 data 卡 → 落盘闭包自然拦下，进报告说明 | 正常拆解，data 闭包闸门 |
| method/param | 不抽取（非目标） | 不抽取 |

模式只是 prompt 与默认值的分叉，节点结构、闸门、落盘纪律完全同一套。

## 4. SpecModule 管线（`src/weft/engine/parse/`）

复用 inspire 全部实测语义：flow 起始标记行单边、script 节点 view 键来自 `TaskDefinition.inputs`（V 任务 `inputs={tick: tick}`）、`reg.script(name)(fn)` 装饰器工厂、run 层 firings 扫描 fail-closed、persist 断点续跑（base_dir = `generated/articles/.runs/`，灵感换名即换 module_id 的规则同样适用：文章换名即换 module_id）。

节点（P 前缀，与 inspire T 前缀区分模块归属）：

| 节点 | 职责 | 输入 → 输出（均 pydantic 校验） |
|---|---|---|
| P1 逻辑核查 | 文章写作逻辑检查（建议性，不阻断） | 全文 + mode → 问题清单 |
| P2 拆解 | fact/claim 拟卡 + 新卡内部连接（supports/uses）+ 占位标记；**文献模式加产 note.summary**（结构化摘要折进此节点，省一次全文往返） | 全文 + mode → 拟建卡集 + 内部连接 + 占位清单 + [摘要] |
| P3 对照审查 | 拟卡 × digest 逐卡分类：矛盾卡 / 新建卡 / 补充卡（含原卡全部信息的完整替换提案）；**note 单独三档判定：new / supplement / unchanged**（见 §5） | 拟建卡 + [摘要] + digest → 分类结果 + note 判定 + 提案卡 |
| P4 匹配 | 文献模式 claim 一律默认 cites=[key]（次级引用语义，见 §3；无需引文者 uncited）；拆解模式同 inspire（候选 = note 卡 summary 为主、bib 条目补充）；fact→data 关联（→ data.refs 建议）；占位 → 现有 fact 匹配 | 分类后卡集 + digest + mode → 匹配/缺口清单 |
| P5 覆盖审查 | 逐要点对账文章原文与草案卡（长文防漏，宁可多报不可漏报） | 原文 + 草案卡 → 覆盖对账 |
| A1 聚合 | 纯脚本无 LLM：校验各节点输出 → 落盘闭包校验 → 写草稿卡/提案 → 原文归档 processed/ → 生成报告 | 前序全部输出 → 落盘 |

**落盘规则（防污染校验闸门，同 inspire"宁可少落，不可落出坏项目"）**：fact 卡仅在 P4 关联到 ≥1 个现有 data 卡后才落盘（`data=[匹配到的 data id]`），关联不到 → 不落盘、报告提示；claim.supports 只允许指向将随之落盘的新 fact 或既有 fact；A1 以"拟落盘卡 ∪ 既有卡"做引用闭包校验，任一悬空 → 该关联连通分量整体不落盘并在报告说明原因。

**fail-closed**：任一 LLM 节点输出非法（schema 不符 / aborted / failed）→ 整链不落盘（与 draft/inspire 闸门同哲学）。P1 的"建议性"指其结论不阻断，输出格式仍须合法。

## 5. note 三档判定与替换提案

同 key note 已存在时（无论 draft / approved），**"有无实质新内容"由管线判断，不无脑出提案**：判定主体是 P3，对照 digest 中的原 note summary（digest 对 note 附 summary 全文）与新解析的摘要逐要点比对。

| 判定 | 条件 | 行为 |
|---|---|---|
| `new` | key 在 bib 且无 note 卡 | 直接写 `metadata/notes/<key>.md` 草稿卡（status: draft） |
| `supplement` | 已有 note 且新解析有实质新内容 | 完整新 note 提案（原 summary + 新内容整合，comment 注明"取代 `<key>`"）→ `inspirations/proposals/<key>.md` → 人工审 → `weft replace <key>`（旧卡归档 `archive/cards/notes/`） |
| `unchanged` | 已有 note 且无实质新内容 | 零写入零提案，报告注明"无实质更新，维持原卡" |

AI 永不直接修改既有卡（inspire D5 哲学延续）。

**`apply_proposal` 扩展**：现仅认 fact/claim 目标（按 `old_rel.parts` 判 `facts/`），扩展 note 目标分支——NoteCard 校验、notes 表闸门替换、归档路径 `archive/cards/notes/`。CLI `weft replace` 与 WebUI 共用本函数，语义自动获得。

## 6. CLI

| 命令 | 语义 |
|---|---|
| `weft parse [<file>] [--key <bibkey>] [--mock]` | 解析一篇文章。无参 = 收件箱中文件修改时间最旧的一个；显式路径仅限 `articles/` 内（防误处理任意文件，同 inspire）；`--key` 给定即文献模式，且 **key 必须 ∈ bib，否则 `E-ARTICLE-KEY` 硬错误拒绝**（fail-closed；不自动拟条目，见 D4）；`--mock` 复用免 key 管线冒烟；生成前要求项目可加载且校验无 error（同 draft/inspire 闸门） |

`weft replace` / `weft missing-cites` 语义不变（replace 新增支持 note 目标，见 §5）。

## 7. 诊断码

- `E-ARTICLE-SHAPE`：节点输出不合 schema（path=`articles/<文件名>`）
- `E-ARTICLE-FAILED`：节点 aborted / 基础设施失败（path 同上）
- `E-ARTICLE-KEY`：`--key` 不在 bib 中
- `W-ARTICLE-LONG`：文章超长提醒（不阻断，不做分块）。阈值 = 模块级常量 60,000 字符（不配置化，YAGNI）
- 命名说明：`E-PARSE` 已被 store 层占用（卡片 YAML 解析失败诊断），故本管线用 `E-ARTICLE-*` 前缀；四个码进诊断码总表（AGENTS.md 红线 5 指向的计划文档清单）。

## 8. 模块组织（第二次管线触发的真重复提炼）

- **`engine/pipeline.py`（新，公用）**：run 层机械件从 `engine/inspire/run.py` 提炼——module 构建、断点续跑/回退逻辑、firings 扫描、节点输出 schema 校验、错误映射；按（harness cores、tick→model 映射、tasklist 构造器、base_dir、错误码前缀）参数化。**inspire 同步切换复用，既有 inspire 测试全绿 = 提炼等价性守护**，不为提炼另建平行测试。
- **`engine/card_writer.py`（新，公用）**：受控写入器从 `engine/inspire/cards.py` 迁移——`write_proposed_cards` 扩为 fact|claim|note 三类 + `write_proposal` 不变；`PROPOSALS_DIR` 常量随迁；inspire / parse 两管线共用，消除 parse → inspire 的跨管线 import。
- **`engine/parse/`（新）**：`schemas.py`（P1–P5 输出契约）、`spec_build.py`（Spec/Tasklist 构造）、`apply.py`（A1 聚合、报告生成）。不建更多目录（呼应"不要一 module 一目录"）。
- `digest.py` 不动（数据层公用件，两管线共用）。
- `apply_proposal`（含 note 扩展）**留在 `engine/inspire/apply.py` 不迁**：它是 CLI / WebUI 的共用应用入口，parse 管线只写提案（经 card_writer）不应用提案，无跨管线 import 需求。

## 9. 红线扩展

- 红线 4 白名单更新：AI 产物受控写入器由 `engine/inspire/cards.py::write_proposed_cards` 迁移并扩展为 `engine/card_writer.py::write_proposed_cards`（+ `write_proposal`）；parse 管线零新增落盘点，运行快照只落 `generated/articles/.runs/`（weft 受管目录），其余任何位置不得出现 `.specmodule/` 残留；守卫测试同步更新。
- 诊断码进总表（§7）。

## 10. 报告结构

`generated/articles/<名>-report.md`：逻辑问题 / note 判定（新建·提案·无更新）/ 新建卡（落盘路径）/ 矛盾（新卡 ↔ 现有卡 id + 理由）/ 替换提案（目标卡、提案路径）/ claim 分类与依据 / fact→data 关联建议 / 文献缺口 / 占位与需补充提示 / 覆盖对账（漏卡可见）。

## 11. 测试策略

- `pipeline.py` 提炼：以既有 inspire 测试全绿守护等价性（不新建平行等价测试）；parse 管线以 pipeline 为底。
- 各节点 prompt 构造单测（**两种模式分叉断言**）+ JSON 解析 pydantic 单测；假客户端按节点分流（ScriptedLLMClient 模式扩展）。
- mock 端到端（两种模式各一）：落盘断言（note 草稿卡 / fact·claim 卡内容与 status、提案暂存、原文归档、报告章节）。
- fail-closed 路径：坏 JSON / aborted → 磁盘零残留 + 对应 `E-ARTICLE-*`。
- note 三档判定：new 直落、supplement 提案、unchanged 零写入各若干例。
- CLI：路径限制、`--key` 闸门（不在 bib 拒绝）、无参最旧优先、`--mock`。
- `apply_proposal` note 目标扩展若干例（含归档路径）。
- 守卫测试：`test_engine_layering` 白名单迁移覆盖 `card_writer`。
- 真实 LLM 冒烟：`pytest -m smoke` 双保险门（同 M2/inspire）。
- 精确测试计数在实施计划中登记（含 init 骨架加目录的计数变化）。

## 12. 决策记录（brainstorm 结论）

| # | 决策 |
|---|---|
| D1 | 统一管线，两种输入（他人文献 / 自己旧稿）都吃，按 `--key` 自然分叉，不建两套 |
| D2 | 输入格式 md/txt（YAGNI；PDF/docx 用户自转） |
| D3 | bib key 前置：`--key` 必须 ∈ bib，硬错误拒绝；"人管 bib、AI 管卡"分工不破 |
| D4 | bib 维护路线定案：**Zotero Better BibTeX 联用，weft 只读 bib**（BBT auto-export = 外部 bib 提供方，文件契约）；不做 module 内自动生成 bib script（元数据幻觉风险 + 需扩 AI 落盘白名单到 assets/ + 重复造轮子）；pyzotero 同步（roadmap #3）为这条线的归宿 |
| D5 | 输入目录 `articles/` 收件箱 + `weft parse`，对称 inspire（目录即状态、原文归档溯源、init 骨架同步） |
| D6 | 同 key note 冲突走三档判定：new 直落 / supplement 提案 / unchanged 零写入——"有无新内容"由管线判断，不无脑出提案（用户明确要求） |
| D7 | 诊断码 `E-ARTICLE-*`（`E-PARSE` 已被 store 层占用） |
| D8 | 模块组织：`engine/parse/` 独立 + run 机械件提炼 `engine/pipeline.py` + 写入器提炼 `engine/card_writer.py`（inspire 同步切换，既有测试守护等价） |
| D9 | note.summary 摘要折进 P2 拆解节点（省一次全文往返）；文献模式 claim 默认 cites=[--key] |
