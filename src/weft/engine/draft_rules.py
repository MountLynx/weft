"""生成时校验（v2）：输出形状解析 + 占位符确定性填充（落盘前最后一道闸门）。

管线 LLM 不再直接写 [@key]：g 产占位符 {{fact-xx}}（图表落点）/{{claim-xx}}
（文献落点，仅 cited claim），f 脚本确定性填充：
- fact → data.refs → figures.yaml 键序字面编号（Fig. 1a / Table 1，与 assemble 一致）
- claim → 其 YAML cites → [@key]
宁可不做不可做错：越界占位符、残余占位符、不在 bib 的 key 一律 DraftRuleError。
DraftError 与 DraftRuleError 集中在此定义，clients/run 复用（避免循环依赖）。
纯函数、不 import specmodule。
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from weft.diagnostics import Diagnostic, Level
from weft.models.narrative import Node
from weft.store.project import Project


class DraftError(RuntimeError):
    """生成层失败（配置缺失 / run 失败 / 校验未过）；消息面向 CLI 直接输出。"""


class DraftRuleError(RuntimeError):
    """硬规则违规：携带诊断，run 层不捕获、CLI 直接打印并退出码 1。"""

    def __init__(self, diagnostic: Diagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(
            f"[{diagnostic.code}] {diagnostic.path} 字段 {diagnostic.field}: "
            f"{diagnostic.message}")


_PLACEHOLDER = re.compile(r"\{\{(fact|claim)-[A-Za-z0-9_-]+\}\}")
_CITEKEY = re.compile(r"@([A-Za-z0-9_-]+)")


class GenOutput(BaseModel):
    """g（draft_gen）输出：带占位符的段落。"""

    model_config = ConfigDict(extra="forbid")
    paragraph: str


class CheckOutput(BaseModel):
    """c1/c2（draft_check）输出：pass 仅通过；fix 用修正文本覆盖工作文本。"""

    model_config = ConfigDict(extra="forbid")
    verdict: Literal["pass", "fix"]
    paragraph: str = ""

    @model_validator(mode="after")
    def _fix_needs_paragraph(self) -> "CheckOutput":
        if self.verdict == "fix" and not self.paragraph.strip():
            raise ValueError("verdict=fix 必须给出修正后的 paragraph")
        return self


def _diag(code: str, node_id: str, part_id: str, field: str | None, message: str):
    return Diagnostic(Level.ERROR, code, f"drafts/{part_id}.md",
                      f"{node_id}.{field}" if field else None, message)


def parse_output(raw, model, node_id: str, part_id: str):
    """LLM 输出 dict → pydantic 模型；不可读返回 (None, E-DRAFT-SHAPE 诊断)。"""
    try:
        if not isinstance(raw, dict):
            raise ValueError("输出不是 JSON 对象")
        return model.model_validate(raw), None
    except (ValidationError, ValueError) as exc:
        msg = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
        return None, _diag("E-DRAFT-SHAPE", node_id, part_id, "output",
                           f"节点输出不可读：{msg}")


def _label_to_text(label: str, project: Project) -> str:
    """Quarto label → 字面编号文本；Fig/Table 分开计数（与 assemble/paper.py 一致）。"""
    figs = [k for k in project.figures if k.startswith("fig")]
    tbls = [k for k in project.figures if k.startswith("tbl")]
    for keys, kind in ((figs, "Fig."), (tbls, "Table")):
        for i, key in enumerate(keys):
            if label.startswith(key):
                return f"{kind} {i + 1}{label[len(key):]}"
    return label


def fill_placeholders(text: str, node: Node, part_id: str,
                      project: Project) -> tuple[str, list[str]]:
    """占位符确定性替换为图表字面编号 / [@cites]；返回 (文本, 软提醒)。"""
    reminders: list[str] = []
    used = {u.id for u in node.uses}
    for m in _PLACEHOLDER.finditer(text):
        target = m.group(0)[2:-2]
        if target not in used:
            raise DraftRuleError(_diag(
                "E-DRAFT-USES", node.id, part_id, "paragraph",
                f"占位符 {m.group(0)} 越界：不属于本节点 uses"))

    def _sub(m: re.Match) -> str:
        target = m.group(0)[2:-2]
        if target.startswith("fact-"):
            fact = project.facts.get(target)
            labels = [ref for d in (fact.data if fact else [])
                      for ref in (project.data_cards[d].refs
                                  if d in project.data_cards else [])]
            if not labels:
                reminders.append(
                    f"W-REF-EMPTY {target} 未关联到任何图表 ref，占位符已移除")
                return ""
            return "；".join(_label_to_text(x, project) for x in labels)
        claim = project.claims.get(target)
        cites = list(claim.cites) if claim else []
        if not cites:
            reminders.append(
                f"W-CITES-EMPTY {target} 分类 cited 但 cites 为空，占位符已移除（缺文献）")
            return ""
        return "（" + "；".join(f"[@{k}]" for k in cites) + "）"

    text = _PLACEHOLDER.sub(_sub, text)
    # 模型常自己给占位符包中文括号，填充后再加一层 → 塌缩去重（e2e 实测）
    # 模型常自己包中文括号，填充后再加一层：直接塌缩（学术文本无合法双括号）
    text = text.replace("（（", "（").replace("））", "）")
    leftover = _PLACEHOLDER.search(text)
    if leftover:
        raise DraftRuleError(_diag("E-DRAFT-SHAPE", node.id, part_id, "paragraph",
                                   f"存在未解析的占位符：{leftover.group(0)}"))
    for key in _CITEKEY.findall(text):
        if key not in project.bib_keys:
            raise DraftRuleError(_diag(
                "E-CITE-NOT-IN-BIB", node.id, part_id, "paragraph",
                f"citekey {key} 不在项目 bib"))
    return text, reminders
