# weft WebUI 部署指南

设计定案：`docs/superpowers/specs/2026-09-06-weft-webui-design.md`；
实施计划（含执行期设计决策 D1–D20）：`docs/superpowers/plans/2026-09-06-weft-webui.md`。

## 安装与启动

```bash
pip install "weft[web]"
weft serve --host 0.0.0.0 --port 8000                      # 注册表模式（推荐）：一个主程序托管多项目
weft serve /srv/weft-projects --host 0.0.0.0 --port 8000   # 扫描模式：现状行为不变
```

- **注册表模式**（`weft serve` 无参数）：项目清单来自全局注册表 `~/.weft/projects.json`
  （`WEFT_HOME` 环境变量可重定向），项目可位于磁盘任意位置。设计定案
  `docs/superpowers/specs/2026-09-29-weft-projects-registry-design.md`。配套 CLI：
  `weft projects add <路径>` 登记现有项目、`weft projects new <名称>` 新建并登记
  （位置回退 `--root` > 注册表默认根 > `~/weft-projects`）、
  `weft projects remove <名称>`（只摘表，绝不删本地文件）、`weft projects list`、
  `weft projects root <目录>`（设默认根）。首页新建表单：位置留空落默认根
  （未配置则提示先执行 `weft projects root`），填写父目录则在其中创建；
  失联项目灰显不可点入，注册表损坏显示错误横幅（fail-closed，`E-REG-MALFORMED`）。
- **扫描模式**（给 `<projects_root>`）：一级子目录中凡含 `metadata/` 的即识别为
  weft 论文项目，首页列出可选；不读写注册表。演示前用 `weft init` 或拷贝
  `examples/paper-demo` 准备多个示例项目（拷贝后删除 `drafts/`、`generated/`
  产物可从零演示）。
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
- `0.0.0.0` 部署注册表模式时，首页"位置"输入等同于"在任意可写目录创建骨架"的能力，建议置于反向代理/VPN 认证之后。
- 卡片/叙事编辑直接写盘（pydantic 校验 + LF 归一），建议项目置于 git 管理下以便回溯。
- 生成运行中强杀服务进程会中断该次 run（daemon 线程）；drafts 落盘为单次写入，
  截断风险可忽略，但演示中请正常等待 run_finished。
