# weft WebUI React 化设计（2026-10-13）

状态：定案（本分支 `webui-react` 内实施）。前置勘察：本文档基于对 `src/weft/web/` 全量路由/模板/测试与参考项目 `itemmanage`（Vue3 + Tauri，仅取其布局与视觉范式）的实测报告写成。

## 0. 定位与范围

把 WebUI 从「FastAPI + Jinja2 + htmx 服务端渲染」整体升级为「FastAPI JSON API + React SPA」。**能力 1:1 保留，不新增业务功能**：现有全部页面（项目列表、dashboard、卡片 CRUD 与审阅、note 文献提案、parts/工作流/节点、draft 生成与运行控制台、图谱、figures、灵感管线与提案对比、诊断、bib 模式切换与一键修复、文件查看）在 React UI 中均有对应入口，交互语义（审阅状态机、生成闸门、fail-closed 隐藏应用按钮等）不变。

参照 `itemmanage` 移植的是**布局骨架与视觉范式**（三栏工作台、行列表、令牌化灰白基调、行内编辑、模态/Toast 范式），不是其技术栈（Vue/Pinia/Tauri 一概不引入）。

## 1. 总体架构

```
浏览器（React SPA，静态资源）
   │  fetch JSON / EventSource SSE
   ▼
FastAPI（src/weft/web/）
   ├─ /api/...            JSON 端点（新增，替代全部 HTML 路由）
   ├─ /api/projects/{pid}/runs/{rid}/events   SSE（沿用 RunManager/事件词表）
   ├─ /static/...         StaticFiles：webui.css、themes/*.css、cytoscape.min.js、app/*（SPA 构建产物）
   ├─ GET / 及其余 GET     SPA shell（static/app/index.html，FileResponse）
   └─ GET /healthz        不变
```

- 旧 `templates/`（20 个 Jinja2 模板）、`static/htmx.min.js`、`static/webui.js` 删除；`jinja2` 从 web extra 移除（实现时先 grep 确认无其他使用点）。
- React 源码在仓库根 `webui/`（独立 Vite 项目，pnpm）；**构建产物输出到 `src/weft/web/static/app/` 并提交入库**——wheel 随包分发、现场无外网可运行（与 htmx/cytoscape vendored 同理），运行时零 Node 依赖。
- SPA 宿主：注册在 `/api`、`/static`、`/healthz` 之后的 catch-all `GET` 返回 `static/app/index.html`（前端 react-router BrowserRouter 接管路径）；`/api/*` 未匹配路径返回 JSON 404。

## 2. 技术选型（决策 D1–D6）

| 决策 | 内容 | 理由 |
|---|---|---|
| D1 | 全量替换，不做 htmx/React 双轨 | 双轨维护两套交互语义成本高于重写；单人项目、一次性切换 |
| D2 | React 18 + TypeScript + Vite 6 + react-router-dom；pnpm | 用户指定 React；与参考项目同为 Vite 系；TS 类型即 API 契约镜像 |
| D3 | 不引 UI 组件库、不引 Redux/React Query | 复刻 itemmanage「手写原语 + 轻状态」范式；数据层用自写 `useApi` fetch hooks（loading/error/data 三态）+ 模块级 Toast 单例 |
| D4 | 图标为内联 SVG 的 `<Icon name>` 组件（约 15 个） | 不 ship 字体文件，离线安全，按需维护 |
| D5 | 样式延续**单一全局 `webui.css`**（重写），组件只写语义类名；不用 scoped CSS/CSS-in-JS | 保住「全部值收敛令牌 + themes/*.css 纯令牌覆盖」既有守卫架构（AGENTS.md 红线级约定）；样式改动无需重建前端 |
| D6 | cytoscape 继续用 `/static/cytoscape.min.js` vendored 文件，图谱页运行时动态注入 `<script>`，不进 bundle | 373KB 不该进主包；构建产物稳定 |

## 3. API 设计

### 3.1 约定

- 前缀 `/api`；路径里项目统一 `/api/projects/{pid}`（pid 语义随 `app.state.projects_source`：registry 名 / 目录名，与现状一致）。
- 成功 mutation 返回 `200 {"ok": true, ...}`；创建返回 `{"ok": true, "id": ...}`。
- 失败：`404 {"detail"}`（项目/卡不存在）；`422 {"detail", "errors": [{field, message}]}`（表单校验、生成闸门拒绝——诊断码在 message/code 内原样透传）；`409 {"detail"}`（运行占用）；项目加载级损坏返回 `200` 但 `available=false` + 诊断列表（对应 unavailable 页，不 404，保住红线 3「加载永不中断」的展示语义）。
- 诊断数据结构统一 `{level, code, path, field, message}`；E-*/W-* 码为稳定标识，API 原样透传不翻译。
- 表单类写操作不再依赖 303 重定向：前端拿到 JSON 后自行跳转/刷新。

### 3.2 端点表（镜像现有页面能力）

**项目层**
| 端点 | 方法 | 对应旧页面 |
|---|---|---|
| `/api/projects` | GET | index（列表 + 可用性 + 计数） |
| `/api/projects` | POST | `/projects/new`（name/path，校验错误 422 回显） |
| `/api/projects/{pid}` | GET | dashboard（stats、bib 模式、待审队列） |
| `/api/projects/{pid}/diagnostics` | GET | diagnostics（诊断表 + 行内 fix 所需数据） |
| `/api/projects/{pid}/bib/fix/{key}` | POST | bib fix（`{result: added\|present\|error}`） |
| `/api/projects/{pid}/bib/switch?to=` | GET/POST | bib_switch_confirm（GET 返 plan 预检，POST 执行） |
| `/api/projects/{pid}/graph` | GET | graph（graph.json 数据；未生成 404 `{needs_generate}`） |
| `/api/projects/{pid}/graph/regenerate` | POST | graph/regenerate（校验 error 422 拒绝） |
| `/api/projects/{pid}/file?path=` | GET | file_view（白名单 drafts/generated + 穿越防护原样保留） |

**卡片**
| 端点 | 方法 | 对应旧页面 |
|---|---|---|
| `/api/projects/{pid}/cards?kind=` | GET | cards 总览/分 kind 列表 |
| `/api/projects/{pid}/card-forms/{kind}` | GET | card_form 渲染所需的规格（FIELD_SPECS + 引用下拉 choices + id 控件形态） |
| `/api/projects/{pid}/cards/{kind}` | POST | card_form 新建（422 回显错误，不落盘） |
| `/api/projects/{pid}/cards/{kind}/{card_id}` | GET | card_detail（entry、bib/pdfwarn 横幅数据、fix 可用性） |
| `.../rename` `.../status` `...`（PATCH） | POST/POST/PATCH | rename / status（approve/reject/draft，note 卡后 managed bib 同步结果在响应内）/ edit（422 回显） |
| `/api/projects/{pid}/notes/propose` | POST(multipart) | bib_propose（PDF 上传 + 线索；同步 LLM 调用，语义不变） |

**叙事与生成**
| 端点 | 方法 | 对应旧页面 |
|---|---|---|
| `/api/projects/{pid}/parts` | GET | parts 页签容器（part 清单 + 摘要） |
| `/api/projects/{pid}/parts/{part_id}` | GET | part_panel（工作流覆盖数据、节点表、草稿预览） |
| `.../parts/{part_id}/workflow` | POST | workflow 覆盖表单 |
| `.../parts/{part_id}/nodes/{node_id}` | GET/PATCH | node_form（GET 返表单数据含 uses 候选/实体速查；PATCH 保存，422 回显） |
| `.../parts/{part_id}/nodes/{node_id}/status` | POST | 节点快捷审阅 |
| `.../parts/{part_id}/generate` | POST | 生成（202 `{run_id}`；闸门 422 诊断列表；占用 409） |
| `/api/projects/{pid}/runs/{run_id}/events` | GET(SSE) | 不变（事件词表 `run_started/…/run_failed` 原样） |

**图表 / 灵感**
| 端点 | 方法 | 对应旧页面 |
|---|---|---|
| `/api/projects/{pid}/figures` | GET | figures 列表（带病只读 `load_error` 语义保留） |
| `/api/projects/{pid}/figures` | POST | figure_form 新增（E-FIG-* 422 透传） |
| `/api/projects/{pid}/figures/{key}` | GET/PATCH | figure_form 编辑回显/保存 |
| `/api/projects/{pid}/figures/{key}/delete` | POST | 删除（E-FIG-IN-USE 拒绝） |
| `/api/projects/{pid}/inspire` | GET | inspire 提案列表 |
| `/api/projects/{pid}/inspire/run` | POST | 灵感管线（202 `{run_id}`；409；422） |
| `/api/projects/{pid}/inspire/proposals/{card_id}` | GET | proposal_compare（字段对照 + diff + `applicable`，fail-closed 原样） |
| `/api/projects/{pid}/inspire/proposals/{card_id}/apply` | POST | 应用提案 |

## 4. 布局与信息架构（复刻 itemmanage）

两态切换（对齐 itemmanage App.vue 的 repo 未开/已开）：

1. **项目仪表盘 `/`**：全屏居中列（max-width 880px），logo + 标题 + 副标语，下方 flex wrap 卡片网格（约 180×140 surface 卡、r-lg、hover 上浮 + 阴影 + 边框加深，hover 出操作角标）；网格尾「新建项目」tile 打开模态（name/path 表单；错误回显在模态内）。
2. **项目工作台 `/p/:pid/...`**：
   - **Topbar 48px**：左 = brand「weft」+ 项目切换下拉（registry 模式列全部项目，scan 模式单项）+ 返回网格入口；右 = 主题切换按钮。
   - **Sidebar 240px**：上=搜索/过滤留位（本期仅导航）；section「导航」：总览、叙事、卡片（kind 分组：data/fact/claim/note/method/param）、图表、图谱、灵感、诊断；active 态 = accent-subtle 底。
   - **CenterPanel flex**：各 section 主视图。范式移植 itemmanage **行列表**（非表格）：行 = 类型图标 + 双行主体（标题 fw-medium + meta 行 fs-xs），hover surface-hover，选中整行反色（accent 底 accent-fg 字）；空状态 = 居中大图标（opacity .2）+ 文案 + primary 按钮。
   - **RightPanel 360px（inspector，可关）**：cards 选中卡 → 详情 + 审阅操作（批准/否决/退回 + comment + 行内重命名）；figures 选中 → 编辑表单；其余 section 右栏隐藏、中栏占满。
   - **StatusBar 28px**：左 = 项目路径；右 = E/W 计数徽章 + 「就绪」。
3. **宽视图**：图谱、运行控制台、提案对比、诊断表在中栏全宽渲染（右栏自动隐藏）。运行控制台 = SSE 日志流（终态后自动刷新来源面板数据）。
4. **不移植 ActivityBar**（itemmanage 右侧 48px 图标条）：它服务其「详情/笔记/类别/插件」多面板信息架构，weft 的 inspector 单面板不需要；右栏关闭按钮承担同等能力（记为决策 D7）。
5. 弹窗范式：Teleport 等价的 fixed overlay（rgba 黑 20%）+ 居中 modal（surface、r-xl、shadow-lg）+ `点遮罩关闭` + 底部 ghost/primary 按钮组。用于新建项目、note 文献提案（multipart 表单）、卡片新建/编辑（表单较长，走中栏路由而非模态）。

## 5. 视觉令牌与主题

`webui.css` 重写为 itemmanage 式**槽位令牌**（沿用既有文件路径与守卫架构）：

- 槽位集对齐 itemmanage：`--bg/--surface/--surface-hover/--surface-active/--text/--text-secondary/--text-muted/--text-heading/--border/--border-light/--border-strong/--accent/--accent-hover/--accent-subtle/--accent-fg/--danger(+hover/subtle)/--success/--warning/--link` + 字号 `--fs-xs..--fs-2xl`、非标字重族、圆角 `--r-sm..--r-full`、动效 `--fast/--normal/--slow/--ease`、布局宽度 `--sidebar-w:240px/--right-w:360px/--topbar-h:48px/--status-h:28px`。旧令牌名不保留（全量重写，无外部消费者）。
- 主色 = notion 式黑白灰 accent（亮色 accent 为近黑、暗色预留为近白），语义色仅 danger/success/warning——**视觉基调与 itemmanage 一致**。
- 全局原语进 webui.css：`button/.btn`（32px 高；`.primary/.ghost/.danger/.icon-btn` 变体；focus-visible 2px accent outline）、`input/select/textarea`（32px、focus 变边框色）、自定义滚动条、`.text-muted/.text-xs/.font-mono/.truncate` 工具类。
- 主题：默认亮色（:root）+ `themes/academic.css` 重制（纸感学术配色，纯令牌覆盖）。**暗色主题不在本期**（旧设计非目标，架构预留不变）。防闪脚本、`data-theme`、`localStorage["weft-theme"]`、Topbar 切换按钮循环语义全部沿用。
- 守卫测试适配：`themes/*.css` 纯令牌断言改为遍历 `static/themes/` 全部 `.css` 文件；`GET /` 返回的 SPA shell 断言含防闪脚本/`weft-theme`/主题 link。

## 6. 前端结构（webui/）

```
webui/
├─ package.json  vite.config.ts  tsconfig.json  vitest 环境配置
├─ index.html                # 防闪脚本 + /static/webui.css + themes link + #root
└─ src/
   ├─ main.tsx  App.tsx      # App = 布局骨架 + 路由表
   ├─ api/client.ts          # fetch 封装：JSON 化、{detail,errors} 归一为 ApiError、multipart
   ├─ api/types.ts           # 端点请求/响应类型（与 pydantic 模型镜像）
   ├─ hooks/useApi.ts        # GET 数据 hook + 手动刷新；mutation 用 client + 局部 state
   ├─ state/theme.ts         # THEMES/applyTheme（沿用 weft-theme key 与 data-theme）
   ├─ state/toast.tsx        # 模块级单例 toast.success/error/info（3.5s 自消）
   ├─ components/
   │  Topbar  Sidebar  CenterPanel  RightPanel  StatusBar
   │  Icon  Modal  Toast  EmptyState  RowList  Tabs  Diff  RunConsole  StatusBadge
   └─ pages/
      ProjectsGrid            # /
      Overview                # /p/:pid（stats + bib 行 + 待审队列）
      Parts / PartPanel / NodeForm          # /p/:pid/parts[/...]
      Cards / CardDetail(inspector) / CardForm
      Figures / Inspire / ProposalCompare
      Graph / Diagnostics / FileView / RunConsolePage / BibSwitch
```

路由：`/`、`/p/:pid`、`/p/:pid/{parts|parts/:partId|parts/:partId/nodes/:nodeId|cards/:kind?|figures|graph|inspire|inspire/proposals/:cardId|diagnostics|bib-switch|runs/:runId}`、`/p/:pid/files?path=`。数据流：页面级 `useApi` 拉取 → 局部 state 承载选中项 → mutation 后手动 refetch（无全局缓存层，与 itemmanage store 直调同风格）。错误策略：ApiError → toast.error（写操作）或页面内错误横幅（读操作）；SSE 终态后触发来源页 refetch。

## 7. 服务端改造

- `routes/` 六个模块重写为 `api/`（同名域拆分：projects/cards/parts/figures/inspire/bib），业务调用点（store/validate/engine/figures_edit/bibgen/registry/runs）**一律不变**——web 层仍是公共 API 之上的薄壳（红线 1/3/4/6 不受影响）。
- `common.py` 的 Jinja2Templates 移除；三档加载器与 `_SAFE_ROOTS` 白名单逻辑原样保留给 API 层复用。
- SPA 宿主路由 + `static/app` 构建产物挂载（见 §1）；`FileResponse` 带 no-cache（index.html）避免更新后缓存漂移，assets 带 hash 文件名天然长效缓存。
- `pyproject.toml`：web extra 移除 jinja2，其余不动。

## 8. 测试策略

- **Python**（主基线）：`tests/test_web_*.py` 全部改写为 JSON API 断言（TestClient，沿用 `tests/webutil.py` 夹具），逐文件对位旧 HTML 测试的语义（校验失败不落盘、闸门拒绝、409、fail-closed、SSE 事件序列、穿越防护、注册表失联、E-*/W-* 透传等）；主题守卫按 §5 适配。**基线 812 collected 中的 141 条 web 用例由新 API 用例等语义替换，全量预期计数在计划文档登记并在执行期回填实测值。**
- **前端**：vitest + @testing-library/react 冒烟若干条（App 挂载与两态切换、theme 模块、api client 错误归一、Toast 单例），`pnpm test` 纳入手工验收，不进 pytest 计数。
- 守卫测试 `tests/test_engine_layering.py` 不动（web 层继续禁 import llm/module_harness）。

## 9. 非目标（延续旧设计 §11 并扩充）

认证/多用户/移动端、卡片删除、WebSocket、多语言 i18n（界面文案维持中文硬编码）、暗色主题、ActivityBar/插件架构、命令面板、拖拽排序、分页/排序、React 状态库、构建产物 CI 自动化（构建为手动 `pnpm build`，产物提交）。

## 10. 决策登记

| # | 决策 | 备注 |
|---|---|---|
| D1 | 全量替换 htmx/Jinja2，无双轨 | |
| D2 | React18+TS+Vite6+react-router，pnpm，源码在 `webui/` | |
| D3 | 无组件库/无状态库；自写 useApi + Toast 单例 | 对齐 itemmanage 范式 |
| D4 | 内联 SVG Icon 组件，不 ship 字体 | |
| D5 | 单一全局 webui.css 重写，组件只写类名 | 保令牌守卫架构 |
| D6 | cytoscape 运行时注入，不进 bundle | |
| D7 | 不移植 ActivityBar，右栏可关闭 | 信息架构无多面板需求 |
| D8 | 构建产物 `static/app/` 提交入库 | wheel 分发 + 离线约束 |
| D9 | 卡片新建/编辑走中栏路由，审阅/详情在右栏 inspector | 表单长，360px 不够 |
| D10 | 诊断码经 API 原样透传，前端不翻译不重组 | 稳定标识红线 |
| D11 | unavailable（加载级损坏）不 404，`available=false` + 诊断列表 | 红线 3 展示语义 |
| D12 | 本期两主题（默认亮 + academic 重制），dark 预留 | 旧设计非目标延续 |
