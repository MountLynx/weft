# WebUI figures.yaml 管理设计定案——图表页查看与增改删（2026-10-12）

## 背景与目标

`metadata/figures.yaml` 是图注注册表（spec §3.6）：键 = Quarto label（`fig-01`/`tbl-01`），键序即 assemble 的字面编号；data 卡 `refs` 引用这些键（含 `键+子图后缀`）。它目前**只能手工编辑**：WebUI 唯一接触点是 data 卡表单的 refs 多选框（选项来自已加载条目），没有任何页面能查看或维护注册表本身。校验侧已有三个相关码（`E-REFS-NOT-IN-FIGURES`、`W-FIGURE-FILE-MISSING`、`W-FIGURE-UNUSED`），但看懂它们、再去手工改 yaml 的闭环是断的。

目标：WebUI 新增"图表"子导航页——列表展示全部条目及其引用/文件状态，支持新增、编辑 caption/subfigs、删除条目；编辑逻辑落 src 层纯函数引擎，WebUI 路由薄封装。

## 范围

- **做**：`/p/{pid}/figures` 页面组（列表 / 新增 / 编辑 / 删除）；引擎 `src/weft/figures_edit.py`；诊断码 E-FIG-LOAD / E-FIG-NAME / E-FIG-COLLISION / E-FIG-IN-USE / E-FIG-VALUE；子导航与 AGENTS.md 红线 5 码表增补。
- **不做**（YAGNI）：图片文件上传/替换（WebUI 无上传先例）；键重命名（会破坏 data 卡 refs，改名诉求走后续独立任务）；CLI `weft figures` 命令组（引擎为纯函数，将来补 CLI 近零成本）；figures_dir 目录浏览。

## 方案取舍

- **A（选定）**：独立引擎 + WebUI 表单。figures.yaml 是人工直接维护的受管注册表，WebUI 表单 = 人的编辑行为（同卡片表单先例，不触红线 4）；引擎自读自写磁盘文件，不假道 store 的加载结果，杜绝"按过期视图重写"。
- B（否）：只读列表页。不满足"操作"诉求（用户明确要编辑能力）。
- C（否）：ruamel round-trip 保注释。引新依赖；figures.yaml 条目 schema 冻结且极简（caption/subfigs），注释属 scaffold 帮助文本，丢注释可接受（决策 F2）。

## 页面与路由规格

子导航 `base.html` 增补 `("figures", "图表", true)`（恒可用；figures.yaml 缺失时页面为空态 + 新增表单）。

| 路由 | 方法 | 行为 |
|---|---|---|
| `/p/{pid}/figures` | GET | 列表页 |
| `/p/{pid}/figures/new` | GET/POST | 新增表单 / 提交 |
| `/p/{pid}/figures/{key}` | GET/POST | 编辑表单 / 保存 |
| `/p/{pid}/figures/{key}/delete` | POST | 删除 |

- **列表页**（模板 `figures.html`）：按 figures.yaml 键序逐行展示——键、类型（`tbl-` 前缀 = 表格，对齐 `assemble/paper.py::_TBL_KEY`；其余 = 图）、caption 摘要、子图数、引用它的 data 卡 id（链接到卡片详情）、标记：`fig-` 前缀且 `figures_dir/{key}.png|pdf` 均缺失 → "文件缺失"（对齐 `W-FIGURE-FILE-MISSING` 语义）；无任何 data 卡引用 → "未被引用"（对齐 `W-FIGURE-UNUSED`；此处计所有状态的 data 卡，权威判定仍以 `weft validate` 为准）。顶部"新增条目"入口；每行"编辑"链接。
- **新增表单**（模板 `figure_form.html` 共用）：类型单选 `fig`/`tbl`；键名可留空 → 自动编号（F5）；caption 单行文本；subfigs 多行 textarea（F7）。
- **编辑表单**：键只读展示（不做键重命名，F8），caption/subfigs 同新增。
- **错误处理**：引擎抛 `FiguresEditError`（携带 `code`/`message`）→ 路由按卡片表单先例 rerender 并回显 `{code} {message}` banner；成功一律 303 回列表页。

## 引擎规格（src/weft/figures_edit.py）

纯函数、不 import web/fastapi，异常类型统一为 `FiguresEditError(code, message)`：

- `load_for_edit(root) -> dict[str, FigureEntry]`：读 `metadata/figures.yaml`（缺文件 = 空映射）；经 `FigureEntry.model_validate` 逐条解析。顶层非映射或任一条目解析失败 → `E-FIG-LOAD`（fail-closed：**注册表有任何解析错误就拒绝一切写操作**，否则整文件重写会静默吞掉坏条目）。这是唯一在 load 阶段抛错的码。
- `next_figure_key(entries, prefix) -> str`：收集匹配 `^{prefix}(\d+)$` 的键取 max+1，格式 `{prefix}{n:02d}`（同 `weft new part` 编号语义；构造上不可能与现有键冲突，仍保留碰撞兜底）。
- `add_entry(entries, key, caption, subfigs, prefix) -> dict`：`key` 为空串时按 `prefix` 自动编号（`prefix` 来自表单的类型单选，取值 `fig-`/`tbl-`）；键名安全成分校验（F4）→ `E-FIG-NAME`；已存在 → `E-FIG-COLLISION`。返回新映射（保持键序，新键追加尾部——assemble 编号 = 键序，新图排最后符合直觉）。
- `update_entry(entries, key, caption, subfigs)`：键不变（F8），替换 caption/subfigs；键不存在 → `E-FIG-COLLISION`（复用"目标不存在/已存在"语义，msg 区分）。
- `remove_entry(entries, key, references)`：`references` 为调用方从 project 收集的 `{data 卡 id: refs 集合}`；若任何卡（**含 rejected**，F6）的 refs 命中 `{key} ∪ {key+sub}` → `E-FIG-IN-USE`，msg 列出引用卡 id。
- `write_figures_yaml(root, entries) -> Path`：确定性重写——键序保持；caption 非空才输出；subfigs 非空才输出（键序保持）；UTF-8、写前 CRLF 归一、固定 LF（同 `store/writer` 惯例）。空条目输出裸键（`fig-01:`），loader 的 `model_validate(value or {})` 兼容。

**subfigs 文本解析**（引擎内 `parse_subfigs(text) -> dict[str, str]`）：逐行处理，空行跳过；按**首个**英文冒号切分，冒号前 strip 后为子图号、冒号后 strip 后为说明；子图号为空或含空白字符 → `E-FIG-VALUE`（msg 指明行内容）；说明可含冒号。subfigs 键序 = 行序。

## 诊断码

| 码 | 级别 | 含义（path=`metadata/figures.yaml`，field=键或 None） |
|---|---|---|
| `E-FIG-LOAD` | 错误（阻断） | figures.yaml 解析失败（顶层非映射/条目非法），写操作全部拒绝 |
| `E-FIG-NAME` | 错误（阻断） | 键名含非法成分（规则同 F4） |
| `E-FIG-COLLISION` | 错误（阻断） | 新增键已存在 / 编辑或删除的键不存在 |
| `E-FIG-IN-USE` | 错误（阻断） | 删除被 data 卡 refs 引用的键（含 rejected 卡） |
| `E-FIG-VALUE` | 错误（阻断） | subfigs 行格式非法（空子图号/含空白） |

进码总表：本设计文档 + AGENTS.md 红线 5 增补。这些码只在 WebUI banner 出现（引擎层），不进 `validate_project`。

## 与现有层的关系

- **不碰**：models（红线 2，`FigureEntry` 原样复用）、store/loader、assemble、validation。
- **红线 4**：figures.yaml 写入是 WebUI 表单 = 人的编辑行为（同 `weft new`/卡片表单先例），非 AI 直接落盘，不新增白名单条款。
- **scaffold**：不 import。键名安全成分规则与 `_ensure_component`（N9）一致但独立实现（异常类型与语义归属不同，F4），测试用样本集锁定两实现行为一致。
- **store**：列表页展示读 `project.figures`（已加载视图）；引擎写路径自读自写磁盘（F12），同一请求内至多两次解析同一个小文件，换取"重写所见即所改"。

## 测试策略（TDD，先红后绿）

新增 `tests/test_figures_edit.py`（引擎）：自动编号（无键从 01 起 / 已有取 max+1 / fig 与 tbl 独立）；键名非法样本（`../x`、含空格、`:`、空串、点首尾）→ E-FIG-NAME；新增已存在键 → E-FIG-COLLISION；追加尾部保持键序；update 不改键序；remove 引用阻断（含 rejected 卡、`key+sub` 命中）；解析失败（顶层列表/坏条目）→ E-FIG-LOAD 零写入；write 输出字节级断言（键序/缺省省略/LF/裸键）；CRLF 输入归一；parse_subfigs 边界（首冒号切分、空行、非法行）；键名规则与 `_ensure_component` 样本集行为一致。

新增 `tests/test_web_figures.py`（路由）：列表页含类型/caption/引用卡链接/文件缺失与未被引用标记；新增（自动编号 + 手输名 + 冲突回显）；编辑保存后列表反映变更；删除成功 / 被引用阻断 banner；手工损坏 figures.yaml 后列表可看、任何写操作回 E-FIG-LOAD；子导航出现"图表"。更新 `tests/test_web_subnav.py`。

计划文档登记精确测试计数（当前基线 651 passed）。

## 决策表

| # | 决策 | 理由 |
|---|---|---|
| F1 | 引擎放 `src/weft/figures_edit.py` 纯函数，WebUI 薄封装 | 与 rename/WebUI 表单共用引擎的架构先例一致；将来补 CLI 零成本 |
| F2 | 整文件重写：不保留注释、丢弃未知键，以 `FigureEntry` 模型为准 | 只依赖 pyyaml；schema 冻结下未知键属非法残留；注释是 scaffold 帮助文本 |
| F3 | 解析失败拒绝一切写操作（E-FIG-LOAD），页面转只读 | 整文件重写会静默吞掉 loader 宽松跳过的坏条目——数据丢失不可接受 |
| F4 | 键名安全成分规则同 `weft new` N9（空、点首尾、空白首尾、`\/:*?"<>|`、控制字符拒绝），独立实现 + 样本集守卫 | 键是图片文件名 stem（`figures/{key}.png`）；避免 scaffold 异常类型泄漏进引擎 |
| F5 | 新增键自动编号 `{prefix}{n:02d}`（fig-/tbl- 独立），手输名允许 | 与 `weft new part` 编号语义一致；键序即编号，自动号排尾部 |
| F6 | 删除引用检查计所有状态 data 卡（含 rejected） | rejected 卡可能被重新批准；删除是不可逆破坏 refs，从严 |
| F7 | subfigs 用 textarea 逐行 `子图号: 说明`（首个冒号切分） | WebUI 无动态表格行先例，避免为单一表单引 JS |
| F8 | 不做键重命名 | 键被 refs 引用，改名 = 引用重写（rename 引擎级别的工作量），独立任务 |
| F9 | 不做图片上传 | WebUI 无上传/二进制先例，范围失控风险；文件缺失已有标记与校验码指路 |
| F10 | 页面类型判定用 `tbl-` 前缀（对齐 assemble），文件缺失标记用 `fig-` 前缀（对齐校验） | 各自对齐现有消费方语义，不新造规则 |
| F11 | 编辑表单键只读；编辑/删除的键不存在 → E-FIG-COLLISION | 键是身份；并发删除/手工改盘的兜底 |
| F12 | 引擎写路径自读自写磁盘，不消费 store 加载结果 | 重写所见即所改，杜绝按过期视图覆盖 |
