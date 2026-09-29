# weft 项目注册表（projects registry）——多项目共存与隔离 设计定案

- 日期：2026-09-29
- 依据：用户需求"一个主程序启动，多个项目共存，项目间隔离，而不是靠切换根目录一次只能看一个"；现状勘察（CLI 单项目寻址、serve 仅单根扫描、项目无元数据、判据两处不一致）
- 状态：设计已获用户逐节确认（brainstorm 决策表见文末 R1–R12，R12 为实现期增补）

## 1. 目标与非目标

**目标**：引入**全局项目注册表**作为"哪些项目存在"的唯一清单，项目可位于磁盘任意位置。一个常驻主程序（`weft serve`）同时托管全部已注册项目，项目之间数据/运行/LLM 配置互相隔离；CLI 配套 `weft projects` 命令组完成登记、新建、摘除、查看与默认位置管理。**删除只摘表、绝不删本地文件**。注册表把"项目身份"与"物理路径"解耦，为将来云端形态（服务器自有 WEFT_HOME、清单即项目全集）预留适配点。

**非目标（YAGNI，明确不做）**：

- "当前激活项目" / CLI 免 cd 按名寻址（`weft validate mypaper` 之类）——现有命令的 `project_dir` 参数一律不动；将来需要时在注册表上长出来（方案 C 的真子集）。
- WebUI 端的 remove/rename/归档操作（本版只做列表展示 + 新建登记闭环）。
- 注册表文件锁 / 多进程并发写（单用户工具，原子替换足够）。
- 失联条目自动清理（删表动作只属于显式 `remove`，自动摘除是它的反面）。
- 云同步本体（多机同步注册表内容、远端项目等）——本版只保证结构上可适配。
- 扫描模式（`weft serve <root>`）的任何行为变化。
- 本地项目文件的删除/移动/重命名功能。

## 2. 现状与问题

| 现状 | 问题 |
|---|---|
| CLI 全部命令靠位置参数 `project_dir`（默认 cwd）定位项目 | 一次只能操作一个项目，多项目要来回切目录 |
| `weft serve <projects_root>`（参数必填）每请求扫描根下一级子目录 | 项目必须集中放进同一个父目录；散落各处的项目看不到 |
| 项目唯一标识 = 目录名，无任何元数据文件 | 没有跨位置的稳定身份 |
| 项目判据两处不一致：`store/loader.py:49-53` 认 `metadata/` 或 `_quarto.yml`，`web/discovery.py:48` 只认 `metadata/` | "什么是一个项目"没有单一答案 |

## 3. 注册表：位置、schema、失败语义

新模块 `src/weft/registry.py`（纯 Python + pydantic；不 import llm/module_harness，红线 1 无涉；模型定义在本模块内，**不动冻结的 `models/` 卡片 schema**）。

**位置**：`$WEFT_HOME/projects.json`，`WEFT_HOME` 未设置时为 `~/.weft/`。`WEFT_HOME` 是测试隔离与云端部署（容器指定家目录）的适配点。

**schema**（`version: 1` 预留演进；UTF-8、indent 2、LF）：

```json
{
  "version": 1,
  "default_root": "D:/weft-projects",
  "projects": [
    {
      "name": "paper-demo",
      "path": "C:/Users/xingy/Desktop/开发/weft/examples/paper-demo",
      "registered_at": "2026-09-29T10:00:00"
    }
  ]
}
```

- `path` 存 `Path.resolve().as_posix()`（绝对路径、正斜杠，JSON 友好）。
- `registered_at` 为本地时间 ISO 8601（秒精度）。
- `default_root` 可为 `null`（未配置），语义见 §4 `new`。
- 写入：临时文件 + `os.replace` 原子替换（同 bibgen 渲染器手法），固定 LF。
- 文件不存在 = 空注册表（合法初态，读侧返回空、写侧按需创建目录与文件）。

**失败语义（R8）**：文件存在但损坏/不可解析/schema 不符 → fail-closed 报 `E-REG-MALFORMED`（诊断含文件绝对路径），**不静默重建、不丢弃用户数据**。全局状态只有一个 JSON 文件，响亮失败优于悄悄重建。

**名称规则（R4）**：注册名是全局唯一 id，同时是 WebUI URL 的 pid。校验器从 `web/routes/core.py` 的 `_validate_project_name` **抽出为共享实现**（落位 `registry.py`，WebUI 改为 import 同一份），语义 = 既有黑名单 + 追加禁止路径分隔符（`/`、`\`）与控制字符。名称、路径（resolve 后）在注册表内双双唯一。

## 4. CLI：`weft projects` 命令组

typer 子应用，五个命令，全部**不带** `project_dir` 参数（它们操作全局状态）：

```
weft projects add <path> [--name NAME]   # 校验是合法 weft 项目后登记；默认名=目录名
weft projects new <name> [--root DIR]    # init_project 骨架 + 登记
weft projects list                       # 表格：名称 / 路径 / 状态 / 登记时间
weft projects remove <name>              # 只摘表，绝不触碰本地文件
weft projects root [<dir>]               # 无参=显示当前默认根；带参=设置
```

- **add**：目标必须存在且通过项目判据（见 R3），否则 `E-REG-NOT-PROJECT` 退出码 1。名称冲突 `E-REG-DUP`、路径已被其他名称登记 `E-REG-PATH-DUP`（提示已有名称），均零写入 fail-closed。成功打印登记的名称与路径。
- **new**：`--root` 为**父目录**，项目落在 `<root>/<name>/`。位置三级回退（R5）：`--root` > 注册表 `default_root` > `~/weft-projects`。执行顺序保证零残留：**先查名称重名**（命中 `E-REG-DUP` 即刻失败、零写入）→ `init_project` 建骨架（目录已存在且非空 → 沿用 `E-INIT-COLLISION` 零写入）→ 登记入表。默认根目录不存在时按需 `mkdir -parents`。
- **list**：纯只读（R6 延伸：不清理、不改表）。每行展示名称 / 路径 / 状态（`ok` / `missing`）/ 登记时间；`missing` = 路径不存在或项目判据不通过。注册表为空时打印引导文案（`weft projects add/new`）。有 missing 条目**不**改变退出码（信息性状态，R9）。
- **remove**：未知名称 `E-REG-UNKNOWN` 退出码 1；成功只从表中摘除并打印提醒"本地文件未删除"。
- **root**：无参打印当前默认根及来源（`配置值` / `默认值 ~/weft-projects`）；带参设置（相对路径转绝对；目录不要求已存在，`new` 时按需创建）。

## 5. `weft serve` 双模式与 WebUI

- **无参 → 注册表模式**：列表页数据 = 注册表逐条**实时**读取 + 探测（R7：沿用 discovery 决策 D7 的"无缓存、每请求重扫"哲学——顺带免费获得"CLI `add` 之后 serve 刷新即见"的跨进程一致性）。可用项目正常渲染；失联项目灰显卡片 + "位置失联：`<path>`" 文案、链接禁用（R9，环境状态非错误）。
- **带 `projects_root` 参数 → 扫描模式**：行为一字不改（含列表过滤判据），不自动登记进注册表——两模式语义各自完整，扫描模式用户零感知。
- **实现形态**：`discovery` 抽出统一入口 `collect_projects(entries) -> list[ProjectEntry]`（输入为 (pid, 路径) 对列表）；扫描模式喂目录扫描结果，注册表模式喂注册表条目。渲染与子路由（`/p/{pid}/…`）零改动；`app.state` 记录模式来源。
- **`POST /projects/new`**：注册表模式下表单增加可选"位置"输入（留空 = 默认根；填父目录则在其中建同名子目录）；创建成功即登记。默认根未配置且位置留空 → 表单错误提示"先执行 `weft projects root <dir>` 设置默认位置"。名称冲突、目标非空分别映射 `E-REG-DUP` / `E-INIT-COLLISION` 的表单错误提示（零写入）。扫描模式表单维持现状（仅名称输入、不登记）。
- **注册表损坏**：列表页渲染错误横幅（含 `E-REG-MALFORMED` 诊断与文件路径）替代项目网格，不白屏 500。**空注册表**：列表页空态 + 引导文案（新建表单照常可用）。
- **RunManager**：锁粒度仍为 project_key；注册表模式下 key = 注册名，全局唯一性由注册表保证，无碰撞。

## 6. 项目间隔离（逐条落实）

| 维度 | 机制 | 状态 |
|---|---|---|
| 数据 | 每请求独立 `load_project`，A 的校验错误/卡片状态不进 B 的内存 | 现状保留 |
| 生成运行 | `RunManager.try_start(project_key)` 每项目串行、互不占锁 | 现状保留，key 换注册名 |
| LLM 配置 | `make_client` 按各项目 root 走 config.json/.env/环境变量回退链 | 现状保留——每项目可挂独立 key |
| 路径安全 | 注册表只提供 root；落盘仍只走 `write_draft`/`card_writer` 白名单与 WebUI files 白名单 | 注册表不新增任何落盘点 |

## 7. 项目判据（R3）

引入共享判定 `is_weft_project(path)`（落位 `store/loader.py` 导出，判据 = loader 既有规则：根下含 `metadata/` **或** `_quarto.yml`），消费方：

- CLI `add`、注册表模式的可用性探测——**统一为 loader 判据**；
- 扫描模式的列表过滤**维持现状**（只认 `metadata/`），保证"扫描模式零行为变化"承诺；与 loader 判据的历史差异保留为已知的列表启发式，不做放宽（放宽会让"只有 `_quarto.yml` 的随机 Quarto 目录"出现在列表里）。

## 8. 诊断码（红线 5 登记）

| 码 | 级别 | 语义 |
|---|---|---|
| `E-REG-MALFORMED` | 错误 | 注册表 JSON 损坏/不可解析/schema 不符（CLI 退出 1；serve 列表页错误横幅） |
| `E-REG-DUP` | 错误 | 注册名已存在 |
| `E-REG-PATH-DUP` | 错误 | 同一路径已用其他名称登记 |
| `E-REG-NOT-PROJECT` | 错误 | `add` 目标不存在或不是 weft 项目 |
| `E-REG-UNKNOWN` | 错误 | `remove` 时未知注册名（WebUI 未知 pid 走常规 404，不用此码） |
| `E-REG-NAME` | 错误 | 注册名不合法（黑名单/路径分隔符/Windows 保留名等；实现期增补，R12） |

沿用码：`E-INIT-COLLISION`（`new` 目标非空）。失联条目是环境状态而非错误，**不设**诊断码（R9）。

## 9. 测试策略（TDD 先红后绿）

- `tests/test_registry.py`：加载/保存/原子写、`WEFT_HOME` 隔离、空文件初态、损坏文件 fail-closed（`E-REG-MALFORMED`）、名称/路径去重、共享名称校验器（黑名单 + 路径分隔符）、默认根三级回退。
- CLI 测试（并入或新立 `tests/test_cli_projects.py`）：五命令快乐路径 + 错误路径 + 退出码；`remove` 后本地文件原样存在；`new` 重名时零写入。
- WebUI 测试：无参 serve 读注册表渲染列表、missing 灰显禁入、`/projects/new` 创建即登记闭环、默认根未配置的表单报错、注册表损坏的错误横幅、扫描模式回归（现有用例全数保持绿）。
- 精确测试计数在实施计划文档中登记。（实现说明：用户裁定跳过计划文档直接实现；实际计数 77 条新增 = test_registry 43 + test_cli_projects 21 + test_web_registry 13，全量 547 passed / 2 deselected，登记于 roadmap M4。）

## 10. 兼容性与文档登记

- 现有项目**无需迁移**：登记是显式动作，不登不影响任何现有用法。
- `weft serve <root>` 老用法一字不改（`projects_root` 参数从必填改可选，带参行为不变）。
- 文档更新随实现落地：`roadmap.md` M4 登记本功能；`AGENTS.md` 必读清单增补本 spec、常用命令清单加 `projects`、红线 5 诊断码表引用本 spec；`docs/webui.md` 增补注册表模式说明。

## 决策表（brainstorm 逐项确认）

| # | 决策 |
|---|---|
| R1 | 架构选方案 A：单文件全局注册表 + serve 双模式（否决 B 约定根目录、C 全局工作区中心） |
| R2 | 注册表位置 `$WEFT_HOME/projects.json`（缺省 `~/.weft/`）；`WEFT_HOME` 为测试与云端适配点 |
| R3 | 注册表通道统一 loader 判据（`metadata/` 或 `_quarto.yml`，共享 `is_weft_project`）；扫描模式列表过滤维持只认 `metadata/`（零行为变化），差异登记为已知非对称 |
| R4 | 注册名即全局唯一 id（= WebUI pid）；名称与路径在表内双唯一；名称校验器抽出共享实现（web 复用） |
| R5 | `new` 位置三级回退：`--root` > `default_root` > `~/weft-projects`；先查重后建骨架，零残留 |
| R6 | `remove` 只摘表不删本地文件，无 purge 变体；`list` 纯只读不自动清理失联条目 |
| R7 | serve 注册表模式每请求实时读注册表 + 探测（沿 D7 无状态哲学，CLI/serve 免同步） |
| R8 | 注册表损坏 fail-closed（`E-REG-MALFORMED`），不静默重建 |
| R9 | 失联（missing）= 环境状态：列表灰显、不设诊断码、不改退出码 |
| R10 | 隔离四维（数据/运行/LLM 配置/路径白名单）全部沿用现状机制，注册表不新增落盘点 |
| R11 | YAGNI 边界：不做按名寻址、WebUI remove/rename、文件锁、自动清理、云同步本体 |
| R12 | 实现期增补：CLI 侧名称不合法需要诊断码 → `E-REG-NAME`（`register_project`/`ensure_registrable` 抛出；WebUI 表单沿用无码文案惯例） |
