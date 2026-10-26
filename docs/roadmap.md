# weft roadmap

- 日期：2026-09-02
- 依据：设计文档 v1（`docs/superpowers/specs/2026-09-01-weft-design.md`）§9 里程碑、§10 扩展场景
- 状态标记：✅ 完成 ｜ 🔨 进行中 ｜ ⬜ 未开始

## 当前状态

**M3 渲染层已实现并合入 main（2026-09-02）**：`weft assemble` 在 part/chapter 级 qmd 之外产出项目根 `paper.qmd`（chapter 原样并入 + References refs div 定位 + Figures/Tables 字面编号，文件名经 weft.yaml `paper_file` 配置，默认 paper.qmd）；投稿资源约定 `assets/`（references.bib / style.csl / template.docx，样例项目已迁移；style.csl 为 Zotero elsevier-with-titles，CC-BY-SA 3.0，出处见文件内 rights 元素）；`weft render`（quarto 子进程封装，docx 默认目标，`--to` 透传）。卡片→叙事→生成→组装→Quarto 全闭环打通。M4 打磨进行中：`weft init` 项目模板已交付（2026-09-04）；扩展场景 2"灵感式写作"已提前落地（`weft inspire` / `replace` / `missing-cites`，见下文扩展场景）。

## M1 数据层 ✅（2026-09-02 合入 main）

纯数据层，不碰 LLM：

- `models/`：四类实体卡（data / fact / claim / note）与叙事节/节点 pydantic 模型（extra=forbid）。
- `store/`：卡片与叙事文件加载，全局 id 唯一、first-wins、目录与 claim_type 一致性校验；加载永不中断（解析失败转 E-PARSE 诊断继续）。
- `validation/`：§4 错误规则（悬空引用 / bib / figures.yaml 等）与提醒规则（缺引文 / 孤儿 / 软词表 / note 缺卡）。
- `graphgen/`：反向索引 + narrative 正向可达集，落盘 `generated/graph.json`、`used-metadata.json`（含 rejected-but-reachable）、`orphans.md`；固定 LF 换行保证黄金比对。
- CLI：`weft validate` / `weft graph` / `weft review`，UTF-8 输出与稳定退出码语义。

## M2 生成层 ✅（2026-09-02）

- `engine/` SpecModule 适配器：全项目唯一 import specmodule 的模块，隔离 API 漂移。
  - `spec_build.py`：叙事节 → Spec/Tasklist（每个 narrative node 一个 task，结构化输出：段落文本 + 引用实体 id + `[@citekey]` 列表）。
  - `run.py`：运行/恢复，产物归一化写入 `drafts/<part-id>.md（时为 section id）`，HTML 注释溯源（node id + 实体 id + run id）；路径白名单强制 AI 只写 `drafts/` 与 `generated/`。
- 生成后校验（§4 生成时三规则）：`[@key]` 必须在 bib（硬）；不属于本段 claim 的 cites（软提醒）；草稿标注实体必须属于节点 uses。
- 验收路径：单章节（03-results + 04-discussion）端到端生成；先 `MockLLMClient`（无 key 可测）后真实 LLM。
- CLI：`weft draft <section>（v1.1 起按 part 寻址）`，`--mock` 免 key 管线冒烟、`--no-align` 跳过对齐；生成前强校验闸门（有错误即拒绝）。

## M3 渲染层 ✅（2026-09-02 合入 main；设计定案：`docs/superpowers/specs/2026-09-02-weft-m3-render-design.md`）

- `assemble/` ✅（v1.1 §4.4 提前交付）：part qmd 拼装 + chapter 目录序合并 + heading 层级映射；strict/lenient 经 weft.yaml `assemble_mode`（默认 strict）。
- paper.qmd 拼接 ✅：chapter 序拼接成项目根 `paper.qmd` + `# References`（refs div 定位，citeproc 只渲染被引条目）+ `# Figures`/`# Tables`（figures.yaml 键序字面编号；图表链路不走 crossref——docx 投稿所见即所得）。
- 投稿资源约定 ✅：`assets/`（references.bib / style.csl / template.docx），`_quarto.yml` 固定路径引用；样例项目已迁移。
- `render.py` ✅：quarto 子进程封装 + CLI `weft render`（docx 默认目标；不重复校验闸门）；打通 卡片→叙事→生成→组装→Quarto 全闭环。

## M4 打磨 🔨

- `weft init` 项目模板 ✅（2026-09-04）：最小合法骨架（init 后 `weft validate` 0 错 0 提醒；六类卡片目录、figures.yaml/weft.yaml 全注释模板、起步 part）；非空目录拒绝（`E-INIT-COLLISION`，零写入 fail-closed）。骨架文件内注释即格式参考，计划与设计决策见 `docs/superpowers/plans/2026-09-04-weft-init.md`。
- `weft new` 模板化创建 ✅（2026-10-10）：`weft new part <chapter> <section> [--id]`（part id 全局 sec-NN 自动编号、文件名章节内 part-NN 自动编号）与 `weft new card <kind> <id>`（六类卡片，落盘目录对齐 writer 规范）；碰撞 fail-closed 零写入（`E-NEW-COLLISION`）、路径成分校验（`E-NEW-NAME`）；桩卡"最小合法+注释示例"，fact/param/note 的待填错误由校验器指路。设计见 `docs/superpowers/specs/2026-10-10-weft-new-template-design.md`。
- WebUI（比赛展示）：`weft serve` 服务器端 Web 应用（全流程含卡片编辑与生成）✅；项目列表页内嵌表单新建项目（复用 `init_project` 骨架、名称黑名单守卫、中文 pid、冲突零写入，2026-09-08，见 `docs/superpowers/plans/2026-09-08-weft-webui-new-project.md`）
- WebUI React 化 ✅（2026-10-13）：整体升级为「FastAPI `/api/*` JSON API + React SPA 三栏工作台」（源码 `webui/`：Vite+TS+react-router，无组件库/无状态库；构建产物 `static/app/` 提交入库，运行时零 Node）。布局复刻 itemmanage 范式：项目卡片网格 ↔ Topbar/侧栏/中栏/右栏 inspector/状态栏，行列表 + 选中反色 + Toast/模态；能力 1:1 保留（审卡/表单/叙事生成 SSE/图谱 cytoscape/figures/灵感管线/提案对比/诊断一键修复/bib 切换/文件预览），服务端语义与诊断码透传不变（153 条 web 用例等语义改写，全量 812 passed）。设计见 `docs/superpowers/specs/2026-10-13-weft-webui-react-design.md`。
- 语义可见性 ✅（2026-10-12）：`weft review` 摘要列、graph.json `summary`、orphans 摘要、`weft show <id>` 速览、WebUI 引用控件/uses/实体速查带「id · 摘要」、WebUI 新建卡 id 解锁语义命名。设计见 `docs/superpowers/specs/2026-10-12-weft-semantic-visibility-design.md`。
- 改名对齐 `weft rename` ✅（2026-10-12）：一条命令完成卡片改名——冲突审查 fail-closed（复用 E-NEW-NAME/E-NEW-COLLISION）+ 全部引用位点同步（文件/frontmatter/data/supports/cites/param.method/derived_from/节点 uses）+ managed bib 自动重渲；`--dry-run` 计划打印；WebUI 详情页表单共用引擎。设计见 `docs/superpowers/specs/2026-10-12-weft-rename-design.md`。
- WebUI 图表管理 ✅（2026-10-12）：figures.yaml 图表页（键序列表 + 引用卡链接 + 文件缺失/未被引用标记）与图注条目新增/编辑/删除（fig-/tbl- 自动编号、删除被引用键 `E-FIG-IN-USE` 阻断、解析失败 `E-FIG-LOAD` 转只读、degraded 项目删除 fail-closed）；`figures_edit` 纯函数引擎（确定性 LF 重写、YAML 重定型防护）。设计见 `docs/superpowers/specs/2026-10-12-weft-webui-figures-design.md`。
- 文献 PDF 上传收录 ✅（2026-10-12）：文献提案表单支持 PDF 上传——pymupdf4llm 确定性转文本作线索拟 entry 草案卡，原件归档 `pdfs/<key>.pdf` 自动填卡 `pdf` 字段，转换全文落 `articles/<key>.md` 供 `weft parse --key` 富化 summary；`W-NOTE-PDF-MISSING` 校验提醒。设计见 `docs/superpowers/specs/2026-10-12-weft-pdf-ingest-design.md`。
- bib 模式切换与一键修复 ✅（2026-10-13）：unmanaged↔managed 双向切换（预检报告 + 逐行改 weft.yaml 保注释 + `weft bib mode`/确认页）与 unmanaged 项目 `E-NOTE-NOT-IN-BIB` 一键修复（note entry 确定性追加进 bib，幂等；`weft bib fix [--all]` + 诊断页/note 详情页按钮）；`E-BIB-MODE` 操作码。设计见 `docs/superpowers/specs/2026-10-13-weft-bib-mode-fix-design.md`。
- WebUI 替换提案对比页 ✅（2026-10-13）：灵感页每张替换提案可进对比查看——逐字段对照（差异单元格高亮）+ 原文逐行统一 diff（+/− 着色），确认后页内应用；目标卡缺失/提案解析失败/id 不一致 fail-closed 呈现警示并隐藏应用按钮。设计见 `docs/superpowers/specs/2026-10-13-weft-webui-proposal-diff-design.md`。
- 断点续跑/回滚接入 CLI（复用 SpecModule 原生能力）。
- 溯源注释完善与用户文档。
- bib 自动生成（bibgen）✅（2026-09-29）：`weft bib sync`；managed 模式以已批准文献卡为真源（note 卡 entry 书目字段，spec 2026-09-29-weft-bibgen），WebUI 批准/编辑即同步，AI 提案与 parse 文献模式两条草案入口。
- 项目注册表（projects registry）✅（2026-09-29）：全局注册表（`$WEFT_HOME/projects.json`）让项目散落磁盘任意位置；`weft projects add/new/list/remove/root` 命令组 + `weft serve` 双模式（无参 = 注册表模式，一个主程序多项目共存且相互隔离；带参 = 扫描模式现状不变）；WebUI 新建表单登记闭环、失联灰显、损坏横幅（E-REG-* fail-closed）；设计定案 `docs/superpowers/specs/2026-09-29-weft-projects-registry-design.md`（决策 R1–R12，测试 547 passed）。
- 卡片章节标签与本章素材生成 ✅（2026-10-26）：`_Card.chapters` 章节标签（schema v1 加性扩展，无迁移）；生成时同章已批 claim/note 自动并入「本章素材」——claim 进占位符合法集（uses ∪ 素材），introduction 综述章的整章文献池从节点级人工枚举放宽到章节级打标；WebUI 卡片页章节筛选 chips、表单 tags 控件（datalist）、叙事面板「本章标签卡」区块、`weft new card --chapter`；W-CHAPTER-VOCAB 软词表。设计定案 `docs/superpowers/specs/2026-10-26-weft-card-chapters-design.md`（决策 H1–H10，pytest 832 / vitest 20）。

## 扩展场景（M4 后，架构已预留）

按设计文档 §10，均不动已冻结的 v1 数据结构：

1. **文章解析** ✅（2026-09-28 落地，设计定案 `docs/superpowers/specs/2026-09-28-weft-parse-design.md`）：`weft parse` SpecModule 五节点管线（逻辑核查 / 拆解+摘要 / 对照审查 / 匹配 / 覆盖），统一管线按 `--key` 分文献模式（note 卡 + 次级引用 claim）与拆解模式（fact/claim，data 闭包）；同 key note 三档判定（new 直落 / supplement 提案 / unchanged 零写入）；run 机械件提炼 `engine/pipeline.py`、受控写入器提炼 `engine/card_writer.py`（inspire 同步复用）。
2. **灵感式写作** ✅（2026-09-04 提前落地，设计定案 `docs/superpowers/specs/2026-09-04-weft-inspire-design.md`）：`weft inspire` SpecModule 四节点管线（逻辑核查 / 卡片拆解 / 现有卡审查·矛盾·补充 / 匹配）+ 内存摘要索引（`weft/digest.py`，穷举比对，非向量 RAG）+ 落盘闭包 fail-closed + 处理报告；补充卡走完整新卡提案，`weft replace` 替换旧卡并归档；`weft missing-cites` 直查缺文献的 cited 卡。
3. **pyzotero 同步**：从 Zotero collection 自动生成/更新 note 卡与 PDF。
4. **数据处理/绘图管理集成**：外部系统以 `data.refs` 编号 + `figures/` 命名契约为界。
5. **Tauri 壳（远期可选）**：PyInstaller 冻结引擎作 sidecar，薄审阅 UI；schema 冻结后才启动。
