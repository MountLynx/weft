# WebUI 卡片新建/编辑迁入右侧边栏 — 实施计划（2026-10-15）

## 背景与目标

卡片页（CardsPage）右栏 inspector 已承载详情/审阅/改名/一键修复，但「编辑」与「新建」
仍跳转独立全页路由 `CardFormPage`（`/cards/:kind/new`、`/cards/:kind/:cardId/edit`）。
目标：卡片编辑（含新建）也直接在右侧边栏进行，不离开卡片页工作台布局。

后端零改动：表单规格端点（`GET /card-forms/{kind}`、`GET /cards/{kind}/{card_id}/edit`）
与写端点（`POST /cards/{kind}`、`PATCH /cards/{kind}/{card_id}`）均现成，
`FormSpec` 前端类型现成。本任务纯前端。

## 设计决策

| # | 决策 | 理由 |
|---|------|------|
| D1 | 编辑/新建改为 CardsPage 组件态 `mode`（view/new/edit），不入 URL；`CardFormPage.tsx` 删除 | 用户目标是"不离开卡片页"；状态态避免双跳转刷新竞态；刷新/深链落到查看态可接受 |
| D2 | 旧路由 `/cards/:kind/new`、`/cards/:kind/:cardId/edit` 保留为 `<Navigate>` 重定向（→ 列表 / 详情） | 浏览器历史/书签兜底，3 行成本 |
| D3 | 动态表单抽为 `components/CardForm.tsx`（specs 驱动渲染原样搬自 CardFormPage）；new/edit 仅 endpoint 与 id 行差异 | 表单渲染逻辑复用，避免两份漂移 |
| D4 | 保存成功后刷新 = 列表 `useApi.reload` + 面板换载触发详情重取；不新增整页 reload | 与现状对齐：现状 create 后侧栏计数同样不刷新（WorkspaceRoute 同位不重挂），不回归不扩大；审阅/改名/修复的 `navigate(0)` 原样保留 |
| D5 | 编辑表单保留 status/comment 字段 | `payload_to_meta` 缺省 status 回落 "draft"，省略会把 approved 卡静默降级 |
| D6 | mode 带上 kind（`{type:"new", kind}`），kind 切换即失效回落 view | 渲染期同步校正范式（与 sel 同款），杜绝跨卡种残留表单 |

## TDD 任务分解

前端测试基线：`cd webui && pnpm test` = **8 passed**。

- T1（红）：`App.test.tsx` 新增 3 测试：
  1. 点 inspector「编辑」铅笔 → 右栏出现编辑表单 → 提交走 PATCH → 回查看态；
  2. 点「新建」→ 右栏出现新建表单（含 id 行）→ 提交走 POST → 跳新卡详情；
  3. 编辑态点「取消」→ 回查看态，且无写请求。
  预期：**11 passed**（8+3）。
- T2（绿）：实现 `CardForm.tsx`、CardsPage 右栏 `CardEditPanel`/`NewCardPanel`、
  App.tsx 删 CardFormPage 路由换重定向，删 `CardFormPage.tsx`。
- T3：`cd webui && pnpm build` 产物 → `src/weft/web/static/app/` 提交入库。
- T4：提交（`feat: WebUI 卡片编辑与新建迁入右侧边栏——右栏内联动态表单，CardFormPage 退场`）。

## 验收

- 卡片页内：详情 → 点铅笔 → 右栏变编辑表单 → 保存/取消均留在卡片页；
- 新建（含空态按钮）→ 右栏新建表单 → 保存后选中新卡并刷新列表；
- `pnpm test` 11 passed；`pnpm build` 成功；pytest 全量不受影响（无后端改动）。
