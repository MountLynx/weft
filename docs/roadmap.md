# weft roadmap

- 日期：2026-09-02
- 依据：设计文档 v1（`docs/superpowers/specs/2026-09-01-weft-design.md`）§9 里程碑、§10 扩展场景
- 状态标记：✅ 完成 ｜ 🔨 进行中 ｜ ⬜ 未开始

## 当前状态

**M2 生成层已完成并合入 main（2026-09-02）**：`engine/` 适配层（specmodule==0.1.4，通道②直构 tasklist，零残留嵌入）+ `weft draft <section>` 单章节端到端生成到 `drafts/`，含生成时三规则闸门、对齐检查（`--no-align` 可关）、溯源注释；免 key `ScriptedLLMClient` 管线测试全绿，真实 LLM 冒烟以 `pytest -m smoke` 显式运行。M1 数据层（97 测试）已于同日合入。下一步进入 M3 渲染层。

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
  - `run.py`：运行/恢复，产物归一化写入 `drafts/<section>.md`，HTML 注释溯源（node id + 实体 id + run id）；路径白名单强制 AI 只写 `drafts/` 与 `generated/`。
- 生成后校验（§4 生成时三规则）：`[@key]` 必须在 bib（硬）；不属于本段 claim 的 cites（软提醒）；草稿标注实体必须属于节点 uses。
- 验收路径：单章节（03-results + 04-discussion）端到端生成；先 `MockLLMClient`（无 key 可测）后真实 LLM。
- CLI：`weft draft <section>`，`--mock` 免 key 管线冒烟、`--no-align` 跳过对齐；生成前强校验闸门（有错误即拒绝）。

## M3 渲染层 ⬜

- `assemble/`：按 nodes 顺序拼装已批准草稿 → `generated/<section>.qmd`；strict/lenient 模式经 `weft.yaml` 配置（默认 strict）。
- 图表落点：fact→data→refs 首次出现处插入，图注取自 figures.yaml，crossref 用 Quarto label（`@fig-01a` / `@tbl-01`）；显示形式由 `_quarto.yml` crossref 配置决定。
- `render.py`：quarto 子进程封装 + CLI `weft render`；打通 卡片→叙事→生成→组装→Quarto 全闭环。

## M4 打磨 ⬜

- 断点续跑/回滚接入 CLI（复用 SpecModule 原生能力）。
- 溯源注释完善、`weft init` 项目模板与文档。
- 真实 LLM 冒烟测试（pytest marker 默认跳过）。

## 扩展场景（M4 后，架构已预留）

按设计文档 §10，均不动已冻结的 v1 数据结构：

1. **文章解析**：AI 从现成文章抽取 fact/claim 草稿卡 → 人工审阅；cited 缺引文 → 提醒补文献。
2. **灵感式写作**：随手记 → 解析成事实/观点草稿卡 → 自动匹配图表（data.refs）→ 标注缺文献处。
3. **pyzotero 同步**：从 Zotero collection 自动生成/更新 note 卡与 PDF。
4. **数据处理/绘图管理集成**：外部系统以 `data.refs` 编号 + `figures/` 命名契约为界。
5. **Tauri 壳（远期可选）**：PyInstaller 冻结引擎作 sidecar，薄审阅 UI；schema 冻结后才启动。
