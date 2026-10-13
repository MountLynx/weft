# weft WebUI React 化实施计划（2026-10-13）

设计文档：`docs/superpowers/specs/2026-10-13-weft-webui-react-design.md`（决策 D1–D12）。
分支：`webui-react`（worktree `.worktrees/webui-react`）。基线：**812 passed, 2 deselected**（worktree venv 实测通过后开工）。

## 任务分解（TDD）

### T1 服务端 API 层（先红后绿）

先改写 `tests/test_web_*.py` 为 JSON API 断言（保留文件名做映射对照），全部跑红 → 重写 `src/weft/web/routes/` 与宿主为 `api/` 端点跑绿。逐文件语义对位与预期计数（合计 **153**，与旧 web 用例数持平；执行期如有偏离回填实测）：

| 文件（旧→新语义） | 旧 | 新预期 |
|---|---|---|
| test_web_app.py：SPA shell 宿主（`/` 返 index.html、`/api/*` 未知 404 JSON、/healthz、禁 /docs） | 3 | 4 |
| test_web_new_project.py：POST /api/projects（校验/冲突/重定向语义转 JSON） | 20 | 20 |
| test_web_registry.py：registry 模式列表/失联/体检 | 13 | 13 |
| test_web_discovery.py：scan 模式发现 | 3 | 3 |
| test_web_pages.py：dashboard payload + unavailable（available=false 不 404） | 5 | 5 |
| test_web_subnav.py：项目 payload 携带导航计数（叙事/卡片 kind 等） | 5 | 4 |
| test_web_theme.py：themes/*.css 全目录纯令牌守卫 + shell 含防闪/weft-theme/主题 link | 3 | 3 |
| test_web_cards.py：列表/详情/status/rename（note 卡 managed bib 同步语义） | 19 | 19 |
| test_web_card_new.py：form-spec（FIELD_SPECS+choices+id 形态）/新建 422 回显不落盘 | 8 | 8 |
| test_web_card_edit.py：编辑回显/PATCH | 7 | 7 |
| test_web_bib_propose.py：multipart 提案/详情横幅数据 | 15 | 15 |
| test_web_parts.py：parts 清单/panel/workflow/节点快捷审阅 | 8 | 8 |
| test_web_node_edit.py：节点表单数据（uses 候选/实体速查）/PATCH | 4 | 4 |
| test_web_generate.py：生成 202→SSE 事件序列/409/闸门 422 | 4 | 4 |
| test_web_figures.py：figures CRUD（E-FIG-* 透传、IN-USE 拒绝、带病只读） | 14 | 14 |
| test_web_inspire.py：run 202/409、提案对比 fail-closed、apply | 10 | 10 |
| test_web_bibmode.py：switch plan/执行、fix added/present/error | 9 | 9 |
| test_web_misc.py：file 白名单/穿越防护/404 | 3 | 3 |

### T2 webui/ 脚手架

`pnpm create vite`（react-ts）→ `webui/`；依赖 react/react-dom/react-router-dom，dev 依赖 vitest/@testing-library/*；`vite.config.ts` 设 `base:'/static/app/'`、`build.outDir:'../src/weft/web/static/app'`、dev proxy `/api|/static` → 127.0.0.1:8000。落 `api/client.ts`（ApiError 归一）、`api/types.ts`、`hooks/useApi.ts`、`state/theme.ts`（沿用 `weft-theme`/`data-theme`）、`state/toast.tsx`、`Icon`。vitest 冒烟：client 错误归一 / theme 切换 / toast 单例 / App 挂载（**预期 6 条，pnpm test 计数**）。

### T3 布局骨架 + webui.css 重写

`webui.css` 重写为槽位令牌（§5 of 设计）+ 全局原语（btn/input/滚动条/工具类）；themes/academic.css 重制为纯令牌。组件：Topbar/Sidebar/CenterPanel/RightPanel/StatusBar/Modal/Toast/EmptyState/RowList/Tabs；两态 App（ProjectsGrid 网格 ↔ 工作台）。布局宽度令牌 240/360/48/28。

### T4 功能页面

按设计 §3.2 端点表逐页接线：Overview、Cards(list)+CardDetail(inspector)+CardForm、Parts+PartPanel+NodeForm+RunConsole(SSE)、Figures、Graph(cytoscape 注入)、Inspire+ProposalCompare(Diff)、Diagnostics、BibSwitch、FileView。全部写操作走 client + toast/横幅错误。

### T5 收尾

删 `templates/`、`htmx.min.js`、`webui.js`；`common.py` 去 Jinja2；web extra 去 jinja2（先 grep 全库确认）；`pnpm build` 产物提交；AGENTS.md 必读文档/常用命令登记（React 构建命令）、roadmap M4 登记；本计划计数回填。

## 验收

1. `pytest tests -q` 全绿，计数 **≥812**（新 API 用例 153 条等语义替换）并在本文件回填精确值。
2. `cd webui && pnpm test` 全绿（6 条）；`pnpm build` 成功且产物已提交。
3. 手工冒烟：`weft serve` 打开 → 项目网格 → 进入示例项目 → 卡片审阅/新建 → parts 面板与节点审阅 → figures/graph/inspire/诊断/bib 切换可达；三主题切换 + 防闪正常；SSE 控制台事件实时滚动。
4. 红线不破：分层守卫、路径白名单、生成闸门、诊断码透传、加载永不中断语义均有对应用例。

## 设计决策（执行期回填）

| # | 偏离/补充 | 理由 |
|---|---|---|
| P1 | 宿主 catch-all 路由对 `/` 也返回 SPA shell；`/docs`、`/openapi.json` 在 openapi_url=None 后同样落 SPA 宿主（无 FastAPI 文档内容即视为禁用生效） | starlette 路由匹配顺序决定，测试断言按实际语义写 |
| P2 | dashboard payload 的 `available` 取 `entry.available`（校验错误项目 available=False 但仍带完整 stats/review_queue；加载级损坏才只有 diagnostics） | 修复执行中发现的语义 bug：available 原被写死 True，丢失「不可用徽章」语义 |
| P3 | `openapi_url=None` 追加于应用工厂 | docs_url=None 只关 UI 页，schema 端点仍在；一并关闭更符合「禁用文档」意图 |
| P4 | 图谱页数据适配按旧 graph.html 内联脚本语义重写（`entities` 字典 + `referenced_by` 反向边 + 旧调色板） | 首版误假设 nodes/edges 数组形状，浏览器走查发现后对齐 |
| P5 | figures 用例 15（新增 GET 带病 422）、bib_propose 用例 14（删表单渲染测试，表单属前端职责）；subnav 4（payload 驱动导航） | 计划预期 153 总数不变，逐文件分布微调 |
| P6 | pnpm v12 拦构建脚本：`webui/pnpm-workspace.yaml` 声明 `onlyBuiltDependencies: [esbuild]` + `dangerouslyAllowAllBuilds`；`package.json` 的 `pnpm` 字段已不被 v12 读取 | esbuild postinstall 需要；CI 模式下 ignored builds 是硬错误 |
| P7 | 卡片审阅后列表刷新用 `navigate(0)` 整页刷新（单用户工具可接受），后续可换局部 refetch | inspector 与列表数据分属两处 useApi，跨组件刷新的最小实现 |

## 实测计数回填

- pytest 全量：**812 passed, 2 deselected**（与基线持平；旧 153 条 web 用例由 153 条 JSON API 用例等语义替换）
- 逐文件（旧→新）：app 3→4、bib_propose 15→14、bibmode 9→9、card_edit 7→7、card_new 8→8、cards 19→19、discovery 3→3、figures 14→15、generate 4→4、inspire 10→10、misc 3→3、new_project 20→20、node_edit 4→4、pages 5→5、parts 8→8、registry 13→13、subnav 5→4、theme 3→3
- 前端 vitest：**6 passed**（client 归一 ×2、theme、toast、App 网格、404 态）
- 构建产物：`static/app/index.html` + `assets/index-*.js` 224 KB（gzip 69 KB）；浏览器走查通过（网格/总览/卡片 inspector/叙事/图谱 cytoscape/academic 主题）
