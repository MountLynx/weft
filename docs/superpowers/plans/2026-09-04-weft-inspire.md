# weft inspire — 灵感式写作→卡片管线 实施计划

- 日期：2026-09-04
- 依据：设计定案 `docs/superpowers/specs/2026-09-04-weft-inspire-design.md`（用户已确认；按用户指示不走 writing-plans 流程直接实现，本文档只登记任务分解、精确计数与执行期决策）
- 基线：247 passed, 1 deselected（inspire worktree 待实测确认）

## 任务分解（TDD，每任务先红后绿）

| # | 模块 | 测试文件 | 预期新增 |
|---|------|----------|----------|
| 1 | `src/weft/digest.py` 摘要索引 | test_digest.py | 4 |
| 2 | `engine/inspire/schemas.py` 节点输出 schema | test_inspire_schemas.py | 8 |
| 3 | `engine/inspire/spec_build.py` 任务表与 flow | test_inspire_spec_build.py | 3 |
| 4 | `engine/inspire/cards.py` 受控写入器 | test_inspire_cards.py | 4 |
| 5 | `engine/inspire/apply.py` 聚合（id 分配/闭包/提案/报告） | test_inspire_apply.py | 7 |
| 6 | `engine/inspire/run.py` 管线运行 + fail-closed | test_inspire_run.py | 4 |
| 7 | CLI `inspire` / `replace` / `missing-cites` | test_cli_inspire.py | 9 |
| 8 | scaffold 加 `inspirations/`；守卫/回归 | test_scaffold.py 更新 | 0 |

**精确预期计数：247 + 39 = 286 passed, 1 deselected（实测一致）。**

## 执行期设计决策

| # | 决策 | 依据 |
|---|------|------|
| D1 | A1"聚合节点"实现为 run 层纯函数 `apply_inspiration`，不占 SpecModule 节点 | 语义等价（firings 事后收集同 M2 draft），免去 4 输入的 view 管道；SpecModule 只跑 T1–T4 |
| D2 | 拟建卡不带真实 id：AI 出临时 key（f1/c1），A1 按**全局 id 命名空间**分配下一个空闲 `fact-NN`/`claim-NN` | id 唯一性是 loader 硬约束，AI 起名必撞 |
| D3 | 补充卡提案的 id = 目标卡 id，结构化字段（data/cites/supports）从原卡**机械继承**，仅 statement 由 LLM 合并（merged_statement） | "完整新卡含原卡信息"且结构化完整性不由 LLM 保障（宁可多做不要出错） |
| D4 | `weft replace` 闸门：在内存 Project 上以新卡对象替换后跑 `validate_project`，有 error 即拒绝且磁盘零改动 | 无需写后回滚 |
| D5 | mock 客户端扩展进 ScriptedLLMClient：按 prompt 起始标记（【灵感·…】）分流四节点响应，默认响应与 helpers.make_minimal_project 自洽（fact→data-01） | 复用 draft 同一假客户端模式，CLI --mock 全链可测 |
| D6 | 矛盾卡（verdict=conflict）仍作为草稿卡落盘，矛盾详情进报告由人仲裁 | 冲突不应吞掉内容 |
| D7 | 原文归档重名 → 拒绝（inspirations/processed/<名>.md 已存在即报错） | 溯源不可覆盖 |
| D8 | claim 卡不写 supports 字段（ClaimCard extra=forbid，无此字段）；AI 拆解的 link 一律解析为 fact.supports → claim id | 冒烟实测抓出 E-PARSE；weft 的支持方向本来就存在 fact 卡上 |
| D9 | inspire 捕获 DraftError（make_client 真实模式无配置时）→ 干净 ERROR | 冒烟实测：否则甩 traceback |
| D10 | 报告内路径以项目根为基准（report.parents[2]） | 冒烟实测：多带一层目录 |

（执行中新增决策续写于此。）

## 验收

1. 全量 286 passed, 1 deselected（实测）。
2. 真实 CLI 冒烟：make_minimal 项目 + `weft inspire` --mock 全链落盘三件套；`weft missing-cites`；`weft replace`。
3. roadmap/AGENTS/诊断码总表同步。
| D11 | inspire 开启 persist（base_dir=generated/inspirations/.runs/）+ Module.resume 断点续跑：同灵感重跑时回退到最后成功节点的 tick 快照，只补跑失败节点；成功后同灵感再跑 = 清场全新跑；已完成节点输出经 load_snapshot_summary 取回 | 用户指出应复用 SpecModule 原生快照/续跑；e2e 实测全链重跑成本高 |
| D12 | SpecModule 实测语义：失败节点的 firing 已被消费（出边写 False），resume 缺省不重试——必须显式 `resume(rollback_to=<最后成功 tick>)`；失败节点的快照 output 是 `Failure(...)` 描述字符串（非 dict），续跑判定须校验值类型而非键存在 | 单测+调试实测 |
| D13 | LLM 空输出（finish=length，推理模型思考 token 耗尽 4096）无可提取，OutputValidator 的围栏/JSON 提取兜底帮不上——api_params 抬高 max_tokens 是正解；OutputFormat json_schema + 强制 tool-use 为可选加强（未启用） | 源码调研 module_harness/outputfmt.py、llm/client.py |
