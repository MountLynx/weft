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
- WebUI（比赛展示）：`weft serve` 服务器端 Web 应用（FastAPI+htmx，全流程含卡片编辑与生成）✅；项目列表页内嵌表单新建项目（复用 `init_project` 骨架、名称黑名单守卫、中文 pid、冲突零写入，2026-09-08，见 `docs/superpowers/plans/2026-09-08-weft-webui-new-project.md`）
- 断点续跑/回滚接入 CLI（复用 SpecModule 原生能力）。
- 溯源注释完善与用户文档。
- bib 自动生成（bibgen）✅（2026-09-29）：`weft bib sync`；managed 模式以已批准文献卡为真源（note 卡 entry 书目字段，spec 2026-09-29-weft-bibgen），WebUI 批准/编辑即同步，AI 提案与 parse 文献模式两条草案入口。
- 项目注册表（projects registry）✅（2026-09-29）：全局注册表（`$WEFT_HOME/projects.json`）让项目散落磁盘任意位置；`weft projects add/new/list/remove/root` 命令组 + `weft serve` 双模式（无参 = 注册表模式，一个主程序多项目共存且相互隔离；带参 = 扫描模式现状不变）；WebUI 新建表单登记闭环、失联灰显、损坏横幅（E-REG-* fail-closed）；设计定案 `docs/superpowers/specs/2026-09-29-weft-projects-registry-design.md`（决策 R1–R12，测试 539 passed）。

## 扩展场景（M4 后，架构已预留）

按设计文档 §10，均不动已冻结的 v1 数据结构：

1. **文章解析** ✅（2026-09-28 落地，设计定案 `docs/superpowers/specs/2026-09-28-weft-parse-design.md`）：`weft parse` SpecModule 五节点管线（逻辑核查 / 拆解+摘要 / 对照审查 / 匹配 / 覆盖），统一管线按 `--key` 分文献模式（note 卡 + 次级引用 claim）与拆解模式（fact/claim，data 闭包）；同 key note 三档判定（new 直落 / supplement 提案 / unchanged 零写入）；run 机械件提炼 `engine/pipeline.py`、受控写入器提炼 `engine/card_writer.py`（inspire 同步复用）。
2. **灵感式写作** ✅（2026-09-04 提前落地，设计定案 `docs/superpowers/specs/2026-09-04-weft-inspire-design.md`）：`weft inspire` SpecModule 四节点管线（逻辑核查 / 卡片拆解 / 现有卡审查·矛盾·补充 / 匹配）+ 内存摘要索引（`weft/digest.py`，穷举比对，非向量 RAG）+ 落盘闭包 fail-closed + 处理报告；补充卡走完整新卡提案，`weft replace` 替换旧卡并归档；`weft missing-cites` 直查缺文献的 cited 卡。
3. **pyzotero 同步**：从 Zotero collection 自动生成/更新 note 卡与 PDF。
4. **数据处理/绘图管理集成**：外部系统以 `data.refs` 编号 + `figures/` 命名契约为界。
5. **Tauri 壳（远期可选）**：PyInstaller 冻结引擎作 sidecar，薄审阅 UI；schema 冻结后才启动。
