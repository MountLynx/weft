# weft WebUI「新建项目」实施计划（2026-09-08）

## 背景与目标

项目列表页（`GET /`）此前只能查看，无法创建项目——webui 设计 §3 路由表无对应条目，§11 非目标亦未排除（遗漏而非有意降期）。本任务补齐：列表页内嵌「新建项目」表单，提交后复用 `weft/scaffold.py::init_project`（CLI `weft init` 同一落盘点，红线 4 不新增旁路）生成骨架，成功 303 跳转新项目仪表盘；空根目录冷启动场景（原先只提示"未发现项目"）随之可操作。

用户拍板（2026-09-08）：

- 项目目录名（即 pid）允许中文等任意安全字符，采用黑名单守卫，不做 ASCII 白名单；
- 入口为列表页内嵌表单（纯 POST 无 JS），不做独立 /new 页面。

## 设计决策

| # | 决策 | 理由 |
|---|------|------|
| D1 | 名称守卫黑名单制：拒绝空名、`.`/`..`/前导点/尾点、`\/:*?"<>|` 与控制字符、Windows 保留设备名（大小写不敏感）、长度 >100；校验前先 strip 首尾空白 | 用户拍板允许中文；pid 是用户可控的落盘路径组件，守卫只能放在 web 层（同 cards.py `_CARD_ID_RE` 先例）；尾点在 Windows 被静默剥离会造成 pid 与实际目录名不一致，故显式拒绝 |
| D2 | 冲突复用 `InitCollisionError`：回显列表页 + 横幅「目标目录非空（条目预览…）；为避免覆盖，未写入任何文件」，fail-closed 零写入；既有空目录维持 init 原语义原地生成 | 与 CLI `weft init` 的 `E-INIT-COLLISION` 语义完全一致，不另造行为 |
| D3 | 不新增 `E-*` 诊断码 | WebUI 表单错误走内联回显（卡片新建同模式），不落诊断表 |
| D4 | 重定向 Location 用 `quote(name, safe="")` percent-encode | 中文 pid 直接放进 Location 头会因 header 编码约束报错；FastAPI 路径参数自动解码，`load_entry_or_404` 按扫描名匹配天然兼容中文 |
| D5 | `GET /` 显式传 `new_error=None, new_name=""` | GET 与错误回显共用模板，避免依赖 Jinja Undefined 隐式行为 |

## 改动面

- `src/weft/web/routes/core.py`：`_validate_project_name` 守卫 + `POST /projects/new`（`index` 补 `new_error`/`new_name` 两个上下文键）
- `src/weft/web/templates/index.html`：错误横幅 + 内嵌表单（列表为空也显示，置于副标题与表格之间）
- `src/weft/web/static/webui.css`：`.new-project` 三行样式

## 任务分解（TDD）

| 任务 | 内容 | 结果 |
|------|------|------|
| T1 | 新增 `tests/test_web_new_project.py`：表单展示×2（含空根目录）、创建成功（303/骨架落盘/列表零诊断/仪表盘可达）、首尾空白 strip、中文名（Location 编码+直达）、冲突零写入、既有空目录原地生成、非法名参数化 12 例 | 先红：20 failed ✅ |
| T2 | core.py + index.html + webui.css 实现 | 后绿：20 passed ✅ |
| T3 | 全量回归 + 计数回填（AGENTS.md/本文档）+ roadmap 更新 | ✅ |

## 测试计数

- 基线：314 passed, 1 deselected
- 本任务新增：20（其中参数化 12 例）
- 全量：**334 passed, 1 deselected** ✅（2026-09-08 实测；warning 为 starlette testclient 的 anyio 既有弃用提示，与本任务无关）
