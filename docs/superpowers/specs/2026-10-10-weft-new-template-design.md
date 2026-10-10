# weft new 命令组设计定案——模板化创建空白 part 与卡片（2026-10-10）

## 背景与目标

`weft init` 只在建项目时一次性生成骨架；之后新增单个空白文件（叙事 part、元数据卡片）没有模板命令：part 要手工照抄 part-01 的 frontmatter 格式新建，卡片只有 WebUI 表单入口。本设计补齐 CLI 侧的模板化创建能力，与"单人 CLI 优先"定位一致。

目标：`weft new part` / `weft new card` 两条子命令，按内置模板生成"最小合法 + 注释示例"的空白文件，编号自动、碰撞 fail-closed、产物即过 loader。

## 范围

- **做**：CLI 命令组 `weft new`（子命令 `part`、`card`）；scaffold.py 模板层扩展；诊断码 E-NEW-NAME / E-NEW-COLLISION；AGENTS.md 红线 5 与 roadmap 增补。
- **不做**（YAGNI）：WebUI 新建 part 入口（后续独立任务）；用户自定义模板目录；卡片自动编号（id 语义性强，见 N4）；`weft new` 全项目校验闸门（见 N8）。

## 方案取舍

- **A（选定）**：模板走 scaffold.py 纯函数层，手写"最小合法 + 注释示例"模板文本。与 init 脚手架同模式，fact 等模型层必填字段可以生成"待填桩"（模型构造不出来的卡也能落模板）。
- B（否）：复用 `store/writer.create_card` 从模型实例生成。缺点：`FactCard.data` 有 `min_length=1` 且无默认值，空桩根本构造不出来；`model_dump()` 全键展开无注释，模板感差。
- C（否）：只做 part。不满足"各种空白文件"的原始诉求。

## 命令规格

```bash
weft new part <chapter> <section> [--id <part_id>] [PROJECT_DIR]
weft new card <kind> <id> [PROJECT_DIR]
```

- `kind` ∈ data|fact|claim|note|method|param，用 Typer 枚举在解析层拒绝非法值。
- 位置参数顺序对齐现有风格（`weft draft`）：必选参数在前，`PROJECT_DIR` 压轴默认 `.`。
- 成功输出 `已创建 <相对路径>` + 一行下一步提示；失败走 `_print_diagnostics` 退出码 1。

## part 语义（N3）

1. `chapter` 必须是单一安全路径成分（见 N9），违者 `E-NEW-NAME`。目标目录 `narrative/<chapter>/` 不存在则创建（含 `narrative/`）。
2. part id：显式 `--id` 优先；缺省自动编号——收集现有 part id 中匹配 `^sec-(\d+)$` 的整数值，取 max+1，格式 `sec-{n:02d}`（无匹配从 sec-01 起）。自动编号在构造上不可能与现有 id 冲突（所有匹配 id 的整数值都进了 max，非匹配 id 形如 `sec-intro` 不会等于 `sec-\d+` 输出），仍保留碰撞兜底检查。
3. 文件名：目标章节内现有 `part-(\d+).md` 取 max+1，格式 `part-{n:02d}.md`。目标路径已存在 → `E-NEW-COLLISION`，零写入。
4. part id 与现有任何 part 重复（跨章节）→ `E-NEW-COLLISION`。part id 与卡片 id 是独立命名空间，互不检查。
5. `section` 必填（part 的 heading 语义）。写入模板时经 `yaml.safe_dump(…, allow_unicode=True).strip()` 生成 YAML 标量（简单词不加引号，含冒号等自动加引号）。
6. 模板：`render_part_template(part_id, section)` 参数化生成；init 脚手架的 `_PART_01_MD` 改由 `render_part_template("sec-01", "Introduction")` 派生，**逐字节不变**（守卫测试锁定）。nodes 示例注释中的示例节点 id 按 part id 的数字段参数化（`para-<NN>-01`；无数字段用 `01`）。

## card 语义（N4/N6/N7）

1. `id` 位置参数必填，显式不自动编号：note 卡 id = bib key、method/param 为 slug，语义性命名不该被序号替代（N4）。
2. id 安全成分校验同 N9 → `E-NEW-NAME`；id 已被**任何种类**卡片占用（全局命名空间，`project.card_paths`）→ `E-NEW-COLLISION`。
3. 落盘路径对齐 `store/writer.card_relpath` 规范映射：data→`metadata/data`、fact→`metadata/facts`、note→`metadata/notes`、method→`metadata/methods`、param→`metadata/methods/params`、claim→`metadata/claims/uncited`（新建 claim 默认 `claim_type: uncited`）。文件名 = `<id>.md`（loader 强制 `E-FILENAME-MISMATCH` 一致性）。目标已存在 → `E-NEW-COLLISION`。
4. 模板 per kind（N6）：`id` + `status: draft` 为实体键；模型层可缺省的字段全部以注释示例给出；模型层必填字段（fact.data/fact.statement、claim.claim_type/claim.statement、method.statement/protocol、param.method）以空占位实体键给出。**明确接受**三类"待填指路"错误：fact 桩 `data: []` 过不了 `min_length=1`（loader 层 E-PARSE）；param 桩 `method: ""` 悬空（校验层 E-DANGLING-REF）；note 桩 id 未登记进 bib（校验层 E-NOTE-NOT-IN-BIB）。三者都会被 `weft validate` 指出、被 `weft draft` 闸门挡住——schema 冻结（红线 2）下这是"模板给骨架、人填血肉"的自然结果。data/claim/method 桩无新增错误。
5. 不经过 `create_card`/`_dump`：模板含注释，直接由 scaffold 写文本（固定 LF、UTF-8、写前归一化不适用——模板本身无 CRLF）。

## 命名安全成分（N9）

拒绝：空串、`.`、`..`、含 `/` `\`、Windows 保留字符 `< > : " | ? *`、控制字符、首尾空格、以 `.` 开头。命中即 `E-NEW-NAME`（path 字段为 `.`，msg 指明非法参数名与值）。允许中文等 Unicode 成分。

作用对象：`chapter` 与卡片 `id`（二者都是落盘路径成分）。part `--id` 只进 frontmatter 不进路径，仅要求非空（YAML 标量转义由 safe_dump 兜底）。

## 诊断码（N8）

| 码 | 级别 | 含义 |
|---|---|---|
| `E-NEW-NAME` | 错误（阻断） | `chapter` 或卡片 id 含非法路径成分 |
| `E-NEW-COLLISION` | 错误（阻断） | 目标文件已存在，或 id 已被占用（fail-closed，零写入） |

进码总表：本设计文档 + AGENTS.md 红线 5 增补。

## 与现有层的关系

- **不碰**：models（红线 2）、store/loader、engine 落盘白名单（红线 4——`weft new` 是"人写"工具，同 WebUI 表单性质，写 `narrative/` 与 `metadata/` 属人的编辑行为，非 AI 落盘）。
- **加载容错**：`weft new` 只从加载结果取 part id / card id 集合做碰撞检查，项目既有错误不阻断新建（区别于 `weft draft` 的全量闸门，N8）。
- scaffold.py 职责从"init 骨架"扩为"内置模板层"，docstring 同步；仍不依赖 engine/LLM。

## 测试策略（TDD，先红后绿）

新增 `tests/test_new_cmd.py`：

- scaffold 纯函数：`render_part_template("sec-01", "Introduction")` 与原 `_PART_01_MD` 逐字节一致（init 守卫）；参数化 id/section/YAML 引用正确。
- part：全新项目自动编号 sec-01/part-01；已有 sec-01 → sec-02、章节内 part-01 → part-02；显式 `--id`；跨章节 id 冲突 E-NEW-COLLISION；目标文件已存在；chapter 非法（`../x`、空、含 `\`）E-NEW-NAME；产物 load_project 无新增错误。
- card：六 kind 参数化落盘路径；claim → uncited 目录且 claim_type 一致；id 冲突；非法 id；fact 桩恰好一条 E-PARSE（data）；param 桩出 E-DANGLING-REF（method 悬空）；note 桩出 E-NOTE-NOT-IN-BIB（id 未入 bib）；data 桩无新增错误；产物文件名 = id。
- CLI：成功输出与退出码 0；失败退出码 1 + 诊断码出现。

init 现有测试（含 golden）保证改造不回归。计划文档登记精确计数（预期全量 ~582 passed）。

## 决策表

| # | 决策 | 理由 |
|---|---|---|
| N1 | 命令组 `weft new`，Typer sub-app（同 projects/bib 模式） | 与现有 CLI 结构一致 |
| N2 | 范围 CLI part + 六类卡片；WebUI 不动 | 单人 CLI 优先；WebUI 卡片已有表单 |
| N3 | part 章节优先寻址，id/文件名自动编号 | 新章节是高频操作，敲起来最短 |
| N4 | 卡片 id 显式必填，不复用 `next_card_id` | note id = bib key，语义命名优先 |
| N5 | 模板层放 scaffold.py；init 模板改由参数化函数派生（字节不变） | 模板单一来源，init 行为守卫锁定 |
| N6 | 桩卡 = id+status:draft+必填空占位+注释示例；fact/param/note 的"待填指路"错误接受 | schema 冻结下的最优折衷，校验器指路 |
| N7 | 落盘路径对齐 `card_relpath`（param → methods/params；claim → uncited） | loader 强制目录一致性，杜绝 E-CLAIM-DIR-MISMATCH |
| N8 | 只做目标碰撞 + 命名检查，不跑全项目闸门 | 新建文件不应被项目既有错误绑架 |
| N9 | 安全成分规则（Windows 兼容），违者 E-NEW-NAME | id 是落盘路径组件，fail-closed |
| N10 | 位置参数 chapter/section/kind/id，PROJECT_DIR 压轴 | 对齐 `weft draft` 风格 |
