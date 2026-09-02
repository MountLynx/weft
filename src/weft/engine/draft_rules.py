"""生成时校验三规则（spec §4 生成时行）+ harness 输出形状解析 + 生成层错误类型。

规则 1 为正文级（§4「草稿中」语义）：段落 [@key]（含 [@a; @b] 多引文形式）与
结构化 cites 双通道合并校验 bib 归属；裸 @id 交叉引用（无方括号）不在规则内。
workflow=methods 裁剪引文规则 1/2（v1.1 §4.3）：方法章不写文献引注。
纯函数、不 import specmodule：从 harness JSON dict 到诊断的映射可独立单测。
硬规则违规由 V 脚本转成 DraftRuleError 上抛（拒绝生成）；软提醒收集带回。
DraftError 与 DraftRuleError 集中在此定义，clients/run 复用（避免循环依赖）。
"""
import re

from weft.diagnostics import Diagnostic, Level
from weft.models.narrative import Node
from weft.store.project import Project


class DraftError(RuntimeError):
    """生成层失败（配置缺失 / run 失败 / 对齐未过）；消息面向 CLI 直接输出。"""


class DraftRuleError(RuntimeError):
    """硬规则违规：携带诊断，run 层不捕获、CLI 直接打印并退出码 1。"""

    def __init__(self, diagnostic: Diagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(
            f"[{diagnostic.code}] {diagnostic.path} 字段 {diagnostic.field}: "
            f"{diagnostic.message}")


def _diag(code: str, node_id: str, part_id: str, field: str, message: str,
          level: Level = Level.ERROR) -> Diagnostic:
    return Diagnostic(level, code, f"drafts/{part_id}.md",
                      f"{node_id}.{field}", message)


def parse_node_draft(value: object, node_id: str,
                     part_id: str) -> tuple[dict | None, Diagnostic | None]:
    """harness JSON 输出形状校验：paragraph 非空 str，uses/cites 是 list[str]。"""
    if not isinstance(value, dict):
        return None, _diag("E-DRAFT-SHAPE", node_id, part_id, "output",
                           "输出不是 JSON 对象")
    paragraph = value.get("paragraph")
    if not isinstance(paragraph, str) or not paragraph.strip():
        return None, _diag("E-DRAFT-SHAPE", node_id, part_id, "output",
                           "paragraph 缺失或为空白")
    for key in ("uses", "cites"):
        v = value.get(key, [])
        if not isinstance(v, list) or any(not isinstance(x, str) for x in v):
            return None, _diag("E-DRAFT-SHAPE", node_id, part_id, "output",
                               f"{key} 不是字符串列表")
    return value, None


def check_node_draft(draft: dict, node: Node, project: Project,
                     part_id: str, workflow: str = "results") -> list[Diagnostic]:
    """规则 1/2/3 + 参数存在性（§4.3：methods 裁剪引文规则、保留 uses 越界）。

    返回诊断列表；硬规则（ERROR）由调用方 raise DraftRuleError。
    """
    diags: list[Diagnostic] = []
    uses = [u.id for u in node.uses]
    # 规则 3（硬，全工作流）：草稿标注引用的实体 id ⊆ 节点 uses
    # get 缺省空表：形状校验放行过的缺键草稿（仅 paragraph）不应 KeyError
    for eid in draft.get("uses", []):
        if eid not in uses:
            diags.append(_diag("E-USES-BEYOND-NODE", node.id, part_id, "uses",
                               f"草稿标注实体 {eid} 不在本节点 uses"
                               f"（{', '.join(uses) or '空'}）"))
    # 参数存在性（硬，全工作流；§4.3 校验裁剪保留项）
    for uid in uses:
        param = project.params.get(uid)
        if param is not None and not param.values:
            diags.append(_diag("E-PARAM-NO-VALUES", node.id, part_id, "uses",
                               f"使用的 param 卡 {uid} 没有任何 values"))
    if workflow == "methods":
        # §4.3：methods 裁剪引文规则 1/2（方法章不写文献引注）
        return diags
    # 本节点所用 claim 的 cites 并集（规则 2 的允许集）
    claim_cites: set[str] = set()
    for uid in uses:
        claim = project.claims.get(uid)
        if claim is not None:
            claim_cites.update(claim.cites)
    # 规则 1/2 的 cite 全集（§4「草稿中」语义）：正文 [@key] 优先、结构化 cites 补充，
    # 去重保序（run 层对首条 ERROR 上抛，顺序必须确定，不能依赖 set 迭代）。
    # 多引文形式 [@a; @b] 按分号拆分并去 @ 前缀；裸 @id 交叉引用（无方括号）不匹配。
    cite_fields: list[tuple[str, str]] = []
    seen: set[str] = set()
    for group in re.findall(r"\[@([^\]]+)\]", draft.get("paragraph", "")):
        for part_key in group.split(";"):
            key = part_key.strip().lstrip("@")
            if key and key not in seen:
                seen.add(key)
                cite_fields.append((key, "paragraph"))
    for key in draft.get("cites", []):
        if key not in seen:
            seen.add(key)
            cite_fields.append((key, "cites"))
    for key, field in cite_fields:
        # 规则 1（硬）：草稿（正文+结构化）中的 [@key] 必须在 bib 内
        if key not in project.bib_keys:
            diags.append(_diag("E-CITE-NOT-IN-BIB", node.id, part_id, field,
                               f"citekey {key} 不在项目 bib"))
        # 规则 2（软）：[@key] 应属于本段所用 claim 的 cites
        elif key not in claim_cites:
            diags.append(_diag("W-CITE-NOT-IN-CLAIM", node.id, part_id, field,
                               f"citekey {key} 不属于本节点所用 claim 的 cites",
                               level=Level.WARNING))
    return diags
