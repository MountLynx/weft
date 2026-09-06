# weft WebUI 部署指南

设计定案：`docs/superpowers/specs/2026-09-06-weft-webui-design.md`；
实施计划（含执行期设计决策 D1–D20）：`docs/superpowers/plans/2026-09-06-weft-webui.md`。

## 安装与启动

```bash
pip install "weft[web]"
weft serve /srv/weft-projects --host 0.0.0.0 --port 8000
```

- `<projects_root>` 下的一级子目录中，凡含 `metadata/` 的即识别为 weft 论文项目，
  首页列出可选；演示前用 `weft init` 或拷贝 `examples/paper-demo` 准备多个示例项目
  （拷贝后删除 `drafts/`、`generated/` 产物可从零演示）。
- 浏览器打开 `http://<server>:8000`。

## LLM 配置

生成走 `weft.engine.make_client`：真实模式读取 config.json / .env / 环境变量
（SpecModule 回退链，`project_root` 取被打开的论文项目根）——服务器上在项目根或
进程环境配置 key。无 key 时勾选页面上的 **mock 模式**，用内置假客户端完整演示
全流程（生成内容为占位文本，但闸门/落盘/SSE 动线与真实一致）。

## 使用动线（演示建议）

1. 项目总览 → 待审阅队列逐项审阅（卡片 ✅/❌、叙事节点快捷审阅）；
2. 卡片页可编辑/新建（id 自动分配，claim_type 变更自动迁移目录）；
3. 叙事工作台按 part 页签：审阅完哪个 part 就勾选 mock 或真实模式生成哪个 part，
   SSE 实时日志可见，完成后草稿预览自动刷新；
4. 元数据图谱一键生成（非 LLM 秒级）；灵感页粘贴文本段 → mock/真实处理 → 提案应用。

## 安全提示

- 单人演示场景，未做认证：仅限内网/演示网络使用，勿暴露公网。
- 卡片/叙事编辑直接写盘（pydantic 校验 + LF 归一），建议项目置于 git 管理下以便回溯。
- 生成运行中强杀服务进程会中断该次 run（daemon 线程）；drafts 落盘为单次写入，
  截断风险可忽略，但演示中请正常等待 run_finished。
