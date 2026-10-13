# WebUI 替换提案对比查看 — 设计定案

日期：2026-10-13 · 状态：已定案（autonomous 会话，决策 C1–C6 为定案）

## 1 背景与目标

灵感管线产出的替换提案（`inspirations/proposals/<目标卡id>.md`，完整新卡）目前
在 WebUI 灵感页只有「应用（旧卡归档）」一个按钮：既看不到提案内容，也看不到
与当前卡的差异，人不看提案全文就无法负责任地点应用——违背"人只审卡片"的核心
模型。CLI `weft replace` 同样直接应用无对比（本设计不扩 CLI，只补 WebUI）。

目标：灵感页每张提案可进入**对比页**，一眼看清"当前卡 → 提案卡"改了什么，
确认后再应用。

## 2 路由与页面

- 新路由 `GET /p/{pid}/inspire/proposals/{card_id}`（`web/routes/inspire.py`），
  模板 `proposal_compare.html`，纯服务端渲染（不引前端 diff 库）。
- 灵感页提案表每行加「对比」链接指向对比页；对比页内保留「✅ 应用」按钮
  （POST 既有 `/apply` 路由，语义零改动）与返回灵感页链接。
- 加载器用 `load_reviewable_or_404`（同卡详情页口径：校验 error 项目恰恰
  最需要审提案）；提案文件不存在 → 404（与 file_view 口径一致）。

## 3 对比呈现（两层）

1. **逐字段对照表**：当前卡与提案卡各自按对应模型（facts/claims/notes 路径
   判别，同 `apply_proposal`）`model_dump()`，按提案卡字段序逐行对照
   （字段 | 当前卡 | 提案卡），值不同加 `changed` 高亮。列表值「、」连接
   （空表→（无））；note 的 entry 走 yaml dump（同详情页）。
2. **逐行统一 diff**：`difflib.unified_diff` 对两份原始 markdown（n=3），
   `+` 行 add 着色、`-` 行 del 着色、`@@` hunk 与 `---/+++` 头淡化；
   `pre-wrap` 防长 statement 溢出。

## 4 容错分支（fail-closed 呈现）

| 情形 | 呈现 | 应用按钮 |
|---|---|---|
| 提案文件缺失 | 404 | — |
| 目标卡不在项目（陈旧残留提案） | 200：警示 banner + 提案原文 | 无 |
| 提案 frontmatter/模型解析失败 | 200：警示 banner + 当前卡 vs 提案原文的 raw diff + 提案原文 | 无 |
| 提案 id ≠ 目标 id | 200：警示 banner + raw diff + 提案原文 | 无 |
| 一切合法 | 字段对照表 + 统一 diff | 有 |

警示 banner 文案直陈原因；四类分支都不改任何磁盘状态（只读页面）。

## 5 样式

`webui.css` 末尾新增 `.compare td.changed`（warning-subtle 底）、`.diff`
（mono + pre-wrap 容器）与 `.diff-add/.diff-del/.diff-hunk/.diff-meta`、
`.proposal-raw`（mono 原文块）。全部走既有设计令牌，themes/*.css 不动
（守卫测试不受影响）。

## 6 红线与诊断码

只读视图，无新落盘点、无新诊断码（错误呈现复用 apply 既有语义的文案），
红线 1–6 不动。schema 未改。

## 7 测试计划（TDD，tests/test_web_inspire.py 新增 7 项）

1. `test_proposal_compare_page` — fact-01 合法提案：200、两侧 statement、
   diff-add/diff-del、字段对照 changed、data 列表渲染、apply 表单在。
2. `test_proposal_compare_page_missing_proposal` — 404。
3. `test_proposal_compare_page_missing_target` — 200 + banner + 无 /apply。
4. `test_proposal_compare_page_unparseable` — 200 + banner + raw diff + 无 /apply。
5. `test_proposal_compare_page_id_mismatch` — 200 + banner + 无 /apply。
6. `test_proposal_compare_page_clean_diff_hidden` — 提案与当前卡逐字节一致：
   无 diff 段、无 changed。
7. `test_inspire_page_links_compare` — 灵感页提案行含对比链接。

预期全量：**812 passed, 2 deselected**（基线 805 + 7）。

## 8 决策表

| # | 决策 | 理由 |
|---|---|---|
| C1 | 独立对比页而非行内展开 | 提案全文+双栏对照在列表行内放不下；独立页可被 dashboard/报告后续复用 |
| C2 | 字段对照表 + raw 统一 diff 双层 | 字段表看语义（改了哪个字段），raw diff 看字面（逐行增删），二者互补 |
| C3 | 服务端渲染 diff，不引 JS 库 | 与全站零构建、htmx-only 的现状一致；diff 计算量小 |
| C4 | 目标缺失/解析失败时隐藏应用按钮 | apply 本就会 ValueError 拒绝，UI 直陈比点了才报错诚实 |
| C5 | 不动 CLI `weft replace` | 用户诉求在 WebUI；CLI 加 diff 另立设计 |
| C6 | 不做"丢弃提案"功能 | 设计文档 §6 提及丢弃但从未实现，与本诉求无关，YAGNI |
