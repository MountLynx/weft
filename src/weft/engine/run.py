"""engine 运行层：一次章节生成 = 一个 SpecModule run（spec §6）。

零残留嵌入（决策 3）：persist/status_file/keep_records/stream_log 全关，
SpecModule 不落盘；产物由 weft.engine.drafts 白名单写入 drafts/。
失败语义（决策 10）：V 脚本抛 DraftRuleError → run() 上抛 → CLI exit 1。
"""
import asyncio
import uuid
from dataclasses import dataclass, field, replace

from module_harness import (
    ALIGN_CHECK_CONFIG,
    EventBus,
    HarnessConfig,
    HarnessRegistry,
    Module,
    OutputFormat,
    register_align_check_harness,
)

from weft.engine.draft_rules import (
    DraftError,
    DraftRuleError,
    _diag,
    check_node_draft,
    parse_node_draft,
)
from weft.engine.spec_build import build_spec, build_tasklist
from weft.models.narrative import NarrativePart
from weft.store.project import Project
from weft.workflow import WORKFLOW_SPECS


@dataclass
class DraftResult:
    part_id: str
    run_id: str
    drafts_by_node: dict[str, dict] = field(default_factory=dict)
    reminders: list[str] = field(default_factory=list)


def _make_validate_script(part: NarrativePart, tick_by_node: dict[str, str],
                          project: Project, workflow: str):
    """V 脚本：逐段形状校验 + 规则闸门；硬规则抛 DraftRuleError（拒绝生成）。"""

    def validate_draft(view):
        reminders: list[str] = []
        for tick, node_id in tick_by_node.items():
            try:
                raw = view[tick].value
            except (KeyError, AttributeError, TypeError) as exc:
                raise DraftRuleError(
                    _diag("E-DRAFT-SHAPE", node_id, part.id, "output",
                          f"节点输出不可读：{exc}")) from exc
            draft, shape = parse_node_draft(raw, node_id, part.id)
            if shape is not None:
                raise DraftRuleError(shape)
            node = next(n for n in part.nodes if n.id == node_id)
            for diag in check_node_draft(draft, node, project, part.id, workflow):
                if diag.is_error:
                    raise DraftRuleError(diag)
                reminders.append(
                    f"{diag.code} {diag.path} 字段 {diag.field}: {diag.message}")
        return {"reminders": reminders}

    return validate_draft


def _register_harnesses(reg, workflow_spec: dict, align: bool) -> None:
    """注册 draft/align harness；api_params 抬高输出上限。

    SpecModule 硬编码默认 max_tokens=4096 且 config.json 不可达；推理型模型
    思考 token 即可耗尽 4096、content 为空（finish=length，e2e 实测——inspire
    管线同因同修，见 2026-09-04-weft-inspire.md 计划 D13）。
    """
    reg.harness("draft_para", HarnessConfig(
        prompt_core=workflow_spec["prompt_core"],
        output_format=OutputFormat(type="json_object"),
        notdo=["不要输出 JSON 以外的任何文本", "不得使用 Markdown 标题或列表"],
        temperature=workflow_spec["temperature"],
        api_params={"max_tokens": 32768},
    ))
    if align:
        register_align_check_harness(reg)
        # 内置 align 配置原样保留，仅叠加 api_params（同名注册即覆盖）
        reg.harness("align_check", replace(
            ALIGN_CHECK_CONFIG, api_params={"max_tokens": 32768}))


def run_draft(project: Project, part: NarrativePart, *, client,
              align: bool = True, workflow: str = "results") -> DraftResult:
    """同步入口；内部自持事件循环（weft CLI 无既有 loop）。

    workflow 由调用方（CLI resolve_workflow）解析；prompt_core/温度/引文规则
    裁剪均按 WORKFLOW_SPECS 路由（v1.1 §4.3）。
    """
    spec = build_spec(project, part, workflow)
    if not spec["nodes"]:
        raise DraftError(f"[E-NOTHING-TO-DRAFT] part {part.id} 无 approved 节点")
    run_id = uuid.uuid4().hex[:8]
    tick_by_node = spec["task_nodes"]
    workflow_spec = WORKFLOW_SPECS[workflow]

    bus = EventBus()
    reg = HarnessRegistry(llm_client=client, event_bus=bus)
    _register_harnesses(reg, workflow_spec, align)
    reg.script("weft_validate_draft")(
        _make_validate_script(part, tick_by_node, project, workflow))

    module = Module(
        spec=spec,
        tasklist=build_tasklist(spec, align=align),
        llm_client=client,
        event_bus=bus,
        registry=reg,
        module_id=f"weft-draft-{part.id}-{run_id}",
        review_harness=None,      # M2 决策 2：tasklist 是代码构造的，跳过一致性审核
        keep_records=False,       # M2 决策 3：零残留
        persist=False,
        status_file=False,
        stream_log=False,
    )
    try:
        # 显式 max_ticks 上限（M2 决策 14d）：链式 flow 实际需 N+2 tick，留足余量
        firings = asyncio.run(module.run(max_ticks=len(tick_by_node) + 10))
    except DraftRuleError:
        raise
    except Exception as exc:
        raise DraftError(f"[E-DRAFT-FAILED] SpecModule run 失败：{exc}") from exc

    result = DraftResult(part_id=part.id, run_id=run_id)
    for firing in firings:
        # tickflow 语义（M2 决策 14c）：harness 失败不流向后继，失败只能在
        # firings 里事后识别——fail-closed。
        if firing.status == "failed":
            node_id = tick_by_node.get(firing.node, firing.node)
            raise DraftRuleError(
                _diag("E-DRAFT-SHAPE", node_id, part.id, "output",
                      f"节点输出不可读：{firing.error or 'harness 失败'}"))
        if firing.status == "aborted":
            raise DraftError(
                f"[E-DRAFT-FAILED] 节点 {firing.node} 基础设施失败：{firing.error}")
        if firing.node in tick_by_node and isinstance(firing.output, dict):
            result.drafts_by_node[tick_by_node[firing.node]] = firing.output
        elif firing.node == "AL" and isinstance(firing.output, dict):
            # aligned 缺失/非布尔一律视为未通过（fail-closed）
            if firing.output.get("aligned") is not True:
                raise DraftError(
                    f"[E-DRAFT-FAILED] 对齐检查未通过：{firing.output.get('suggestions', '')}")
        elif firing.node == "V" and isinstance(firing.output, dict):
            result.reminders = list(firing.output.get("reminders", []))
    return result
