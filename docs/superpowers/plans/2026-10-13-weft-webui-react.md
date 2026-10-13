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
| P1 | （待回填） | |

## 实测计数回填

- （执行完成后回填：pytest 总数、web/API 用例数、vitest 数）
