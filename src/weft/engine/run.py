"""engine 运行层（draft v2）：一次段落生成 = 一个六节点 SpecModule run。

零残留嵌入（决策 3）：persist/status_file/keep_records/stream_log 全关，
SpecModule 不落盘；产物由 weft.engine.drafts 白名单写入 drafts/。
节点链：g 起草（占位符）→ c1 校验（fix 覆盖）→ l 衔接 → p 润色 →
c2 复检（复用 check harness）→ f 脚本占位符确定性填充（DraftRuleError 即拒绝）。
"""
import asyncio
import uuid
from dataclasses import dataclass, replace

from module_harness import (
    ALIGN_CHECK_CONFIG,
    EventBus,
    HarnessConfig,
    HarnessRegistry,
    Module,
    OutputFormat,
)

from weft.engine.draft_rules import (
    DraftError,
    DraftRuleError,
    _diag,
    fill_placeholders,
)
from weft.engine.spec_build import (
    build_node_spec,
    build_tasklist,
    effective_paragraph,
)
from weft.models.narrative import Node, NarrativePart
from weft.store.project import Project
from weft.workflow import WORKFLOW_SPECS

_MAX_TICKS = 10   # 5 LLM 节点 + f + 余量（M2 决策 14d）


@dataclass
class DraftResult:
    node_id: str
    run_id: str
    paragraph: str
    reminders: list[str]


def _register_harnesses(reg, workflow_spec: dict) -> None:
    """注册 g/c1-c2/l/p 四个 harness；api_params 抬高输出上限。

    SpecModule 硬编码默认 max_tokens=4096 且 config.json 不可达；推理型模型
    思考 token 即可耗尽 4096、content 为空（finish=length，e2e 实测——
    inspire 管线同因同修，见 2026-09-04-weft-inspire.md 计划 D13）。
    draft_gen 温度取 workflow 的 §4.3 章节梯度（methods 低 / discussion 高）。
    """
    reg.harness("draft_gen", HarnessConfig(
        prompt_core=workflow_spec["prompt_core"],
        output_format=OutputFormat(type="text"),
        notdo=["不要输出任何解释或前后缀", "不得使用 Markdown 标题或列表"],
        temperature=workflow_spec["temperature"],
        api_params={"max_tokens": 32768},
    ))
    reg.harness("draft_check", HarnessConfig(
        prompt_core="你是学术写作引擎的段落审查器，宁可 fix 不要放过事实偏移，只输出 JSON。",
        output_format=OutputFormat(type="json_object"),
        notdo=["不要输出 JSON 以外的任何文本"],
        temperature=0.2,
        api_params={"max_tokens": 32768},
    ))
    reg.harness("draft_link", HarnessConfig(
        prompt_core="你是学术写作引擎的段落衔接优化器，只输出纯文本段落。",
        output_format=OutputFormat(type="text"),
        notdo=["不要输出任何解释或前后缀"],
        temperature=0.4,
        api_params={"max_tokens": 32768},
    ))
    reg.harness("draft_polish", HarnessConfig(
        prompt_core="你是学术英语润色器，事实不偏移优先于文采，只输出纯文本段落。",
        output_format=OutputFormat(type="text"),
        notdo=["不要输出任何解释或前后缀"],
        temperature=0.4,
        api_params={"max_tokens": 32768},
    ))


def _make_fill_script(node: Node, part_id: str, project: Project):
    """f 脚本：覆盖链合成有效文本 → 占位符确定性填充（唯一落盘前置闸门）。"""

    def fill(view):
        out = {}
        for tick in ("g", "c1", "l", "p", "c2"):
            try:
                out[tick] = view.field(tick)
            except (KeyError, AttributeError, TypeError) as exc:
                raise DraftRuleError(_diag(
                    "E-DRAFT-SHAPE", node.id, part_id, "output",
                    f"节点输出不可读：{exc}")) from exc
        text, err = effective_paragraph(out)
        if err:
            raise DraftRuleError(_diag(
                "E-DRAFT-SHAPE", node.id, part_id, "output", err))
        paragraph, reminders = fill_placeholders(text, node, part_id, project)
        return {"paragraph": paragraph, "reminders": reminders}

    return fill


def run_draft(project: Project, part: NarrativePart, node: Node, *, client,
              workflow: str = "results", overview: str = "",
              prior_paragraphs: list[str] | None = None,
              prev_tail: str | None = None,
              next_head: str | None = None) -> DraftResult:
    """同步入口；一次只生成一个段落（节点）。内部自持事件循环。"""
    workflow_spec = WORKFLOW_SPECS[workflow]
    node_spec = build_node_spec(project, node)
    run_id = uuid.uuid4().hex[:8]
    context = {"prior": list(prior_paragraphs or []),
               "prev_tail": prev_tail, "next_head": next_head}
    tasklist = build_tasklist(project, node, node_spec, overview,
                              workflow_spec["prompt_core"], context)

    bus = EventBus()
    reg = HarnessRegistry(llm_client=client, event_bus=bus)
    _register_harnesses(reg, workflow_spec)
    reg.script("weft_fill_placeholders")(
        _make_fill_script(node, part.id, project))

    module = Module(
        spec={"task_nodes": {t: t for t in ("g", "c1", "l", "p", "c2")}},
        tasklist=tasklist,
        llm_client=client,
        event_bus=bus,
        registry=reg,
        module_id=f"weft-draft-{part.id}-{node.id}-{run_id}",
        review_harness=None,      # tasklist 代码构造，跳过一致性审核（M2 决策 2）
        keep_records=False,       # M2 决策 3：零残留
        persist=False,
        status_file=False,
        stream_log=False,
    )
    try:
        firings = asyncio.run(module.run(max_ticks=_MAX_TICKS))
    except DraftRuleError:
        raise
    except Exception as exc:
        raise DraftError(f"[E-DRAFT-FAILED] SpecModule run 失败：{exc}") from exc

    reminders: list[str] = []
    paragraph: str | None = None
    for firing in firings:
        if firing.status == "failed":
            raise DraftRuleError(_diag(
                "E-DRAFT-SHAPE", node.id, part.id, "output",
                f"节点输出不可读：{firing.error or 'harness 失败'}"))
        if firing.status == "aborted":
            raise DraftError(
                f"[E-DRAFT-FAILED] 节点 {firing.node} 基础设施失败：{firing.error}")
        if firing.node == "f" and isinstance(firing.output, dict):
            paragraph = firing.output.get("paragraph", "")
            reminders = list(firing.output.get("reminders", []))
    if paragraph is None:
        raise DraftError(f"[E-DRAFT-FAILED] 节点 {node.id} 未产出段落（f 未完成）")
    return DraftResult(node_id=node.id, run_id=run_id, paragraph=paragraph,
                       reminders=reminders)
