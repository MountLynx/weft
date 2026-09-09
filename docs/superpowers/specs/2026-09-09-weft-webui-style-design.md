# weft WebUI 样式美化设计（令牌化主题架构）

日期：2026-09-09
状态：已与用户对齐，待实施
关联：`src/weft/web/`（weft serve WebUI，FastAPI + Jinja2 + htmx）

## 1. 背景与目标

现状：WebUI 16 个模板共用一份 38 行的极简 `webui.css`（GitHub 风格雏形），颜色/间距/字体全部硬编码在组件规则里，无主题能力。

目标：

1. **视觉升级**——在现有 GitHub 风格基础上系统化精修（设计令牌、阴影、徽章、按钮分级、表格与统计卡观感），不重排页面结构。
2. **令牌化架构**——全部样式值收敛到 `:root` 语义令牌；组件规则只引用令牌，不写死值。
3. **第二主题「学术纸面」**——米白纸色、衬线字体、砖红点缀、细线分隔，呼应"AI 学术写作引擎"的产品气质。
4. **用户可自定义**——新增主题 = 照抄一个纯令牌覆盖文件；导航栏可视化切换，localStorage 持久化。

非目标（本期不做）：暗色主题（令牌架构已预留，后续加一套覆盖文件即可）；`prefers-color-scheme` 跟随系统；页面布局重构；任何 htmx 交互行为改动；服务端主题配置。

## 2. 已定决策

| # | 决策点 | 定案 |
|---|--------|------|
| D1 | 风格方向 | A「精致 GitHub 风」演进，不推倒重来 |
| D2 | CSS 架构 | 方案一：基础样式 + 主题独立文件（主题文件只含令牌覆盖块） |
| D3 | 第二主题 | C「学术纸面风」 |
| D4 | 切换机制 | 顶栏分段控件 + localStorage，`<html data-theme>` 驱动，纯前端 |
| D5 | 改动范围 | CSS 为主 + 小幅模板语义调整（加 class/控件），不动结构与 htmx 行为 |
| D6 | 暗色模式 | 暂不做，令牌架构预留 |

## 3. 文件组织

```
src/weft/web/static/
  webui.css            # :root 令牌定义 + 全部组件样式（只引用令牌）
  themes/academic.css  # 仅 [data-theme="academic"] { --令牌: 值 } 覆盖块
  webui.js             # 已有；追加主题切换控件的事件逻辑
```

- `base.html` `<head>` 中新增一行 `<link rel="stylesheet" href="/static/themes/academic.css">`。
- 主题文件**只允许出现令牌覆盖**，不允许出现组件选择器——这是"主题 = 纯令牌文件"约定的守卫点（见 §8 测试）。
- 用户自定义主题路径：复制 `themes/academic.css` 为 `themes/<名字>.css` 改令牌值，再在 `base.html` 与 `webui.js` 注册（完整三步骤见 §6 第 4 条）。

## 4. 令牌集（语义化，约 30 个）

按用途分组，命名稳定后即为公共 API（自定义主题依赖它）：

- **表面**：`--bg`（页面底色）、`--bg-subtle`（卡片/表头浅底）、`--bg-nav`（顶栏底色）、`--bg-inset`（run-log 等深色内嵌区，可缺省）
- **文字**：`--fg`、`--fg-muted`、`--fg-nav`、`--fg-on-accent`
- **边框/分隔**：`--border`、`--border-muted`
- **品牌/强调**：`--accent`、`--accent-subtle`（链接悬停底、信息徽章底）
- **语义色三件套**（success/warning/danger 各配 `--x`、`--x-subtle` 底、`--x-border` 边）：徽章、横幅、统计卡、按钮共用
- **形状**：`--radius`、`--radius-lg`、`--radius-pill`、`--shadow-sm`、`--shadow-md`
- **字体**：`--font-body`、`--font-mono`；学术主题用 `--font-body` 切衬线（Georgia + Noto Serif SC / 系统宋体回退），等宽字体两主题一致（Consolas 系）
- **间距**：`--space-1` … `--space-6`（4/8/12/16/24/32px 基准）

默认主题取值即精修后的 GitHub 色板（`#ffffff` / `#f6f8fa` / `#24292f` 顶栏 / `#1f2328` 文字 / `#0969da` 链接 / `#1a7f37` `#9a6700` `#cf222e` 语义色等）；学术主题取值以视觉稿为准（`#faf7f0` 纸底 / `#2c2a26` 墨色 / `#9a3324` 砖红 / `#3f6b4a` 墨绿 success / `#8a6116` 赭黄 warning / 细线代盒、小圆角 2px、阴影置零）。

## 5. 组件升级清单（两主题共享同一套组件规则）

- **顶栏**：深色条改令牌驱动；右侧新增分段式主题切换控件（胶囊两段：☀ 默认 / 📜 学术，激活段实底）。
- **按钮三级**：`.btn-primary`（实底强调）、默认（浅底描边+微阴影）、`.btn-danger`（危险红）。现有 `button.ok`/`button.bad` 选择器保留并映射到新样式，模板逐步替换为语义 class。
- **徽章**：`.badge.approved/draft/rejected` 改"浅底+深字+同系边框"（GitHub 风），不再纯白字实底；学术主题经令牌自动变为细描边小方章。
- **统计卡 `.stat`**：浅底卡片+微阴影；`draft 待审`/`错误` 在有值时用对应语义浅底突出（模板已具备 `bad` class 钩子，draft 卡新增同型 class）。
- **表格 `.list`**：外框圆角+裁剪、表头浅底、行分隔线弱化（`--border-muted`）、悬停行高亮。
- **页签 `.tabs`、横幅 `.banner`、字段错误、表单控件**：统一圆角/间距/焦点环（`:focus-visible` 用 `--accent`）。
- **run-log**：保持深色终端观感（`--bg-inset` 缺省即深色，学术主题不强制反色）。

## 6. 切换机制细节

1. `base.html` `<head>` 内联脚本（CSS `<link>` 之前）：读 `localStorage.getItem("weft-theme")`，非空则 `document.documentElement.dataset.theme = 值`——**刷新无闪烁**；脚本包 try/catch（隐私模式 localStorage 可能抛异常，失败静默走默认主题）。
2. 顶栏切换控件点击：写 `data-theme` + localStorage，纯前端零请求，立即生效。
3. 无存储值 / 值为空 → 默认主题（不设 `data-theme`）。
4. 控件 HTML 静态写在 `base.html` 顶栏（不做动态渲染）；`webui.js` 中的 `THEMES = [{id:"", label:"☀ 默认"}, {id:"academic", label:"📜 学术"}]` 常量数组只用于绑定点击与同步激活态高亮。新增主题的步骤：加令牌覆盖文件 → `base.html` 加 `<link>` 与一段控件 → `THEMES` 数组加一项，共三处。

## 7. 模板调整清单（最小集）

| 模板 | 调整 |
|------|------|
| `base.html` | 防闪内联脚本、`themes/academic.css` `<link>`、顶栏切换控件 |
| `index.html` / `dashboard.html` | 主操作按钮加 `.btn-primary`；draft 统计卡加语义 class |
| `card_detail.html` / `part_panel.html` 等含 approve/reject 按钮处 | `ok`/`bad` 按钮补 `.btn-primary`/`.btn-danger`（保留旧 class 兼容） |
| 其余模板 | 不动，靠组件级 CSS 自动升级 |

## 8. 测试

- 现有 serve 测试全绿（334 passed 基线不回退）。
- 新增：`/static/themes/academic.css` 路由 200；`base.html` 渲染含防闪脚本、`data-theme` 控件与 academic.css `<link>` 的断言。
- 新增守卫：`themes/academic.css` 内容只含 `--` 开头的自定义属性声明（正则扫描，拦截组件选择器混入主题文件）。
- 视觉验收：浏览器手动过 16 个模板 × 2 主题（项目列表、总览、卡片、审阅、图谱、灵感、运行控制台为必看点）。

## 9. 视觉稿存档

高保真并排视觉稿见 `.superpowers/brainstorm/666-1788921255/content/themes-preview.html`（本地未入库；实施时以本文件 §4-§5 的令牌取值描述为准）。
