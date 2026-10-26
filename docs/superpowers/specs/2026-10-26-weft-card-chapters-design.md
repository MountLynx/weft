# 卡片章节标签与本章素材生成 — 设计定案

日期：2026-10-26 · 状态：已定案（决策 H1–H10 为定案）

## 1 背景与目标

卡片（六卡种）与叙事章节之间没有显式关联：一张 claim 卡该进引言还是讨论，
只存在于作者脑中；写引言时要在全部卡片里人工翻找文献论断，再逐个填进节点
uses。同时，`01-introduction` 章节的生成基建（workflow 词表、prompt_core、
温度、init 骨架目录）v1.1 起已存在，`weft draft` 对 introduction part 可跑通，
但素材仍只能经节点 uses 逐卡指定——引言所需的「整章文献池」没有组织载体。

目标两件事，互为表里：

1. **章节标签**：每张卡可标 `chapters: [标签…]`（多值），声明它服务的章节；
   WebUI 卡片列表可按章节筛选，叙事面板可看「本章标签卡」。
2. **introduction 生成支持**：生成 part 时，自动把「与本 part 章节匹配的
   已批标签卡」作为**本章素材**并入生成提示——introduction 节点只列主干
   uses，同章已批的文献论断（claim）与文献要点（note）自动可供引用与行文。

## 2 数据结构（schema v1 加性扩展，走 §3 流程）

`_Card` 公共基类（`src/weft/models/cards.py`）新增：

```yaml
chapters: [introduction, results]   # 可选，默认 []；多值标签，保序保原样
```

- **加性可选字段**：旧卡文件无此键 → 默认 `[]`，加载零迁移；不设 backfill
  迁移脚本（无数据形状变化，v1.1 迁移先例是目录结构变更，此处不适用）。
- 模型层不清洗不排序：标签是用户自由文本，归一化只发生在匹配/展示时（H3）。
- `extra="forbid"` 防漂移语义不变：除 `chapters` 外的未知键仍报 E-PARSE。
- 序列化走 `store/writer.py` 既有 `model_dump` 通道，无写层改动。

**归一化规则**（`weft/workflow.py::normalize_chapter`，新导出）：剥数字前缀
（复用 `_NUM_PREFIX = ^[\d\s._-]+`）+ strip + lower。`01-introduction` /
`Introduction` / `introduction` 归一化后相等。

## 3 校验（新诊断码，软提醒）

`W-CHAPTER-VOCAB`（warning，不阻断）：非 rejected 卡的 `chapters` 中出现
**归一化后不匹配任何叙事章节目录名**的标签时提醒。项目没有任何叙事 part 时
不提醒（空项目先标后建章是正常工作流）。

- 允许超集：提前给计划中的章节打标签只提醒不阻断（与 purpose/role 软词表同
  语义）； typo 靠提醒暴露，不会静默分裂筛选与素材匹配。
- rejected 卡豁免全部提醒（既有约定）。

## 4 生成集成：本章素材（chapter materials）

### 4.1 选取规则（`engine/spec_build.py::collect_chapter_materials`）

以 part 的第一级章节目录名为基准（`project.part_chapters`），在**全项目**收：

- **claims**：`status == approved` 且 `chapters` 归一化含该章节 →
  `{id, claim_type, statement, cites, note_summaries}`（与 uses 内 claim 同形，
  无 role）；
- **notes**：`status == approved`、summary 非空且章节匹配 →
  `{key, summary}`（背景要点，不是占位符目标）。

data/fact/method/param 不进素材（H6）。素材在 `run_part_draft` 算一次全集，
`run_draft` 内**按节点过滤**：剔除当前节点 uses 已含的 claim id——uses 永远
优先，素材是补充。

### 4.2 提示注入（`build_node_spec` / 各 prompt）

`build_node_spec(project, node, materials=None)`：materials 非空时挂
`spec["materials"]`。`gen_prompt` 在 uses 之后追加一段（素材为空则整段缺席，
**无标签项目的 prompt 与现状逐字节一致**，既有测试零扰动）：

```
本章素材（卡片 chapters 标签自动并入，可选补充；引用其中的 claim 时同样写 {{claim-xx}} 占位符）：
{JSON}
```

`check_prompt` / `recheck_prompt`：一致性基准扩为「uses 实体全文 + 本章素材
（若有）+ 节点 logic」，审查项①③同步措辞；素材 JSON 只在有素材时附加。

### 4.3 硬闸门语义（`draft_rules.fill_placeholders`）

合法占位符目标集 = `node.uses` ∪ **素材 claims**（per-node 过滤后）。
`E-DRAFT-USES` 码与 fail-closed 语义不变，只是合法集合从「节点级人工枚举」
放宽到「节点级人工枚举 + 同章已批标签卡」——后者同样是人工审定（批准 + 打
章节标签两个动作），这正是章节标签「方便书写」的落点。素材 claim 的
`{{claim-xx}}` 填充走既有通道（cites → `[@key]` 单引注块）。

notes 素材不可被占位符引用（占位符体系只有 fact/claim 两类，不变）；它们
为行文提供文献内容，引用仍需经某张 claim 的 cites。

`weft draft` 生成闸门（红线 6）不动：validate 有 error 仍拒绝生成。

## 5 WebUI

### 5.1 API（`src/weft/web/`）

- `GET /cards/{kind}`：rows 增加 `"chapters": [...]`（原样列表）。
- part 面板 payload（`api/parts.py::_panel_payload`）增加：
  - `chapter`：本 part 第一级章节目录名（如 `03-results`）；
  - `chapter_cards`：章节匹配的全部标签卡（六卡种），
    `[{id, kind, status, key, used}]`——`used` = 已被本 part 任一节点 uses
    引用；作者据此把素材填进 uses（或依赖 4.1 自动并入）。
- 卡片表单规格（`card_forms.py`）：六卡种 FIELD_SPECS 统一追加
  `chapters` 字段，新 widget **`tags`**（自由文本 + datalist）；choices 增
  `chapter_names`（已知章节归一化名并集）；`values_for_template` 把列表
  join 成 `", "` 分隔文本，`payload_to_meta` / `form_to_meta` 解析回列表
  （`[,，;；\n]` 分隔、去重保序）。

### 5.2 前端（`webui/src`）

- **CardsPage**：列表上方（链路筛选条之前）渲染**章节筛选 chips**——来自当
  前卡种 rows 的 chapters 并集，多选并集、再点取消、可清除；组件态不入 URL
  （与链路筛选 L6 同语义）。两个筛选维度叠加 = 行须同时满足（AND）。
- **CardForm**：`tags` widget = 文本输入 + `<datalist>`（已知章节名，允许
  超集自由输入）。
- **PartsPage**：面板新增「本章标签卡」区块，行显示 id · 状态 · 摘要 ·
  used 标记，点击跳对应卡片页。
- 契约同步 `webui/src/api/types.ts`；`pnpm build` 产物 `static/app/` 入库。

## 6 CLI

- `weft new card <kind> <id> [--chapter <标签>]…`（可多次）：模板写入
  `chapters: [...]`；不指定时不写该键（保持模板最小）。
- `weft show`：`chapters` 非空时随字段表打印（空则跳过，与 comment 同例）；
  `weft validate` 自然带出 W-CHAPTER-VOCAB。
- init 骨架 part 模板注释补一句章节标签用法提示。

## 7 红线与诊断码

- schema 加性扩展走 §3 流程：本设计文档登记 + 全量校验绿；无迁移脚本（H2）。
- 新诊断码：`W-CHAPTER-VOCAB`（warning）。登记进 AGENTS.md 红线 5 码表。
- 落盘白名单（红线 4）不变：chapters 只经既有 `save_card` / `create_card`
  通道（人写场景）；生成产物落盘点不变。
- 红线 1/2/3/6 语义不变。

## 8 非目标（v1）

- 叙事节点反向展示章节标签、图谱（graph.json）呈现 chapters。
- data/fact/method/param 进素材池（H6：引言/讨论的素材是文献论断与要点）。
- 按章节一键生成整章（part 仍是生产单位，节点仍是审阅单位）。
- W-ORPHAN 豁免：标签不等于叙事引用，孤儿提醒维持 uses 口径。

## 9 测试计划（TDD）

**后端**（`tests/test_card_chapters.py` 新建 +10；`tests/test_web_card_chapters.py` 新建 +3）：

1. `test_card_chapters_roundtrip` — 六卡种模型默认 `[]`；显式列表；
   save_card → load 往返保真；claim 换 claim_type 迁移文件不丢 chapters。
2. `test_chapters_extra_forbid_unchanged` — 未知键仍 E-PARSE（防漂移未松动）。
3. `test_validate_chapter_vocab` — 有章节项目：未知标签 W-CHAPTER-VOCAB；
   归一化匹配（大小写/数字前缀）不提醒；rejected 豁免；无章节项目不提醒。
4. `test_collect_chapter_materials` — approved + 章节匹配入选（claim 带注
   要点）；draft/rejected 排除；章节不匹配排除；note 空 summary 排除。
5. `test_build_node_spec_materials` — 注入/缺席两形态；`gen_prompt` /
   `check_prompt` 含素材 JSON；无素材 prompt 与旧版逐字节一致。
6. `test_fill_placeholders_materials` — 素材 claim 占位符填 `[@key]`；
   双方之外的 id 仍 E-DRAFT-USES；素材内 note key 占位符仍拒绝。
7. `test_run_draft_introduction_materials_end_to_end` — mock 客户端，
   `01-introduction` part：节点 uses 一张 claim，另一张已批 claim 标
   introduction → 草稿含两处 `[@key]`；introduction prompt 被使用。
8. `test_part_draft_passes_materials` — `run_part_draft` 组装素材全集并
   per-node 剔除 uses。
9. `test_web_card_list_chapters` / `test_web_part_panel_chapter_cards` /
   `test_web_form_spec_tags` — API 三件套。
10. `test_new_card_chapter_option` — `weft new card --chapter` 两次写入。

**前端**（vitest，+3）：

1. CardsPage 章节 chips 渲染 + 并集过滤 + 清除。
2. CardForm tags 控件输入解析为列表提交（payload 断言）。
3. PartsPage 本章标签卡区块 + used 标记 + 跳转链接。

预期全量：**pytest 832 passed, 2 deselected**（基线 818 + 14，见计划 D5）；
**vitest 20 passed**（基线 16 + 4）。

## 10 决策表

| # | 决策 | 理由 |
|---|---|---|
| H1 | 字段名 `chapters: list[str]`（基类，六卡种通用） | 一张卡可服务多章（引言+讨论复用同一论断）；复数标签语义直白 |
| H2 | 加性可选、无迁移脚本 | 旧卡缺键即默认 `[]`，零数据形状变化；§3 流程以设计文档 + 全量校验履行 |
| H3 | 归一化匹配（剥数字前缀 + lower）只在匹配时做 | 模型层保用户原文；`01-introduction` 与 `Introduction` 语义相等是展示层事实 |
| H4 | 校验只出 W-CHAPTER-VOCAB 软提醒，且无章节项目豁免 | 先标后建章是正常流；typo 靠提醒，不阻断 |
| H5 | 素材 = approved 的 claim（可引用）+ note（背景） | 引言/讨论的行文素材是文献论断与要点；claim 形状与 uses 完全一致，占位符通道零新增 |
| H6 | data/fact/method/param 不进素材池 | fact 是本文发现（引言不该自引）；method/param 走 logic 承载（M2 语义） |
| H7 | 素材 claims 进占位符合法集（uses ∪ 素材） | 「整章文献池自动可引」是本功能核心价值；审定主体仍是人（批准 + 打标） |
| H8 | 素材为空时 prompt 逐字节不变 | 无标签项目零行为漂移，既有测试不动即回归证明 |
| H9 | 章节筛选与链路筛选两维度 AND、维度内并集、组件态 | 与 L5/L6 惯例一致；避免一套 query 管道 |
| H10 | notes 素材不可占位符引用 | 占位符体系只有 fact/claim；引用须经 claim.cites，审阅链不断 |
