"""engine 运行层：一次章节生成 = 一个 SpecModule run（spec §6）。

零残留嵌入（决策 3）：persist/status_file/keep_records/stream_log 全关，
SpecModule 不落盘；产物由 weft.engine.drafts 白名单写入 drafts/。
失败语义（决策 10）：V 脚本抛 DraftRuleError → run() 上抛 → CLI exit 1。
"""
import asyncio
import uuid
from dataclasses import dataclass, field

from module_harness import (
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

DRAFT_PARA_CORE = WORKFLOW_SPECS["results"]["prompt_core"]


@dataclass
class DraftResult:
    part_id: str
    run_id: str
    drafts_by_node: dict[str, dict] = field(default_factory=dict)
    reminders: list[str] = field(default_factory=list)


def _make_validate_script(part: NarrativePart, tick_by_node: dict[str, str],
                          project: Project):
    """V 脚本：逐段形状校验 + 三规则；硬规则抛 DraftRuleError（拒绝生成）。"""

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
            for diag in check_node_draft(draft, node, project, part.id):
                if diag.is_error:
                    raise DraftRuleError(diag)
                reminders.append(
                    f"{diag.code} {diag.path} 字段 {diag.field}: {diag.message}")
        return {"reminders": reminders}

    return validate_draft


def run_draft(project: Project, part: NarrativePart, *, client,
              align: bool = True) -> DraftResult:
    """同步入口；内部自持事件循环（weft CLI 无既有 loop）。"""
    spec = build_spec(project, part)
    if not spec["nodes"]:
        raise DraftError(f"[E-NOTHING-TO-DRAFT] part {part.id} 无 approved 节点")
    run_id = uuid.uuid4().hex[:8]
    tick_by_node = spec["task_nodes"]

    bus = EventBus()
    reg = HarnessRegistry(llm_client=client, event_bus=bus)
    reg.harness("draft_para", HarnessConfig(
        prompt_core=DRAFT_PARA_CORE,
        output_format=OutputFormat(type="json_object"),
        notdo=["不要输出 JSON 以外的任何文本", "不得使用 Markdown 标题或列表"],
        temperature=0.3,
    ))
    if align:
        register_align_check_harness(reg)
    reg.script("weft_validate_draft")(
        _make_validate_script(part, tick_by_node, project))

    module = Module(
        spec=spec,
        tasklist=build_tasklist(spec, align=align),
        llm_client=client,
        event_bus=bus,
        registry=reg,
        module_id=f"weft-draft-{part.id}-{run_id}",
        review_harness=None,      # 决策 2：tasklist 是代码构造的，跳过一致性审核
        keep_records=False,       # 决策 3：零残留
        persist=False,
        status_file=False,
        stream_log=False,
    )
    try:
        # 显式 max_ticks 上限：默认 100 会让 >99 节点的节静默耗尽 tick，
        # V/AL 不触发 = 校验被绕过；链式 flow 实际需 N+2 tick，留足余量。
        firings = asyncio.run(module.run(max_ticks=len(tick_by_node) + 10))
    except DraftRuleError:
        raise
    except Exception as exc:
        raise DraftError(f"[E-DRAFT-FAILED] SpecModule run 失败：{exc}") from exc

    result = DraftResult(part_id=part.id, run_id=run_id)
    for firing in firings:
        # tickflow 语义：llm Failure 的节点出边写 False，V 不再触发（AND-join
        # 缺 token）——失败只能在 firings 里事后识别，V 脚本的形状/规则闸门
        # 只覆盖"输出是合法 JSON 但形状/规则不过"的情形。
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
            # json_object 只保证是对象、不保证 schema：aligned 缺失/非布尔
            # 一律视为未通过（fail-closed），不得静默放行对齐闸门。
            if firing.output.get("aligned") is not True:
                raise DraftError(
                    f"[E-DRAFT-FAILED] 对齐检查未通过：{firing.output.get('suggestions', '')}")
        elif firing.node == "V" and isinstance(firing.output, dict):
            result.reminders = list(firing.output.get("reminders", []))
    return result
