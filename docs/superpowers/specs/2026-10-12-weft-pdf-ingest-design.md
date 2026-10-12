# 文献 PDF 上传收录设计定案——上传 → 文本转换 → 条目提案 → 落位（2026-10-12）

## 背景与目标

文献卡（note 卡）的人工成本集中在两处：书目字段（entry）要照着 PDF 手抄，源文件（`NoteCard.pdf` 字段，schema 已有）要手工放文件、手工填路径。现有 WebUI 已有"AI 提案文献"表单（`/p/{pid}/notes/propose`，单次 LLM 调用线索 → entry 草案卡），但线索只能手工粘贴；项目里没有任何 PDF 摄取能力，`weft parse` 又只认 `articles/` 下的 md/txt。

目标：文献提案表单支持直接上传 PDF——服务器端确定性转换为文本，以其为线索拟 entry 草案卡，PDF 归档 `pdfs/<key>.pdf` 并自动填卡，转换全文落 `articles/<key>.md` 供后续 `weft parse --key` 产出 summary。**note 卡产物不变**：仍是简要概括 + entry + 次级引用 claim（parse 文献模式现有形态），不把全文倒进卡。

## 范围

- **做**：`bib_propose.html` 表单增 PDF 文件输入；文本转换模块 `src/weft/pdftext.py`（pymupdf4llm 懒加载，web extra 增依赖）；propose 路由改造（staging → 转换 → 提案 → 落位）；校验新提醒 `W-NOTE-PDF-MISSING`；诊断码 E-PDF-SHAPE / E-PDF-CONVERT；AGENTS.md 红线 5 码表增补；demo 项目补 `pdfs/smith2020.pdf` 并修正该卡 pdf 路径为根相对。
- **不做**（YAGNI）：扫描版 PDF / OCR（无文本层 → E-PDF-CONVERT 指路）；WebUI parse 触发器（runs 机制可复用，独立任务；summary 富化仍走 CLI `weft parse --key`）；`E-ARTICLE-KEY` 闸门放开（parse 设计定案 D4"不自动拟条目"维持，bib 先行、parse 后行）；PDF 在线预览/下载；批量上传与大小限额；note 卡 schema 改动（`pdf` 字段已存在，红线 2 不触）；pyzotero 同步（扩展场景 3 不变）。

## 方案取舍

- **A（选定）**：挂在现有文献提案表单上。提案流程（线索 → entry 草案 → 人批准 → managed bib sync）已打通，PDF 只是给这条流水线换一个更省力的线索来源 + 顺路完成归档与转换产物落位；不新增页面、不新增管线。
- B（否）：独立"PDF 收件箱"页面 + 全自动链（上传即 parse）。把 entry 提案与 summary 生产的两道人审闸门并成一步，越过 parse 设计的三档判定与 B2 人审兜底；且 WebUI parse 触发器要引 runs 机制，范围失控。
- C（否）：转换器并入 `weft parse`（`--pdf` 参数）。改 parse 命令面 = parse 设计定案修订；且 parse 要求 key 先在 bib，鸡生蛋问题依旧，还得另想 staging。

## 流程与路由规格

表单 `bib_propose.html`：在线索 textarea 之外增加文件输入（`<input type="file" accept=".pdf">`），两者皆可空但**至少其一**（皆空 → 表单错误字符串回显，不进码表）；附提示文案"上传 PDF 将自动提取线索、归档原件到 pdfs/ 并生成 articles/<key>.md"。

`POST /p/{pid}/notes/propose`（multipart，`python-multipart` 已是 web 依赖）按序执行，任一步失败即 rerender 表单回显 `{code} {message}` banner（卡片表单先例）：

1. **E-PDF-SHAPE**：有上传时校验后缀 `.pdf`（大小写不敏感）且内容非空 → 不过则拒绝，未写任何文件。
2. **staging**：原件写 `articles/<原始文件名>.pdf`（覆盖语义，见 U3）。
3. **转换**：`pdftext.extract_text(staging 路径)` → 全文文本（内存中）；`PdfTextError`（E-PDF-CONVERT）→ banner，**PDF 留在 staging**（可换文件重试或手删）。
4. **提案**：线索 = 转换文本前 `CLUES_CHARS`（6000）字符，表单手填线索若有则拼接在后（"补充线索：…"）；`propose_note(project, clues, client, source_pdf=<原始文件名>)` → （key, fields）；`fields["pdf"] = "pdfs/<key>.pdf"`，comment 记来源文件名。BibProposeError → banner，PDF 仍留 staging。
5. **落卡**：`write_proposed_cards(project, [("note", fields)])` → `metadata/notes/<key>.md`（draft，既有路径）。
6. **落位**：staging PDF 移至 `pdfs/<key>.pdf`（覆盖，U3/U2）；转换全文写 `articles/<key>.md`（UTF-8、LF 归一）。此步失败**不回滚卡**：303 重定向带 `?pdfwarn=1`（复用 `?bib=` 查询参数先例），详情页 banner 提示，`W-NOTE-PDF-MISSING` 长期兜底指路。
7. 成功 303 → `/p/{pid}/cards/note/<key>`（既有跳转）。

后续人审路径不变：批准草案卡（entry 人审，B2 兜底）→ managed bib 自动同步；`weft parse --key <key>` 读 `articles/<key>.md` → summary/次级引用（note 三档判定，parse 现行为，本设计不改其语义）。

## 引擎规格（src/weft/pdftext.py）

不 import web/fastapi；`pymupdf4llm` 在函数体内懒 import（CLI-only 安装不受影响，红线 1 不涉——不碰 llm/module_harness）；异常类型 `PdfTextError(code, message)`：

- `validate_upload_name(filename: str) -> None`：后缀非 `.pdf`（大小写不敏感）或文件名为空 → `E-PDF-SHAPE`。
- `extract_text(pdf_path: Path) -> str`：懒 import pymupdf4llm 调 `to_markdown(str(pdf_path))`；import/IO/转换异常 → `E-PDF-CONVERT`；产物 strip 后长度 < `MIN_TEXT_CHARS`（200，模块常量，覆盖扫描版与纯图页）→ 同码，msg 区分"无有效文本层（扫描版？）"。
- `CLUES_CHARS = 6000`：进提案线索的截取上限（propose 是单次轻量调用；60k 上限是 parse 的事，两处互不相干）。

`bib_propose.propose_note` 签名微调（U6）：增可选 `source_pdf: str | None = None`，仅用于 comment 尾部记"来源 PDF：<文件名>"；`pdf` 字段值由路由侧在拿到 key 后回填（`fields["pdf"] = f"pdfs/{key}.pdf"`），引擎函数不预填。无 PDF 调用时行为与现状逐字节一致（回归保障）。

## 校验与诊断码

`validation/rules.py` note 检查处增 `W-NOTE-PDF-MISSING`（进 `validate_project`，提醒级不阻断）：note 卡 `pdf` 字段非空且 `(项目根 / 字段值)` 不存在时提醒；空字段不检查；`../` 与绝对路径形态照常按 Path 语义解析后判存在（不另设码）。

| 码 | 级别 | 含义 | path |
|---|---|---|---|
| `E-PDF-SHAPE` | 错误（阻断） | 上传非 .pdf / 空文件（staging 之前拒绝） | `articles` |
| `E-PDF-CONVERT` | 错误（阻断） | PDF 转换失败 / 无有效文本层（扫描版）/ 文本过短（<200 字符） | `articles/<staging 文件名>` |
| `W-NOTE-PDF-MISSING` | 提醒（不阻断） | note 卡 pdf 字段指向的文件不存在（项目根相对解析） | 卡相对路径，field=`pdf` |

进码总表：本设计文档 + AGENTS.md 红线 5 增补。E-PDF-* 只在 WebUI banner 出现（引擎层），不进 `validate_project`；W-NOTE-PDF-MISSING 是唯一进校验器的新码。

## 与现有层的关系

- **不碰**：models（红线 2，`NoteCard.pdf` 字段原样使用）、store/loader、assemble、bibgen 渲染器、parse 管线语义（`E-ARTICLE-KEY`、三档判定、`W-ARTICLE-LONG` 均维持）。
- **红线 4**：PDF 上传是人的行为（同 WebUI 表单先例），md 转换产物与 `pdfs/` 归档是用户发起的确定性工具写入（同 bib 渲染器/注册表先例）——均非 AI 直接落盘，不新增白名单条款；`articles/` 本就是用户收件箱。
- **收件箱互不干扰**：parse 无参模式只扫 `articles/*.md|*.txt`（cli.py），staging 的 `.pdf` 不会被抓取。已知简化：提案成功但未批准时 `articles/<key>.md` 会留在收件箱，可能被后续无参 parse（拆解模式）选中——单人场景可接受，删卡不级联清理（U8）。
- **依赖**：pyproject `web` extra 增 `pymupdf4llm>=0.0.17`（纯本地确定性转换、无 torch 级重依赖；`python-multipart` 已在）。
- **demo**：`examples/paper-demo/metadata/notes/smith2020.md` 的 `pdf: "../pdfs/smith2020.pdf"` 修正为根相对 `pdfs/smith2020.pdf`，并用 pymupdf 生成一次单页占位 PDF（含该卡题名文本）入库，保证修正后 demo 校验不新增提醒。

## 测试策略（TDD，先红后绿）

新增 `tests/test_pdftext.py`：`importorskip("pymupdf4llm")`；测试内用 pymupdf 生成单页 PDF（写入已知题名文本）→ `extract_text` 断言含该文本；空文本页 → E-PDF-CONVERT；`validate_upload_name` 样本集（`.PDF` 大写通过、`.md`/空名拒绝）。

扩展 `tests/test_web_bib_propose.py`：路由测试 mock `pdftext.extract_text`（不依赖真实库）——上传成功链路（卡落盘含 `pdf` 字段、`pdfs/<key>.pdf` 存在、`articles/<key>.md` 存在且 LF、staging 已移走、comment 含来源文件名）；仅线索无文件回归不变；皆空表单错误；非 .pdf → E-PDF-SHAPE 且零写入；转换失败 → banner + PDF 留 staging + 无卡；落位失败（monkeypatch 移动操作抛错）→ 303 带 `?pdfwarn=1` 且卡已建。

`W-NOTE-PDF-MISSING`：并入现有 validation note 测试（缺失提醒 / 文件存在不提醒 / 空字段不提醒 / `../` 形态照常解析）。

demo 修正后跑 `weft validate` 断言无新增提醒。计划文档登记精确测试计数（当前基线 744 passed，afae618 口径）。

## 决策表

| # | 决策 | 理由 |
|---|---|---|
| U1 | 转换库 pymupdf4llm，懒 import，进 web extra | 纯本地、确定性、无重依赖；CLI-only 安装不受影响；MinerU 级管线（torch）超出单人工具需要 |
| U2 | PDF 归档 `pdfs/<key>.pdf`（项目根相对），覆盖写；卡 `pdf` 字段同值 | `NoteCard.pdf` schema 字段已预留；卡是真源，同名 pdf 视为同主孤儿覆盖无害 |
| U3 | staging 用 `articles/` 收原件；提案成功才落 `pdfs/` 与转换 md | 复用既有收件箱语义，失败重试零新状态；parse 只扫 md/txt，staging 不干扰 |
| U4 | `E-ARTICLE-KEY` 闸门不动；WebUI parse 触发器不做 | parse 设计定案 D4（不自动拟条目）与 B2 人审兜底维持；两道人审闸门（entry / summary）不合并 |
| U5 | 扫描版 PDF 不支持，E-PDF-CONVERT 指路 | OCR 是独立重活，YAGNI；报错信息给出"扫描版？"提示 |
| U6 | `propose_note` 增可选 `source_pdf`，fields 增 `pdf` 键 | 签名向后兼容；无 PDF 调用路径行为不变 |
| U7 | `W-NOTE-PDF-MISSING` 进校验器，项目根相对解析 | 对齐 `W-FIGURE-FILE-MISSING` 先例；根相对与 `paper_file` 等路径字段惯例一致 |
| U8 | 转换 md 写 `articles/<key>.md`；未批准提案的残留不级联清理 | 不落 md 则 CLI parse 无从消费；单人场景残留可手工删 |
| U9 | 线索 = 转换文本前 6000 字符 + 手填线索拼接在后 | 首页区域足够提出题名/作者/年份；手填线索保留兜底与纠偏通道 |
| U10 | 落位顺序：卡先落，PDF/md 后移；落位失败不回滚卡，`?pdfwarn=1` 提示 | 卡是真源；PDF/md 缺失有 W-NOTE-PDF-MISSING 长期兜底 |
| U11 | 非 .pdf / 空上传 → E-PDF-SHAPE，staging 之前拒绝 | 廉价检查前移，失败零副作用 |
| U12 | demo 补占位 PDF + 修正 smith2020 卡路径为根相对 | 修正后 demo 校验不得新增提醒；占位 PDF 兼作转换器测试素材 |
