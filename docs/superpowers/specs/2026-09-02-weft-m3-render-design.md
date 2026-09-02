# weft M3 渲染层设计（paper.qmd 拼接 + References/Figures + 投稿资源约定）

- 日期：2026-09-02
- 状态：定案；待实现
- 关系：细化 v1 §7（组装与渲染）并**作废其中"图表按 fact→data→refs 首次出现处插入正文"**；补充 v1.1 §4.4 的纸级组装形态。roadmap M3 相应改写。
- 背景：最终投稿形态为 Word（docx）。排版习惯是图不插正文、文末集中 Figures；参考文献由 Quarto citeproc 自动生成但默认无节标题；子图（Fig. 1a/1b）实际在同一张图片文件内。Quarto 的 crossref 子图语法在 docx 排版能力有限，故**图表链路整体不走 crossref**，编号以字面文本呈现。

## 1. 最终文档 paper.qmd（拼接）

- `weft assemble` 在 chapter 级 qmd（`generated/<chapter>.qmd`）之外，产出项目根 **`paper.qmd`**（文件名可经 weft.yaml 配置，默认 `paper.qmd`；不占用 `index.qmd`——标题/作者/摘要等前置信息不归 weft，留在 `_quarto.yml` 或人工文件中）。
- 拼接 = 各 chapter qmd 正文依目录序**原样并入**（chapter heading 已含 `#`/`##` 层级，方案 B：不用 `{{< include >}}`），之后追加 References 与 Figures 两节（见 §2/§3）。单文件、字节确定。
- 图片路径以项目根为基准（`figures/fig-01.png`），与 paper.qmd 位置一致。

## 2. References 节

```markdown
# References {.unnumbered}

::: {#refs}
:::
```

- `::: {#refs} :::` 是 citeproc 的官方文献定位 div（Pandoc 行为：文档中存在该 div 时，参考文献列表插入此处；否则插到文档末尾且无标题）。渲染时空 div 被替换为文献列表；条目完全由 Quarto 依正文 `[@key]` + `_quarto.yml` 的 `bibliography` 生成，**weft 不生成任何条目，只标记位置**。
- `# References {.unnumbered}` 由 weft 写死在组装产物里（`.unnumbered` 防止进入章节编号）。**`_quarto.yml` 不得再设 `reference-section-title`**——该选项同样会给文献节加标题，两边都写会重复。
- 该节只出现在 paper.qmd；chapter 级 qmd 不带。

## 3. Figures 节

```markdown
# Figures {.unnumbered}

![](figures/fig-01.png)

**Fig. 1** 不同温度下的反应速率。误差线表示三个重复的标准差。
```

- 由 `figures.yaml` 确定性生成（纯脚本，无 LLM）：一图一段，`![](figures/<key>.png)` + `**Fig. N** <caption>`；**N = figures.yaml 键序**，前缀固定 `Fig.`（表格键 `tbl-xx` 同构进 `# Tables {.unnumbered}`，前缀 `Table`）。
- **不走 crossref**：图片不带 `{#fig-xx}` label、图注不进 crossref 编号体系——weft 是图编号的唯一权威（figures.yaml 顺序即编号），docx 下所见即所得。
- **子图不做 Quarto 子图语法**（docx 排版受限；实际子图在同一图片文件内）。正文对子图的引用为**纯文本**（如 `Fig. 1a`），由人直接写在草稿/叙事 logic 中，weft 不校验、不展开（方案 B）。生成时引文规则不受影响（规则 1 只扫 `[@key]` 引文形状）。
- 原 v1 §7"图表按首次出现处插入"作废；`_quarto.yml` 的 crossref 图表前缀配置保留无害，但不再被图链路消费。

## 4. 投稿资源约定（assets/）

```text
project/
├── assets/
│   ├── references.bib    # 书目（唯一事实源）
│   ├── style.csl         # 引文格式（如 elsevier-with-titles.csl）
│   └── template.docx     # Word 参考样式（Quarto reference-doc）
```

`_quarto.yml` 固定写法（M4 `weft init` 模板照此自动生成）：

```yaml
project:
  type: default
bibliography: assets/references.bib
csl: assets/style.csl
format:
  docx:
    reference-doc: assets/template.docx
```

- weft loader 不受影响：bibliography 路径仍从 `_quarto.yml` 读取，任意路径合法；存量项目 `references.bib` 在项目根继续合法。
- `examples/paper-demo` 随 M3 实现迁移到该约定（bib 移入 assets/，补 style.csl 与 template.docx）。

## 5. 实现范围与验收（M3）

- assemble 扩展：paper.qmd 拼接 + References/Figures 节生成（纯脚本，无 LLM；输出固定 LF）。
- `render.py` + CLI `weft render`：quarto 子进程封装，docx 为默认目标格式。
- 校验：无新增（图引用为纯文本，不校验；figures.yaml 既有校验不变）。
- 验收：样例项目 `weft assemble` 产出 paper.qmd 含正文 + References + Figures 三部分且字节确定（黄金比对）；`quarto render` 出 docx（人工冒烟）。
- M3 动工先做一次渲染冒烟，钉死三个 Quarto 行为：refs div 替换、`.unnumbered` 在编号配置下的表现、docx 对 `::: div` 的处理。

## 6. 明确不做

- 图表正文内插入；crossref 图表编号（label/crossref 链路整体不用）。
- Quarto 子图语法；子图引用的标记与校验。
- `reference-section-title` 协调（weft 写死标题，文档约定即可）。
