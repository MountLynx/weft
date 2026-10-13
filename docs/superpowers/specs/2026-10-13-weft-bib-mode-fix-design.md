# weft bib 模式切换与一键修复设计定案（2026-10-13）

## 1. 背景与目标

unmanaged 项目经 PDF/线索提案产生的 draft note 卡携带全新 bib key，必然触发
`E-NOTE-NOT-IN-BIB`（bibgen 设计 §7：unmanaged 规则含 draft）。b2c5a84 已解锁审阅面
（P-D9），但恢复仍要求用户手抄条目进 bib——修复路径没有产品化。

目标：

1. **bib 模式切换**：unmanaged ↔ managed 双向切换（改 `weft.yaml` 的 `bib.managed`），
   切换前出预检报告，杜绝数据静默丢失。
2. **一键修复**：unmanaged 项目把 note 卡的 `entry` 经 `bibgen.render_entry` 确定性
   追加进 bib 文件（幂等），清掉 `E-NOTE-NOT-IN-BIB`。

入口：WebUI（仪表盘 bib 模式块、诊断页行内按钮、note 详情页按钮）与 CLI
（`weft bib mode`、`weft bib fix`）双入口，共用同一引擎实现。

## 2. 非目标

- **bib 条目导入为文献卡**：unmanaged→managed 预检只报告无卡手写条目，不自动导入
  （需要 BibTeX 解析器，V2 另立设计）。
- **自动修改 `_quarto.yml`**：bibliography 形状不满足时拒绝并指引手修，不代改用户文件。
- **managed 项目的 note 修复**：managed 用 `weft bib sync` 管辖，一键修复不适用。
- **AI 参与**：全程确定性工具操作，不涉引擎 LLM 管线。

## 3. 引擎层（`src/weft/bibgen.py` 扩展）

### 3.1 BibModeError

`class BibModeError(Exception)`——切换/修复前置失败的统一异常；呈现时统一带码
`E-BIB-MODE`（新码，§6）。

### 3.2 预检 `plan_switch(project, to_managed) -> SwitchPlan`（零写入）

`SwitchPlan` 字段：

| 字段 | 含义 |
| --- | --- |
| `to_managed` | 目标模式 |
| `from_managed` | 当前模式（apply_switch 执行前核对，防竞态） |
| `bib_files` | 当前 bibliography 声明且存在的文件（loader 口径） |
| `hand_only_entries` | bib 中存在、但无对应 approved+entry note 卡的 key——managed 化后**下次 sync 将消失**，逐条列出 |
| `notes_not_in_bib` | 非 rejected note 中 id 不在 bib 的 key——unmanaged 化后将报 E-NOTE-NOT-IN-BIB（entry 非空者可用一键修复） |

前置（违反抛 `BibModeError`）：

- `project.bib_cfg_error` 非空 → 拒绝（先修 weft.yaml）。
- `to_managed` 且 `len(bib_files) != 1` → 拒绝（E-BIB-SHAPE 同口径；managed 化会造出
  常驻错误状态，fail-closed）。
- managed→unmanaged 无形状前置（bibliography 现状本就合法或本就缺失）。

### 3.3 执行 `apply_switch(project_root, plan) -> None`

- **逐行改 `weft.yaml`，注释全保留**（scaffold 模板注释即文档，`yaml.safe_dump` 会毁掉）；
  "bib: 块"指 `bib:` 行起至下一个顶层键（零缩进行）或文件尾：
  - `bib:` 块内定位 `managed:` 行 → 翻转布尔值；
  - 无 `bib:` 块 → 文件尾追加 `\nbib:\n  managed: <bool>\n`；
  - 有块无 `managed:` 键 → 块首插入 `  managed: <bool>`。
- 原子写（tmp + `os.replace`），固定 LF；执行前重读文件核对当前值与 plan 出发值一致，
  不一致抛 `BibModeError`（"weft.yaml 已变化，请刷新重试"）。
- **不自动 sync**（决策 M1）：to_managed 后 bib ≠ 渲染产物由现有 `W-BIB-STALE` 提醒接管；
  预检已警告 `hand_only_entries` 将在下次 sync 消失。

### 3.4 修复 `fix_note_in_bib(project, key) -> str`（返回 `"added"` 或 `"present"`）

前置（违反抛 `BibModeError`）：

- `project.bib_managed` → 拒绝（提示 managed 用 `weft bib sync`）；
- `bib_cfg_error` 非空 → 拒绝；
- `len(project.bib_files) != 1` → 拒绝（含 bibliography 缺失 / 文件不存在两种形态，指引修 `_quarto.yml`）；
- note 不存在或 `status == "rejected"` → 拒绝；
- `note.entry is None` → 拒绝（指引补 entry 或改名复用已有 key）。

幂等：key 已在 `project.bib_keys` → 返回 `"present"`，零写入。
执行：`render_entry(note)`（`BibValueError` 裸穿，调用方标 `[E-BIB-VALUE]`）→ 追加到
唯一 bib 文件（前置 `\n` 分隔、结尾 `\n`；文件不存在则创建）；原子写；既有内容逐字节保留。

### 3.5 `fixable_notes(project) -> list[str]`

非 rejected、`entry` 非 None、id 不在 `bib_keys`、unmanaged、bib 文件恰一个——排序返回。
诊断页/详情页按钮可见性与 CLI `--all` 共用此口径。

## 4. WebUI（新路由模块 `src/weft/web/routes/bibmode.py`）

全部经 `load_reviewable_or_404`（决策 M6）：报错项目恰恰是修复目标用户（b2c5a84 先例）。

| 路由 | 行为 |
| --- | --- |
| `GET /p/{pid}/bib/switch?to=managed\|unmanaged` | 确认页 `bib_switch_confirm.html`：预检报告（`hand_only_entries` 逐条大字警告）；`to` 非法 → 404 |
| `POST /p/{pid}/bib/switch`（form `to`） | `apply_switch` → 303 → `dashboard?bibmode=switched`（横幅：已切换 + 下一步提示）；前置失败 → 确认页 rerender 带 `[E-BIB-MODE]` 错误 |
| `POST /p/{pid}/bib/fix/{key}`（form `back` ∈ `diagnostics\|card`） | 成功 → 303 回原页 `?fix=added\|present`（横幅）；失败 → 303 回原页 `?fix=error`（通用横幅：前置已变化请刷新） |

模板改动：`dashboard.html`（stats 下新增 bib 模式块：当前模式徽章 + 切换链接，
managed 时附 sync 提示）、`diagnostics.html`（E-NOTE-NOT-IN-BIB 行内 key ∈ fixable
时显示一键修复按钮）、`card_detail.html`（note 卡 fixable 时状态表单旁显示按钮）、
`base.html` 不动（query 横幅在各页内自行渲染，figures 页 `?pdfwarn` 先例）。

## 5. CLI（`cli.py` bib 组）

- `weft bib mode`：显示当前模式。
- `weft bib mode managed|unmanaged [--yes]`：load → `plan_switch` → 打印报告
  （`hand_only_entries` 逐条）→ `typer.confirm`（`--yes` 跳过）→ `apply_switch` → 打印
  结果与下一步提示（managed：记得 `weft bib sync`；unmanaged：可用 `weft bib fix`）。
- `weft bib fix KEY|--all`：`fix_note_in_bib`；`--all` 遍历 `fixable_notes`；逐条打印
  added/present/`[E-BIB-MODE]` 错误；managed 项目整体拒绝。

## 6. 诊断码

- 新增 **`E-BIB-MODE`**（错误）：切换/修复动作前置失败的稳定标识（`E-INIT-COLLISION`
  先例——操作异常码，不进 `validate_project`，不是项目状态诊断）。
- 复用：`E-BIB-SHAPE`（切换后可能的状态，预检已前置拦截）、`E-BIB-VALUE`（修复时
  `render_entry` 失败）、`W-BIB-STALE`（切换后 bib 与渲染不一致的常态提醒）。

## 7. 架构红线影响

- **红线 4（路径白名单）**：增补——`bibgen.py` 确定性写 unmanaged bib 目标文件（修复
  追加）与 `weft.yaml` 的 `bib.managed`（模式切换）；均为确定性工具落盘，非 AI 产物。
- **红线 5（码表）**：`E-BIB-MODE` 进 AGENTS.md 码表。
- 红线 1/2/3/6 不受影响：无 AI import、schema 冻结不动、加载不中断语义不变、生成闸门不变。

## 8. 测试策略（先红后绿）

- 引擎：plan_switch 双向（前置/报告内容）、apply_switch（翻转/追加块/插键/注释保留/
  竞态拒绝/LF/原子性）、fix_note_in_bib（追加/幂等/各前置拒绝/render 失败穿透）、
  fixable_notes 口径（约 14 条）。
- WebUI：确认页渲染与 404、切换 POST 成功/失败、修复 POST added/present/error、
  dashboard bib 块、诊断页与详情页按钮显隐（约 9 条）。
- CLI：mode 显示/切换/`--yes`、fix 单个/`--all`/managed 拒绝（约 5 条）。

## 9. 决策表

| M# | 决策 | 理由 |
| --- | --- | --- |
| M1 | 切换不自动 sync | `W-BIB-STALE` 接管；防手写条目被静默清掉（B4 纯派生定案下 sync 即覆盖） |
| M2 | `weft.yaml` 逐行改保注释 | scaffold 模板注释即使用文档；`safe_dump` 重写毁注释 |
| M3 | to_managed 前置 bibliography 恰一个 | E-BIB-SHAPE 同口径；不满足拒改 `weft.yaml`，不造出常驻错误态（fail-closed） |
| M4 | 修复幂等返回 `present` | 重复点击/并发安全，零写入 |
| M5 | `E-BIB-MODE` 为操作异常码 | 仿 `E-INIT-COLLISION`：动作失败非项目状态，不进 validate |
| M6 | bibmode 路由用 `load_reviewable_or_404` | 报错项目恰是修复目标用户（b2c5a84 / P-D9 先例） |
| M7 | bib→卡导入、自动改 `_quarto.yml` 列为非目标 | 需 BibTeX 解析器 / 易踩坏用户文件；V2 另立设计 |
| M8 | 修复失败经 `?fix=error` 通用横幅 | 按钮可见⇒fixable 曾成立，失败只剩竞态；不值得为竞态做重渲染通道 |
