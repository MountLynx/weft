"""inspire 管线运行层：T1–T4 一次 SpecModule run（inspire 设计 §4）。

零残留嵌入同 M2 决策 3；A1 聚合在 run 层之外（apply.py，计划 D1）。
失败语义同 M2 决策 14c：harness 失败不流向后继，firings 事后扫描 fail-closed
（failed → E-INSPIRE-SHAPE，aborted / 缺输出 → E-INSPIRE-FAILED）。
"""
import asyncio
import uuid
from dataclasses import dataclass

from module_harness import (
    EventBus,
    HarnessConfig,
    HarnessRegistry,
    Module,
    OutputFormat,
)
from pydantic import ValidationError

from weft.digest import build_digest
from weft.engine.inspire.schemas import (
    ExtractOutput,
    LogicOutput,
    MatchOutput,
    ReviewOutput,
)
from weft.engine.inspire.spec_build import build_inspire_tasklist
from weft.store.project import Project

_HARNESS_CORES = {
    "inspire_logic": "你是灵感笔记的逻辑核查器，只输出 JSON。",
    "inspire_extract": "你是学术写作引擎的卡片拆解器，只输出 JSON。",
    "inspire_review": "你是元数据卡审查器，必须对照现有卡索引穷举比对，只输出 JSON。",
    "inspire_match": "你是文献与数据匹配器，只准使用索引中出现的 key，只输出 JSON。",
}
_TICK_MODELS = {"t01": LogicOutput, "t02": ExtractOutput,
                "t03": ReviewOutput, "t04": MatchOutput}
_MAX_TICKS = 12   # 4 节点链 + 余量（M2 决策 14d）


class InspireError(Exception):
    """message 首段含 [E-INSPIRE-SHAPE] / [E-INSPIRE-FAILED]（风格同 draft）。"""


@dataclass
class InspireResult:
    run_id: str
    logic: LogicOutput
    extract: ExtractOutput
    review: ReviewOutput
    match: MatchOutput


def _register_harnesses(reg) -> None:
    """注册 T1–T4 四个 harness；api_params 抬高输出上限。

    SpecModule 硬编码默认 max_tokens=4096，config.json 不可达（from_env 只读
    providers/models/rules）；推理型模型思考 token 即可耗尽 4096，content 为空
    （finish=length，e2e 实测）。api_params 优先级最高，唯此一途。
    """
    for name, core in _HARNESS_CORES.items():
        reg.harness(name, HarnessConfig(
            prompt_core=core,
            output_format=OutputFormat(type="json_object"),
            notdo=["不要输出 JSON 以外的任何文本"],
            temperature=0.2,
            api_params={"max_tokens": 32768},
        ))


def run_inspire(project: Project, text: str, *, client) -> InspireResult:
    run_id = uuid.uuid4().hex[:8]
    tasklist = build_inspire_tasklist(text, build_digest(project))
    bus = EventBus()
    reg = HarnessRegistry(llm_client=client, event_bus=bus)
    _register_harnesses(reg)

    module = Module(
        spec={"task_nodes": {tick: tick for tick in _TICK_MODELS}},
        tasklist=tasklist,
        llm_client=client,
        event_bus=bus,
        registry=reg,
        module_id=f"weft-inspire-{run_id}",
        review_harness=None,      # tasklist 代码构造，跳过一致性审核（M2 决策 2）
        keep_records=False,       # 零残留（M2 决策 3）
        persist=False,
        status_file=False,
        stream_log=False,
    )
    try:
        firings = asyncio.run(module.run(max_ticks=_MAX_TICKS))
    except InspireError:
        raise
    except Exception as exc:
        raise InspireError(f"[E-INSPIRE-FAILED] SpecModule run 失败：{exc}") from exc

    outputs: dict[str, dict] = {}
    for firing in firings:
        if firing.status == "failed":
            raise InspireError(
                f"[E-INSPIRE-SHAPE] 节点 {firing.node} 输出不可读："
                f"{firing.error or 'harness 失败'}")
        if firing.status == "aborted":
            raise InspireError(
                f"[E-INSPIRE-FAILED] 节点 {firing.node} 基础设施失败：{firing.error}")
        if isinstance(firing.output, dict):
            outputs[firing.node] = firing.output
    missing = set(_TICK_MODELS) - set(outputs)
    if missing:
        raise InspireError(f"[E-INSPIRE-FAILED] 节点未完成：{sorted(missing)}")

    parsed = {}
    for tick, model in _TICK_MODELS.items():
        try:
            parsed[tick] = model.model_validate(outputs[tick])
        except ValidationError as exc:
            raise InspireError(
                f"[E-INSPIRE-SHAPE] 节点 {tick} 输出不合 schema："
                f"{exc.errors()[0]['msg']}") from exc
    return InspireResult(run_id=run_id, logic=parsed["t01"],
                         extract=parsed["t02"], review=parsed["t03"],
                         match=parsed["t04"])
