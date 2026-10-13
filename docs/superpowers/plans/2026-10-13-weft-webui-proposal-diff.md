# WebUI 替换提案对比查看 — 实施计划

设计：`docs/superpowers/specs/2026-10-13-weft-webui-proposal-diff-design.md`（决策 C1–C6）
分支：`webui-proposal-diff`（worktree `.worktrees/webui-proposal-diff`，合回 main 后删除）
基线计数：805 passed, 2 deselected → 目标 **812 passed, 2 deselected**

## 任务分解（TDD）

- **T1 测试先行（红）**：`tests/test_web_inspire.py` 新增 7 项（设计 §7 清单），
  跑 `pytest tests/test_web_inspire.py` 确认 7 红（404/链接项外全失败或断言失败）。
- **T2 对比路由（绿）**：`web/routes/inspire.py` 增 `GET .../proposals/{card_id}`：
  404 分支、五类容错分支（设计 §4 表）、字段对照行构造（`_fmt_field` 列表「、」
  连接 / entry yaml）、`difflib.unified_diff` 行分类
  （add/del/hunk/meta/ctx）。模板 `proposal_compare.html`（banner、对照表、
  diff pre、apply 表单、返回链接）。
- **T3 样式**：`webui.css` 末尾追加 `.compare td.changed`、`.diff` 容器、
  `.diff-add/.diff-del/.diff-hunk/.diff-meta`、`.proposal-raw`（全令牌）。
- **T4 灵感页链接**：`inspire.html` 提案行加「对比」链接；
  `test_inspire_page_links_compare` 转绿。
- **T5 全量与回填**：全量 pytest（812）→ 文档计数回填 → 中文 conventional
  commit（feat: WebUI 替换提案对比页…）→ 合回 main、删 worktree/分支。

## 设计决策（执行期回填）

| # | 偏离/定案 | 说明 |
|---|---|---|
| P1 | T1 红态为 6 红非 7 | `missing_proposal` 在路由不存在时本就 404（天然守卫项），其余 6 项先红后绿 |
| P2 | 实测计数 812 passed, 2 deselected | 与计划一致（基线 805 + 7）；`tests/test_web_inspire.py` 10 passed |
| P3 | diff 行 `<span class="diff-*">` + `min-width:100%` | pre-wrap 长行折行时保持整行着色，无需表格化 diff |
