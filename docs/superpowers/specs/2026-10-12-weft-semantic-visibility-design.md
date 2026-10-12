# weft 语义可见性设计定案（编号 → 内容/语义的展示层翻译）

- 日期：2026-10-12
- 状态：定案（用户已确认方向 A：展示层补语义 + 语义命名约定；schema 不动）
- 关联：weft new 模板设计（N4 语义命名优先）、v1 设计 §3（冻结）、红线 2/5

## 1. 背景与问题

weft 的引用与链接以实体 id 为锚：卡片 `data-01`/`fact-01`、part `sec-03`、节点
`para-03-01`。语义内容其实早已存在（data.description、fact/claim/method.statement、
note.summary、节点 logic），且 LLM 生成侧已携带全文（`engine/spec_build.py` 传 uses
实体全文 + logic）——缺口全部在**人**的接触面上：

1. `weft review` 只输出 `类型 + id + 路径`，审阅者看到编号不知道内容；
2. `graph.json` 实体只有 kind/status/referenced_by，`orphans.md` 只有 id + 路径，
   顺着 `fact.data → data → claim` 引用链追内容没有语义锚；
3. WebUI 卡片表单的引用字段（data/supports/cites/derived_from）是裸 id 复选框，
   part 工作台 uses 单元格是裸 id 列表，节点编辑的实体 datalist 也是裸 id；
4. WebUI 新建 data/fact/claim 卡时 id 输入框 `readonly` 锁死自动编号，与 CLI
   `weft new card` 的 N4 决策（"语义性命名不该被序号替代"）不一致——想用语义 id
   只能走 CLI 或手写文件。

## 2. 目标 / 非目标

**目标**：在不动数据结构（红线 2）的前提下，让所有"人看编号"的地方都能就近看到
语义摘要；WebUI 与 CLI 的语义 id 能力对齐。

**非目标（YAGNI）**：
- 不改卡片 schema、不改诊断码格式与码表（无新增 E-*/W-*）；
- 不做 rename 工具、不迁移存量编号 id（examples/paper-demo 的 data-01 等保持原样）；
- 不做 WebUI 新建 part 入口（维持 weft new 设计 N2 的后续任务）；
- 不动 inspire/parse 管线的 LLM digest（`digest.py` 职责不同，不复用不合并）。

## 3. 设计

### 3.1 语义标签单一来源 `src/weft/labels.py`（新增，纯函数）

```
KEY_FIELD = {"data": "description", "fact": "statement", "claim": "statement",
             "note": "summary", "method": "statement", "param": "method"}
cap(text, limit) -> str            # 超长截断加 "…"（沿用 digest.py 的 _cap 惯例）
entity_digest(project, eid, limit=40) -> str   # 实体的 KEY_FIELD 值；缺失/为空 → ""
label_map(project, ids) -> dict[str, str]      # 批量 id → digest（供模板一次注入）
```

- `KEY_FIELD` 从 `web/routes/cards.py` 的 `_KEY_FIELD` 收编（D1），列表页行为不变；
- 映射沿用 WebUI 既有约定（D2）：param 的 key 字段是 `method`（引用 id）——与卡片
  列表页一致；param 本就 slug 命名，不另造约定；
- 展示截断上限 40 字符（终端/表格行宽友好，D3）；graph.json 存全文不截断（机器消费）。

### 3.2 `weft review` 输出附摘要列

- 卡片行：`  {label}  {id}  {relpath}  ｜ {digest}`（digest 为空则连同分隔符省略）；
- 节点行：`  {part.id}/{node.id}  {relpath}  ｜ {logic 摘要}`（同规则）。

### 3.3 graph 产物带语义

- `graph.json` 每个实体新增 `"summary"` 键：KEY_FIELD 全文（缺失为 `""`）；
  `"version"` 保持 2——纯附加可选字段，向后兼容（D5）；黄金文件随之再生成；
- `orphans.md` 行尾追加摘要：`- {eid}（{kind}）— {path}：{digest}`（空则止于 path，D6）。

### 3.4 新命令 `weft show <card_id>`

- 打印实体速览：头行 `# {id}（{kind} 卡，{status}）— {relpath}`，其后逐字段
  `名: 值`（列表逗号连接、映射 JSON、全文不截断），末尾打印反向引用
  `被引用: referenced_by 摘要`（来自 `graphgen.build_index`，帮助从编号反查关系）；
- 未知 id：`ERROR 项目中不存在实体：{id}`，退出码 1——沿用 `weft graph` OSError 的
  无码 ERROR 行先例，**不新增诊断码**（D7）；
- 只查卡片（六类）；节点语义经 review/工作台已可见，不扩（YAGNI）。

### 3.5 WebUI 四处

1. **解锁新建卡 id**（D8）：`card_form.html` 的 auto 分支去掉 `readonly`
   （保留 `next_card_id` 预填作缺省）；服务端守卫原样生效
   （`_CARD_ID_RE` 格式 + `..` 拒绝 + `create_card` 碰撞 FileExistsError），零新增逻辑；
2. **引用控件带摘要**（D9）：`build_choices` 增加返回标签映射
   `{choices_key: {id: digest}}`，`card_form.html` multiselect 复选框文案渲染为
   `id · digest`（checkbox `value` 仍为裸 id，提交语义不变）；note 的 bibkey 下拉、
   param 的 method 下拉同法（摘要来自 note.summary / method.statement）；
3. **part 工作台 uses 摘要**：`_panel_ctx` 注入 use 标签映射，uses 单元格渲染
   `id(role) · digest`；
4. **节点编辑实体速查**：`entity_ids` datalist 保持裸 id（浏览器对 option label
   支持不一），表单下方新增"实体速查"清单块：每行 `id · digest`，纯静态 HTML。

## 4. 决策表

| # | 决策 | 理由 |
|---|------|------|
| D1 | 摘要/key 字段单一来源 `labels.py`；web `_KEY_FIELD` 收编 | CLI/graph/web 三方共用，防漂移 |
| D2 | KEY_FIELD 沿用 WebUI 既有映射（param→method） | 与列表页一致，不发明第二套约定 |
| D3 | 展示截断 40 字符；graph.json 存全文 | 行宽友好 vs 机器消费 |
| D4 | review 摘要列用 `｜` 分隔、空摘要省略整段 | 行保持紧凑、输出确定 |
| D5 | graph.json 加 `summary` 键、version 保持 2 | 派生产物非冻结 schema；附加字段向后兼容 |
| D6 | orphans.md 行尾 `：{digest}` | 与 graph.json 同源（labels.py） |
| D7 | `weft show` 无新诊断码，ERROR 行 + exit 1 | 沿用 graph OSError 先例；红线 5 码表不动 |
| D8 | WebUI auto 卡 id 去 readonly、保留预填 | 与 CLI N4 对齐；服务端守卫已完备 |
| D9 | 摘要以标签映射注入模板；checkbox value 不变 | 展示与提交语义分离，表单解析零改动 |
| D10 | 命名约定写入 manual（新卡优先语义 id，编号作缺省回退）；不做 rename | 工具支持已就绪，约定零成本；rename 违 YAGNI |

## 5. 兼容性与风险

- **黄金文件**：`tests/golden/graph.json` 因新增 summary 键需再生成——派生产物的
  预期演进，计划中显式登记；`used-metadata.json`、`paper.qmd` 不受影响；
- **既有测试**：review 输出格式变更会触及 `test_cli.py` 相关断言（更新期望）；
  WebUI 列表页、表单解析行为不变；
- **守卫**：无 CSS 改动（主题令牌守卫不涉及）；引擎分层、路径白名单、schema 冻结
  均不触及；
- **性能**：label_map 为内存字典组装，量级 = 卡片数，无 IO 放大。

## 6. 验收

1. `weft review` 每个待审实体行可读到语义摘要；节点行可读到 logic 摘要；
2. `weft graph` 产物中任一实体可不经开文件获知其内容；孤儿报告同样；
3. `weft show fact-01` 一屏看清卡片内容与被引关系；未知 id 报错退出 1；
4. WebUI 新建 fact 卡可自定语义 id 并成功落盘 `metadata/facts/<语义id>.md`；
5. WebUI 表单复选框、uses 单元格、节点速查均显示 `id · 摘要`；
6. 全量测试绿（精确计数见实施计划）。
