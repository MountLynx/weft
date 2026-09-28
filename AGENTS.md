# AGENTS.md — weft 工作区指令

## 项目定位

weft：AI 学术写作引擎（Python 包，src 布局）。核心模型：元数据卡片为经线（data/fact/claim/note 原子 Markdown+YAML 卡），叙事流为纬线（`narrative/<chapter>/…/part-*.md`，part 为生产单位）；人只审卡片与叙事流（`status: draft|approved|rejected`），AI 只写 `drafts/` 与 `generated/`。单人 CLI 优先，Quarto 负责最终渲染。

**必读文档**（改敏感区前先读）：
- `docs/superpowers/specs/2026-09-01-weft-design.md` — 设计 v1；**§3 数据结构已冻结**（改动需迁移脚本 + 全量校验）、§4 校验规则、§9 里程碑
- `docs/roadmap.md` — 里程碑状态（M1 数据层 ✅、M2 生成层 ✅、M3 渲染层 ✅（2026-09-02 合入 main）、M4 打磨 🔨：`weft init` ✅）
- `docs/superpowers/plans/2026-09-02-weft-m2-engine.md` — M2 计划，其"设计决策 1-14"含大量执行期实测修订（SpecModule 0.1.4 的真实行为语义）
- `docs/superpowers/specs/2026-09-02-weft-v1.1-design.md` — 设计 v1.1 增补（method/param、目录树、workflow、assemble）；与 v1 冲突处以 v1.1 为准
- `docs/superpowers/plans/2026-09-02-weft-v1.1-implementation.md` — v1.1 实现计划，其"设计决策 1-23"为执行期定案（workflow 判定、前文传递、assemble heading 映射等语义）
- `docs/superpowers/specs/2026-09-02-weft-m3-render-design.md` — M3 渲染层设计定案（paper.qmd 拼接、References refs div、Figures/Tables 字面编号、assets 资源约定）
- `docs/superpowers/specs/2026-09-04-weft-inspire-design.md` — 灵感式写作→卡片管线设计定案（摘要索引、T1–T4 节点、落盘闭包、replace 替换归档）；其计划文档 `2026-09-04-weft-inspire.md` 含执行期决策 D1–D10
- `docs/superpowers/specs/2026-09-28-weft-parse-design.md` — 文章解析管线设计定案（统一管线双模式：文献/拆解、note 三档判定、E-ARTICLE-* 诊断码）；其计划文档 `2026-09-28-weft-parse.md` 含执行期决策 P1–P12
- `docs/superpowers/specs/2026-09-09-weft-webui-style-design.md` — WebUI 样式令牌化主题架构定案（webui.css 令牌 + themes/*.css 纯令牌覆盖、导航切换/localStorage/防闪脚本；主题文件只许含令牌声明，有守卫测试）

## 常用命令（Windows + Git Bash）

```bash
.venv/Scripts/python.exe -m pip install -e ".[dev]"     # 安装（含 pytest）
.venv/Scripts/python.exe -m pytest tests -q             # 全量测试（391 passed, 2 deselected）
.venv/Scripts/python.exe -m pytest tests/test_xxx.py -v # 聚焦测试
.venv/Scripts/weft.exe --help                           # CLI：init / validate / graph / review / draft / assemble / render / inspire / parse / replace / missing-cites / serve
WEFT_SMOKE_LLM=1 .venv/Scripts/python.exe -m pytest tests -m smoke -v   # 真实 LLM 冒烟（默认排除，双保险门）
```

- 远程仓库：GitHub `MountLynx/weft`（公开，origin 已配置）。提交到本地 main 后可推送 `git push`（main 跟踪 origin/main）；密钥/敏感文件严禁入库（.env 已 gitignore）。
- 提交信息用中文 conventional commit（`feat:`/`fix:`/`docs:`/`test:`/`chore:`）。
- 测试先红后绿（TDD）；新增任务在计划文档里登记精确测试计数。

## 架构红线（有守卫测试强制）

1. **分层**：`src/weft/engine/` 是全项目唯一允许 import `module_harness` / `llm`（PyPI 包 `specmodule[openai]>=0.2.0,<0.3`，版本锁定）的 src 层。违规会被 `tests/test_engine_layering.py` 抓住。tests/ 豁免（可 import llm.client 造假响应）。
2. **数据结构 v1 冻结**：卡片 schema（`src/weft/models/`，pydantic `extra="forbid"`）不改；schema 变更走设计文档 §3 迁移流程。
3. **加载永不中断**：store 加载对单卡解析/编码/IO 失败一律转 `E-PARSE` 诊断后继续（宁可一次看全所有问题）。
4. **路径白名单**：AI 产物唯一落盘点是 `engine/drafts.py::write_draft` 的 `drafts/<part_id>.md` 与 `engine/card_writer.py` 的 `metadata/` 草稿卡 + `inspirations/proposals/` 提案（均固定 LF，写入前归一化 CRLF）。draft 管线的 SpecModule 以零残留模式运行（`persist/status_file/keep_records/stream_log` 全 False）；inspire/parse 管线例外——开启 persist 断点续跑，运行快照只落 `generated/inspirations/.runs/` 与 `generated/articles/.runs/`（weft 受管目录），其余任何位置不得出现 `.specmodule/` 残留。
5. **诊断码是稳定标识**：`E-*`（错误，阻断）/`W-*`（提醒，不阻断），总表见 M1/M2/v1.1 计划文档及 `2026-09-04-weft-init.md`（E-INIT-COLLISION）、`2026-09-04-weft-inspire.md`（E-INSPIRE-SHAPE / E-INSPIRE-FAILED）、`2026-09-28-weft-parse.md`（E-ARTICLE-SHAPE / E-ARTICLE-FAILED / E-ARTICLE-KEY / W-ARTICLE-LONG）；新增码必须进表。生成时诊断 path=`drafts/<part>.md`、field=`<节点id>.<字段>`。
6. **生成闸门**：`weft draft` 先跑 `validate_project`，有任何 error 即拒绝生成；生成时硬规则（引文必须在 bib——正文 `[@key]` 与结构化 cites 双通道、uses 越界）在 run 内抛 `DraftRuleError` → 退出码 1 且不写 drafts。

## SpecModule 嵌入要点（实测语义，勿凭直觉改）

- 通道②：`Module(spec=..., tasklist=Tasklist(...), review_harness=None, persist=False, status_file=False, keep_records=False, stream_log=False)`。
- **flow 必须多行**：tickflow 起始标记行只允许一条边（`[p01] --> AL\nAL --> V`）。
- script 节点的 view 键来自 `TaskDefinition.inputs`，不是 flow 边——V 任务要 `inputs={tick: tick}`。
- harness 失败不流向后继（出边写 False，AND-join 的 V 不触发）——run 层事后扫 firings：`failed`→E-DRAFT-SHAPE、`aborted`→E-DRAFT-FAILED（fail-closed）。
- `reg.script(name)` 是装饰器工厂：`reg.script(name)(fn)`。
- 真实 LLM 配置（config.json + .env）按用户指示放在 `C:/Users/xingy/Desktop/开发/SpecModule/`，冒烟测试运行时复制进 tmp 项目；`.env` 已进 .gitignore，**任何密钥不得入库**。

## 工作流约定

- 功能开发用 git worktree（`.worktrees/<分支名>`，已 gitignore），完成后合回 main 并删除 worktree/分支；实施计划写在 `docs/superpowers/plans/YYYY-MM-DD-*.md`（含 TDD 任务分解与精确预期计数），执行期的设计偏离回填到计划的"设计决策"表。
- Windows 注意：诊断输出统一切 UTF-8（cli.py 的 `_ensure_utf8_stdout` 已处理）；生成文件固定 LF。
- 样例项目 `examples/paper-demo/` 是 M1 验收基准（graph 黄金文件在 `tests/golden/`）；手动冒烟产生的 `examples/paper-demo/drafts/` 用完要删。
