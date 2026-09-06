# weft WebUI 设计（2026-09-06）

状态：设计定案（brainstorm 已获用户逐节确认）。实施计划另立：`docs/superpowers/plans/2026-09-06-weft-webui.md`。

## 0. 背景与定位

为学校 LLM 开发比赛制作**可部署到服务器的 Web 应用**，展示 weft「AI 学术写作引擎」完整工作流。非本地优先工具：部署后在浏览器中操作，界面为中文。

功能层级（用户确认）：

1. **浏览**：元数据卡片、叙事流、诊断、元数据图谱、drafts/generated 产物；
2. **审阅**：卡片与叙事节点的 status / comment（人只审卡片与叙事流——weft 核心工作流的 Web 化）；
3. **编辑**：六类卡片的创建与编辑、叙事节点（含 uses 成对编辑）编辑；
4. **生成**：触发 draft（按 part）与 inspire（灵感式写作），SSE 实时进度流。

定位原则：web 层是 weft 公共 API 之上的**薄壳**——不复制业务逻辑、不绕过校验、不新增 AI 产物落盘白名单。

## 1. 总体架构

- 新增 `src/weft/web/`（FastAPI 应用），作为包的可选扩展：依赖组 `[web]`（fastapi、uvicorn、jinja2），不安装不影响现有 CLI 与测试。
- 新增 CLI 子命令：`weft serve <projects_root> --host 0.0.0.0 --port 8000`。
- **集成方式：进程内调用**（对比过 subprocess 调 CLI：隔离性好但进度流与结构化结果都要解析 stdout/文件，复杂度不划算，否决）。读操作 `load_project()` + `validate_project()` 直接用 pydantic 模型渲染；生成调用 engine 逐节点 `run_draft`。
- 分层合规：web 层只 import `weft.store / validation / graphgen / engine` 公共 API，**不** import `module_harness` / `llm`（红线 1 不受影响）；engine 落盘白名单（`write_draft`、inspire 落盘点）原样保留（红线 4）；诊断码不新增（红线 5）；生成闸门与 CLI 完全一致（红线 6）。
- **前端**：Jinja2 + htmx 局部刷新；htmx、cytoscape.js vendor 进 `src/weft/web/static/`（现场无外网可运行）；SSE 用浏览器原生 EventSource + 少量原生 JS，无构建链。
- 页面按模块拆分路由文件，模板与静态资源随包分发；每个视图单元职责单一（项目发现 / 卡片 / 叙事 / 生成运行 / 图谱 / 诊断），便于独立测试。

### 1.1 生成运行器提炼

`cli.draft` 中"闸门校验 → 逐 approved 节点 run_draft → 渲染写盘"的编排逻辑提炼为 engine 层可复用 runner（新增进度回调参数），CLI 与 web 共用同一条路径——避免双实现漂移。对 engine 是最小侵入，不改变任何现有语义（含前文传递 prior_paragraphs/prev_tail/next_head）。

## 2. 项目发现

- `weft serve` 启动参数指定**项目根目录**；扫描其一级子目录，**含 `metadata/` 目录者识别为 weft 论文项目**；项目 id = 目录名。
- 首页列出全部项目：卡片数、审阅进度、validate 诊断摘要；演示时可放多个示例项目切换。
- 损坏项目不阻断列表：显示为"不可用"并给 E-PARSE 摘要（加载永不中断原则，红线 3）。

## 3. 页面与路由

| 路由 | 方法 | 内容 |
|---|---|---|
| `/` | GET | 项目列表（扫描结果 + 统计摘要） |
| `/p/{pid}/` | GET | 总览仪表盘：卡片/审阅/诊断统计 + 全局待审阅队列 |
| `/p/{pid}/cards` | GET | 六类卡片总览（status 过滤） |
| `/p/{pid}/cards/{kind}` | GET | 某类卡列表 |
| `/p/{pid}/cards/{kind}/{card_id}` | GET | 卡片详情（只读视图） |
| `/p/{pid}/cards/{kind}/{card_id}/edit` | GET/POST | 编辑表单 |
| `/p/{pid}/cards/{kind}/new` | GET/POST | 新建（先选卡种，模板预填） |
| `/p/{pid}/cards/{kind}/{card_id}/status` | POST | 审阅（status + comment） |
| `/p/{pid}/parts` | GET | 叙事工作台（每 part 一个页签） |
| `/p/{pid}/parts/{part_id}` | GET | part 页签内容（htmx 局部加载） |
| `/p/{pid}/parts/{part_id}/nodes/{node_id}` | GET/POST | 节点编辑面板（含 uses） |
| `/p/{pid}/parts/{part_id}/nodes/{node_id}/status` | POST | 节点审阅 |
| `/p/{pid}/parts/{part_id}/generate` | POST | 触发该 part 生成（返回 run_id） |
| `/p/{pid}/runs/{run_id}/events` | GET | SSE 实时进度流 |
| `/p/{pid}/inspire` | GET/POST | 灵感页签：输入文本段 → 触发 → 提案列表 |
| `/p/{pid}/inspire/proposals/{proposal_id}/apply` | POST | 应用单张提案（走 engine.inspire 现有 apply 逻辑） |
| `/p/{pid}/graph` | GET | 元数据图谱（cytoscape 渲染 `generated/graph.json`） |
| `/p/{pid}/diagnostics` | GET | validate 全量诊断表（E-*/W-*，可按 code/path 过滤） |
| `/p/{pid}/files/{path}` | GET | `drafts/` 与 `generated/` 产物只读预览 |

注：`/cards/{kind}/new` 必须先于 `/cards/{kind}/{card_id}` 注册（避免 "new" 被吞进 card_id）。执行期路由偏差（D21）：`/inspire` 的触发拆分为 `/inspire/run`（表单语义更清晰）；新增 `/graph/regenerate`（图谱一键生成按钮，设计 §6）。

## 4. 卡片浏览与编辑

### 4.1 控件映射规则

| 字段形态 | 控件 |
|---|---|
| 短文本（id、key） | 文本框（id 只读） |
| 长文本（statement、description、summary、logic） | 文本域 |
| 软词表（purpose、role） | 下拉（选项取自 validation 层词表）+ datalist 允许自定义输入（模型层放行超集） |
| 实体引用列表（fact.data、claim.supports） | 多选下拉，选项 = 项目已加载对应卡 |
| 文献引用（claim.cites、note.key） | 多选/单选下拉，选项 = `project.bib_keys` |
| 图号引用（data.refs） | 多选下拉，选项 = `figures.yaml` 已有 ref |
| 节点 uses | 成对编辑（见 §5） |
| status | draft/approved/rejected 三态 |

引用字段全部下拉选择（选项来自项目加载结果），从源头杜绝悬空引用；校验器仍作兜底。

### 4.2 编辑与写回

- 新增 `store/writer.py`：`save_card` / `create_card` / `save_part`（叙事文件整体写回）。设计 §5 本就规划 store 负责"加载/查询/保存"，此为补齐而非破冻结；模型（pydantic `extra="forbid"`）不改（红线 2）。
- 提交 → 构造对应模型实例 → **失败**：回显表单、按字段高亮错误与诊断码，不落盘；**成功**：frontmatter 序列化 → 固定 LF 写回原路径（文件名 = id 不变）。claim 卡的 `claim_type` 变更由 writer 计算规范路径并迁移文件（loader 强制目录与 `claim_type` 一致）。
- 写回后对该卡单独校验并就地提示结果；全局诊断随之刷新。
- **新建**：卡种页签（data/fact/claim/note/method/param）→ 必填字段模板预填 → id 按卡种规则自动分配下一序号（两位零填充进位，跳过已用，提示"文件名 = id"）；note 卡 id = bib key（下拉选择）。
- **不提供删除**：否决用 `status: rejected` 表达；历史归 git。

## 5. 叙事工作台

- 页签对应每个 part；页签内左侧按顺序列节点（status 徽章 + ✅/❌ 快捷审阅），右侧为该 part 专属生成控制台，底部为该 part 当前草稿预览（生成后即时刷新）。
- 节点行 [▾ 编辑] 原位展开编辑面板（htmx）：`purpose`（词表下拉）、`logic`（文本域）、`uses` 成对编辑、`status` + `comment`；按节点保存，pydantic 校验不过不落盘。
- **uses 成对编辑**：每行 =「实体 id 下拉（按 fact/claim/data 分组）+ role 下拉（软词表 + datalist）+ 移除」，[+ 添加 use] 增行；悬空引用就地红字提示。
- part 级 `workflow` 显式路由覆盖在页签头部暴露为下拉（词表校验同 CLI，E-WORKFLOW-UNKNOWN 语义不变）。
- 审阅与生成在同一页签内完成：审阅完哪个 part 就生成哪个 part（用户确认的动线）。

## 6. 生成流程（draft / inspire）

- **闸门**：与 CLI 一致——`load_project` + `validate_project`，有 error 拒绝生成并展示诊断（红线 6）。
- **执行**：后台线程跑 §1.1 的共享 runner，逐节点 `run_draft`；每项目一把锁，运行中重复触发返回 409 并页面提示。
- **进度流**：事件 `run_started / node_started / node_finished / node_failed / draft_written / run_finished / run_failed`（载荷含节点 id、诊断、reminders）推入内存队列 → SSE 推送；粒度为节点级（SpecModule tick 级进度不暴露，Out of scope）。
- **一致性**：运行基于**开始时加载的项目快照**；运行中的卡片编辑不进入本次 run（页面提示"生成中"）。
- **LLM 客户端**：真实模式 `make_client`（.env / 环境变量，部署时配置）；页面提供 **mock 模式开关**（`ScriptedLLMClient`，免 key 完整演示，比赛保底）。
- **inspire**：独立页签；输入文本段 → 后台运行（persist 断点续跑语义不变，快照仍落 `generated/inspirations/.runs/`，红线 4）→ SSE → 提案卡列表 → 逐张「应用」（走 engine.inspire 现有 apply/replace 逻辑）或丢弃。
- **graph 页**：`generated/graph.json` 缺失时提供「生成图谱」按钮（graphgen 秒级非 LLM，直接进程内调用）。

## 7. 诊断

- diagnostics 页呈现 `validate_project` 全量结果：表格列 = 级别 / 码 / path / field / message，可按码与级别过滤。
- 总览仪表盘显示 E/W 计数摘要与全局待审阅队列。
- 不新增诊断码；如实现中确需新增，按红线 5 进总表。

## 8. 安全与并发

- 单人演示场景：**不做认证**；部署文档注明仅限内网/演示环境，勿暴露公网。
- 生成任务每项目串行（简单锁）；多项目互不影响。
- files 预览路由限制在 `drafts/`、`generated/` 白名单目录内，拒绝路径穿越。

## 9. 测试

- FastAPI `TestClient` + 现有 `ScriptedLLMClient`（tests 豁免层造假响应，不碰真实 llm）。
- 覆盖清单：项目扫描识别（含损坏项目不阻断）、卡列表/详情、编辑写回（校验失败回显、CRLF 归一为 LF、文件名=id）、新建 id 自动分配、审阅 status/comment、uses 成对编辑与悬空引用提示、生成闸门拒绝、SSE 事件序列（mock 客户端）、409 并发锁、files 路径穿越拒绝。
- 现有 260 个测试不回归；新增测试的精确计数登记进实施计划文档（TDD 先红后绿）。

## 10. 部署

```bash
pip install "weft[web]"
weft serve /srv/weft-projects --host 0.0.0.0 --port 8000
```

- LLM 配置：环境变量 / `.env`（`make_client` 现有机制）；无 key 时用 mock 开关演示。
- 静态资源（htmx、cytoscape）vendor 进包，现场无外网可运行。
- 里程碑定位：并入 M4 打磨阶段（`docs/roadmap.md` 在实施计划中同步更新）。

## 11. 非目标（YAGNI）

认证与多用户、实时协作、移动端适配、卡片删除、YAML 源码编辑模式、生成进程隔离、WebSocket（用 SSE）、多语言界面、SpecModule tick 级进度暴露、`figures.yaml` 与 `_quarto.yml` 的 Web 编辑（保持人工直接维护）。
