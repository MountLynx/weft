# 卡片章节标签与本章素材生成 — 实施计划

日期：2026-10-26 · 设计定案：`docs/superpowers/specs/2026-10-26-weft-card-chapters-design.md`
基线：pytest 818 passed, 2 deselected；vitest 16 passed。TDD 先红后绿。

## T1 schema 与校验（后端）

- `models/cards.py`：`_Card` 基类加 `chapters: list[str] = []`。
- `workflow.py`：导出 `normalize_chapter(name)`（剥 `_NUM_PREFIX` + strip + lower）。
- `validation/rules.py`：`_check_chapters` → `W-CHAPTER-VOCAB`（有章节项目才查，
  rejected 豁免），挂进 `validate_project`。
- 测试（`tests/test_card_chapters.py`，+4）：roundtrip（含 claim 换目录迁移）、
  extra=forbid 未松动、W-CHAPTER-VOCAB 四态、normalize_chapter 单元。

## T2 本章素材生成集成（后端）

- `engine/spec_build.py`：`collect_chapter_materials(project, chapter_dir)`；
  `build_node_spec(project, node, materials=None)`；gen/check/recheck prompt
  素材段（空素材逐字节不变）。
- `engine/draft_rules.py`：`fill_placeholders(…, material_ids=frozenset())`，
  合法集 = uses ∪ 素材 claims；E-DRAFT-USES 文案更新。
- `engine/run.py`：`run_draft(…, materials=None)` per-node 过滤 + fill 闭包。
- `engine/part_draft.py`：算素材全集传 `run_draft`。
- 测试（+6）：collect 四态、spec/prompt 两形态 + 逐字节回归、占位符三态、
  introduction 端到端 mock、part_draft 传递。

## T3 WebUI API 与 CLI（后端）

- `web/api/cards.py`：rows 加 `chapters`。
- `web/api/parts.py`：面板加 `chapter` / `chapter_cards`（id/kind/status/key/used）。
- `web/card_forms.py`：六卡种 FIELD_SPECS 加 `chapters`（widget `tags`）；
  choices 加 `chapter_names`；values/解析通道（tags ⇄ list）。
- `cli.py`：`weft new card --chapter`（多次）；`weft show` 空列表跳过。
- `scaffold.py`：卡片模板加 `# chapters: []` 注释行；part 模板注释提示。
- 测试（`tests/test_web_card_chapters.py` +3、`tests/test_card_chapters.py` +1）。

## T4 前端（webui/）

- `api/types.ts`：CardsList.rows、PanelPayload、FieldSpec.widget 加 `"tags"`。
- `CardsPage.tsx`：章节筛选 chips（并集、可清除，与链路筛选 AND）。
- `CardForm.tsx`：`tags` 控件（input + datalist）。
- `PartsPage.tsx`：「本章标签卡」区块（used 标记 + 卡片页跳转）。
- vitest（+3）；`pnpm build` 产物 `static/app/` 入库。

## T5 文档与收尾

- AGENTS.md：设计文档登记 + 红线 5 码表加 W-CHAPTER-VOCAB + 基线计数。
- roadmap.md：M4 追加条目。
- 本文件回填执行期决策与精确计数。

## 执行期决策

| # | 决策 | 理由 |
|---|---|---|
| D1 | tags 控件提交原文文本，服务端 `parse_tags` 统一解析（分隔 `,，;；\n`、去重保序、容忍列表直传） | 与 text 控件同范式：表单态即原文，解析单点在服务端；后端测试锁 `["introduction", "03-results"]` 去重形态 |
| D2 | 章节筛选 chips 复用 `.filter-bar`/`.chip` 既有类，无新 CSS | `.chip` 样式元素无关（button 可用），走令牌，themes 守卫测试不受影响 |
| D3 | 素材段注入点：gen 在 uses 之后、check/recheck 在 uses JSON 之后；无素材整段缺席 | 无标签项目 prompt 与旧版逐字节一致（H8），既有测试零扰动即回归证明 |
| D4 | `weft show` 空 chapters 跳过打印（与 comment 同例） | 全量旧卡都有空默认值，打印 `（无）` 是噪音 |
| D5 | 实际新增测试 14 后端 + 4 前端（计划原估 13 + 3） | 前端多 1 例：章节筛选与链路筛选叠加 AND 的独立冒烟；tags 控件加 datalist 渲染断言 |

## 测试计数（完成后回填）

- pytest：818 → **832 passed, 2 deselected**（+14：test_card_chapters.py 10 + test_web_card_chapters.py 4；另 test_new_cmd 金样随 part 模板提示行同步更新，不计新增）
- vitest：16 → **20 passed**（+4：ChapterTags.test.tsx——章节 chips 并集/清除 2、tags 控件提交 1、本章标签卡区块 1）
- 端到端冒烟（手动）：demo 副本 `01-introduction` part，uses 1 张 cited claim + 同章标签 claim-04（不在 uses）→ 草稿同时含 `[@smith2020]`（uses）与 `[@doe2021]`（素材）；标签 `Introduction` 归一化匹配 `01-introduction`；W-ORPHAN 按设计保留。
