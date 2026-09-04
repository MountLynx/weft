"""inspire 管线运行层：T1–T4 一次 SpecModule run（inspire 设计 §4）。

A1 聚合在 run 层之外（apply.py，计划 D1）。与 M2 draft 的零残留 fast mode
不同，inspire 开启 persist（base_dir 指向 generated/inspirations/.runs/，
weft 受管目录）：每 tick 快照落 run.sqlite，失败后重跑同一灵感经
Module.resume() 从断点续跑（已执行节点不重算），节点输出经
load_snapshot_summary 取回。灵感换名即换 module_id，互不干扰。

失败语义同 M2 决策 14c：harness 失败不流向后继，事后扫描 fail-closed
（failed → E-INSPIRE-SHAPE，aborted / 缺输出 → E-INSPIRE-FAILED）。
"""
import asyncio
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from module_harness import (
    EventBus,
    HarnessConfig,
    HarnessRegistry,
    Module,
    OutputFormat,
)
from module_harness.query import load_snapshot_summary, run_db_path
from module_harness.status import query_run_status
from pydantic import ValidationError

from weft.digest import build_digest
from weft.engine.inspire.schemas import (
    CoverageOutput,
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
    "inspire_cover": "你是成卡覆盖审查器，逐要点对账原文与草案卡，宁可多报不可漏报，只输出 JSON。",
}
_TICK_MODELS = {"t01": LogicOutput, "t02": ExtractOutput,
                "t03": ReviewOutput, "t04": MatchOutput, "t05": CoverageOutput}
_MAX_TICKS = 14   # 5 节点链 + 余量（M2 决策 14d）


class InspireError(Exception):
    """message 首段含 [E-INSPIRE-SHAPE] / [E-INSPIRE-FAILED]（风格同 draft）。"""


@dataclass
class InspireResult:
    run_id: str
    logic: LogicOutput
    extract: ExtractOutput
    review: ReviewOutput
    match: MatchOutput
    coverage: CoverageOutput
    module_id: str = ""
    resumed: bool = False


def _runs_base(project: Project) -> Path:
    return project.root / "generated" / "inspirations" / ".runs"


def _module_id(source: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(source).stem).strip("-")
    return f"weft-inspire-{slug or 'inspire'}"[:120]


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


def _build_module(project: Project, text: str, client, module_id: str) -> Module:
    tasklist = build_inspire_tasklist(text, build_digest(project))
    bus = EventBus()
    reg = HarnessRegistry(llm_client=client, event_bus=bus)
    _register_harnesses(reg)
    return Module(
        spec={"task_nodes": {tick: tick for tick in _TICK_MODELS}},
        tasklist=tasklist,
        llm_client=client,
        event_bus=bus,
        registry=reg,
        module_id=module_id,
        base_dir=_runs_base(project),
        review_harness=None,      # tasklist 代码构造，跳过一致性审核（M2 决策 2）
        keep_records=True,        # firings 落库：断点取回节点输出 + 审计
        persist=True,             # 每 tick 快照（续跑依赖）
        status_file=True,         # 阶段状态（跨进程查询）
        control=False,
        stream_log=False,
    )


def run_inspire(project: Project, text: str, *, client,
                source: str = "inspire") -> InspireResult:
    module_id = _module_id(source)
    base_dir = _runs_base(project)
    prior = load_snapshot_summary(module_id, base_dir=base_dir)

    resumed = False
    resume_tick = 0
    if prior is not None:
        outs = prior.get("outputs") or {}
        # 失败节点的快照 output 是 Failure 描述字符串（非 dict）——不算完成
        complete = all(isinstance(outs.get(t), dict) for t in _TICK_MODELS)
        status = query_run_status(module_id, base_dir=base_dir)
        if complete:
            # 上一次已全程完成：同灵感重跑 = 全新运行，清场防陈旧输出混入
            # 实际落盘布局：base_dir/.specmodule/runs/<module_id>/
            shutil.rmtree(run_db_path(module_id, base_dir=base_dir).parent,
                          ignore_errors=True)
            prior = None
        elif status is not None and status.phase == "running":
            raise InspireError(
                f"[E-INSPIRE-FAILED] run {module_id} 正在运行（phase=running），"
                "不接受并发重跑")
        else:
            # 断点续跑：失败节点在 tickflow 里已被消费（出边写 False），
            # resume 不会重试——须回退到最后一个成功节点的 tick 快照。
            # 线性链 t01..t04：tick i = 节点 t0{i+1}。
            leading = 0
            for tick in _TICK_MODELS:
                if isinstance(outs.get(tick), dict):
                    leading += 1
                else:
                    break
            if leading == 0:
                # 首节点即失败，无可回退快照 → 清场全新跑
                shutil.rmtree(run_db_path(module_id, base_dir=base_dir).parent,
                              ignore_errors=True)
            else:
                resumed = True
                resume_tick = leading - 1

    module = _build_module(project, text, client, module_id)
    try:
        if resumed:
            firings = asyncio.run(module.resume(rollback_to=resume_tick,
                                                max_ticks=_MAX_TICKS))
        else:
            firings = asyncio.run(module.run(max_ticks=_MAX_TICKS))
    except InspireError:
        raise
    except Exception as exc:
        raise InspireError(f"[E-INSPIRE-FAILED] SpecModule run 失败：{exc}") from exc

    # 节点输出：以持久化 firings 的最新值为底（续跑时覆盖已完成节点），
    # 本次 firings 里的输出优先（更新）。
    summary = load_snapshot_summary(module_id, base_dir=base_dir)
    outputs: dict[str, dict] = dict((summary or {}).get("outputs") or {})
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
    missing = {t for t in _TICK_MODELS
               if not isinstance(outputs.get(t), dict)}
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
    return InspireResult(run_id=module_id, logic=parsed["t01"],
                         extract=parsed["t02"], review=parsed["t03"],
                         match=parsed["t04"], coverage=parsed["t05"],
                         module_id=module_id, resumed=resumed)
