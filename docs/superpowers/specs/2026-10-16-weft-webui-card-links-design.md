# WebUI 卡片链路筛选与跳转 — 设计定案

日期：2026-10-16 · 状态：已定案（决策 L1–L10 为定案）

## 1 背景与目标

卡片间存在逻辑链（多对多 DAG）：`fact.data → data`、`fact.supports → claim`、
`claim.cites → note`、`param.method → method`、`method/param.derived_from → note`
（`src/weft/web/card_forms.py` FIELD_SPECS）。WebUI 卡片页目前是单卡种平铺列表 +
右栏死文本字段表，链条既看不见也走不动——审一张 fact 时想知道"还有哪些 fact
压在同一批 data 上"只能回列表逐张翻。

目标：全链路（六卡种）两件事——

1. **筛选**：侧栏左下角标签式筛选区，标签随选中卡变化（= 选中卡的直接邻居，
   双向），多选并集过滤当前列表（用户定案，修正了最初"inspector 内点标签筛选"
   的设想）。
2. **跳转**：inspector 引用字段值 chip 化，点击跨卡种直达那张卡。

## 2 数据与端点

- 新端点 `GET /api/projects/{pid}/cards/links`（`src/weft/web/api/cards.py`），
  加载用 `load_reviewable_or_404`（与卡列表同口径：校验错误项目恰恰最需要看链路）。
- 数据源：`weft.graphgen.index.build_index(project)` **实时计算**，并在每张卡上
  合并正向链接字段。**不复用 `/api/projects/{pid}/graph` 的静态
  `generated/graph.json`**——它只在手动重新生成时更新，卡片编辑后必然陈旧（L1）。
- **路由注册顺序**：`/cards/links` 必须注册在 `/cards/{kind}` 之前，否则 `links`
  被当成卡种名 404（L2）。
- 现有 `/cards/{kind}` 响应形状零改动，既有 API 测试不受影响。

响应形状（`links` 键 = **目标卡种**，不是字段名；悬空引用保留在 `links`、
天然进不了 `referenced_by`——`_edge` 按目标卡种过滤）：

```json
{
  "entities": {
    "fact-01": {
      "kind": "fact", "status": "draft", "summary": "…",
      "links": {"data": ["data-01"], "claim": ["claim-02"]},
      "referenced_by": {"facts": [], "claims": [], "methods": [], "params": [], "nodes": []}
    }
  }
}
```

`summary` 同列表行 `key` 口径（KEY_FIELD 值）；`referenced_by` 五键语义同
`graphgen/index.py` docstring；rejected 卡包含在内（L8）；`nodes` 键前端忽略（L10）。

## 3 前端架构

- **新增 `CardsUiContext`**（`webui/src/state/`，仿 `toast.tsx` 的 context 模式），
  Provider 挂在 `App.tsx` 的 `Workspace` 内（Sidebar 与页面元素的公共祖先）：
  1. 选中卡镜像 `{kind, id} | null`——CardsPage 仍是选中态唯一属主，effect 上报；
  2. 标签选中态 `tagSel: string[]`（`kind/id` 串）+ toggle/clear 动作；
  3. `/cards/links` 数据——Provider 内 useApi，仅当 `pathname` 命中 `/cards/*`
     时激活请求。
- Sidebar 读 context 渲染筛选区；CardsPage 读 `tagSel` 过滤 rows。
- 契约同步 `webui/src/api/types.ts`；`pnpm build` 产物 `static/app/` 提交入库。

## 4 交互规格

### 4.1 侧栏筛选区（`Sidebar.tsx`）

- 位置：导航项之后、底部区块，小节标题「筛选」；仅当路由在 `/cards/*` 且存在
  有效选中卡时渲染；区域 `max-height` + 滚动（note 页邻居可达三组）。
- 标签 = 选中卡的**直接邻居（双向）**，按邻居卡种分组（组标题带卡种图标）：

| 选中卡种 | 标签组 |
|---|---|
| data | fact（反向：谁引用我） |
| fact | data、claim（正向） |
| claim | fact（反向）、note（正向 cites） |
| note | claim、method、param（全反向） |
| method | param（反向）、note（正向 derived_from） |
| param | method（正向）、note（正向 derived_from） |

- pill 形态：`id + 计数徽章`（计数 = 当前卡种列表里连着该标签的卡数，纯前端由
  links payload 算）；点击切换选中（多选、**并集**），再点取消；有选中时显示
  「清除筛选」。
- 邻接判定对称规则：卡 c 连着标签 t ⟺ `t ∈ c.links[t.kind]` **或**
  `c ∈ t.referenced_by[反向键]`。反向键 = `referenced_by` 中以来源卡种复数
  命名的键（fact→facts、claim→claims、method→methods、param→params；
  data/note 无出链，走前一判据即可）。任一方向命中即算连通。
- 选中卡无任何邻居时筛选区整区隐藏（悬空引用不成 pill，不产生空分组）。

### 4.2 筛选条（`CardsPage.tsx` 列表上方）

- 激活时渲染：每个选中标签一枚 chip——**点 chip 名跳转**到那张卡（反向邻居的
  打开路径：data 卡 → 点 fact-03 pill → 筛选条点 fact-03），**✕ 单独移除**该
  标签；尾部「清除」全部。

### 4.3 Inspector 引用字段 chip 化（`CardsPage.tsx`）

- 前端常量表字段→目标卡种：fact.data→data、fact.supports→claim、
  claim.cites→note、method.derived_from→note、param.method→method、
  param.derived_from→note；data 与 note 无出链字段。data 卡的 `refs` 是图号
  不是卡，不做 chip。
- chip 点击跳转 `/cards/{目标种}/{id}`；目标 id 不在 links entities（悬空引用）
  → 警示色 + title「悬空引用」，点击仍导航（现有路由对不存在卡已是无选中安全态）。
- chips 数据来自既有 detail payload 的 `card.fields` + 常量表，**不依赖 links
  请求**——links 挂了只隐藏筛选区，inspector/列表照常。

### 4.4 状态规则

1. 换选中卡或换卡种 → `tagSel` 清空（标签是"这张卡的邻居"上下文，L3/L6）。
2. 筛选态不入 URL、不持久化（L6）：R1 语义下标签态生命周期只有几秒。
3. 多选并集下选中卡自己恒在结果集（它连着自己的每个邻居），无空列表分支
  （仍防御性保留空态渲染）。
4. rejected 卡照常出现在 pills 与筛选结果（L8）；悬空引用不生成 pill（L9）。

## 5 样式

`webui.css` 末尾新增 `.filter-panel`（分组/pill/计数徽章/滚动）、`.filter-bar`
、`.chip`（含 `.chip.active`/`.chip.dangling`）。全部走既有设计令牌，
`themes/*.css` 不动（守卫测试不受影响）。

## 6 红线与诊断码

只读端点 + 纯前端过滤：无新落盘点、无新诊断码、schema 未动、红线 1–6 不动。
`build_index` 为既有纯函数，本设计不改 graphgen 层。

## 7 非目标（v1）

- 叙事节点反向边（`referenced_by.nodes`）的展示与跳转——目标在叙事页，另立话题。
- "data→facts 覆盖矩阵"式概览（原方案 2 的检查需求）——将来若需要放图谱/诊断页。
- 标签态 URL 持久化、inspector「被引用区」（被侧栏 pills 取代，见 L7）。

## 8 测试计划（TDD）

**后端**（`tests/test_web_card_links.py` 新建，+5）：

1. `test_card_links_payload` — 六卡种 entities 形状：kind/status/summary、
   links 按目标卡种（fact 含 data+claim 两组；param 含 method+note）、
   referenced_by 五键。
2. `test_card_links_forward_keeps_dangling` — 悬空引用在 `links` 里出现、
   不出现在任何 `referenced_by`。
3. `test_card_links_includes_rejected` — rejected 卡在 entities 且反向边完整。
4. `test_card_links_route_precedes_kind` — `/cards/links` 200（不被
   `/cards/{kind}` 吞）；`/cards/unknown-kind` 仍 404。
5. `test_card_links_unknown_project_404`。

**前端**（vitest 冒烟，+4）：

1. pills 分组渲染 + 计数徽章（选中 fact → data/claim 两组）。
2. 多选并集过滤 rows；再点取消；「清除筛选」复原。
3. 换选中卡 → 标签选中态清空、过滤失效。
4. 筛选条 chip 名跳转 + ✕ 移除；inspector 悬空 chip 警示类。

预期全量：**pytest 817 passed, 2 deselected**（基线 812 + 5）；
**vitest 12 passed**（基线 8 + 4）。

## 9 决策表

| # | 决策 | 理由 |
|---|---|---|
| L1 | 链路数据实时 `build_index` + forward 合并，不复用静态 graph.json | graph.json 仅手动再生成时更新，卡片编辑后陈旧；实时端点永远正确且代价小 |
| L2 | 筛选放侧栏左下、标签式、可多选；标签随选中卡变化 | 用户两轮定案（修正 inspector 内筛选设想 + 选 R1 随选语义） |
| L3 | 标签 = 选中卡直接邻居（双向），按邻居卡种分组 | R1 的直接推论；六卡种统一一条规则，无每卡种特例 |
| L4 | pill=过滤切换；筛选条 chip 名=导航；字段 chip=导航 | 过滤与导航单一职责分离；反向跳转经筛选条两击到达，正向一击 |
| L5 | 多选并集 | 标签筛选惯例；选中卡恒在结果集，无空态分支 |
| L6 | 标签态不入 URL、换卡即清空 | R1 下状态生命周期极短，持久化无收益，省一套 query 管道 |
| L7 | 取消 inspector「被引用区」 | 侧栏 pills 已完整展示双向邻居，重复展示无增量 |
| L8 | rejected 照常进 pills/筛选结果 | 审阅需看见被否决卡的支撑关系；StatusBadge 自明状态 |
| L9 | 悬空引用：进 links、成警示 chip、不成 pill | 字段值是真实落盘内容必须可见；pill 必然空结果是噪音 |
| L10 | `referenced_by.nodes` v1 忽略 | 导航目标在叙事页，与本设计的卡链路是两个话题 |
