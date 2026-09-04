# draft 管线 v2 —— 单段落六节点管线 实施计划

- 日期：2026-09-04
- 依据：用户设计指令（宁可多做不出错、一节点一事）；拼接成稿仍归 `weft assemble`
- 基线：297 passed, 1 deselected

## 管线设计

一次 `weft draft <part>` = 对 part 内每个 approved 节点各跑一次六节点 SpecModule run：

```
[g] --> c1
c1 --> l
l  --> p
p  --> c2
c2 --> f
```

| 节点 | harness | 职责 | 输出 |
|---|---|---|---|
| g 生成 | draft_gen | 输入=研究总述+节点 uses+实体全文（fact 带 data 描述；claim 带分类与 note 摘要）；生成段落+占位符 `{{fact-xx}}`（图表落点）/`{{claim-xx}}`（文献落点，仅 cited claim） | `{paragraph}` |
| c1 校验 | draft_check | 对照卡片/uses/占位符安排；通过只输出 pass，不通过输出修正文本 | `{verdict, paragraph?}` |
| l 衔接 | draft_link | 前后 part 内容（前文必传、后文如有）做段间衔接 | `{paragraph}` |
| p 润色 | draft_polish | 事实不偏移 + 学术写作风格 | `{paragraph}` |
| c2 复检 | draft_check（复用） | 防润色偏移；同 c1 覆盖语义 | `{verdict, paragraph?}` |
| f 填充 | script fill | 覆盖链合成有效文本→占位符确定性填充：fact→data.refs→figures.yaml 键序字面编号（Fig. 1a / Table 1）；claim→其 YAML cites→`[@key]`；残余占位符/越界/不在 bib → DraftRuleError | `{paragraph, reminders}` |

工作文本包裹 `<<<PARAGRAPH … >>>` 定界符（模型定位 + mock 提取）。

## 其他决策

| # | 决策 |
|---|---|
| D1 | 研究总述固定放 `overview.md`（项目根，init 骨架新增模板；engine 读不到则视为空并跳过） |
| D2 | cited claim 空 cites 时：占位符移除 + WARN 提醒（不硬失败）；uncited claim 出现占位符 → 移除 + WARN |
| D3 | `--no-align` 移除（c1/c2 恒运行，语义取代 align）；旧 V/align/uses-自报校验被 c1/c2/f 取代 |
| D4 | fill 后仍跑 `[@key] ∈ bib` 硬校验（双保险） |
| D5 | mock 客户端：gen 从 prompt JSON 提取 uses 发占位符；check 恒 pass；link/polish 回显定界符内文本 |

## 任务分解（TDD）

1. spec_build：build_node_spec + 五 harness 任务表（红→绿，tests/test_spec_build.py 重写）
2. draft_rules：新输出形状解析 + fill 脚本（tests/test_draft_rules.py 扩充）
3. run：run_draft(project, part, node, client, context) 六节点运行 + 覆盖语义（tests/test_engine_run.py 扩充）
4. clients：四个新分支 mock（tests/test_clients.py 扩充）
5. cli：draft 循环节点、--no-align 移除、overview 读取（tests/test_cli_draft.py 更新）
6. scaffold overview.md（test_scaffold 计数 6→7 文件）
7. 回归 + e2e（/tmp/weft-inspire-real 的 sec-03 真实 draft）

精确计数完成后回填。

## 实测结果回填

- 全量 256 passed, 1 deselected（重写口径：旧 draft/spec/clients/rules 测试整体替换，inspire 全部保留）。
- e2e：/tmp/weft-inspire-real sec-03 真实 LLM 三节点连跑（结果见提交说明）。
- D6（执行期新增）：g 与 l/p 均为纯文本输出，工作文本以 <<<PARAGRAPH…>>> 定界符在链上直传——JSON 包裹会让 mock 与模型都要二次解析，纯文本直传更稳。
